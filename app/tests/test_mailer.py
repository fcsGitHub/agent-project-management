"""M11-I35 email channel: off-by-default (no SMTP config → no behavior change),
instant per-notification emails once SMTP is configured, recipients resolved
from the same plan as the notification projection, outcomes recorded on the
event stream, and the write path never blocked by SMTP I/O."""
from __future__ import annotations

import time

import pytest

from apm import config
from apm.domains import mailer


@pytest.fixture(autouse=True)
def _restore_identity():
    """/api/session/identity mutates settings.user_id globally; restore it so a
    leaked identity can't re-shape the next test's default admin user (the app
    boot would register that identity WITHOUT an email, breaking mail asserts)."""
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


class FakeSMTP:
    """Captures send_message calls; programmable failure and latency."""
    sent: list[dict] = []
    fail: bool = False
    stall: float = 0.0

    def __init__(self, host, port, timeout=None, ssl=False, context=None):
        pass

    def starttls(self, context=None):
        pass

    def login(self, user, passwd):
        pass

    def send_message(self, msg):
        if type(self).stall:
            time.sleep(type(self).stall)
        if type(self).fail:
            raise OSError("smtp unavailable")
        part = msg.get_body(preferencelist=("plain",))
        type(self).sent.append({
            "from": msg["From"], "to": msg["To"],
            "subject": msg["Subject"], "body": part.get_content() if part else "",
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
    FakeSMTP.fail = False
    FakeSMTP.stall = 0.0
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", FakeSMTP)
    yield


def _configure(monkeypatch):
    monkeypatch.setattr(config.settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(config.settings, "smtp_from", "agentpm@test.local")
    monkeypatch.setattr(config.settings, "smtp_port", 587)


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "邮件演示", "ontology": "software-dev", "requirement": "I35"})
    assert r.status_code == 200
    return r.json()


def _wait_mail(n=1, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(FakeSMTP.sent) >= n:
            return True
        time.sleep(0.05)
    return False


def test_off_by_default(client, tmp_data, isolated_ontologies, project):
    # Default settings: no SMTP config → assignment produces no email activity.
    assert mailer.smtp_configured() is False
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "email": "qa@x.local"})
    client.post(f"/api/projects/{project['id']}/items",
                json={"concept_id": "bug", "title": "t"})
    time.sleep(0.3)
    assert not FakeSMTP.sent
    evs = client.get("/api/events", params={"event_type": "email.notified"}).json()["events"]
    assert evs == []


def test_instant_email_on_assignment(client, tmp_data, isolated_ontologies, project, monkeypatch):
    _configure(monkeypatch)
    pid = project["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "email": "qa@x.local"})
    bug = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "bug", "title": "邮件指派"}).json()
    assert client.patch(f"/api/items/{bug['id']}",
                        json={"assignee_type": "human", "assignee_id": "qa-wang"}).status_code == 200

    assert _wait_mail(1), "mail never sent"
    mail = FakeSMTP.sent[-1]
    assert mail["to"] == "qa@x.local" and mail["from"] == "agentpm@test.local"
    assert "邮件指派" in mail["subject"]

    for _ in range(100):
        evs = client.get("/api/events", params={"event_type": "email.notified"}).json()["events"]
        if evs:
            break
        time.sleep(0.05)
    assert evs and evs[0]["payload"]["to"] == "qa@x.local"
    assert evs[0]["payload"]["summary"].startswith("被指派工作项")


def test_user_without_email_skipped(client, tmp_data, isolated_ontologies, project, monkeypatch):
    _configure(monkeypatch)
    pid = project["id"]
    client.post("/api/users", json={"id": "no-mail", "name": "无邮箱"})
    bug = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "bug", "title": "b"}).json()
    client.patch(f"/api/items/{bug['id']}",
                 json={"assignee_type": "human", "assignee_id": "no-mail"})
    time.sleep(0.4)
    assert not FakeSMTP.sent
    assert client.get("/api/events", params={"event_type": "email.notified"}).json()["events"] == []


def test_smtp_failure_recorded(client, tmp_data, isolated_ontologies, project, monkeypatch):
    _configure(monkeypatch)
    FakeSMTP.fail = True
    pid = project["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "email": "qa@x.local"})
    bug = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "bug", "title": "必然失败"}).json()
    client.patch(f"/api/items/{bug['id']}",
                 json={"assignee_type": "human", "assignee_id": "qa-wang"})
    for _ in range(100):
        evs = client.get("/api/events", params={"event_type": "email.failed"}).json()["events"]
        if evs:
            break
        time.sleep(0.05)
    assert evs and "smtp unavailable" in evs[0]["payload"]["detail"]


