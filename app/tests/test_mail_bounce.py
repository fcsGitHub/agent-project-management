"""I120 bounce suppression and inbound filters (docs/01 §AL.2, Jira
suppression-list semantics): a delivery failure from MAILER-DAEMON/POSTMASTER
flips the failed recipient's email channel off (in-app notifications are
untouched; the user re-enables via the regular email toggle), unknown
recipients are honest no-ops, and comma-separated ignore addresses/keywords
silently drop inbound noise — all with an imap.message_processed audit trail
that survives rebuild."""
from __future__ import annotations

import pytest

from apm import config
from apm.core import db, projections
from apm.domains import imap_in


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def imap_env(monkeypatch):
    monkeypatch.setattr(config.settings, "imap_host", "imap.example.com")
    monkeypatch.setattr(config.settings, "imap_user", "inbox@example.com")
    monkeypatch.setattr(config.settings, "imap_pass", "secret")


def _stub(monkeypatch, *messages):
    monkeypatch.setattr(imap_in, "_fetch_messages", lambda: list(messages))


def _notify_flag(user_id: str) -> int:
    return db.get_conn().execute(
        "SELECT email_notify FROM users WHERE id = ?", (user_id,)).fetchone()["email_notify"]


def _routed(message_id: str) -> str:
    return db.get_conn().execute(
        "SELECT routed FROM imap_seen WHERE message_id = ?", (message_id,)).fetchone()["routed"]


def test_bounce_suppresses_then_resume(client, tmp_data, isolated_ontologies, imap_env, monkeypatch):
    pid = client.post("/api/projects",
                      json={"name": "退信演示", "ontology": "software-dev",
                            "requirement": "I120"}).json()["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "email": "qa@x.com"})
    assert _notify_flag("qa-wang") == 1

    _stub(monkeypatch, {
        "message_id": "<bounce-1@x.com>", "from": "MAILER-DAEMON@yahoo.com (Mail Delivery System)",
        "subject": "Undelivered Mail Returned to Sender", "body": "qa@x.com failed permanently",
        "in_reply_to": "", "references": "", "x_failed_recipients": "qa@x.com",
    })
    assert imap_in.poll_inbox()["processed"] == 1
    assert _notify_flag("qa-wang") == 0            # email channel off…
    assert _routed("<bounce-1@x.com>") == "suppress"
    # …in-app notifications untouched: qa-wang still gets assigned in-app rows
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "站内通知不受影响"}).json()
    client.patch(f"/api/items/{it['id']}",
                 json={"assignee_type": "human", "assignee_id": "qa-wang"})
    n = db.get_conn().execute(
        "SELECT COUNT(*) AS c FROM notifications WHERE user_id = 'qa-wang'").fetchone()["c"]
    assert n >= 1

    # the user re-enables via the regular runtime toggle
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert client.post("/api/notifications/prefs",
                       json={"email_enabled": True}).status_code == 200
    assert _notify_flag("qa-wang") == 1

    # audit trail survives rebuild
    projections.rebuild()
    assert _routed("<bounce-1@x.com>") == "suppress"


def test_bounce_edge_cases(client, tmp_data, isolated_ontologies, imap_env, monkeypatch):
    client.post("/api/projects",
                json={"name": "退信边界", "ontology": "software-dev", "requirement": "I120"})
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "email": "qa@x.com"})

    # unknown recipient → honest no-op (routed=bounce), nobody suppressed
    _stub(monkeypatch, {
        "message_id": "<bounce-2@x.com>", "from": "postmaster@ elsewhere.example",
        "subject": "Delivery Status Notification", "body": "stranger@nowhere.com failed",
        "in_reply_to": "", "references": "", "x_failed_recipients": "",
    })
    imap_in.poll_inbox()
    assert _routed("<bounce-2@x.com>") == "bounce"
    assert _notify_flag("qa-wang") == 1

    # body-quoted recipient (no header) suppresses; the mailbox's own address
    # is never picked as the victim
    _stub(monkeypatch, {
        "message_id": "<bounce-3@x.com>", "from": "mailer-daemon@example.com",
        "subject": "Returned mail", "body": "inbox@example.com failed; qa@x.com failed too",
        "in_reply_to": "", "references": "", "x_failed_recipients": "",
    })
    imap_in.poll_inbox()
    assert _routed("<bounce-3@x.com>") == "suppress"
    assert _notify_flag("qa-wang") == 0

    # already-off → second bounce is a no-op with routed=bounce
    _stub(monkeypatch, {
        "message_id": "<bounce-4@x.com>", "from": "mailer-daemon@example.com",
        "subject": "Returned mail", "body": "qa@x.com failed",
        "in_reply_to": "", "references": "", "x_failed_recipients": "",
    })
    imap_in.poll_inbox()
    assert _routed("<bounce-4@x.com>") == "bounce"


def test_ignore_filters(client, tmp_data, isolated_ontologies, imap_env, monkeypatch):
    pid = client.post("/api/projects",
                      json={"name": "过滤演示", "ontology": "software-dev",
                            "requirement": "I120"}).json()["id"]
    monkeypatch.setattr(config.settings, "imap_ignore_addresses", "spam@x.com, @junk.io")
    monkeypatch.setattr(config.settings, "imap_ignore_keywords", "促销,unsubscribe")

    # exact address hit / @domain suffix hit / keyword hit (case-insensitive) /
    # a normal mail that must remain untouched
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "email": "qa@x.com"})
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200
    _stub(monkeypatch,
          {"message_id": "<m1@x.com>", "from": "Spam <spam@x.com>",
           "subject": "hello", "body": "buy", "in_reply_to": "",
           "references": "", "x_failed_recipients": ""},
          {"message_id": "<m2@junk.io>", "from": "a@junk.io",
           "subject": "hello", "body": "", "in_reply_to": "",
           "references": "", "x_failed_recipients": ""},
          {"message_id": "<m3@x.com>", "from": "shop@x.com",
           "subject": "Best UNSUBSCRIBE offers", "body": "",
           "in_reply_to": "", "references": "", "x_failed_recipients": ""},
          {"message_id": "<m4@x.com>", "from": "qa@x.com",
           "subject": "[过滤演示] 正常来信", "body": "", "in_reply_to": "",
           "references": "", "x_failed_recipients": ""})
    assert imap_in.poll_inbox()["processed"] == 4
    assert _routed("<m1@x.com>").startswith("ignored")
    assert _routed("<m2@junk.io>").startswith("ignored")
    assert _routed("<m3@x.com>").startswith("ignored")
    assert _routed("<m4@x.com>") == "user"  # normal routing unaffected
    items = client.get(f"/api/projects/{pid}/items").json()["items"]
    assert [i["title"] for i in items] == ["正常来信"]
