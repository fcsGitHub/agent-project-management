"""Smoke 17 (M11-I35): email notification channel — off by default with no SMTP
config, instant assignment mail once configured (captured by an in-process SMTP
stub), outcome recorded on the event stream, the write path never blocked by
SMTP latency, and rebuild survival of the delivery trail."""
import time

import pytest

from apm.core import projections
from apm.domains import mailer


class StubSMTP:
    sent: list[dict] = []
    stall: float = 0.0

    def __init__(self, *a, **k):
        pass

    def starttls(self, context=None):
        pass

    def login(self, *a):
        pass

    def send_message(self, msg):
        if type(self).stall:
            time.sleep(type(self).stall)
        type(self).sent.append({"to": msg["To"], "subject": msg["Subject"]})

    def quit(self):
        pass


@pytest.mark.smoke
def test_smoke_17_email_channel(client, tmp_data, isolated_ontologies, monkeypatch):
    StubSMTP.sent.clear()
    StubSMTP.stall = 0.0
    monkeypatch.setattr(mailer.smtplib, "SMTP", StubSMTP)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", StubSMTP)

    p = client.post("/api/projects",
                    json={"name": "冒烟17邮件", "ontology": "software-dev",
                          "requirement": "email"}).json()
    pid = p["id"]

    # Off by default: no SMTP config → no emails, identical behavior.
    assert mailer.smtp_configured() is False
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "email": "qa@x.local"})
    bug = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "bug", "title": "冒烟缺陷"}).json()
    time.sleep(0.3)
    assert not StubSMTP.sent

    # Configure SMTP (env layer) → assignment mails instantly.
    monkeypatch.setattr(mailer.config.settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(mailer.config.settings, "smtp_from", "agentpm@test.local")
    assert mailer.smtp_configured() is True

    # Write path must not wait on SMTP: stall the stub, expect a fast response.
    StubSMTP.stall = 2.0
    t0 = time.monotonic()
    client.patch(f"/api/items/{bug['id']}",
                 json={"assignee_type": "human", "assignee_id": "qa-wang"})
    write_elapsed = time.monotonic() - t0
    assert write_elapsed < 1.0, f"write blocked on SMTP ({write_elapsed:.2f}s)"

    for _ in range(120):
        if StubSMTP.sent:
            break
        time.sleep(0.05)
    StubSMTP.stall = 0.0
    assert StubSMTP.sent, "mail never sent"
    assert StubSMTP.sent[0]["to"] == "qa@x.local"
    assert "冒烟缺陷" in StubSMTP.sent[0]["subject"]

    # Outcome recorded on the event stream.
    for _ in range(120):
        evs = client.get("/api/events", params={"event_type": "email.notified"}).json()["events"]
        if evs:
            break
        time.sleep(0.05)
    assert evs and evs[0]["payload"]["to"] == "qa@x.local"
    assert evs[0]["payload"]["source_event_id"] > 0

    # Rebuild: the delivery trail lives in the event log — it survives.
    projections.rebuild()
    assert client.get("/api/events",
                      params={"event_type": "email.notified"}).json()["events"]

    # Atom feed (M11-I36): key-authenticated, member-visible, well-formed.
    import xml.etree.ElementTree as ET
    key = client.get("/api/me/feed-key").json()["feed_key"]
    r = client.get(f"/api/projects/{pid}/feed.atom", params={"key": key})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/atom+xml")
    root = ET.fromstring(r.text)
    assert root.tag.endswith("feed")
    # Rotating the key kills the old one.
    new_key = client.post("/api/me/feed-key/rotate").json()["feed_key"]
    assert client.get(f"/api/projects/{pid}/feed.atom",
                      params={"key": key}).status_code == 401
    assert client.get(f"/api/projects/{pid}/feed.atom",
                      params={"key": new_key}).status_code == 200
