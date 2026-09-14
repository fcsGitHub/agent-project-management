"""IMAP inbox-to-task (M35-I107, docs/01 §AH.1): Redmine's receive_imap and
Jira's mail handlers poll a mailbox, match the sender to an account, and route
the message into a container. The mailbox pass is an env-gated optional
channel with the same shape as SMTP — unset IMAP_HOST means off. A sender
whose email matches users.email lands a first-class item through create_item's
full validation chain under their own identity (default project = their first
membership); unmatched senders fall back to the intake identity in
IMAP_FALLBACK_PROJECT_ID when set, else are ignored (Redmine
--unknown-user=ignore). Message-IDs project into imap_seen (drop_projections),
so re-polls and rebuilds never duplicate an item."""
from __future__ import annotations

import email
import re
from email import policy

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on
from apm.domains.items import create_item
from apm.domains.members import is_instance_admin

router = APIRouter(tags=["imap"])


# ---------------------------------------------------------------- projectors
@on("imap.message_processed")
def _proj_message_processed(conn, e):
    p = e.payload
    conn.execute(
        "INSERT INTO imap_seen (message_id, from_email, routed, item_id,"
        " project_id, processed_at) VALUES (?,?,?,?,?,?)"
        " ON CONFLICT(message_id) DO NOTHING",
        (p["message_id"], p.get("from_email"), p["routed"],
         p.get("item_id"), p.get("project_id"), e.ts),
    )


# ---------------------------------------------------------------- fetching
def _configured() -> bool:
    from apm import config

    return bool(config.settings.imap_host and config.settings.imap_user
                and config.settings.imap_pass)


def _fetch_messages() -> list[dict]:
    """Unseen messages as plain dicts — the only imaplib-touching function,
    so tests stub this (same seam as mailer's FakeSMTP)."""
    import imaplib

    from apm import config

    s = config.settings
    client = imaplib.IMAP4_SSL(s.imap_host, s.imap_port)
    try:
        client.login(s.imap_user, s.imap_pass)
        client.select("INBOX")
        _, data = client.search(None, "UNSEEN")
        out = []
        for num in data[0].split():
            _, msg_data = client.fetch(num, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw, policy=policy.default)
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_content()
                        break
            else:
                body = str(msg.get_content())
            out.append({
                "message_id": (msg.get("Message-ID") or "").strip(),
                "from": email.utils.parseaddr(msg.get("From", ""))[1],
                "subject": str(msg.get("Subject") or "").strip(),
                "body": body.strip()[:2000],
                "in_reply_to": str(msg.get("In-Reply-To") or "").strip(),
                "references": str(msg.get("References") or "").strip(),
                # I120: Exim/qmail-style bounce header quoting the failed recipient
                "x_failed_recipients": " ".join(msg.get_all("X-Failed-Recipients") or []),
            })
            client.store(num, "+FLAGS", "\\Seen")
        return out
    finally:
        client.logout()


# ---------------------------------------------------------------- processing
def _default_project(conn, user_id: str) -> str | None:
    if is_instance_admin(user_id):
        row = conn.execute(
            "SELECT id FROM projects ORDER BY created_at LIMIT 1").fetchone()
        return row["id"] if row else None
    row = conn.execute(
        "SELECT project_id FROM project_members WHERE user_id = ?"
        " ORDER BY project_id LIMIT 1", (user_id,)).fetchone()
    return row["project_id"] if row else None


