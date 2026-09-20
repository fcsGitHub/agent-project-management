"""Smoke 56 (M51): weekly report deepening & distribution — the corpus layer
(deterministic per-item comment digest, no model), the digest email (mail body
self-contained: funnel/overdue/comparison/artifact path), and the pref gate
(email channel off → no mail, in-app notification untouched)."""
from __future__ import annotations

import time
from datetime import date, timedelta

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
def test_smoke_56_m51_weekly_corpus_digest(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "冒烟周报分发", "ontology": "software-dev"}).json()["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "email": "qa@x.local"})
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "qa-wang", "role": "owner"}).status_code == 200

    # --- ① 项目数据：1 完成 + 2 条评论（语料素材）------------------------------
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "冒烟周报任务"}).json()
    client.patch(f"/api/items/{it['id']}", json={"status": "done"})
    client.post(f"/api/items/{it['id']}/comments", json={"body": "冒烟进展：接口联调通过"})
    client.post(f"/api/items/{it['id']}/comments", json={"body": "冒烟进展：前端联调中"})

    # --- ② sweep 周报：语料段 + digest 邮件（对齐 sweep 实际 UTC 今天）---------
    from apm.core import events as events_mod
    from apm.domains.automations import _report_status_weekly
    sweep_today = events_mod.utcnow()[:10]
    config.settings.weekly_report_day = date.fromisoformat(sweep_today).isoweekday()
    r = client.post("/api/automations/sweep", json={"force": True})
    assert r.status_code == 200 and r.json()["reported"] >= 1

    lst = client.get(f"/api/projects/{pid}/reports").json()["reports"]
    weekly = [x for x in lst if x["source"] == "weekly"]
    assert len(weekly) == 1 and weekly[0]["metrics"]["done_pct"] == 100
    art = client.get(f"/api/projects/{pid}/artifacts/{weekly[0]['path']}").json()
    assert "## 本期动态（评论）" in art["content"]
    assert "冒烟进展：接口联调通过" in art["content"]
    assert "首期报告，无上期数据可比" in art["content"]

    # owner 邮件正文自含结论（语料不进邮件——邮件带指标/环比/工件路径）
    assert _wait_mail(1), "digest mail never sent"
    mail = FakeSMTP.sent[-1]
    assert mail["to"] == "qa@x.local" and "周报" in mail["subject"]
    assert "完成度约 100%" in mail["body"] and "首期周报" in mail["body"]
    assert weekly[0]["path"] in mail["body"]

    # --- ③ 下一期环比 + email 偏好关断 ----------------------------------------
    nxt = (date.fromisoformat(sweep_today) + timedelta(days=7)).isoformat()
    it2 = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "task", "title": "第二周任务"}).json()
    client.patch(f"/api/items/{it2['id']}", json={"status": "done"})
    client.patch(f"/api/items/{it2['id']}", json={"status": "open"})
    assert _report_status_weekly(db.get_conn(), nxt) == 1
    lst2 = client.get(f"/api/projects/{pid}/reports").json()["reports"]
    weekly2 = [x for x in lst2 if x["source"] == "weekly"]
    assert len(weekly2) == 2
    art2 = client.get(f"/api/projects/{pid}/artifacts/{weekly2[0]['path']}").json()
    assert "## 环比（vs" in art2["content"]
    assert _wait_mail(2), "second digest never sent"
    mail2 = FakeSMTP.sent[-1]
    assert "环比 vs" in mail2["body"]  # digest 的环比分期也自含

    # qa-wang 关掉 report_weekly 的 email 通道 → 第三期不发邮件，站内通知照在
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert client.put("/api/me/notification-prefs", json={
        "prefs": [{"kind": "report_weekly", "inapp": True, "email": False}]}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    nxt2 = (date.fromisoformat(sweep_today) + timedelta(days=14)).isoformat()
    assert _report_status_weekly(db.get_conn(), nxt2) == 1
    time.sleep(0.4)
    assert len(FakeSMTP.sent) == 2, "email gate failed to hold"
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    kinds = [n["kind"] for n in client.get("/api/notifications").json()["notifications"]]
    assert kinds.count("report_weekly") == 3  # in-app untouched by the email gate
