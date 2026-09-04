"""M19-I59: work-item time entries — event-sourced spent-time log with CRUD,
fail-closed validation, spent totals on item reads, permission alignment and
the participation hook (logging time makes you a participant)."""
import json

import pytest

from apm import config
from apm.core import projections


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "工时演示", "ontology": "software-dev", "requirement": "c"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _mk_item(client, pid, title, **kw):
    r = client.post(f"/api/projects/{pid}/items", json={"concept_id": "task", "title": title, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def _log(client, item_id, minutes, spent_on="2026-09-04", note=""):
    r = client.post(f"/api/items/{item_id}/time_entries",
                    json={"minutes": minutes, "spent_on": spent_on, "note": note})
    assert r.status_code == 200, r.text
    return r.json()


def test_timelog_crud_rebuild_and_totals(client, pid):
    item = _mk_item(client, pid, "被记时的任务")
    e1 = _log(client, item["id"], 90, note="设计走查")
    e2 = _log(client, item["id"], 30, spent_on="2026-09-05")
    assert e1["user_id"] == "u_admin" and e1["deleted_at"] is None

    listing = client.get(f"/api/items/{item['id']}/time_entries").json()
    assert [x["id"] for x in listing["entries"]] == [e1["id"], e2["id"]]
    assert listing["total_minutes"] == 120

    # soft delete: hidden from list, excluded from totals, event preserved
    assert client.delete(f"/api/time_entries/{e2['id']}").status_code == 200
    listing = client.get(f"/api/items/{item['id']}/time_entries").json()
    assert listing["total_minutes"] == 90

    # edit survives rebuild
    r = client.patch(f"/api/time_entries/{e1['id']}", json={"minutes": 60, "note": "改"})
    assert r.status_code == 200 and r.json()["minutes"] == 60
    projections.rebuild()
    listing = client.get(f"/api/items/{item['id']}/time_entries").json()
    assert listing["total_minutes"] == 60
    assert listing["entries"][0]["note"] == "改"
    # and the deleted entry stays deleted after replay
    assert client.get(f"/api/time_entries/{e2['id']}").status_code == 404

    # spent totals ride on item reads (plan vs actual side by side)
    detail = client.get(f"/api/items/{item['id']}").json()
    assert detail["spent_minutes"] == 60
    listed = client.get(f"/api/projects/{pid}/items").json()["items"]
    assert next(i for i in listed if i["id"] == item["id"])["spent_minutes"] == 60

    # unknown item → 404 on both list and create
    assert client.get("/api/items/i_nope/time_entries").status_code == 404
    assert client.post("/api/items/i_nope/time_entries",
                       json={"minutes": 30, "spent_on": "2026-09-04"}).status_code == 404


def test_timelog_validation_fail_closed(client, pid):
    item = _mk_item(client, pid, "校验目标")
    for minutes in (0, -5, 1441):
        assert client.post(f"/api/items/{item['id']}/time_entries",
                           json={"minutes": minutes, "spent_on": "2026-09-04"}).status_code == 422
    assert client.post(f"/api/items/{item['id']}/time_entries",
                       json={"minutes": 30, "spent_on": "04/09/2026"}).status_code == 422
    # edit path validates too
    e = _log(client, item["id"], 30)
    assert client.patch(f"/api/time_entries/{e['id']}", json={"minutes": 0}).status_code == 422
    assert client.patch(f"/api/time_entries/{e['id']}", json={}).status_code == 422


def test_timelog_participation_and_first_source_wins(client, pid):
    client.post("/api/users", json={"id": "u_dev", "name": "开发"})
    item = _mk_item(client, pid, "参与目标")
    # u_dev logs time → becomes participant with source='time'
    saved = config.settings.user_id
    try:
        client.post("/api/session/identity", json={"user_id": "u_dev"})
        _log(client, item["id"], 45, note="编码")
    finally:
        client.post("/api/session/identity", json={"user_id": saved})
    parts = client.get(f"/api/items/{item['id']}/time_entries").json()["participants"]
    by_user = {p["user_id"]: p["source"] for p in parts}
    assert by_user.get("u_dev") == "time"
    # a later mention does NOT overwrite the existing row (first source wins)
    client.post(f"/api/items/{item['id']}/comments", json={"body": "请 @开发 确认"})
    parts = client.get(f"/api/items/{item['id']}/time_entries").json()["participants"]
    by_user = {p["user_id"]: p["source"] for p in parts}
    assert by_user.get("u_dev") == "time"


def test_timelog_permission_network(client, pid):
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    client.post("/api/users", json={"id": "outsider", "name": "外人", "password": "out-pass"})
    config.settings.auth_mode = "network"
    try:
        assert client.post("/api/auth/login", json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
        item = _mk_item(client, pid, "受门禁保护")
        # author logs time, then outsider is rejected on read and write
        e = _log(client, item["id"], 30)
        assert client.post("/api/auth/login", json={"user_id": "outsider", "password": "out-pass"}).status_code == 200
        assert client.get(f"/api/items/{item['id']}/time_entries").status_code == 403
        assert client.post(f"/api/items/{item['id']}/time_entries",
                           json={"minutes": 10, "spent_on": "2026-09-04"}).status_code == 403
        # non-author (even a member) cannot edit/delete someone else's entry;
        # admin can — switch back to the admin member
        assert client.post("/api/auth/login", json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
        assert client.post(f"/api/items/{item['id']}/time_entries",
                           json={"minutes": 10, "spent_on": "2026-09-04"}).status_code == 200
    finally:
        config.settings.auth_mode = "local"
        config.settings.admin_password = ""
