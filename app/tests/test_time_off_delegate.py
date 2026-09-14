"""I117 delegated time-off (docs/01 §AK.2, Atlassian "on leave until"
automation): a stretch registered with a delegate moves the vacationer's
active shared-project items to the delegate on the first day and back on the
last day — both moves are plain item.assigned events, so the assignee
notification and the audit trail come for free; rebuild replays the final
state."""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from apm import config
from apm.core import db, projections
from apm.domains import automations


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


def _d(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


@pytest.fixture()
def world(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "转派演示", "ontology": "software-dev", "requirement": "I117"})
    assert r.status_code == 200
    pid = r.json()["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    client.post("/api/users", json={"id": "li-lei", "name": "李雷"})
    client.post(f"/api/projects/{pid}/members",
                json={"user_id": "qa-wang", "role": "contributor"})
    client.post(f"/api/projects/{pid}/members",
                json={"user_id": "li-lei", "role": "contributor"})
    return pid


def _make_item(client, pid, title, assignee=None, status=None):
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": title}).json()
    if status:
        assert client.patch(f"/api/items/{it['id']}", json={"status": status}).status_code == 200
    if assignee:
        assert client.patch(f"/api/items/{it['id']}",
                            json={"assignee_type": "human", "assignee_id": assignee}).status_code == 200
    return it["id"]


def _assignee(iid):
    return db.get_conn().execute(
        "SELECT assignee_id FROM items WHERE id = ?", (iid,)).fetchone()["assignee_id"]


def test_delegate_validation(client, tmp_data, isolated_ontologies, world):
    pid = world
    client.post("/api/users", json={"id": "outsider", "name": "外人"})
    client.post("/api/session/identity", json={"user_id": "qa-wang"})

    # an outsider shares no project with the vacationer → 422
    assert client.post("/api/me/time-off", json={
        "start_date": _d(1), "end_date": _d(3), "delegate": "outsider"}).status_code == 422
    # delegating to yourself is pointless → 422
    assert client.post("/api/me/time-off", json={
        "start_date": _d(1), "end_date": _d(3), "delegate": "qa-wang"}).status_code == 422
    # a real shared-project stand-in passes and round-trips
    r = client.post("/api/me/time-off", json={
        "start_date": _d(1), "end_date": _d(3), "delegate": "li-lei"})
    assert r.status_code == 200, r.text
    assert r.json()["delegate"] == "li-lei"
    rows = client.get("/api/me/time-off").json()["time_off"]
    assert rows[0]["delegate"] == "li-lei"


def test_first_day_moves_shared_active_items(client, tmp_data, isolated_ontologies, world):
    pid = world
    it1 = _make_item(client, pid, "活跃一", assignee="qa-wang")
    it2 = _make_item(client, pid, "活跃二", assignee="qa-wang")
    done = _make_item(client, pid, "已完成", assignee="qa-wang", status="done")
    # a project where li-lei is NOT a member must not leak to them
    r2 = client.post("/api/projects",
                     json={"name": "隔离项目", "ontology": "software-dev", "requirement": "I117"})
    pid2 = r2.json()["id"]
    it3 = _make_item(client, pid2, "别处的任务", assignee="qa-wang")

    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    off = client.post("/api/me/time-off", json={
        "start_date": _d(0), "end_date": _d(5), "delegate": "li-lei"}).json()

    moved = automations._delegate_time_off(db.get_conn(), _d(0))
    assert moved == 2
    assert _assignee(it1) == "li-lei"
    assert _assignee(it2) == "li-lei"
    assert _assignee(done) == "qa-wang"   # finished work never moves
    assert _assignee(it3) == "qa-wang"    # non-shared project untouched

    # the audit payload records who the item belongs back to
    ev = db.get_conn().execute(
        "SELECT payload FROM events WHERE event_type = 'item.assigned' AND agg_id = ?"
        " ORDER BY id DESC LIMIT 1", (it1,)).fetchone()
    p = json.loads(ev["payload"])
    assert p["original_assignee"] == "qa-wang"
    assert p["delegate_off"] == off["id"]

    # the delegate received the regular assigned notifications
    n = db.get_conn().execute(
        "SELECT COUNT(*) AS c FROM notifications WHERE user_id = 'li-lei'"
        " AND kind = 'assigned'").fetchone()["c"]
    assert n >= 2

    # idempotent: a same-day re-sweep finds nothing left to move
    assert automations._delegate_time_off(db.get_conn(), _d(0)) == 0


def test_last_day_moves_back_but_spares_own_work(client, tmp_data, isolated_ontologies, world):
    pid = world
    it1 = _make_item(client, pid, "活跃一", assignee="qa-wang")
    it2 = _make_item(client, pid, "活跃二", assignee="qa-wang")
    own = _make_item(client, pid, "李雷自己的任务", assignee="li-lei")

    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    client.post("/api/me/time-off", json={
        "start_date": _d(0), "end_date": _d(5), "delegate": "li-lei"})
    assert automations._delegate_time_off(db.get_conn(), _d(0)) == 2

    # middle days do nothing
    assert automations._delegate_time_off(db.get_conn(), _d(2)) == 0
    # last day returns exactly the delegated items — not the delegate's own work
    assert automations._delegate_time_off(db.get_conn(), _d(5)) == 2
    assert _assignee(it1) == "qa-wang"
    assert _assignee(it2) == "qa-wang"
    assert _assignee(own) == "li-lei"
    # idempotent
    assert automations._delegate_time_off(db.get_conn(), _d(5)) == 0


def test_no_delegate_is_a_noop(client, tmp_data, isolated_ontologies, world):
    pid = world
    it1 = _make_item(client, pid, "活跃一", assignee="qa-wang")
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert client.post("/api/me/time-off", json={
        "start_date": _d(0), "end_date": _d(3)}).status_code == 200
    assert automations._delegate_time_off(db.get_conn(), _d(0)) == 0
    assert _assignee(it1) == "qa-wang"


def test_rebuild_replays_delegate_state(client, tmp_data, isolated_ontologies, world):
    pid = world
    it1 = _make_item(client, pid, "活跃一", assignee="qa-wang")
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    off = client.post("/api/me/time-off", json={
        "start_date": _d(0), "end_date": _d(5), "delegate": "li-lei"}).json()
    assert automations._delegate_time_off(db.get_conn(), _d(0)) == 1

    projections.rebuild()
    conn = db.get_conn()
    row = conn.execute(
        "SELECT delegate FROM user_time_off WHERE id = ?", (off["id"],)).fetchone()
    assert row["delegate"] == "li-lei"     # the stretch replays with its delegate
    assert _assignee(it1) == "li-lei"      # item.assigned replays the handoff
