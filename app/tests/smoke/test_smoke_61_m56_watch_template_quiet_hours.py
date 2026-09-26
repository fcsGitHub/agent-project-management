"""Smoke 61 (M56): watch template sharing & quiet hours — own rules export as
a project-agnostic template that a teammate imports into their project with
honest imported/skipped accounting (rebuild reproduces), and a per-user quiet
window pauses email push while in-app keeps flowing; @mention and the weekly
digest break through; outside the window mail recovers."""
from __future__ import annotations

import time

import pytest

from apm import config
from apm.core import events, projections
from apm.domains import mailer


class StubSMTP:
    sent: list[dict] = []

    def __init__(self, *a, **k):
        pass

    def starttls(self, context=None):
        pass

    def login(self, *a):
        pass

    def send_message(self, msg):
        type(self).sent.append({"to": msg["To"], "subject": msg["Subject"],
                                "body": msg.get_body(preferencelist=("plain",)).get_content()
                                if msg.get_body(preferencelist=("plain",)) else ""})

    def quit(self):
        pass


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.mark.smoke
def test_smoke_61_m56_watch_template_quiet_hours(client, tmp_data, isolated_ontologies,
                                                 monkeypatch):
    StubSMTP.sent.clear()
    monkeypatch.setattr(mailer.smtplib, "SMTP", StubSMTP)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", StubSMTP)
    monkeypatch.setattr(mailer.config.settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(mailer.config.settings, "smtp_from", "agentpm@test.local")

    # --- ① 模板导出→导入 roundtrip：A 的关注配置一键搬给 B ---------------------
    pa = client.post("/api/projects",
                     json={"name": "冒烟模板甲", "ontology": "software-dev"}).json()["id"]
    pb = client.post("/api/projects",
                     json={"name": "冒烟模板乙", "ontology": "software-dev"}).json()["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "email": "qa@x.local"})
    assert client.post(f"/api/projects/{pb}/members",
                       json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200

    # u_admin（甲乙两个项目的 owner）配置两条带条件的规则
    assert client.post(f"/api/projects/{pa}/watch-rules",
                       json={"event_type": "item.status_changed",
                             "condition": {"status_group": "done"}}).status_code == 200
    assert client.post(f"/api/projects/{pb}/watch-rules",
                       json={"event_type": "item.created",
                             "condition": {"concept_id": "task"}}).status_code == 200
    tpl = client.get("/api/watch-rules/export").json()
    assert tpl["version"] == 1 and len(tpl["rules"]) == 2

    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    r = client.post(f"/api/projects/{pb}/watch-rules/import", json={"rules": tpl["rules"]})
    assert r.status_code == 200 and r.json() == {"imported": 2, "skipped": 0}
    r2 = client.post(f"/api/projects/{pb}/watch-rules/import", json={"rules": tpl["rules"]})
    assert r2.json() == {"imported": 0, "skipped": 2}  # 模板不覆盖已有
    rules = client.get("/api/watch-rules").json()["rules"]
    assert len(rules) == 2 and all(rules[i]["condition"] for i in (0, 1))
    projections.ensure_handlers_registered()
    projections.rebuild()
    assert client.get("/api/watch-rules").json()["rules"] == rules  # 事件可重放

    # --- ② 静默窗口：邮件静默、站内照常 ----------------------------------------
    assert client.put("/api/me/quiet-hours",
                      json={"start": "22:00", "end": "08:00"}).status_code == 200
    monkeypatch.setattr(mailer, "_now_hhmm", lambda: "23:30")  # 窗口内
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    bug = client.post(f"/api/projects/{pb}/items",
                      json={"concept_id": "bug", "title": "深夜缺陷"}).json()
    client.patch(f"/api/items/{bug['id']}",
                 json={"assignee_type": "human", "assignee_id": "qa-wang"})
    time.sleep(0.4)
    assert not StubSMTP.sent  # 邮件推送被静默
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    notes = client.get("/api/notifications").json()["notifications"]
    assert any(n["kind"] == "assigned" and "深夜缺陷" in n["summary"] for n in notes)

    # --- ③ @提及与周报 digest 突破；窗口外邮件恢复 ------------------------------
    events.emit(event_type="notification.sent", agg_type="project", agg_id=pb,
                project_id=pb,
                payload={"user_id": "qa-wang", "kind": "mention", "summary": "深夜提及"})
    deadline = time.monotonic() + 5
    while len(StubSMTP.sent) < 1 and time.monotonic() < deadline:
        time.sleep(0.05)
    assert StubSMTP.sent and StubSMTP.sent[0]["to"] == "qa@x.local"
    events.emit(event_type="notification.sent", agg_type="project", agg_id=pb,
                project_id=pb,
                payload={"user_id": "qa-wang", "kind": "report_weekly",
                         "summary": "周报已生成", "digest": "每周摘要正文"})
    deadline = time.monotonic() + 5
    while len(StubSMTP.sent) < 2 and time.monotonic() < deadline:
        time.sleep(0.05)
    assert "每周摘要正文" in StubSMTP.sent[1]["body"]

    monkeypatch.setattr(mailer, "_now_hhmm", lambda: "12:00")  # 窗口外
    bug2 = client.post(f"/api/projects/{pb}/items",
                       json={"concept_id": "bug", "title": "白天缺陷"}).json()
    client.patch(f"/api/items/{bug2['id']}",
                 json={"assignee_type": "human", "assignee_id": "qa-wang"})
    deadline = time.monotonic() + 5
    while len(StubSMTP.sent) < 3 and time.monotonic() < deadline:
        time.sleep(0.05)
    assert "白天缺陷" in StubSMTP.sent[-1]["subject"]

    # 收尾：清除静默 = 关闭
    assert client.put("/api/me/quiet-hours", json={"start": "", "end": ""}).status_code == 200
    assert client.get("/api/me/quiet-hours").json() == {"start": None, "end": None}
