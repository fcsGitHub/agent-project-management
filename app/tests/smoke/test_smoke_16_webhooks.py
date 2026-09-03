"""Smoke 16 (M10-I32): outbound webhooks — signed delivery against a local
receiver (HMAC-SHA256 over the raw body + X-APM-* headers), the write path
returning before a stalling receiver answers (delivery never blocks writes),
retry-then-failure recording, and rebuild survival."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from apm.core import projections
from apm.domains import webhooks as wh_mod


class HookReceiver(BaseHTTPRequestHandler):
    records: list[dict] = []
    status: int = 200
    stall: float = 0.0

    def do_POST(self):
        import time as _t
        started = _t.monotonic()
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if type(self).stall:
            _t.sleep(type(self).stall)
        type(self).records.append({
            "raw": raw, "finished": _t.monotonic(),
            "path": self.path,
            "signature": self.headers.get("X-APM-Signature"),
            "event": self.headers.get("X-APM-Event"),
            "delivery": self.headers.get("X-APM-Delivery"),
        })
        status = 500 if self.path.endswith("/bad") else type(self).status
        self.send_response(status)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


@pytest.mark.smoke
def test_smoke_16_webhooks(client, tmp_data, isolated_ontologies, monkeypatch):
    monkeypatch.setattr(wh_mod, "RETRY_DELAYS", (0.05, 0.05, 0.05))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), HookReceiver)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    HookReceiver.records.clear()
    HookReceiver.status = 200
    HookReceiver.stall = 0.0
    try:
        p = client.post("/api/projects",
                        json={"name": "冒烟16 webhook", "ontology": "software-dev",
                              "requirement": "webhook"}).json()
        pid = p["id"]

        # Two hooks: one healthy, one that answers 500 (retry path), one slow one
        # for the non-blocking timing check.
        ok = client.post(f"/api/projects/{pid}/webhooks",
                         json={"url": f"{base}/ok", "events": ["item.created"]}).json()
        bad = client.post(f"/api/projects/{pid}/webhooks",
                          json={"url": f"{base}/bad", "events": ["item.created"]}).json()
        slow = client.post(f"/api/projects/{pid}/webhooks",
                           json={"url": f"{base}/slow", "events": ["item.created"]}).json()
        assert ok["has_secret"] and bad["has_secret"] and slow["has_secret"]

        # Non-blocking: the stalling receiver holds the connection ~2s, the write
        # must return well before that.
        HookReceiver.stall = 2.0
        t0 = time.monotonic()
        bug = client.post(f"/api/projects/{pid}/items",
                          json={"concept_id": "bug", "title": "冒烟缺陷"}).json()
        write_elapsed = time.monotonic() - t0
        assert write_elapsed < 1.0, f"write blocked on delivery ({write_elapsed:.2f}s)"
        HookReceiver.stall = 0.0

        # The healthy delivery arrives, signed over the raw body.
        for _ in range(120):
            hits = [r for r in HookReceiver.records if r["event"] == "item.created"
                    and "/ok" not in r["raw"].decode("utf-8", "ignore")[:0]]
            if hits:
                break
            time.sleep(0.05)
        ok_hits = [r for r in HookReceiver.records if r["signature"]]
        assert ok_hits, "no signed delivery reached the receiver"
        import hashlib
        import hmac
        got = ok_hits[0]
        expected = hmac.new(ok["secret"].encode(), got["raw"], hashlib.sha256).hexdigest()
        assert got["signature"] == expected, "signature must be HMAC-SHA256 of the raw body"
        assert got["delivery"] and got["delivery"].startswith("dl_")

        # Delivery outcomes land on the event stream: delivered for `ok`,
        # failed after retries for `bad`.
        from apm.core import db
        delivered = False
        failed = None
        for _ in range(200):
            conn = db.get_conn()
            delivered = conn.execute(
                "SELECT 1 FROM events WHERE event_type='webhook.delivered' AND agg_id=?",
                (ok["id"],)).fetchone() is not None
            failed = conn.execute(
                "SELECT payload FROM events WHERE event_type='webhook.delivery_failed' AND agg_id=?",
                (bad["id"],)).fetchone()
            if delivered and failed:
                break
            time.sleep(0.05)
        assert delivered, "webhook.delivered missing"
        assert failed, "webhook.delivery_failed missing"
        assert json.loads(failed["payload"])["attempts"] == 4  # 1 + 3 retries

        # Rebuild: the webhook rows survive (secrets are runtime state and may
        # legitimately vanish — url/events/enabled are the sourced part).
        projections.rebuild()
        hooks = client.get(f"/api/projects/{pid}/webhooks").json()["webhooks"]
        assert {h["url"] for h in hooks} == {f"{base}/ok", f"{base}/bad", f"{base}/slow"}
        assert client.delete(f"/api/projects/{pid}/webhooks/{slow['id']}").status_code == 200

        # Notifications (M10-I34): assignment notifies the assignee; read-all clears.
        client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
        client.patch(f"/api/items/{bug['id']}",
                     json={"assignee_type": "human", "assignee_id": "qa-wang"})
        client.post("/api/session/identity", json={"user_id": "qa-wang"})
        notes = client.get("/api/notifications").json()
        assert notes["user_id"] == "qa-wang" and notes["unread"] >= 1
        assert notes["notifications"][0]["kind"] == "assigned"
        assert client.post("/api/notifications/read", json={"all": True}).status_code == 200
        assert client.get("/api/notifications").json()["unread"] == 0
        client.post("/api/session/identity", json={"user_id": "u_admin"})
    finally:
        srv.shutdown()
