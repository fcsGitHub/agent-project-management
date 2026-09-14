"""M42-I129 velocity comparison (docs/01 §AO.2, Jira velocity chart): per
completed cycle, committed = the first non-zero scope total inside the window
(I125 commitment anchor), completed = those items first resolved within the
window; an average line runs across cycles. Mounts and resolutions are
manufactured with backdated events + real API PATCHes (I121 pattern) so live
state and replay agree. No completed cycles → honest empty."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from apm import config
from apm.core import db, projections


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "速率对比", "ontology": "software-dev", "requirement": "I129"})
    assert r.status_code == 200
    return r.json()["id"]


def _d(offset: int) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=offset)).isoformat()


def _dt(offset: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=offset)


def _mount_backdated(conn, pid, iid, cycle_id, when: datetime):
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM events").fetchone()["m"]
    conn.execute(
        "INSERT INTO events (ts, actor_type, actor_id, project_id, agg_type, agg_id,"
        " event_type, payload, prev_event_id) VALUES (?,?,?,?,?,?,?,?,?)",
        (when.isoformat(), "human", "u_admin", pid, "item", iid, "item.updated",
         json.dumps({"cycle_id": cycle_id}), row))
    conn.commit()


def _done_backdated_and_patch(client, conn, pid, iid, when: datetime):
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM events").fetchone()["m"]
    conn.execute(
        "INSERT INTO events (ts, actor_type, actor_id, project_id, agg_type, agg_id,"
        " event_type, payload, prev_event_id) VALUES (?,?,?,?,?,?,?,?,?)",
        (when.isoformat(), "human", "u_admin", pid, "item", iid, "item.status_changed",
         '{"status": "done", "status_group": "done"}', row))
    conn.commit()
    assert client.patch(f"/api/items/{iid}", json={"status": "done"}).status_code == 200


def test_velocity_per_cycle_and_average(client, tmp_data, isolated_ontologies, project):
    conn = db.get_conn()
    c1 = client.post(f"/api/projects/{project}/cycles",
                     json={"name": "Sprint 1", "start_date": _d(-12), "end_date": _d(-6)}).json()
    c2 = client.post(f"/api/projects/{project}/cycles",
                     json={"name": "Sprint 2", "start_date": _d(-5), "end_date": _d(-1)}).json()

    # Sprint 1: 3 mounted (backdated into the window), 2 resolved inside it
    s1 = []
    for i in range(3):
        it = client.post(f"/api/projects/{project}/items",
                         json={"concept_id": "task", "title": f"S1 任务{i}"}).json()
        s1.append(it["id"])
        _mount_backdated(conn, pid=project, iid=it["id"], cycle_id=c1["id"],
                         when=_dt(-11))
        assert client.patch(f"/api/items/{it['id']}",
                            json={"cycle_id": c1["id"]}).status_code == 200
    for iid in s1[:2]:
        _done_backdated_and_patch(client, conn, project, iid, _dt(-7))

    # Sprint 2: 2 mounted, 1 resolved inside it
    s2 = []
    for i in range(2):
        it = client.post(f"/api/projects/{project}/items",
                         json={"concept_id": "task", "title": f"S2 任务{i}"}).json()
        s2.append(it["id"])
        _mount_backdated(conn, pid=project, iid=it["id"], cycle_id=c2["id"],
                         when=_dt(-4))
        assert client.patch(f"/api/items/{it['id']}",
                            json={"cycle_id": c2["id"]}).status_code == 200
    _done_backdated_and_patch(client, conn, project, s2[0], _dt(-2))

    v = client.get(f"/api/projects/{project}/velocity").json()
    assert [(c["name"], c["committed"], c["completed"]) for c in v["cycles"]] == [
        ("Sprint 1", 3, 2), ("Sprint 2", 2, 1)]
    assert v["average_completed"] == 1.5

    projections.rebuild()
    v2 = client.get(f"/api/projects/{project}/velocity").json()
    v2.pop("generated_at")
    v.pop("generated_at")
    assert v2 == v


def test_no_completed_cycles_is_honest_empty(client, tmp_data, isolated_ontologies, project):
    # only a future cycle exists
    client.post(f"/api/projects/{project}/cycles",
                json={"name": "未来", "start_date": _d(1), "end_date": _d(7)})
    v = client.get(f"/api/projects/{project}/velocity").json()
    assert v["cycles"] == [] and v["average_completed"] is None
