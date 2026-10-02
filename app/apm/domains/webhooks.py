"""Outbound webhooks (M10-I32): per-project event push with Gitea/GitLab-style
semantics (docs/01 §I.1) — HMAC-SHA256 over the raw body (`X-APM-Signature`),
`X-APM-Event`/`X-APM-Delivery` headers for filtering and idempotency, and every
delivery outcome (delivered/failed) recorded on the event stream.

Architectural constraint (docs/10 §M10): the post-emit hook only ENQUEUES —
delivery runs on a background worker thread so network I/O never blocks the
write path (the essential difference from M9's synchronous rule executor).

Secrets never enter events (M8-I26 principle): the secret lives only in the
projection table (rebuild wipes it, like user passwords) and is returned once
at creation / rotation.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import queue
import secrets as pysecrets
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on
from apm.domains.projects import require_project

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])

EVENT_WHITELIST = (
    "item.created", "item.updated", "item.status_changed", "item.assigned",
    "approval.requested", "approval.granted", "approval.rejected",
    "feature.created", "automation.rule_fired",
)
HTTP_TIMEOUT = 5.0
RETRY_DELAYS = (1.0, 4.0, 16.0)  # seconds between retries (tests monkeypatch this)

_queue: "queue.Queue[dict]" = queue.Queue(maxsize=1000)
_worker: threading.Thread | None = None


# ---------------------------------------------------------------- projectors
@on("webhook.created")
def _proj_webhook_created(conn, e):
    p = e.payload
    conn.execute(
        "INSERT INTO webhooks (id, project_id, url, secret, events_json, enabled,"
        " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (e.agg_id, e.project_id, p["url"], "", json.dumps(p["events"], ensure_ascii=False),
         1 if p.get("enabled", True) else 0, e.ts, e.ts),
    )


@on("webhook.updated")
def _proj_webhook_updated(conn, e):
    p = e.payload
    sets, params = [], []
    if "url" in p:
        sets.append("url = ?")
        params.append(p["url"])
    if "events" in p:
        sets.append("events_json = ?")
        params.append(json.dumps(p["events"], ensure_ascii=False))
    if "enabled" in p:
        sets.append("enabled = ?")
        params.append(1 if p["enabled"] else 0)
    if sets:
        sets.append("updated_at = ?")
        params.extend([e.ts, e.agg_id])
        conn.execute(f"UPDATE webhooks SET {', '.join(sets)} WHERE id = ?", params)


@on("webhook.deleted")
def _proj_webhook_deleted(conn, e):
    conn.execute("DELETE FROM webhooks WHERE id = ?", (e.agg_id,))


# ---------------------------------------------------------------- helpers
def _row(webhook_id: str):
    return db.get_conn().execute(
        "SELECT * FROM webhooks WHERE id = ?", (webhook_id,)).fetchone()


def _parse(row, *, with_secret: bool = False) -> dict:
    w = dict(row)
    w["events"] = json.loads(w.pop("events_json") or "[]")
    secret = w.pop("secret") or ""
    w["has_secret"] = bool(secret)
    if with_secret:
        w["secret"] = secret
    w["enabled"] = bool(w["enabled"])
    return w


def list_webhooks(project_id: str) -> list[dict]:
    rows = db.get_conn().execute(
        "SELECT * FROM webhooks WHERE project_id = ? ORDER BY created_at, id",
        (project_id,),
    ).fetchall()
    return [_parse(r) for r in rows]


def _validate_url(url: str) -> None:
    parsed = urlparse(url or "")
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=422, detail="url must be an http(s) URL")
    # SSRF 防护：服务器会主动 POST 事件 payload 到该地址，默认拒绝环回/
    # 私网/链路本地/保留段目标（云元数据 169.254.169.254 亦被覆盖）。
    from apm import config

    if config.settings.webhook_allow_private:
        return
    import ipaddress
    import socket

    host = parsed.hostname or ""
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise HTTPException(status_code=422, detail=f"cannot resolve webhook host '{host}'")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            raise HTTPException(
                status_code=422,
                detail="webhook host must be a public address (private/loopback/link-local blocked)")


def _validate_events(events_sub: list[str]) -> None:
    if not isinstance(events_sub, list) or not events_sub:
        raise HTTPException(status_code=422, detail="events must be a non-empty list")
    bad = [e for e in events_sub if e not in EVENT_WHITELIST]
    if bad:
        raise HTTPException(
            status_code=422, detail=f"events not subscribable: {bad} (whitelist: {EVENT_WHITELIST})")


def _set_secret(webhook_id: str, secret: str) -> None:
    """Runtime-state write, exactly like users.password_hash (M8-I26): direct
    UPDATE, never an event."""
    conn = db.get_conn()
    conn.execute("UPDATE webhooks SET secret = ? WHERE id = ?", (secret, webhook_id))
    conn.commit()


# ---------------------------------------------------------------- CRUD API
class WebhookIn(BaseModel):
    url: str
    events: list[str]
    enabled: bool = True


class WebhookPatch(BaseModel):
    url: str | None = None
    events: list[str] | None = None
    enabled: bool | None = None


@router.get("/projects/{project_id}/webhooks")
def get_webhooks(project_id: str) -> dict:
    require_project(project_id)
    return {"webhooks": list_webhooks(project_id)}


@router.post("/projects/{project_id}/webhooks")
def create_webhook(project_id: str, body: WebhookIn) -> dict:
    require_project(project_id)
    _validate_url(body.url)
    _validate_events(body.events)
    wid = new_id("wh")
    events.emit(
        event_type="webhook.created", agg_type="webhook", agg_id=wid,
        project_id=project_id,
        payload={"url": body.url, "events": body.events, "enabled": body.enabled},
    )
    secret = pysecrets.token_hex(32)  # returned exactly once; never evented
    _set_secret(wid, secret)
    out = _parse(_row(wid), with_secret=True)
    return out


@router.patch("/projects/{project_id}/webhooks/{webhook_id}")
def patch_webhook(project_id: str, webhook_id: str, body: WebhookPatch) -> dict:
    require_project(project_id)
    row = _row(webhook_id)
    if not row or row["project_id"] != project_id:
        raise HTTPException(status_code=404, detail=f"webhook {webhook_id} not found")
    payload: dict = {}
    if body.url is not None:
        _validate_url(body.url)
        payload["url"] = body.url
    if body.events is not None:
        _validate_events(body.events)
        payload["events"] = body.events
    if body.enabled is not None:
        payload["enabled"] = body.enabled
    if payload:
        events.emit(
            event_type="webhook.updated", agg_type="webhook", agg_id=webhook_id,
            project_id=project_id, payload=payload,
        )
    return _parse(_row(webhook_id))


@router.delete("/projects/{project_id}/webhooks/{webhook_id}")
def delete_webhook(project_id: str, webhook_id: str) -> dict:
    require_project(project_id)
    row = _row(webhook_id)
    if not row or row["project_id"] != project_id:
        raise HTTPException(status_code=404, detail=f"webhook {webhook_id} not found")
    events.emit(
        event_type="webhook.deleted", agg_type="webhook", agg_id=webhook_id,
        project_id=project_id, payload={"url": row["url"]},
    )
    return {"webhook_id": webhook_id, "deleted": True}


@router.post("/projects/{project_id}/webhooks/{webhook_id}/rotate")
def rotate_secret(project_id: str, webhook_id: str) -> dict:
    require_project(project_id)
    row = _row(webhook_id)
    if not row or row["project_id"] != project_id:
        raise HTTPException(status_code=404, detail=f"webhook {webhook_id} not found")
    secret = pysecrets.token_hex(32)
    _set_secret(webhook_id, secret)
    return {"webhook_id": webhook_id, "secret": secret}


@router.post("/projects/{project_id}/webhooks/{webhook_id}/replay/{delivery_id}")
def replay_delivery(project_id: str, webhook_id: str, delivery_id: str) -> dict:
    """Manual redelivery (M10-I33): resend the payload of a recorded delivery
    under a NEW delivery id, single attempt (an explicit human action)."""
    require_project(project_id)
    row = _row(webhook_id)
    if not row or row["project_id"] != project_id:
        raise HTTPException(status_code=404, detail=f"webhook {webhook_id} not found")
    evs, _ = events.query_events(
        project_id=project_id, agg_type="webhook", agg_id=webhook_id, limit=200)
    original = next((e for e in evs
                     if e.payload.get("delivery_id") == delivery_id
                     and e.event_type in ("webhook.delivered", "webhook.delivery_failed")), None)
    if original is None:
        raise HTTPException(status_code=404, detail=f"delivery {delivery_id} not found")
    source = events.get_event(original.payload.get("event_id") or 0)
    if source is None:
        raise HTTPException(status_code=410, detail="原始事件已不可用（事件流不含该 event_id）")
    return _deliver(_parse(row, with_secret=True), source.as_dict(), retries=False)


@router.post("/projects/{project_id}/webhooks/{webhook_id}/ping")
def ping_webhook(project_id: str, webhook_id: str) -> dict:
    """Test ping (M10-I33): deliver a synthetic ping payload, single attempt."""
    require_project(project_id)
    row = _row(webhook_id)
    if not row or row["project_id"] != project_id:
        raise HTTPException(status_code=404, detail=f"webhook {webhook_id} not found")
    ping = {"id": 0, "event_type": "ping", "project_id": project_id,
            "payload": {"summary": "AgentPM webhook 测试 ping"}}
    return _deliver(_parse(row, with_secret=True), ping, retries=False)


# ---------------------------------------------------------------- delivery
def _sign(secret: str, raw_body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def _deliver_once(url: str, headers: dict[str, str], raw_body: bytes) -> tuple[int, float]:
    start = time.monotonic()
    req = urllib.request.Request(url, data=raw_body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return resp.status, time.monotonic() - start
    except urllib.error.HTTPError as e:  # HTTP error statuses still have a code
        return e.code, time.monotonic() - start


def _deliver(webhook: dict, event_dict: dict, *, retries: bool = True) -> dict:
    """Deliver one event to one webhook with retries; record the outcome as an
    event (delivered/failed) so history survives rebuild. `retries=False` gives
    a single attempt (manual replay / ping)."""
    raw_body = json.dumps(event_dict, ensure_ascii=False).encode("utf-8")
    delivery_id = f"dl_{pysecrets.token_hex(8)}"
    headers = {
        "Content-Type": "application/json",
        "X-APM-Event": event_dict["event_type"],
        "X-APM-Delivery": delivery_id,
        "X-APM-Webhook": webhook["id"],
    }
    if webhook.get("secret"):
        headers["X-APM-Signature"] = _sign(webhook["secret"], raw_body)

    delays = RETRY_DELAYS if retries else ()
    attempts, last_code, last_err = 0, None, None
    for attempt in range(1 + len(delays)):
        if attempt:
            time.sleep(delays[attempt - 1])
        attempts = attempt + 1
        try:
            last_code, took = _deliver_once(webhook["url"], headers, raw_body)
            if 200 <= last_code < 300:
                result = {"delivery_id": delivery_id, "event_type": event_dict["event_type"],
                          "event_id": event_dict["id"], "attempts": attempts,
                          "status_code": last_code, "duration_ms": round(took * 1000)}
                events.emit(
                    event_type="webhook.delivered", agg_type="webhook", agg_id=webhook["id"],
                    project_id=webhook["project_id"], actor_type="system",
                    payload=result,
                )
                return result
            last_err = f"HTTP {last_code}"
        except (urllib.error.URLError, OSError, ValueError) as e:
            last_err = str(e) or e.__class__.__name__
    result = {"delivery_id": delivery_id, "event_type": event_dict["event_type"],
              "event_id": event_dict["id"], "attempts": attempts,
              "status_code": last_code, "error": last_err}
    events.emit(
        event_type="webhook.delivery_failed", agg_type="webhook", agg_id=webhook["id"],
        project_id=webhook["project_id"], actor_type="system",
        payload=result,
    )
    return result


def _worker_loop() -> None:
    while True:
        event_dict = _queue.get()
        try:
            if event_dict.get("_gen") != db.generation():
                # Enqueued before a reset — processing it against the new
                # generation's db would deliver a stale event (or crash on a
                # missing table). Drop before any db access (M92-I279).
                logger.debug("webhook worker dropped stale-generation event #%s",
                             event_dict.get("id"))
                continue
            rows = db.get_conn().execute(
                "SELECT * FROM webhooks WHERE project_id = ? AND enabled = 1",
                (event_dict.get("project_id") or "",),
            ).fetchall()
            for row in rows:
                subscribed = json.loads(row["events_json"] or "[]")
                if event_dict["event_type"] not in subscribed:
                    continue
                try:
                    _deliver(_parse(row, with_secret=True), event_dict)
                except Exception:  # a broken webhook must never kill the worker
                    logger.exception("webhook delivery crashed for %s", row["id"])
        except Exception:
            # The worker must survive anything (M92-I278: e.g. db gone mid-teardown).
            logger.exception("webhook worker crashed on %s", event_dict.get("event_type"))
        finally:
            _queue.task_done()


def enqueue(event: events.Event) -> None:
    """Post-emit hook: enqueue only — never block the write path on network I/O."""
    if not event.project_id:
        return
    try:
        item = event.as_dict()
        item["_gen"] = db.generation()  # stale items are dropped after a test reset (M92-I279)
        _queue.put_nowait(item)
    except queue.Full:
        logger.warning("webhook queue full; dropping event #%s", event.id)


def install_webhooks_engine() -> None:
    """Idempotent: wire the enqueue hook + start the background worker."""
    global _worker
    events.add_post_emit_hook(enqueue)
    if _worker is None or not _worker.is_alive():
        _worker = threading.Thread(target=_worker_loop, name="apm-webhooks", daemon=True)
        _worker.start()
