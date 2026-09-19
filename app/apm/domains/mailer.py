"""Email notification channel (M11-I35): instant, per-notification emails over
an optional SMTP configuration (docs/01 §J.1 — Redmine ships instant-only and
configures SMTP at the environment layer). When APM_SMTP_HOST/APM_SMTP_FROM are
unset the whole channel is off and behavior matches pre-M11 exactly.

Architecture mirrors the M10 webhook delivery: the post-emit hook only enqueues
(never blocks the write path); a background worker thread sends via smtplib and
records the outcome on the event stream (`email.notified` / `email.failed`).
Recipients are resolved with the same `plan_notifications` the notification
projection uses — the two channels can never disagree on recipients."""
from __future__ import annotations

import logging
import queue
import smtplib
import ssl
import threading
import time
from email.message import EmailMessage

from apm import config
from apm.core import db, events
from apm.domains.notifications import NOTIFY_EVENTS, plan_notifications, pref_allows

logger = logging.getLogger(__name__)

_queue: "queue.Queue[dict]" = queue.Queue(maxsize=500)
_worker: threading.Thread | None = None


def smtp_configured() -> bool:
    s = config.settings
    return bool(s.smtp_host and s.smtp_from)


def enqueue(event: events.Event) -> None:
    """Post-emit hook: resolve recipients and enqueue emails — never blocks."""
    if not smtp_configured():
        return
    if event.event_type not in NOTIFY_EVENTS:
        return
    try:
        pairs = plan_notifications(db.get_conn(), event)
    except Exception:
        logger.exception("mail recipient resolution failed for #%s", event.id)
        return
    conn = db.get_conn()
    for user_id, kind, summary in pairs:
        if not pref_allows(conn, user_id, kind, "email"):
            continue  # I96: per-kind email gate (same gate the in-app channel uses)
        row = conn.execute(
            "SELECT email, email_notify FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row or not row["email"]:
            continue  # no address → silently skip (email is opt-in by profile)
        if not row["email_notify"]:
            continue  # user-level email preference off (M11-I37)
        try:
            _queue.put_nowait({
                "to": row["email"], "user_id": user_id, "kind": kind,
                "summary": summary, "event_id": event.id,
                "project_id": event.project_id,
            })
        except queue.Full:
            logger.warning("mail queue full; dropping mail to %s", row["email"])


def _send(item: dict) -> tuple[bool, str, int | None]:
    s = config.settings
    msg = EmailMessage()
    msg["From"] = s.smtp_from
    msg["To"] = item["to"]
    msg["Subject"] = f"[AgentPM] {item['summary']}"
    msg.set_content(f"{item['summary']}\n\nkind: {item['kind']}\n")
    start = time.monotonic()
    try:
        # 校验证书/主机名的默认 SSL 上下文：SMTP 凭据不得被中间人截获。
        ssl_ctx = ssl.create_default_context()
        if s.smtp_port == 465:
            server = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=10, context=ssl_ctx)
        else:
            server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10)
            if s.smtp_tls:
                server.starttls(context=ssl_ctx)
        try:
            if s.smtp_user:
                server.login(s.smtp_user, s.smtp_pass)
            server.send_message(msg)
        finally:
            server.quit()
        return True, "sent", round((time.monotonic() - start) * 1000)
    except (OSError, smtplib.SMTPException) as e:
        return False, str(e) or e.__class__.__name__, None


def _worker_loop() -> None:
    while True:
        item = _queue.get()
        try:
            ok, detail, took_ms = _send(item)
            events.emit(
                event_type="email.notified" if ok else "email.failed",
                agg_type="email", agg_id=f"em_{item['event_id']}_{item['user_id']}",
                project_id=item["project_id"], actor_type="system",
                payload={"to": item["to"], "kind": item["kind"], "summary": item["summary"],
                         "source_event_id": item["event_id"], "detail": detail,
                         "duration_ms": took_ms},
            )
        except Exception:  # the worker must survive anything
            logger.exception("mail worker crashed on %s", item)
        finally:
            _queue.task_done()


def install_mailer() -> None:
    """Idempotent: wire the enqueue hook + start the background worker."""
    global _worker
    events.add_post_emit_hook(enqueue)
    if _worker is None or not _worker.is_alive():
        _worker = threading.Thread(target=_worker_loop, name="apm-mailer", daemon=True)
        _worker.start()
