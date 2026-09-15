"""M43-I133 completion-driven respawn (docs/01 §AP.3, YouTrack reset
workflow): a task with recurrence_days=N respawns as a fresh copy N days
after its done first-arrival — completion-driven cadence, not calendar. The
respawn reuses create_item's validation chain, keeps assignee/cycle/the
recurrence itself, records an item.respawned fact for idempotency, and the
audit chain (respawn_of) is queryable. Pure event machinery — rebuild-safe."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from apm import config
from apm.core import db, projections
from apm.domains import automations


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "重建演示", "ontology": "software-dev", "requirement": "I133"})
    assert r.status_code == 200
    return r.json()["id"]


def _backdate_done(iid: str, days_ago: int):
    conn = db.get_conn()
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM events").fetchone()["m"]
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    conn.execute(
        "INSERT INTO events (ts, actor_type, actor_id, project_id, agg_type, agg_id,"
        " event_type, payload, prev_event_id) VALUES (?,?,?,?,?,?,?,?,?)",
        (when.isoformat(), "human", "u_admin", "p", iid, "item.status_changed",
         '{"status": "done", "status_group": "done"}', row))
    conn.commit()


def _utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def test_respawn_after_recurrence_window(client, pid, tmp_data, isolated_ontologies):
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "周会"}).json()["id"]
    assert client.patch(f"/api/items/{it}",
                        json={"recurrence_days": 7}).status_code == 200
    assert client.patch(f"/api/items/{it}", json={"status": "done"}).status_code == 200

    # done today, window is 7 days → nothing yet
    assert automations._respawn_recurring(db.get_conn(), _utc_today()) == 0

    # backdate the done first-arrival 7 days back → window reached
    conn = db.get_conn()
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM events").fetchone()["m"]
    when = datetime.now(timezone.utc) - timedelta(days=7)
    conn.execute(
        "INSERT INTO events (ts, actor_type, actor_id, project_id, agg_type, agg_id,"
        " event_type, payload, prev_event_id) VALUES (?,?,?,?,?,?,?,?,?)",
        (when.isoformat(), "human", "u_admin", pid, "item", it, "item.status_changed",
         '{"status": "done", "status_group": "done"}', row))
    conn.commit()

    spawned = automations._respawn_recurring(conn, _utc_today())
    assert spawned == 1
    items = client.get(f"/api/projects/{pid}/items").json()["items"]
    respawned = [i for i in items if i["title"] == "周会" and i["id"] != it]
    assert len(respawned) == 1 and respawned[0]["status"] == "open"
    # the recurrence continues on the new card
    assert respawned[0]["recurrence_days"] == 7

    # audit chain: respawn_of points back to the original
    ev = conn.execute(
        "SELECT payload FROM events WHERE event_type = 'item.respawned'").fetchone()
    import json
    assert json.loads(ev["payload"])["respawn_of"] == it

    # idempotent: the respawned fact blocks a second spawn of the same source
    assert automations._respawn_recurring(conn, _utc_today()) == 0

    projections.rebuild()
    items = client.get(f"/api/projects/{pid}/items").json()["items"]
    assert len([i for i in items if i["title"] == "周会"]) == 2


def test_open_task_never_respawns(client, pid, tmp_data, isolated_ontologies):
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "还开着"}).json()["id"]
    assert client.patch(f"/api/items/{it}", json={"recurrence_days": 3}).status_code == 200
    assert automations._respawn_recurring(db.get_conn(), _utc_today()) == 0
    items = client.get(f"/api/projects/{pid}/items").json()["items"]
    assert len(items) == 1