def _route_message(conn, msg: dict) -> dict:
    import re

    from apm import config

    # parseaddr here (not only in _fetch_messages) so every entry path —
    # real IMAP, stubs, future webhooks — gets the same normalized address
    from_email = email.utils.parseaddr(msg.get("from") or "")[1].lower()
    row = conn.execute(
        "SELECT id, name FROM users WHERE LOWER(COALESCE(email, '')) = ?",
        (from_email,)).fetchone()
    title = msg.get("subject") or "(无主题来信)"

    # I113 (docs/01 §AJ.1, Jira Split-Regex lite): a `[项目名]` subject prefix
    # routes to that project when the sender is its member; non-members or
    # unknown names fall through to the default routing, keeping the prefix.
    prefix_project = None
    m = re.match(r"\[([^\[\]]{1,60})\]\s*", title)
    if m and row:
        named = conn.execute(
            "SELECT p.id FROM projects p JOIN project_members pm ON pm.project_id = p.id"
            " WHERE p.name = ? AND pm.user_id = ?",
            (m.group(1), row["id"])).fetchone()
        if named:
            prefix_project = named["id"]
            stripped = title[m.end():].strip()
            if stripped:
                title = stripped

    if row:  # known sender → their own identity
        user_id, author_name = row["id"], row["name"]
        project_id = prefix_project or _default_project(conn, user_id)
        if not project_id:
            return {"routed": "skipped", "reason": "no visible project", "user_id": user_id}
        item = create_item(
            project_id=project_id, concept_id="task", title=title[:200],
            actor_type="human", actor_id=user_id,
        )
        _attach_body(item["id"], project_id, user_id, author_name, msg.get("body"))
        return {"routed": "user", "user_id": user_id,
                "project_id": project_id, "item_id": item["id"]}

    fallback = config.settings.imap_fallback_project_id
    if fallback:  # unknown sender but a drop-box project is configured
        item = create_item(
            project_id=fallback, concept_id="task", title=title[:200],
            actor_type="intake", actor_id="intake",
        )
        _attach_body(item["id"], fallback, "intake", "intake", msg.get("body"))
        return {"routed": "intake", "project_id": fallback, "item_id": item["id"]}
    return {"routed": "skipped", "reason": "unknown sender"}  # Redmine ignore


def _attach_body(item_id: str, project_id: str, author_id: str,
                 author_name: str, body: str | None) -> None:
    """The email body becomes the item's first comment — items carry no
    description column, and a plain comment.created event reuses the M18
    pipeline (no mention parsing: mail bodies never @-notify anyone)."""
    if not body:
        return
    events.emit(
        event_type="comment.created", agg_type="comment", agg_id=new_id("cm"),
        project_id=project_id, actor_type="automation", actor_id="imap",
        payload={"item_id": item_id, "author_id": author_id, "body": body,
                 "mentions_json": "[]", "author_name": author_name},
    )


def _find_thread_item(conn, msg: dict) -> dict | None:
    """I114 (docs/01 §AJ.2, Jira replies-become-comments): if the mail's
    In-Reply-To/References chain points at a Message-ID this system already
    processed into an item, the reply belongs to that item's conversation —
    it must become a comment, not a new task."""
    refs = re.findall(r"<[^>]+>",
                      f"{msg.get('in_reply_to', '')} {msg.get('references', '')}")
    if not refs:
        return None
    marks = ",".join("?" for _ in refs)
    return conn.execute(
        f"SELECT item_id, project_id FROM imap_seen WHERE message_id IN ({marks})"
        " AND item_id IS NOT NULL LIMIT 1", tuple(refs)).fetchone()


def poll_inbox() -> dict:
    """One mailbox pass; every outcome is an imap.message_processed event
    (routed=user/intake or skipped), and the imap_seen projection makes the
    whole pass idempotent per Message-ID."""
    if not _configured():
        return {"enabled": False, "processed": 0}
    conn = db.get_conn()
    processed = 0
    for msg in _fetch_messages():
        message_id = msg.get("message_id")
        if not message_id or conn.execute(
            "SELECT 1 FROM imap_seen WHERE message_id = ?", (message_id,)
        ).fetchone():
            continue

        normalized = email.utils.parseaddr(msg.get("from") or "")[1].lower()

        # I120: bounces flip the failed recipient's email channel off; filter
        # hits are silently ignored; both keep the message_processed audit.
        if _is_bounce(msg):
            result = _process_bounce(conn, msg)
        else:
            why = _ignored(conn, msg)
            result = {"routed": "ignored", "reason": why} if why else None
        if result is not None:
            events.emit(
                event_type="imap.message_processed", agg_type="imap_message",
                agg_id=message_id, project_id=result.get("project_id", ""),
                actor_type="automation", actor_id="imap",
                payload={"message_id": message_id, "from_email": normalized,
                         "subject": msg.get("subject"), **result},
            )
            processed += 1
            continue

        # I114: a reply in a known thread becomes a comment on that item —
        # never a new task (Jira replies-become-comments semantics)
        thread = _find_thread_item(conn, msg)
        if thread is not None:
            from_email = normalized
            sender = conn.execute(
                "SELECT id, name FROM users WHERE LOWER(COALESCE(email, '')) = ?",
                (from_email,)).fetchone()
            if sender:
                author_id, author_name = sender["id"], sender["name"]
                routed = "reply"
            else:
                author_id, author_name = "intake", "intake"
                routed = "reply_intake"
            _attach_body(thread["item_id"], thread["project_id"],
                         author_id, author_name, msg.get("body"))
            result = {"routed": routed, "item_id": thread["item_id"],
                      "project_id": thread["project_id"]}
            events.emit(
                event_type="imap.message_processed", agg_type="imap_message",
                agg_id=message_id, project_id=thread["project_id"],
                actor_type="automation", actor_id="imap",
                payload={"message_id": message_id,
                         "from_email": from_email,
                         "subject": msg.get("subject"), **result},
            )
            processed += 1
            continue

        result = _route_message(conn, msg)
        events.emit(
            event_type="imap.message_processed", agg_type="imap_message",
            agg_id=message_id, project_id=result.get("project_id", ""),
            actor_type="automation", actor_id="imap",
            payload={"message_id": message_id, "from_email": normalized,
                     "subject": msg.get("subject"), **result},
        )
        processed += 1
    return {"enabled": True, "processed": processed}


