"""ntfy push channel (M67-I202, docs/01 §BL.2): the third physical delivery
surface next to in-app and email. A mirror of the mailer — post-emit hook
resolves recipients, gates run per user, a queue + background worker thread
keeps network I/O off the write path. ntfy semantics: the push is one POST to
the user's topic URL with Title/Priority/Tags/Click headers; delivery facts
land as push.notified/push.failed events exactly like email.notified (the
audit trail stays uniform across physical channels)."""
from __future__ import annotations

import logging
import queue
import threading

import urllib.request

from apm import config
from apm.core import db, events
from apm.domains.mailer import _now_hhmm
from apm.domains.notifications import (
    NOTIFY_EVENTS, plan_notifications, pref_allows, quiet_active,
)

logger = logging.getLogger(__name__)

_queue: "queue.Queue[dict]" = queue.Queue(maxsize=500)
_worker: threading.Thread | None = None

# Urgent kinds map to ntfy's top priority (phone alarm semantics); everything
# else delivers at the default level.
_HIGH_PRIORITY_KINDS = {"mention", "approval", "approval_reminder"}


def enqueue(event: events.Event) -> None:
    """Post-emit hook: resolve recipients and enqueue pushes — never blocks."""
    if event.event_type not in NOTIFY_EVENTS:
        return
    try:
        pairs = plan_notifications(db.get_conn(), event)
    except Exception:
        logger.exception("push recipient resolution failed for #%s", event.id)
        return
    conn = db.get_conn()
    # M62-I187: rule-level channel routing rides on notification.sent payloads —
    # a watch rule re-routes toward push like toward email; user-level gates
    # (pref matrix, quiet hours) still apply underneath.
    override = event.payload.get("channels") \
        if isinstance(event.payload.get("channels"), list) else None
    for user_id, kind, summary in pairs:
        if override is not None:
            if "push" not in override:
                continue  # this rule routes away from push
        elif not pref_allows(conn, user_id, kind, "push"):
            continue  # I96 gate: per-kind push column
        row = conn.execute(
            "SELECT push_url, push_token, quiet_start, quiet_end FROM users WHERE id = ?",
            (user_id,)).fetchone()
        if not row or not row["push_url"]:
            continue  # no topic → silently skip (push is opt-in by profile)
        is_digest = (event.event_type == "notification.sent"
                     and bool(event.payload.get("digest")))
        if kind != "mention" and not is_digest and quiet_active(
                row["quiet_start"], row["quiet_end"], _now_hhmm()):
            continue  # M56-I169 semantics: DND applies to every outbound channel
        try:
            _queue.put_nowait({
                "user_id": user_id, "kind": kind, "summary": summary,
                "event_id": event.id, "project_id": event.project_id,
                "push_url": row["push_url"], "push_token": row["push_token"] or "",
            })
        except queue.Full:
            logger.warning("push queue full; dropping push to %s", user_id)


def _send(item: dict) -> tuple[bool, str, int | None]:
    import time

    priority = "5" if item["kind"] in _HIGH_PRIORITY_KINDS else "3"
    req = urllib.request.Request(
        item["push_url"], data=item["summary"].encode("utf-8"), method="POST",
        headers={
            "Title": f"[AgentPM] {item['kind']}",
            "Priority": priority,
            "Tags": item["kind"],
            **({"Click": config.settings.web_base_url}
               if config.settings.web_base_url else {}),
            **({"Authorization": f"Bearer {item['push_token']}"}
               if item["push_token"] else {}),
        })
    start = time.monotonic()
    try:
        # default SSL context: push tokens must not be MITM-intercepted
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status < 300, f"http {resp.status}", round((time.monotonic() - start) * 1000)
    except OSError as e:
        return False, str(e) or e.__class__.__name__, None


def _worker_loop() -> None:
    while True:
        item = _queue.get()
        try:
            ok, detail, took_ms = _send(item)
            events.emit(
                event_type="push.notified" if ok else "push.failed",
                agg_type="push", agg_id=f"pu_{item['event_id']}_{item['user_id']}",
                project_id=item["project_id"], actor_type="system",
                payload={"user_id": item["user_id"], "kind": item["kind"],
                         "summary": item["summary"], "source_event_id": item["event_id"],
                         "detail": detail, "duration_ms": took_ms},
            )
        except Exception:  # the worker must survive anything
            logger.exception("push worker crashed on %s", item)
        finally:
            _queue.task_done()


def install_pusher() -> None:
    """Idempotent: wire the enqueue hook + start the background worker."""
    global _worker
    events.add_post_emit_hook(enqueue)
    if _worker is None or not _worker.is_alive():
        _worker = threading.Thread(target=_worker_loop, name="apm-pusher", daemon=True)
        _worker.start()
