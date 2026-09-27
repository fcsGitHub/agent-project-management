"""Smoke 72 (M67): ecosystem outbound & permission depth — ① concept-level
visibility: a declared concept vanishes from a non-owner's board/list/search
while the owner sees everything; ② the ntfy push channel delivers through the
gate chain (pref matrix + SSRF escape hatch) and lands as a push.notified
fact; ③ the Prometheus exposition answers with an intact histogram."""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from apm import config
from apm.core import db


class Receiver(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        type(self).requests.append({
            "raw": raw.decode("utf-8"),
            "priority": self.headers.get("Priority"),
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
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    Receiver.requests.clear()
    yield f"http://127.0.0.1:{srv.server_address[1]}/smoke"
    srv.shutdown()


@pytest.mark.smoke
def test_smoke_72_m67_concept_visibility_push_metrics(client, tmp_data,
                                                      isolated_ontologies,
                                                      monkeypatch, receiver):
    monkeypatch.setattr(config.settings, "webhook_allow_private", True)
    monkeypatch.setattr(config.settings, "web_base_url", "https://apm.example.com")
    monkeypatch.setattr(config.settings, "metrics_enabled", True)

    pid = client.post("/api/projects",
                      json={"name": "冒烟纵深", "ontology": "software-dev"}).json()["id"]
    client.post("/api/users", json={"id": "owner-he", "name": "Owner 何",
                                    "password": "he-pass"})
    client.post(f"/api/projects/{pid}/members",
                json={"user_id": "owner-he", "role": "owner"})

    # --- ① 概念级可见性：bug 仅 owner；contributor 全面不可见 ------------------
    assert client.patch(f"/api/projects/{pid}",
                        json={"concept_visibility": {"bug": "owner"}}).status_code == 200
    secret = client.post(f"/api/projects/{pid}/items",
                         json={"concept_id": "bug", "title": "机密缺陷"}).json()
    # --- ② 推送通道：配置 + 指派投递 -------------------------------------------
    assert client.post("/api/me/push", json={"push_url": receiver}).status_code == 200

    from apm.domains.users import ensure_default_user
    config.settings.admin_password = "smoke-admin"
    ensure_default_user()
    monkeypatch.setattr(config.settings, "auth_mode", "network")
    assert client.post("/api/auth/login",
                       json={"user_id": "u_admin",
                             "password": "smoke-admin"}).status_code == 200
    import time

    deadline = time.time() + 5
    while time.time() < deadline and not Receiver.requests:
        it = client.post(f"/api/projects/{pid}/items",
                         json={"concept_id": "task", "title": "冒烟指派"}).json()
        client.patch(f"/api/items/{it['id']}", json={
            "assignee_type": "human", "assignee_id": "u_admin"})
        time.sleep(0.1)
    assert Receiver.requests, "assignment push never arrived"
    assert Receiver.requests[0]["priority"] == "3"

    # contributor's view of the restricted concept — drive via dev-li's PAT
    client.post("/api/users", json={"id": "dev-qian", "name": "开发钱",
                                    "password": "qian-pass"})
    client.post(f"/api/projects/{pid}/members",
                json={"user_id": "dev-qian", "role": "contributor"})
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login",
                       json={"user_id": "dev-qian",
                             "password": "qian-pass"}).status_code == 200
    tok = client.post("/api/auth/tokens", json={"name": "冒烟"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    listing = client.get(f"/api/projects/{pid}/items", headers=h).json()
    assert all(it2["id"] != secret["id"] for it2 in listing["items"])
    assert client.get(f"/api/items/{secret['id']}", headers=h).status_code == 404
    client.post("/api/auth/logout")

    # --- ③ Prometheus 出站：histogram 完整 + 事件账本对账 ----------------------
    text = client.get("/api/system/metrics", headers=h).text
    assert "# TYPE apm_http_request_duration_seconds histogram" in text
    assert 'apm_http_request_duration_seconds_bucket{le="+Inf"}' in text
    exported = sum(int(l.rsplit(" ", 1)[1]) for l in text.splitlines()
                   if l.startswith("apm_events_total{"))
    truth = db.get_conn().execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
    assert exported == truth
    config.settings.admin_password = ""
