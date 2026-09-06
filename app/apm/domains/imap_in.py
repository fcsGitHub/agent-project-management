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
    from apm import config

    # parseaddr here (not only in _fetch_messages) so every entry path —
    # real IMAP, stubs, future webhooks — gets the same normalized address
    from_email = email.utils.parseaddr(msg.get("from") or "")[1].lower()
    row = conn.execute(
        "SELECT id, name FROM users WHERE LOWER(COALESCE(email, '')) = ?",
        (from_email,)).fetchone()
    title = msg.get("subject") or "(无主题来信)"
    if row:  # known sender → their own identity, their first project
        user_id, author_name = row["id"], row["name"]
        project_id = _default_project(conn, user_id)
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
        result = _route_message(conn, msg)
        normalized = email.utils.parseaddr(msg.get("from") or "")[1].lower()
        events.emit(
            event_type="imap.message_processed", agg_type="imap_message",
            agg_id=message_id, project_id=result.get("project_id", ""),
            actor_type="automation", actor_id="imap",
            payload={"message_id": message_id, "from_email": normalized,
                     "subject": msg.get("subject"), **result},
        )
        processed += 1
    return {"enabled": True, "processed": processed}


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
