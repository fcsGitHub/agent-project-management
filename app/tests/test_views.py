"""M16-I50: saved views — event-sourced CRUD with fail-closed definition
validation, M8-style visibility, and execution that reuses the existing
filter path (view_id result == hand-built query params)."""
import json

import pytest

from apm.core import projections


@pytest.fixture
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "视图演示", "ontology": "software-dev", "requirement": "v"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _mk_item(client, pid, title, **kw):
    r = client.post(f"/api/projects/{pid}/items", json={"concept_id": "task", "title": title, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_view_crud_and_rebuild(client, pid):
    r = client.post(f"/api/projects/{pid}/views", json={
        "name": "高优先级任务", "is_public": True,
        "definition": {"concept_id": "task", "priority": "high"},
    })
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["owner_id"] == "u_admin" and v["is_public"] == 1
    assert json.loads(v["definition"]) == {"concept_id": "task", "priority": "high"}

    r = client.patch(f"/api/views/{v['id']}", json={"name": "高优", "is_public": False})
    assert r.status_code == 200
    assert r.json()["name"] == "高优" and r.json()["is_public"] == 0

    assert client.get(f"/api/views/{v['id']}").status_code == 200
    assert len(client.get(f"/api/projects/{pid}/views").json()["views"]) == 1

    # deleted view disappears from list; 404 afterwards
    assert client.delete(f"/api/views/{v['id']}").status_code == 200
    assert client.get(f"/api/views/{v['id']}").status_code == 404
    assert client.get(f"/api/projects/{pid}/views").json()["views"] == []

    # rebuild replays the remaining event stream consistently
    projections.rebuild()
    assert client.get(f"/api/projects/{pid}/views").json()["views"] == []

    # a surviving view keeps its projection after rebuild
    r = client.post(f"/api/projects/{pid}/views", json={"name": "V", "definition": {}})
    assert r.status_code == 200
    before = client.get(f"/api/projects/{pid}/views").json()["views"]
    projections.rebuild()
    after = client.get(f"/api/projects/{pid}/views").json()["views"]
    assert after == before


def test_view_validation_fail_closed(client, pid):
    for bad_def, why in (
        ({"nonsense": "x"}, "unknown key"),
        ({"priority": ""}, "empty value"),
        ({"status_group": "bogus"}, "bad status_group"),
        ({"cf": "novalue"}, "cf without colon"),
        ({"group_by": "bogus"}, "bad group_by"),
        ({"group_by": "field:nope"}, "undeclared field"),
        ({"cf": "nope:true"}, "undeclared cf field"),
        ("not-a-dict", "wrong type"),
    ):
        r = client.post(f"/api/projects/{pid}/views", json={"name": "x", "definition": bad_def})
        assert r.status_code == 422, f"{why}: {r.status_code} {r.text}"

    # declared-but-project-disabled field is rejected for group_by/cf
    r = client.patch(f"/api/projects/{pid}/fields", json={"field_id": "tags", "active": False})
    assert r.status_code == 200, r.text
    for bad in ({"group_by": "field:tags"}, {"cf": "tags:frontend"}):
        r = client.post(f"/api/projects/{pid}/views", json={"name": "x", "definition": bad})
        assert r.status_code == 422, f"disabled field: {r.status_code}"

    # unknown view & cross-project
    assert client.get("/api/views/v_nope").status_code == 404
    r = client.post("/api/projects", json={"name": "别处", "ontology": "software-dev", "requirement": "x2"})
    other = r.json()["id"]
    v = client.post(f"/api/projects/{other}/views", json={"name": "o", "definition": {}}).json()
    r = client.get(f"/api/projects/{pid}/items", params={"view_id": v["id"]})
    assert r.status_code == 422


def test_view_execution_same_as_manual_filters(client, pid):
    _mk_item(client, pid, "高优A", priority="high")
    _mk_item(client, pid, "低优B", priority="low")
    c = _mk_item(client, pid, "标签C", priority="high")
    r = client.patch(f"/api/items/{c['id']}", json={"custom_fields": {"tags": ["frontend"]}})
    assert r.status_code == 200, r.text
    _mk_item(client, pid, "普通D")

    v = client.post(f"/api/projects/{pid}/views", json={
        "name": "高优", "is_public": True,
        "definition": {"priority": "high"},
    }).json()
    via_view = {i["id"] for i in client.get(
        f"/api/projects/{pid}/items", params={"view_id": v["id"]}).json()["items"]}
    manual = {i["id"] for i in client.get(
        f"/api/projects/{pid}/items", params={"priority": "high"}).json()["items"]}
    assert via_view == manual and len(via_view) == 2

    # explicit param narrows the view (explicit wins)
    narrowed = {i["id"] for i in client.get(
        f"/api/projects/{pid}/items", params={"view_id": v["id"], "priority": "low"}).json()["items"]}
    assert narrowed == {i["id"] for i in client.get(
        f"/api/projects/{pid}/items", params={"priority": "low"}).json()["items"]}

    # cf + group_by definition drives the board identically
    v2 = client.post(f"/api/projects/{pid}/views", json={
        "name": "UI标签", "definition": {"cf": "tags:frontend", "group_by": "lifecycle"},
    }).json()
    board = client.get(f"/api/projects/{pid}/board", params={"view_id": v2["id"]}).json()
    board_ids = {i["id"] for b in board["buckets"] for i in b["items"]}
    assert board_ids == {c["id"]}
    via_items = {i["id"] for i in client.get(
        f"/api/projects/{pid}/items", params={"view_id": v2["id"]}).json()["items"]}
    assert via_items == board_ids

    # view from another ontology-declared field is fine for group_by
    v3 = client.post(f"/api/projects/{pid}/views", json={
        "name": "按标签分组", "definition": {"group_by": "field:tags"},
    }).json()
    board3 = client.get(f"/api/projects/{pid}/board", params={"view_id": v3["id"]}).json()
    assert board3["group_by"] == "field:tags"


def test_view_visibility_network(client, pid):
    """network mode: public -> members read, private -> owner/admin only,
    viewers cannot create, non-members 403."""
    from apm import config

    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    client.post("/api/users", json={"id": "dev-zhang", "name": "Dev 张", "password": "dev-pass"})
    client.post("/api/users", json={"id": "outsider", "name": "外人", "password": "out-pass"})
    client.post(f"/api/projects/{pid}/members", json={"user_id": "dev-zhang", "role": "contributor"})

    config.settings.auth_mode = "network"
    try:
        assert client.post("/api/auth/login",
                           json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
        r = client.post(f"/api/projects/{pid}/views", json={
            "name": "admin私", "definition": {"priority": "high"}, "is_public": False})
        assert r.status_code == 200
        mine_id = r.json()["id"]
        r = client.post(f"/api/projects/{pid}/views", json={
            "name": "公开", "definition": {}, "is_public": True})
        assert r.status_code == 200
        pub_id = r.json()["id"]

        # admin (creator) sees both
        visible = {v["id"] for v in client.get(f"/api/projects/{pid}/views").json()["views"]}
        assert {mine_id, pub_id} <= visible

        # contributor 张三: public yes, private no; may create; may not delete admin's
        assert client.post("/api/auth/login",
                           json={"user_id": "dev-zhang", "password": "dev-pass"}).status_code == 200
        visible = {v["id"] for v in client.get(f"/api/projects/{pid}/views").json()["views"]}
        assert pub_id in visible and mine_id not in visible
        assert client.get(f"/api/views/{pub_id}").status_code == 200
        assert client.get(f"/api/views/{mine_id}").status_code == 403
        r = client.post(f"/api/projects/{pid}/views", json={"name": "z", "definition": {}})
        assert r.status_code == 200
        zview = r.json()["id"]
        assert client.delete(f"/api/views/{mine_id}").status_code == 403
        assert client.delete(f"/api/views/{zview}").status_code == 200  # own view ok

        # non-member: 403 on list and on public view detail
        assert client.post("/api/auth/login",
                           json={"user_id": "outsider", "password": "out-pass"}).status_code == 200
        assert client.get(f"/api/projects/{pid}/views").status_code == 403
        assert client.get(f"/api/views/{pub_id}").status_code == 403
        assert client.get(f"/api/projects/{pid}/items", params={"view_id": pub_id}).status_code == 403
    finally:
        config.settings.auth_mode = "local"
        config.settings.admin_password = ""
