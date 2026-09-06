"""I111 personal time-off (docs/01 §AI.2, Taiga capacity-pain / Jira PTO
semantics): a time-off stretch is an evented date range — own-data CRUD with
overlap refusal, consumed by the workload page (🏖 on-leave flag) and the
my-schedule month; the projection survives rebuild."""
from __future__ import annotations

from datetime import date, timedelta

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
                    json={"name": "休假演示", "ontology": "software-dev", "requirement": "I111"})
    assert r.status_code == 200
    return r.json()


def _d(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def test_roundtrip_overlap_and_cancel(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200
    # qa-wang has active work so the workload row exists
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "QA 的活跃任务"}).json()
    client.patch(f"/api/items/{it['id']}",
                 json={"assignee_type": "human", "assignee_id": "qa-wang"})

    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    r = client.post("/api/me/time-off",
                    json={"start_date": _d(1), "end_date": _d(3), "reason": "年假"})
    assert r.status_code == 200, r.text
    off_id = r.json()["id"]

    # overlap (partial, touching, and contained) is refused — 409
    for s, e in ((str(_d(2)), str(_d(5))), (_d(0), _d(1)), (_d(2), _d(2)), (_d(1), _d(3))):
        resp = client.post("/api/me/time-off", json={"start_date": s, "end_date": e})
        assert resp.status_code == 409, (s, e, resp.text)
    assert client.post("/api/me/time-off",
                       json={"start_date": _d(5), "end_date": _d(1)}).status_code == 422

    # workload flags the member as on leave today? no — leave starts tomorrow,
    # so today it is False; cancel path then rebuild still replays the stretch
    wl = client.get("/api/portfolio/workload").json()
    me_row = next(m for m in wl["members"] if m["user_id"] == "qa-wang")
    assert me_row["on_leave"] is False

    # own-data: admin cannot see or cancel qa-wang's stretch
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    assert client.delete(f"/api/me/time-off/{off_id}").status_code == 404
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert client.delete(f"/api/me/time-off/{off_id}").status_code == 200
    rows = client.get("/api/me/time-off").json()["time_off"]
    assert rows == [] or all(r["cancelled_at"] for r in rows if r["id"] == off_id)


def test_on_leave_flag_and_rebuild(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "休假者的任务"}).json()
    client.patch(f"/api/items/{it['id']}",
                 json={"assignee_type": "human", "assignee_id": "qa-wang"})

    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    # a stretch covering today (yesterday → tomorrow)
    assert client.post("/api/me/time-off",
                       json={"start_date": _d(-1), "end_date": _d(1), "reason": "病假"}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    wl = client.get("/api/portfolio/workload").json()
    me_row = next(m for m in wl["members"] if m["user_id"] == "qa-wang")
    assert me_row["on_leave"] is True

    projections.rebuild()
    wl2 = client.get("/api/portfolio/workload").json()
    me_row2 = next(m for m in wl2["members"] if m["user_id"] == "qa-wang")
    assert me_row2["on_leave"] is True  # projection survives replay
