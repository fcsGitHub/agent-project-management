"""M56-I169 静默时段（docs/01 §BA.2，Slack DND 语义）：用户级免打扰窗口内
邮件推送静默、站内照常（铃铛即实时面）；@提及突破（急迫性最高，与 I96
mention 不可关断同族）；周报 digest 已是 M51 的批量窗口，不再重复抑制；
窗口外邮件照常。窗口判定是纯函数——跨午夜 start>end、边界含端点、相等或
缺失/非法=关（坏日程绝不吞掉整个邮件通道）。"""
from __future__ import annotations

import time

import pytest

from apm import config
from apm.core import events
from apm.domains import mailer
from apm.domains.notifications import quiet_active


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
        type(self).sent.append({"to": msg["To"], "subject": msg["Subject"],
                                "body": part.get_content() if part else ""})

    def quit(self):
        pass


@pytest.fixture(autouse=True)
def smtp_stub(monkeypatch):
    FakeSMTP.sent.clear()
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", FakeSMTP)
    yield


def _configure(monkeypatch):
    monkeypatch.setattr(config.settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(config.settings, "smtp_from", "agentpm@test.local")
    monkeypatch.setattr(config.settings, "smtp_port", 587)


def _wait_mail(n=1, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(FakeSMTP.sent) >= n:
            return True
        time.sleep(0.05)
    return False


def test_quiet_window_predicate():
    """纯函数五面：同日窗口/跨午夜/边界含端点/相等与缺失=关/非法=关。"""
    assert quiet_active("22:00", "08:00", "23:30")  # 跨午夜·start 侧
    assert quiet_active("22:00", "08:00", "01:00")  # 跨午夜·end 侧
    assert quiet_active("09:00", "18:00", "12:00")  # 同日窗口
    assert quiet_active("09:00", "18:00", "09:00")  # 边界含端点
    assert quiet_active("09:00", "18:00", "18:00")
    assert not quiet_active("09:00", "18:00", "08:59")
    assert not quiet_active("22:00", "08:00", "12:00")  # 跨午夜窗口外
    assert not quiet_active("09:00", "09:00", "09:00")  # 相等=关
    assert not quiet_active(None, None, "12:00")        # 缺失=关
    assert not quiet_active("25:00", "08:00", "12:00")  # 非法=关（防御）


def test_quiet_hours_roundtrip_and_validation(client, tmp_data, isolated_ontologies):
    assert client.put("/api/me/quiet-hours",
                      json={"start": "22:00"}).status_code == 422  # 只给一端
    assert client.put("/api/me/quiet-hours",
                      json={"start": "22:00", "end": "25:00"}).status_code == 422
    assert client.put("/api/me/quiet-hours",
                      json={"start": "22:00", "end": "8:00"}).status_code == 422
    assert client.put("/api/me/quiet-hours",
                      json={"start": "09:00", "end": "09:00"}).status_code == 422
    assert client.put("/api/me/quiet-hours",
                      json={"start": "22:00", "end": "08:00"}).status_code == 200
    assert client.get("/api/me/quiet-hours").json() == {"start": "22:00", "end": "08:00"}
    assert client.put("/api/me/quiet-hours",
                      json={"start": "", "end": ""}).json()["start"] is None  # 清除=关闭


def test_quiet_hours_email_gate(client, tmp_data, isolated_ontologies, monkeypatch):
    """窗口内：指派邮件静默、站内照常；@提及与 digest 邮件突破；
    窗口外恢复。_now_hhmm 打桩保证确定性。"""
    _configure(monkeypatch)
    pid = client.post("/api/projects",
                      json={"name": "静默项目", "ontology": "software-dev"}).json()["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "email": "qa@x.local"})
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert client.put("/api/me/quiet-hours", json={"start": "22:00", "end": "08:00"}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "u_admin"})

    monkeypatch.setattr(mailer, "_now_hhmm", lambda: "23:30")  # 窗口内
    bug = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "bug", "title": "深夜任务"}).json()
    client.patch(f"/api/items/{bug['id']}",
                 json={"assignee_type": "human", "assignee_id": "qa-wang"})
    time.sleep(0.4)
    assert not FakeSMTP.sent  # 邮件被静默
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    notes = client.get("/api/notifications").json()["notifications"]
    assert any(n["kind"] == "assigned" and "深夜任务" in n["summary"] for n in notes)  # 站内照常
    client.post("/api/session/identity", json={"user_id": "u_admin"})

    # @提及突破（急迫性最高）
    events.emit(event_type="notification.sent", agg_type="project", agg_id=pid,
                project_id=pid,
                payload={"user_id": "qa-wang", "kind": "mention", "summary": "深夜提及你"})
    assert _wait_mail(1)
    assert FakeSMTP.sent[0]["to"] == "qa@x.local"
    # 周报 digest 突破（已是批量窗口，静默期不重复抑制）
    events.emit(event_type="notification.sent", agg_type="project", agg_id=pid,
                project_id=pid,
                payload={"user_id": "qa-wang", "kind": "report_weekly",
                         "summary": "周报已生成", "digest": "每周摘要正文"})
    assert _wait_mail(2)
    assert "每周摘要正文" in FakeSMTP.sent[1]["body"]

    # 窗口外恢复
    monkeypatch.setattr(mailer, "_now_hhmm", lambda: "12:00")
    bug2 = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "bug", "title": "白天任务"}).json()
    client.patch(f"/api/items/{bug2['id']}",
                 json={"assignee_type": "human", "assignee_id": "qa-wang"})
    assert _wait_mail(3)
    assert "白天任务" in FakeSMTP.sent[-1]["subject"]
