"""M11-I35 email channel: off-by-default (no SMTP config → no behavior change),
instant per-notification emails once SMTP is configured, recipients resolved
from the same plan as the notification projection, outcomes recorded on the
event stream, and the write path never blocked by SMTP I/O."""
from __future__ import annotations

import time

import pytest

from apm import config
from apm.domains import mailer


class FakeSMTP:
    """Captures send_message calls; programmable failure and latency."""
    sent: list[dict] = []
    fail: bool = False
    stall: float = 0.0

    def __init__(self, host, port, timeout=None, ssl=False):
        pass

    def starttls(self):
        pass

    def login(self, user, passwd):
        pass

    def send_message(self, msg):
        if type(self).stall:
            time.sleep(type(self).stall)
        if type(self).fail:
            raise OSError("smtp unavailable")
        type(self).sent.append({
            "from": msg["From"], "to": msg["To"],
            "subject": msg["Subject"], "body": msg.get_content(),
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
