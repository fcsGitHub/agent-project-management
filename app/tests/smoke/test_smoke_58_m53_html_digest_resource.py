"""Smoke 58 (M53): presentation & resource slice — the weekly digest mail is
multipart/alternative (HTML part with badges + CTA, plain-text floor intact)
carrying the .md attachment, and the workload endpoint exposes per-member
two-week due buckets (whole-week time-off marks a bucket grey)."""
from __future__ import annotations

import time
from datetime import date, timedelta

import pytest

from apm import config
from apm.core import db
from apm.domains import mailer


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = (config.settings.user_id, config.settings.weekly_report_day,
             config.settings.web_base_url)
    yield
    (config.settings.user_id, config.settings.weekly_report_day,
     config.settings.web_base_url) = saved


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
        html_part = msg.get_body(preferencelist=("html",))
        type(self).sent.append({
            "to": msg["To"],
            "body": part.get_content() if part else "",
            "html": html_part.get_content() if html_part else "",
            "attachments": [
                {"filename": a.get_filename()} for a in msg.iter_attachments()
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
def test_smoke_58_m53_html_digest_resource_buckets(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "冒烟呈现", "ontology": "software-dev"}).json()["id"]
    monkey_base = "http://web.local"
    config.settings.web_base_url = monkey_base
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "email": "qa@x.local"})
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "qa-wang", "role": "owner"}).status_code == 200

    # --- ① 项目数据：1 完成 + 1 超期 + 1 下周到期（徽标素材 + 资源桶素材）------
    it_done = client.post(f"/api/projects/{pid}/items",
                          json={"concept_id": "task", "title": "已完成"}).json()
    client.patch(f"/api/items/{it_done['id']}", json={"status": "done"})
    it_late = client.post(f"/api/projects/{pid}/items",
                          json={"concept_id": "task", "title": "超期项",
                                "due_date": "2026-01-05", "estimate_hours": 6}).json()
    assert it_late["id"]
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    next_week = (monday + timedelta(days=8)).isoformat()  # 下下周的周二
    it_next = client.post(f"/api/projects/{pid}/items",
                          json={"concept_id": "task", "title": "下周项",
                                "due_date": next_week, "estimate_hours": 12}).json()
    assert it_next["id"]
    client.patch(f"/api/items/{it_next['id']}",
                 json={"assignee_type": "human", "assignee_id": "qa-wang"})

    # --- ② sweep：HTML+纯文本双 part + 附件 -----------------------------------
    from apm.core import events as events_mod
    from apm.domains.automations import _report_status_weekly
    sweep_today = events_mod.utcnow()[:10]
    config.settings.weekly_report_day = date.fromisoformat(sweep_today).isoweekday()
    r = client.post("/api/automations/sweep", json={"force": True})
    assert r.status_code == 200 and r.json()["reported"] >= 1
    # sweep 同时会发 due_soon 等其它提醒邮件——按内容定位周报 digest 邮件
    mail = None
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and mail is None:
        for m in FakeSMTP.sent:
            if "完成度约" in m["body"] and m["attachments"]:
                mail = m
                break
        time.sleep(0.05)
    assert mail is not None, "digest mail never sent"

    assert mail["to"] == "qa@x.local"
    # HTML part：结论前置 + 超期红徽标 + CTA
    assert "完成度约" in mail["html"] and "超期" in mail["html"]
    assert f"{monkey_base}/#/p/{pid}/reports" in mail["html"]
    # 纯文本底线 + .md 附件共存（multipart/mixed(alternative(plain, html), file)）
    assert "完成度约" in mail["body"]
    atts = list(mail["attachments"])
    assert len(atts) == 1 and atts[0]["filename"].startswith("weekly-report-2026-W")

    # --- ③ 资源热力：qa-wang 两周桶（下周项落第二桶；久远超期项不进前向桶）----
    wl = client.get("/api/portfolio/workload").json()
    me = [m for m in wl["members"] if m["user_id"] == "qa-wang"][0]
    assert len(me["weeks"]) == 2
    b1, b2 = me["weeks"]
    assert b1["due_items"] == 0 and b1["est_hours"] == 0
    assert b2["due_items"] == 1 and b2["est_hours"] == 12
    assert b1["on_leave"] is False and b2["on_leave"] is False

    # --- ④ rebuild 后邮件事实与桶投影一致 --------------------------------------
    from apm.core import projections
    projections.ensure_handlers_registered()
    projections.rebuild()
    wl2 = client.get("/api/portfolio/workload").json()
    me2 = [m for m in wl2["members"] if m["user_id"] == "qa-wang"][0]
    assert me2["weeks"][1]["est_hours"] == 12
    evs = client.get("/api/events",
                     params={"event_type": "artifact.report_generated"}).json()["events"]
    assert any(e["payload"].get("source") == "weekly" for e in evs)
