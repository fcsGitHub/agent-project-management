"""Smoke 57 (M52): weekly report distribution completed — a subscriber (not
an owner) opts in via the subscription endpoint, the sweep mails owner and
subscriber one digest each with the .md attachment, the per-kind email pref
gate still holds for subscribers, and unsubscribing stops future mails."""
from __future__ import annotations

import time
from datetime import date

import pytest

from apm import config
from apm.core import db
from apm.domains import mailer


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = (config.settings.user_id, config.settings.weekly_report_day)
    yield
    (config.settings.user_id, config.settings.weekly_report_day) = saved


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
        type(self).sent.append({
            "to": msg["To"], "subject": msg["Subject"],
            "body": part.get_content() if part else "",
            "attachments": [
                {"filename": a.get_filename(), "content": a.get_content()}
                for a in msg.iter_attachments()
            ],
        })

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
def test_smoke_57_m52_subscription_attachment(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "冒烟订阅", "ontology": "software-dev"}).json()["id"]
    # 带邮箱的 owner（创建者 u_admin 无邮箱→静默跳过）+ 订阅者
    client.post("/api/users", json={"id": "boss", "name": "老板", "email": "boss@x.local"})
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "email": "qa@x.local"})
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "boss", "role": "owner"}).status_code == 200
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200

    # --- ① 订阅：成员自选成为周报收件人 ---------------------------------------
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert client.post(f"/api/projects/{pid}/report-subscription").status_code == 200
    assert client.get(f"/api/projects/{pid}/report-subscription").json()["subscribed"] is True
    client.post("/api/session/identity", json={"user_id": "u_admin"})

    # --- ② sweep：owner 与订阅者各一份 digest 邮件，均带 .md 附件 -------------
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "冒烟订阅任务"}).json()
    client.patch(f"/api/items/{it['id']}", json={"status": "done"})
    from apm.core import events as events_mod
    from apm.domains.automations import _report_status_weekly
    sweep_today = events_mod.utcnow()[:10]
    config.settings.weekly_report_day = date.fromisoformat(sweep_today).isoweekday()
    r = client.post("/api/automations/sweep", json={"force": True})
    assert r.status_code == 200 and r.json()["reported"] >= 1

    assert _wait_mail(2), "owner+subscriber mails never sent"
    tos = sorted(m["to"] for m in FakeSMTP.sent[:2])
    assert tos == ["boss@x.local", "qa@x.local"]
    for m in FakeSMTP.sent[:2]:
        atts = list(m["attachments"])
        assert len(atts) == 1 and atts[0]["filename"].startswith("weekly-report-2026-W")
        assert "## 总体健康" in atts[0]["content"]

    # --- ③ 偏好关断只闸邮件通道：订阅者站内通知照常 ---------------------------
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert client.put("/api/me/notification-prefs", json={
        "prefs": [{"kind": "report_weekly", "inapp": True, "email": False}]}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    nxt = _next_week(sweep_today)
    assert _report_status_weekly(db.get_conn(), nxt) == 1
    assert _wait_mail(3)
    assert FakeSMTP.sent[-1]["to"] == "boss@x.local"  # 订阅者被 email 门闸住
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    kinds = [n["kind"] for n in client.get("/api/notifications").json()["notifications"]]
    assert kinds.count("report_weekly") == 2  # 两期都在，邮件被闸站内照常

    # --- ④ 退订：下一期收件人只剩 owner ---------------------------------------
    assert client.delete(f"/api/projects/{pid}/report-subscription").status_code == 200
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    assert _report_status_weekly(db.get_conn(), _next_week(nxt)) == 1
    assert _wait_mail(4)
    assert FakeSMTP.sent[-1]["to"] == "boss@x.local"
    assert all(m["to"] != "qa@x.local" for m in FakeSMTP.sent[3:])  # 退订后不再收


def _next_week(iso_day: str) -> str:
    from datetime import timedelta
    return (date.fromisoformat(iso_day) + timedelta(days=7)).isoformat()
