"""I96 per-kind notification preferences (docs/01 §AD.2, GitLab Custom level):
delivery gates live at the delivery path — in-app gate in _notify, email gate in
mailer.enqueue — mention is always deliverable, missing rows default to on, and
prefs are runtime state that survives rebuilds (not in drop_projections)."""
from __future__ import annotations

import time

import pytest

from apm import config
from apm.core import db, projections
from apm.domains import mailer


@pytest.fixture(autouse=True)
def _restore_identity():
    """/api/session/identity mutates settings.user_id globally; restore it."""
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


class FakeSMTP:
    sent: list[dict] = []

    def __init__(self, host, port, timeout=None, ssl=False):
        pass

    def starttls(self):
        pass

    def login(self, user, passwd):
        pass

    def send_message(self, msg):
        type(self).sent.append({"to": msg["To"], "subject": msg["Subject"]})

    def quit(self):
        pass


@pytest.fixture(autouse=True)
def smtp_stub(monkeypatch):
    FakeSMTP.sent.clear()
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", FakeSMTP)


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "偏好演示", "ontology": "software-dev", "requirement": "I96"})
    assert r.status_code == 200
    return r.json()


def _assign(client, pid: str, title: str, assignee: str = "qa-wang") -> None:
    bug = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "bug", "title": title}).json()
    assert client.patch(f"/api/items/{bug['id']}",
                        json={"assignee_type": "human", "assignee_id": assignee}).status_code == 200


def _assigned_count(client) -> int:
    out = client.get("/api/notifications").json()
    return [n["kind"] for n in out["notifications"]].count("assigned")


def test_matrix_shape_defaults_all_on(client, tmp_data, isolated_ontologies, project):
    body = client.get("/api/me/notification-prefs").json()
    assert body["email_enabled"] is True
    kinds = {k["kind"]: k for k in body["kinds"]}
    # I126 joins approval_reminder as the seventh kind
    assert set(kinds) == {"assigned", "approval", "comment", "item", "mention",
                          "due_soon", "approval_reminder"}
    assert all(k["inapp"] and k["email"] for k in kinds.values())


def test_inapp_gate_blocks_new_notifications(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    _assign(client, pid, "闸门前一项")
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert _assigned_count(client) == 1

    # qa-wang turns off in-app "assigned" (own-data preference)
    assert client.put("/api/me/notification-prefs", json={
        "prefs": [{"kind": "assigned", "inapp": False, "email": True}]}).status_code == 200

    client.post("/api/session/identity", json={"user_id": "u_admin"})
    _assign(client, pid, "闸门后一项")
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert _assigned_count(client) == 1  # the gated assignment stays silent


def test_mention_cannot_be_turned_off_via_api(client, tmp_data, isolated_ontologies, project):
    assert client.put("/api/me/notification-prefs", json={
        "prefs": [{"kind": "mention", "inapp": False, "email": True}]}).status_code == 422
    assert client.put("/api/me/notification-prefs", json={
        "prefs": [{"kind": "nope", "inapp": False, "email": True}]}).status_code == 422


def test_mention_delivered_even_if_row_forced_off(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    # force an off-row past the API (raw insert) — the gate must still deliver
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO notification_prefs (user_id, kind, inapp, email, updated_at)"
        " VALUES ('qa-wang','mention',0,0,'2026-09-05T00:00:00')")
    conn.commit()

    bug = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "bug", "title": "提及对象"}).json()
    assert client.post(f"/api/items/{bug['id']}/comments",
                       json={"body": "@QA 王 请看这条"}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    out = client.get("/api/notifications").json()
    assert "mention" in [n["kind"] for n in out["notifications"]]


def test_email_gate_blocks_mail(client, tmp_data, isolated_ontologies, project, monkeypatch):
    monkeypatch.setattr(config.settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(config.settings, "smtp_from", "agentpm@test.local")
    monkeypatch.setattr(config.settings, "smtp_port", 587)
    pid = project["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "email": "qa@x.local"})
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert client.put("/api/me/notification-prefs", json={
        "prefs": [{"kind": "assigned", "inapp": True, "email": False}]}).status_code == 200

    client.post("/api/session/identity", json={"user_id": "u_admin"})
    _assign(client, pid, "邮件应被闸住")
    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline and not FakeSMTP.sent:
        time.sleep(0.05)
    assert not FakeSMTP.sent  # per-kind email gate held


def test_rebuild_keeps_prefs_and_replays_gate(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    _assign(client, pid, "rebuild 前一项")
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert client.put("/api/me/notification-prefs", json={
        "prefs": [{"kind": "assigned", "inapp": False, "email": True}]}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    _assign(client, pid, "rebuild 前二项")

    projections.rebuild()

    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    # The gate lives at the delivery path, and replay IS re-delivery: rebuild
    # re-evaluates every historical assignment against the *current* pref, so
    # even the pre-gate notification stays hidden. live==replay by construction.
    assert _assigned_count(client) == 0
    body = client.get("/api/me/notification-prefs").json()
    assigned = next(k for k in body["kinds"] if k["kind"] == "assigned")
    assert assigned["inapp"] is False  # runtime pref survives rebuild