def test_email_pref_toggle_stops_mail_but_not_notifications(client, tmp_data, isolated_ontologies, project, monkeypatch):
    _configure(monkeypatch)
    pid = project["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "email": "qa@x.local"})
    bug = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "bug", "title": "开关前"}).json()
    client.patch(f"/api/items/{bug['id']}",
                 json={"assignee_type": "human", "assignee_id": "qa-wang"})
    assert _wait_mail(1), "mail before toggle"

    # Toggle off (as the affected user) → mails stop, in-app notifications stay.
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert client.get("/api/notifications").json()["email_enabled"] is True
    client.post("/api/notifications/prefs", json={"email_enabled": False})
    assert client.get("/api/notifications").json()["email_enabled"] is False

    bug2 = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "bug", "title": "开关后"}).json()
    client.patch(f"/api/items/{bug2['id']}",
                 json={"assignee_type": "human", "assignee_id": "qa-wang"})
    time.sleep(0.4)
    assert len(FakeSMTP.sent) == 1, "no mail after opting out"
    notes = client.get("/api/notifications").json()
    assert notes["unread"] == 2  # in-app flow unaffected
    assert notes["email_enabled"] is False


def test_write_not_blocked_by_slow_smtp(client, tmp_data, isolated_ontologies, project, monkeypatch):
    _configure(monkeypatch)
    FakeSMTP.stall = 2.0
    pid = project["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "email": "qa@x.local"})
    bug = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "bug", "title": "慢邮件"}).json()
    t0 = time.monotonic()
    client.patch(f"/api/items/{bug['id']}",
                 json={"assignee_type": "human", "assignee_id": "qa-wang"})
    elapsed = time.monotonic() - t0
    assert elapsed < 1.0, f"write blocked on SMTP ({elapsed:.2f}s)"
    assert _wait_mail(1, timeout=5.0), "stalled mail eventually sent"


def test_weekly_report_digest_body(client, tmp_data, isolated_ontologies, project, monkeypatch):
    """M51-I154: report_weekly mail carries the self-contained digest body
    (conclusions inline, artifact path as evidence); non-weekly mails keep
    the plain one-line format."""
    _configure(monkeypatch)
    pid = project["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "email": "qa@x.local"})
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "qa-wang", "role": "owner"}).status_code == 200
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "周报任务"}).json()
    client.post(f"/api/items/{it['id']}/comments", json={"body": "进展评论"})
    from apm.core import db
    from apm.domains.automations import _report_status_weekly
    assert _report_status_weekly(db.get_conn(), "2026-09-21") == 1

    assert _wait_mail(1), "digest mail never sent"
    mail = FakeSMTP.sent[-1]
    assert mail["to"] == "qa@x.local" and "周报" in mail["subject"]
    assert "完成度约" in mail["body"] and "开放风险" in mail["body"]
    assert "首期周报" in mail["body"]
    assert "artifacts/reports/status-" in mail["body"]

    # 非周报事件：邮件仍是原单行格式（digest 透传对既有邮件零影响）
    bug = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "bug", "title": "单行邮件"}).json()
    client.patch(f"/api/items/{bug['id']}",
                 json={"assignee_type": "human", "assignee_id": "qa-wang"})
    assert _wait_mail(2)
    plain = FakeSMTP.sent[-1]
    assert "kind: assigned" in plain["body"]


def test_weekly_report_attachment(client, tmp_data, isolated_ontologies, project, monkeypatch):
    """M52-I156: the weekly digest mail carries the report .md as an
    attachment (filename with ISO week key, content = the git blob); the
    non-weekly mail stays attachment-free."""
    _configure(monkeypatch)
    pid = project["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "email": "qa@x.local"})
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "qa-wang", "role": "owner"}).status_code == 200
    from apm.core import db
    from apm.domains.automations import _report_status_weekly
    assert _report_status_weekly(db.get_conn(), "2026-09-21") == 1
    assert _wait_mail(1), "digest mail never sent"
    mail = FakeSMTP.sent[-1]
    atts = list(mail["attachments"])
    assert len(atts) == 1
    assert atts[0]["filename"] == "weekly-report-2026-W39.md"
    assert "## 总体健康" in atts[0]["content"]

    # 对照：非周报邮件无附件
    bug = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "bug", "title": "无附件邮件"}).json()
    client.patch(f"/api/items/{bug['id']}",
                 json={"assignee_type": "human", "assignee_id": "qa-wang"})
    assert _wait_mail(2)
    assert not list(FakeSMTP.sent[-1]["attachments"])


def test_weekly_report_attachment_missing_degrades(client, tmp_data, isolated_ontologies, project, monkeypatch):
    """git 内容读取失败 → 邮件降级为仅 digest 正文，发送不失败。"""
    _configure(monkeypatch)
    pid = project["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "email": "qa@x.local"})
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "qa-wang", "role": "owner"}).status_code == 200
    # 工件读取在 _send 内走 gitrepo.read_file——让它抛错（写路径不受影响：
    # write_file 不经过 read_file）
    from apm.content import gitrepo as gitrepo_mod

    def _boom(*a, **k):
        raise FileNotFoundError("gone")

    monkeypatch.setattr(gitrepo_mod, "read_file", _boom)
    from apm.core import db
    from apm.domains.automations import _report_status_weekly
    assert _report_status_weekly(db.get_conn(), "2026-09-21") == 1
    assert _wait_mail(1), "digest mail never sent"
    mail = FakeSMTP.sent[-1]
    assert not list(mail["attachments"])  # 附件缺失降级
    assert "完成度约" in mail["body"]      # 正文自含结论照常
