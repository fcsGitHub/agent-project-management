"""Smoke 22 (M16-I52): saved views end-to-end — CRUD, fail-closed validation,
default-view fallback on the board, and rebuild consistency."""
import pytest

from apm.core import projections


@pytest.mark.smoke
def test_smoke_22_saved_views(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "冒烟视图", "ontology": "software-dev", "requirement": "s22"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    def mk(title, **kw):
        r = client.post(f"/api/projects/{pid}/items", json={"concept_id": "task", "title": title, **kw})
        assert r.status_code == 200, r.text
        return r.json()

    mk("高优甲", priority="high")
    mk("高优乙", priority="high")
    mk("低优丙", priority="low")

    # CRUD + validation gate
    v = client.post(f"/api/projects/{pid}/views", json={
        "name": "高优视图", "is_public": True, "definition": {"priority": "high"}}).json()
    assert client.post(f"/api/projects/{pid}/views",
                       json={"name": "坏", "definition": {"hacker": True}}).status_code == 422

    # view execution equals the hand-built filter
    via_view = {i["id"] for i in client.get(
        f"/api/projects/{pid}/items", params={"view_id": v["id"]}).json()["items"]}
    manual = {i["id"] for i in client.get(
        f"/api/projects/{pid}/items", params={"priority": "high"}).json()["items"]}
    assert via_view == manual and len(via_view) == 2

    # default view: board without params lands on it
    r = client.post(f"/api/views/{v['id']}/make-default")
    assert r.status_code == 200 and r.json()["is_default"] == 1
    board = client.get(f"/api/projects/{pid}/board").json()
    assert board["applied_view_id"] == v["id"]
    board_ids = {i["id"] for b in board["buckets"] for i in b["items"]}
    assert board_ids == via_view

    # rebuild consistency: definition, flags and default all survive
    projections.rebuild()
    views = client.get(f"/api/projects/{pid}/views").json()["views"]
    assert len(views) == 1
    assert views[0]["is_default"] == 1 and views[0]["definition"] == {"priority": "high"}
    assert client.get(f"/api/projects/{pid}/board").json()["applied_view_id"] == v["id"]

    # unknown view → 404; delete → gone from board fallback
    assert client.get("/api/views/v_missing").status_code == 404
    assert client.delete(f"/api/views/{v['id']}").status_code == 200
    board = client.get(f"/api/projects/{pid}/board").json()
    assert board["applied_view_id"] is None
