"""I105 due-date reminders (docs/01 §AG.2, Plane/Linear semantics): the daily
sweep's built-in reminder emits one item.due_soon_notified per item per day
(idempotent via the event stream), the human assignee is the recipient, and
both delivery channels gate it as kind "due_soon" (defaults on, turnable)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from apm import config
from apm.core import db, events, projections


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "提醒演示", "ontology": "software-dev", "requirement": "I105"})
    assert r.status_code == 200
    return r.json()


def _today() -> str:
    return events.utcnow()[:10]


def _mkitem(client, pid: str, title: str, due: str, assignee: str | None = "qa-wang",
            status: str | None = None) -> str:
    item = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": title, "due_date": due}).json()
    if assignee:
        assert client.patch(f"/api/items/{item['id']}",
                            json={"assignee_type": "human", "assignee_id": assignee}).status_code == 200
    if status:
        assert client.patch(f"/api/items/{item['id']}", json={"status": status}).status_code == 200
    return item["id"]


def test_window_boundaries_and_daily_idempotency(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    today = _today()
    in_window = [today,                                 # due today
                 (date.fromisoformat(today) + timedelta(days=3)).isoformat()]
    outside = (date.fromisoformat(today) + timedelta(days=4)).isoformat()  # beyond N=3
    due_id = _mkitem(client, pid, "窗口内今天", in_window[0])
    edge_id = _mkitem(client, pid, "窗口边界+3", in_window[1])
    _mkitem(client, pid, "窗口外+4", outside)
    _mkitem(client, pid, "无负责人", today, assignee=None)
    _mkitem(client, pid, "已完成", today, status="done")

    r = client.post("/api/automations/sweep", json={})
    assert r.status_code == 200, r.text
    assert r.json()["notified"] == 2
    evs = [e for e in client.get("/api/events", params={
        "event_type": "item.due_soon_notified"}).json()["events"]]
    assert {e["agg_id"] for e in evs} == {due_id, edge_id}
    assert all(e["payload"]["assignee_id"] == "qa-wang" for e in evs)

    # assignee's in-app bell got the due_soon notifications
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    kinds = [n["kind"] for n in client.get("/api/notifications").json()["notifications"]]
    assert kinds.count("due_soon") == 2
    client.post("/api/session/identity", json={"user_id": "u_admin"})

    # a forced re-sweep the same day never duplicates (event-stream idempotency)
    r2 = client.post("/api/automations/sweep", json={"force": True})
    assert r2.json()["notified"] == 0


def test_pref_gate_blocks_delivery_not_the_event(client, tmp_data, isolated_ontologies, project):
    from apm.domains.notifications import pref_allows

    pid = project["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    # qa-wang turns off due_soon on both channels before the sweep
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert client.put("/api/me/notification-prefs", json={
        "prefs": [{"kind": "due_soon", "inapp": False, "email": False}]}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "u_admin"})

    _mkitem(client, pid, "被闸的提醒", _today())
    r = client.post("/api/automations/sweep", json={})
    assert r.json()["notified"] == 1  # the fact is evented either way

    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    kinds = [n["kind"] for n in client.get("/api/notifications").json()["notifications"]]
    assert "due_soon" not in kinds  # in-app gate held
    conn = db.get_conn()
    assert pref_allows(conn, "qa-wang", "due_soon", "inapp") is False
    assert pref_allows(conn, "qa-wang", "due_soon", "email") is False


def test_rebuild_replays_id_and_keeps_idempotency(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    _mkitem(client, pid, "重建存活提醒", _today())
    assert client.post("/api/automations/sweep", json={}).json()["notified"] == 1

    projections.rebuild()
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    notes = [n for n in client.get("/api/notifications").json()["notifications"]
             if n["kind"] == "due_soon"]
    assert len(notes) == 1  # deterministic id, replayed exactly once

    client.post("/api/session/identity", json={"user_id": "u_admin"})
    assert client.post("/api/automations/sweep",
                       json={"force": True}).json()["notified"] == 0  # still idempotent
