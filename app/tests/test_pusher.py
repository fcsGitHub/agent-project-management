"""M67-I202 ntfy 推送通道（docs/01 §BL.2，mailer 的物理通道镜像）：
users.push_url/push_token 走 webhook 同款 SSRF 门（allow_private 逃生门给
自托管内网 ntfy）；通道矩阵第三列 pref_allows(push)/watch channels；
静默时段对推送生效、mention 突破且 Priority=5；投递事实 push.notified 与
email.notified 同族入流（审计 trail 跨物理通道一致）。"""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from apm import config
from apm.core import db, events


class Receiver(BaseHTTPRequestHandler):
    """Records ntfy-style POSTs: Title/Priority/Tags headers + auth."""
    requests: list[dict] = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        type(self).requests.append({
            "raw": raw.decode("utf-8"),
            "title": self.headers.get("Title"),
            "priority": self.headers.get("Priority"),
            "tags": self.headers.get("Tags"),
            "auth": self.headers.get("Authorization"),
        })
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


@pytest.fixture()
def receiver():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    Receiver.requests.clear()
    yield f"http://127.0.0.1:{srv.server_address[1]}/topic"
    srv.shutdown()


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    # 接收器跑在环回——SSRF 门显式放开（webhook 套件同款惯例）。
    monkeypatch.setattr(config.settings, "webhook_allow_private", True)
    monkeypatch.setattr(config.settings, "web_base_url", "https://apm.example.com")
    yield


def _wait_for(n: int, timeout: float = 5.0) -> None:
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(Receiver.requests) >= n:
            return
        time.sleep(0.02)
    raise AssertionError(f"expected {n} pushes, saw {len(Receiver.requests)}")


def test_push_config_ssrf_gate_and_roundtrip(client, tmp_data, monkeypatch):
    # private/loopback blocked by default (same discipline as webhooks)
    monkeypatch.setattr(config.settings, "webhook_allow_private", False)
    r = client.post("/api/me/push", json={"push_url": "http://127.0.0.1:9/topic"})
    assert r.status_code == 422
    # with the escape hatch on, the LAN ntfy (canonical self-hosted setup) is admitted
    monkeypatch.setattr(config.settings, "webhook_allow_private", True)
    assert client.post("/api/me/push", json={
        "push_url": "http://127.0.0.1:9/topic", "push_token": "tok123"}).status_code == 200
    cfg = client.get("/api/me/push").json()
    assert cfg == {"push_url": "http://127.0.0.1:9/topic", "has_token": True}
    # clearing the URL clears the token too
    assert client.post("/api/me/push", json={"push_url": None}).status_code == 200
    assert client.get("/api/me/push").json() == {"push_url": None, "has_token": False}


def test_delivery_priority_and_event_audit(client, tmp_data, receiver):
    config.settings.webhook_allow_private = True
    try:
        assert client.post("/api/me/push", json={
            "push_url": receiver, "push_token": "tok123"}).status_code == 200
        pid = client.post("/api/projects",
                          json={"name": "推送项目", "ontology": "software-dev"}).json()["id"]
        # assignment fires on PATCH, not create (M8 create semantics)
        it = client.post(f"/api/projects/{pid}/items",
                         json={"concept_id": "task", "title": "被指派的项"}).json()
        client.patch(f"/api/items/{it['id']}", json={
            "assignee_type": "human", "assignee_id": "u_admin"})
        _wait_for(1)
        push = Receiver.requests[0]
        assert "被指派的项" in push["raw"]
        assert push["priority"] == "3" and push["title"].startswith("[AgentPM]")
        assert push["auth"] == "Bearer tok123"

        # the delivery fact is evented like email.notified (audit uniformity) —
        # poll briefly: the worker emits right after the HTTP round-trip
        row = None
        import time

        deadline = time.time() + 5
        while time.time() < deadline:
            row = db.get_conn().execute(
                "SELECT event_type FROM events WHERE event_type = 'push.notified'"
                " ORDER BY id DESC LIMIT 1").fetchone()
            if row:
                break
            time.sleep(0.02)
        assert row and row["event_type"] == "push.notified"
    finally:
        config.settings.webhook_allow_private = False


def test_pref_gate_and_watch_channel_routing(client, tmp_data, receiver):
    config.settings.webhook_allow_private = True
    try:
        assert client.post("/api/me/push", json={"push_url": receiver}).status_code == 200
        pid = client.post("/api/projects",
                          json={"name": "路由项目", "ontology": "software-dev"}).json()["id"]
        client.post("/api/users", json={"id": "dev-li", "name": "开发李"})
        client.post(f"/api/projects/{pid}/members",
                    json={"user_id": "dev-li", "role": "contributor"})
        # dev-li gets the same receiver (own-data endpoint is per-user; the
        # test drives the column directly to stay in u_admin's session)
        db.get_conn().execute("UPDATE users SET push_url = ? WHERE id = 'dev-li'",
                              (receiver,))
        db.get_conn().commit()

        # turn the push column off for assignments on u_admin
        prefs = client.put("/api/me/notification-prefs", json={
            "prefs": [{"kind": "assigned", "inapp": True, "email": True, "push": False}]})
        assert prefs.status_code == 200
        it1 = client.post(f"/api/projects/{pid}/items",
                          json={"concept_id": "task", "title": "静音的指派"}).json()
        client.patch(f"/api/items/{it1['id']}", json={
            "assignee_type": "human", "assignee_id": "u_admin"})
        # ...while dev-li (push pref untouched, defaults on) receives theirs
        it2 = client.post(f"/api/projects/{pid}/items",
                          json={"concept_id": "task", "title": "李的指派"}).json()
        client.patch(f"/api/items/{it2['id']}", json={
            "assignee_type": "human", "assignee_id": "dev-li"})
        _wait_for(1)
        assert len(Receiver.requests) == 1
        assert "李的指派" in Receiver.requests[0]["raw"]

        # a watch rule can route toward push explicitly (rule-level override);
        # the status change must come from someone other than the rule's owner
        # (M54 self-event suppression skips a watcher's own actions)
        r = client.post(f"/api/projects/{pid}/watch-rules", json={
            "event_type": "item.status_changed", "channels": ["push"]})
        assert r.status_code in (200, 201), r.text
        item = client.post(f"/api/projects/{pid}/items",
                           json={"concept_id": "task", "title": "关注的状态项"}).json()
        before = len(Receiver.requests)
        events.emit(event_type="item.status_changed", agg_type="item", agg_id=item["id"],
                    project_id=pid, actor_type="human", actor_id="dev-li",
                    payload={"status": "in_progress", "status_group": "in_progress"})
        _wait_for(before + 1)
        assert any("关注的状态项" in q["raw"] for q in Receiver.requests[before:])
    finally:
        config.settings.webhook_allow_private = False
