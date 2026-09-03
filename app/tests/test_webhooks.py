"""M10-I32 outbound webhooks: event-sourced CRUD with the secret kept out of
events, signed delivery (HMAC-SHA256 over the raw body) verified end-to-end
against an in-process receiver, retry-then-failure recording, disabled hooks
staying silent, and rebuild survival."""
from __future__ import annotations

import hashlib
import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from apm.core import projections
from apm.domains import webhooks


class Receiver(BaseHTTPRequestHandler):
    """Programmable receiver: records requests, returns `status` (settable)."""
    requests: list[dict] = []
    status: int = 200
    stall: float = 0.0

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        type(self).requests.append({
            "raw": raw,
            "event": self.headers.get("X-APM-Event"),
            "delivery": self.headers.get("X-APM-Delivery"),
            "signature": self.headers.get("X-APM-Signature"),
            "webhook": self.headers.get("X-APM-Webhook"),
        })
        if type(self).stall:
            import time as _t
            _t.sleep(type(self).stall)
        self.send_response(type(self).status)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):  # silence test output
        pass


@pytest.fixture()
def receiver():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    Receiver.requests.clear()
    Receiver.status = 200
    Receiver.stall = 0.0
    yield f"http://127.0.0.1:{srv.server_address[1]}/hook"
    srv.shutdown()


@pytest.fixture(autouse=True)
def fast_retries(monkeypatch):
    monkeypatch.setattr(webhooks, "RETRY_DELAYS", (0.05, 0.05, 0.05))


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "webhook 演示", "ontology": "software-dev", "requirement": "I32"})
    assert r.status_code == 200
    return r.json()


def test_webhook_crud_secret_never_evented_and_rebuild(client, project):
    pid = project["id"]
    r = client.post(f"/api/projects/{pid}/webhooks",
                    json={"url": "http://127.0.0.1:9/hook", "events": ["item.created"]})
    assert r.status_code == 200
    wh = r.json()
    assert wh["has_secret"] is True and len(wh["secret"]) == 64

    # The secret must not appear anywhere in the event stream.
    evs = client.get("/api/events", params={"event_type": "webhook.created"}).json()["events"]
    assert len(evs) == 1 and wh["secret"] not in evs[0]["payload"].__str__()

    # Rebuild wipes the runtime-state secret but keeps the webhook itself.
    projections.rebuild()
    hooks = client.get(f"/api/projects/{pid}/webhooks").json()["webhooks"]
    assert len(hooks) == 1 and hooks[0]["url"] == wh["url"] and hooks[0]["has_secret"] is False

    # Fail-closed: bad url / unsubscribable event / empty list.
    assert client.post(f"/api/projects/{pid}/webhooks",
                       json={"url": "ftp://x/y", "events": ["item.created"]}).status_code == 422
    assert client.post(f"/api/projects/{pid}/webhooks",
                       json={"url": "http://x/y", "events": ["webhook.created"]}).status_code == 422
    assert client.post(f"/api/projects/{pid}/webhooks",
                       json={"url": "http://x/y", "events": []}).status_code == 422

    assert client.patch(f"/api/projects/{pid}/webhooks/{wh['id']}",
                        json={"enabled": False}).status_code == 200
    rot = client.post(f"/api/projects/{pid}/webhooks/{wh['id']}/rotate")
    assert rot.status_code == 200 and len(rot.json()["secret"]) == 64
    assert client.delete(f"/api/projects/{pid}/webhooks/{wh['id']}").status_code == 200
    assert client.get(f"/api/projects/{pid}/webhooks").json()["webhooks"] == []


def test_delivery_signed_and_recorded(client, project, receiver):
    pid = project["id"]
    wh = client.post(f"/api/projects/{pid}/webhooks",
                     json={"url": receiver, "events": ["item.created"]}).json()

    item = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "bug", "title": "签名验证"}).json()

    deadline_ok = False
    import time
    for _ in range(100):
        if Receiver.requests:
            deadline_ok = True
            break
        time.sleep(0.05)
    assert deadline_ok, "receiver never got the delivery"

    got = Receiver.requests[-1]
    # Signature = HMAC-SHA256 over the RAW body bytes (docs/01 §I.1).
    expected = hmac.new(wh["secret"].encode(), got["raw"], hashlib.sha256).hexdigest()
    assert got["signature"] == expected
    assert got["event"] == "item.created"
    assert got["delivery"] and got["delivery"].startswith("dl_")
    assert got["webhook"] == wh["id"]
    assert json.loads(got["raw"])["payload"]["title"] == "签名验证"
    assert json.loads(got["raw"])["agg_id"] == item["id"]  # 事件字典：工作项 id 在 agg_id

    from apm.core import db
    row = db.get_conn().execute(
        "SELECT 1 FROM events WHERE event_type = 'webhook.delivered' AND agg_id = ?",
        (wh["id"],)).fetchone()
    assert row, "webhook.delivered must be recorded on the event stream"


def test_failure_retries_then_failed_recorded(client, project, receiver):
    pid = project["id"]
    Receiver.status = 500
    wh = client.post(f"/api/projects/{pid}/webhooks",
                     json={"url": receiver, "events": ["item.created"]}).json()
    client.post(f"/api/projects/{pid}/items",
                json={"concept_id": "bug", "title": "必然失败"})

    import time
    from apm.core import db
    for _ in range(200):
        row = db.get_conn().execute(
            "SELECT payload FROM events WHERE event_type = 'webhook.delivery_failed' AND agg_id = ?",
            (wh["id"],)).fetchone()
        if row:
            break
        time.sleep(0.05)
    assert row, "webhook.delivery_failed must be recorded after retries"
    payload = json.loads(row["payload"])
    assert payload["attempts"] == 4 and payload["status_code"] == 500  # 1 + 3 retries
    assert len(Receiver.requests) == 4


def test_disabled_webhook_stays_silent(client, project, receiver):
    pid = project["id"]
    wh = client.post(f"/api/projects/{pid}/webhooks",
                     json={"url": receiver, "events": ["item.created"], "enabled": False}).json()
    client.post(f"/api/projects/{pid}/items", json={"concept_id": "bug", "title": "静默"})
    import time
    time.sleep(0.4)  # give the worker a fair chance to (wrongly) deliver
    assert not Receiver.requests
    # Re-enable → same project events flow again (row state drives delivery).
    client.patch(f"/api/projects/{pid}/webhooks/{wh['id']}", json={"enabled": True})
    client.post(f"/api/projects/{pid}/items", json={"concept_id": "bug", "title": "恢复"})
    for _ in range(100):
        if Receiver.requests:
            break
        time.sleep(0.05)
    assert Receiver.requests and Receiver.requests[-1]["event"] == "item.created"