# ---------------------------------------------------------------- bounce & filters
_ADDR = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")


def _is_bounce(msg: dict) -> bool:
    """I120 (docs/01 §AL.2, the standard bounce-sender convention): delivery
    failure notices come from MAILER-DAEMON or POSTMASTER. Only the sender's
    local part must match — the domain varies (mailer-daemon@yahoo.com …)."""
    addr = email.utils.parseaddr(msg.get("from") or "")[1].lower()
    return addr.split("@", 1)[0] in ("mailer-daemon", "postmaster")


def _bounce_recipient(msg: dict) -> str | None:
    """The addressee the original mail failed for: the X-Failed-Recipients
    header when present, else the first plausible address quoted in the body
    (never the mailbox itself)."""
    from apm import config

    own = (config.settings.imap_user or "").lower()
    m = _ADDR.search(msg.get("x_failed_recipients") or "")
    if m and m.group(0).lower() != own:
        return m.group(0).lower()
    for m in _ADDR.finditer(msg.get("body") or ""):
        if m.group(0).lower() != own:
            return m.group(0).lower()
    return None


def _ignored(conn, msg: dict) -> str | None:
    """I120 inbound filters — comma-separated addresses (exact or @domain),
    and subject keywords. A hit means silently ignore, Redmine
    --unknown-user=ignore style; the message_processed event records why."""
    from apm import config

    from_email = email.utils.parseaddr(msg.get("from") or "")[1].lower()
    for entry in (config.settings.imap_ignore_addresses or "").split(","):
        entry = entry.strip().lower()
        if not entry:
            continue
        if from_email == entry or (entry.startswith("@") and from_email.endswith(entry)):
            return f"ignored address {entry}"
    subject = (msg.get("subject") or "").lower()
    for kw in (config.settings.imap_ignore_keywords or "").split(","):
        kw = kw.strip().lower()
        if kw and kw in subject:
            return f"ignored keyword '{kw}'"
    return None


def _process_bounce(conn, msg: dict) -> dict:
    """A delivery failure for one of our users flips their email channel off —
    the suppression-list semantics of keeping a dead address on a list being
    spamming them forever. In-app notifications are untouched; the user turns
    the channel back on via the regular email toggle (runtime preference, same
    family as POST /notifications/prefs). routed=suppress means we acted,
    routed=bounce means nothing to do (unknown or already-off recipient)."""
    rcpt = _bounce_recipient(msg)
    row = conn.execute(
        "SELECT id, email_notify FROM users WHERE LOWER(COALESCE(email, '')) = ?",
        (rcpt or "",)).fetchone()
    if row is not None and row["email_notify"]:
        conn.execute(
            "UPDATE users SET email_notify = 0, updated_at = ? WHERE id = ?",
            (events.utcnow(), row["id"]))
        conn.commit()
        return {"routed": "suppress", "recipient": rcpt, "user_id": row["id"]}
    return {"routed": "bounce", "recipient": rcpt}


# ---------------------------------------------------------------- admin API
class PollOut(BaseModel):
    enabled: bool
    processed: int


@router.post("/imap/poll")
def poll_now() -> PollOut:
    from apm import config

    if not is_instance_admin(events.effective_actor()):
        raise HTTPException(status_code=403, detail="admin role required for mailbox polling")
    if not _configured():
        raise HTTPException(status_code=409, detail="IMAP is not configured (IMAP_HOST/USER/PASS)")
    return PollOut(**poll_inbox())
