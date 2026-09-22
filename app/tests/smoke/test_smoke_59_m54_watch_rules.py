"""Smoke 59 (M54): user-built watch rules roundtrip — a member watches
「item.status_changed」 on a project, another member's action produces a
watch notification in-app AND an email through the existing channels, the
per-kind pref gate mutes both channels while the facts stay on the stream,
and removing the rule stops future notifications."""
from __future__ import annotations

import time

import pytest

from apm import config
from apm.core import db
from apm.domains import mailer


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


class FakeSMTP:
    sent: list[dict] = []

    def __init__(self, host, port, timeout=None, ssl=False, context=None):
        pass

    def starttls(self, context=None):
        pass

    def login(self, user, passwd):
        pass

    def send_message(self, msg):
        part = msg.get_body(preferencelist=("plain",))
        type(self).sent.append({"to": msg["To"],
                                "body": part.get_content() if part else ""})

    def quit(self):
        pass


@pytest.fixture(autouse=True)
def smtp_stub(monkeypatch):
    FakeSMTP.sent.clear()
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(config.settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(config.settings, "smtp_from", "agentpm@test.local")
    monkeypatch.setattr(config.settings, "smtp_port", 587)
    yield


def _wait_mail(n=1, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(FakeSMTP.sent) >= n:
            return True
        time.sleep(0.05)
    return False


@pytest.mark.smoke
def test_smoke_59_m54_watch_rules(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "冒烟关注", "ontology": "software-dev"}).json()["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "email": "qa@x.local"})
    client.post("/api/users", json={"id": "dev-li", "name": "李工"})
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "dev-li", "role": "contributor"}).status_code == 200

    # --- ① qa-wang 建 watch：状态变更 -----------------------------------------
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    r = client.post(f"/api/projects/{pid}/watch-rules",
                    json={"event_type": "item.status_changed"})
    assert r.status_code == 200, r.text
    assert [x["event_type"] for x in client.get("/api/watch-rules").json()["rules"]] \
        == ["item.status_changed"]

    # --- ② 他人动作 → 站内 + 邮件双通道 ---------------------------------------
    client.post("/api/session/identity", json={"user_id": "dev-li"})
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "冒烟关注任务"}).json()
    client.patch(f"/api/items/{it['id']}", json={"status": "done"})
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    notes = client.get("/api/notifications").json()["notifications"]
    wk = [n for n in notes if n["kind"] == "watch"]
    assert len(wk) == 1 and "关注任务" in wk[0]["summary"]
    assert _wait_mail(1), "watch email never sent"
    assert FakeSMTP.sent[-1]["to"] == "qa@x.local"
    assert "watch" in FakeSMTP.sent[-1]["body"]

    # --- ③ 偏好关断：两通道全静默，事件照发 -----------------------------------
    assert client.put("/api/me/notification-prefs", json={
        "prefs": [{"kind": "watch", "inapp": False, "email": False}]}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "dev-li"})
    it2 = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "task", "title": "被闸的任务"}).json()
    client.patch(f"/api/items/{it2['id']}", json={"status": "done"})
    time.sleep(0.4)
    assert not _wait_mail(2), "email gate failed to hold"
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert len([n for n in client.get("/api/notifications").json()["notifications"]
                if n["kind"] == "watch"]) == 1  # 站内被闸
    sent = client.get("/api/events",
                      params={"event_type": "notification.sent"}).json()["events"]
    assert len([e for e in sent if e["payload"].get("kind") == "watch"]) == 2  # 事实照发

    # --- ④ 删规则 → 之后的动作不再产生 watch 通知 ------------------------------
    assert client.delete(f"/api/projects/{pid}/watch-rules/item.status_changed").status_code == 200
    client.post("/api/session/identity", json={"user_id": "dev-li"})
    it3 = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "task", "title": "退订后动作"}).json()
    client.patch(f"/api/items/{it3['id']}", json={"status": "done"})
    time.sleep(0.3)
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert len([n for n in client.get("/api/notifications").json()["notifications"]
                if n["kind"] == "watch"]) == 1  # 不再新增
    assert client.get("/api/watch-rules").json()["rules"] == []
    client.post("/api/session/identity", json={"user_id": "u_admin"})
