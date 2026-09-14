"""I119 project cycles (docs/01 §AL.1, Plane Cycles / OpenProject 17.3
sprint-version split): an iteration is a date-boxed container orthogonal to
milestones. Minimal face — evented cycle CRUD with overlap refusal, items
mount by cycle_id (project-scoped validation), and the daily sweep explicitly
carries a finished cycle's unfinished items into the next cycle via
cycle.carried_over, ownership-only (start/due untouched); rebuild replays."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from apm import config
from apm.core import db, projections
from apm.domains import cycles


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "迭代演示", "ontology": "software-dev", "requirement": "I119"})
    assert r.status_code == 200
    return r.json()["id"]


def _d(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def test_cycle_crud_validation_and_rebuild(client, tmp_data, isolated_ontologies, project):
    r = client.post(f"/api/projects/{project}/cycles",
                    json={"name": "Sprint 1", "start_date": _d(-14), "end_date": _d(-1)})
    assert r.status_code == 200, r.text
    c1 = r.json()
    # overlapping (touching and contained) is refused — 409
    for s, e in ((_d(-20), _d(-10)), (_d(-10), _d(0)), (_d(-14), _d(-1))):
        resp = client.post(f"/api/projects/{project}/cycles",
                           json={"name": "重叠", "start_date": s, "end_date": e})
        assert resp.status_code == 409, (s, e, resp.text)
    assert client.post(f"/api/projects/{project}/cycles",
                       json={"name": "倒序", "start_date": _d(5), "end_date": _d(1)}).status_code == 422
    assert client.post(f"/api/projects/{project}/cycles",
                       json={"name": "坏日期", "start_date": "x", "end_date": _d(1)}).status_code == 422
    # next cycle, no overlap
    c2 = client.post(f"/api/projects/{project}/cycles",
                     json={"name": "Sprint 2", "start_date": _d(0), "end_date": _d(13)}).json()

    r = client.patch(f"/api/cycles/{c1['id']}", json={"name": "Sprint 1（顺延）"})
    assert r.status_code == 200 and r.json()["name"] == "Sprint 1（顺延）"

    rows = client.get(f"/api/projects/{project}/cycles").json()["cycles"]
    assert [c["name"] for c in rows] == ["Sprint 1（顺延）", "Sprint 2"]

    projections.rebuild()
    rows = client.get(f"/api/projects/{project}/cycles").json()["cycles"]
    assert [c["id"] for c in rows] == [c1["id"], c2["id"]]  # projection survives replay

    assert client.delete(f"/api/cycles/{c2['id']}").status_code == 200
    assert client.patch(f"/api/cycles/{c2['id']}", json={"name": "x"}).status_code == 404
    rows = client.get(f"/api/projects/{project}/cycles").json()["cycles"]
    assert [c["id"] for c in rows] == [c1["id"]]


def test_item_mount_and_board_filter(client, tmp_data, isolated_ontologies, project):
    c1 = client.post(f"/api/projects/{project}/cycles",
                     json={"name": "Sprint 1", "start_date": _d(-7), "end_date": _d(7)}).json()
    other = client.post("/api/projects",
                        json={"name": "别的项目", "ontology": "software-dev", "requirement": "I119"}).json()["id"]
    c_other = client.post(f"/api/projects/{other}/cycles",
                          json={"name": "别家周期", "start_date": _d(0), "end_date": _d(5)}).json()

    it1 = client.post(f"/api/projects/{project}/items",
                      json={"concept_id": "task", "title": "周期内任务"}).json()
    it2 = client.post(f"/api/projects/{project}/items",
                      json={"concept_id": "task", "title": "周期外任务"}).json()
    # cross-project cycle refused
    assert client.patch(f"/api/items/{it1['id']}",
                        json={"cycle_id": c_other["id"]}).status_code == 422
    # unknown cycle refused
    assert client.patch(f"/api/items/{it1['id']}",
                        json={"cycle_id": "cy_nope"}).status_code == 404
    assert client.patch(f"/api/items/{it1['id']}",
                        json={"cycle_id": c1["id"]}).status_code == 200

    items = client.get(f"/api/projects/{project}/items", params={"cycle": c1["id"]}).json()["items"]
    assert [i["title"] for i in items] == ["周期内任务"]
    board = client.get(f"/api/projects/{project}/board", params={"cycle": c1["id"]}).json()
    on_board = [i["title"] for b in board["buckets"] for i in b["items"]]
    assert on_board == ["周期内任务"]  # board honors the cycle filter

    projections.rebuild()
    items = client.get(f"/api/projects/{project}/items", params={"cycle": c1["id"]}).json()["items"]
    assert [i["title"] for i in items] == ["周期内任务"]  # mount survives replay


def test_sweep_carries_unfinished_into_next_cycle(client, tmp_data, isolated_ontologies, project):
    c1 = client.post(f"/api/projects/{project}/cycles",
                     json={"name": "Sprint 1", "start_date": _d(-14), "end_date": _d(-1)}).json()
    c2 = client.post(f"/api/projects/{project}/cycles",
                     json={"name": "Sprint 2", "start_date": _d(0), "end_date": _d(13)}).json()
    open1 = client.post(f"/api/projects/{project}/items",
                        json={"concept_id": "task", "title": "未完成一"}).json()
    done1 = client.post(f"/api/projects/{project}/items",
                        json={"concept_id": "task", "title": "已完成一"}).json()
    for it, status in ((open1, None), (done1, "done")):
        assert client.patch(f"/api/items/{it['id']}", json={"cycle_id": c1["id"]}).status_code == 200
        if status:
            assert client.patch(f"/api/items/{it['id']}", json={"status": status}).status_code == 200
    # a dated item proves carryover never touches schedule fields
    assert client.patch(f"/api/items/{open1['id']}",
                        json={"due_date": _d(3)}).status_code == 200

    moved = cycles.carryover_finished_cycles(db.get_conn(), _d(0))
    assert moved == 1
    row = db.get_conn().execute(
        "SELECT cycle_id, due_date FROM items WHERE id = ?", (open1["id"],)).fetchone()
    assert row["cycle_id"] == c2["id"] and row["due_date"] == _d(3)
    done_row = db.get_conn().execute(
        "SELECT cycle_id FROM items WHERE id = ?", (done1["id"],)).fetchone()
    assert done_row["cycle_id"] == c1["id"]  # finished work stays in its cycle
    ev = db.get_conn().execute(
        "SELECT payload FROM events WHERE event_type = 'cycle.carried_over'"
        " AND agg_id = ?", (c1["id"],)).fetchone()
    import json
    p = json.loads(ev["payload"])
    assert p["from_cycle"] == c1["id"] and p["to_cycle"] == c2["id"] and p["count"] == 1

    # idempotent via the carried_over fact
    assert cycles.carryover_finished_cycles(db.get_conn(), _d(0)) == 0


def test_no_next_cycle_is_honest_noop(client, tmp_data, isolated_ontologies, project):
    c1 = client.post(f"/api/projects/{project}/cycles",
                     json={"name": "孤周期", "start_date": _d(-10), "end_date": _d(-1)}).json()
    it = client.post(f"/api/projects/{project}/items",
                     json={"concept_id": "task", "title": "无处可去"}).json()
    assert client.patch(f"/api/items/{it['id']}",
                        json={"cycle_id": c1["id"]}).status_code == 200
    assert cycles.carryover_finished_cycles(db.get_conn(), _d(0)) == 0
    assert db.get_conn().execute(
        "SELECT cycle_id FROM items WHERE id = ?", (it["id"],)).fetchone()["cycle_id"] == c1["id"]
