"""M22-I68: global search — FTS5 index stays in sync with the item/comment
projections (including rebuild), Chinese bigram matching works, results are
scoped to the caller's visible projects, and an empty query is rejected."""
import pytest

from apm.core import projections


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "搜索演示", "ontology": "software-dev", "requirement": "I68"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_search_index_visibility_and_rebuild(client, pid):
    # two items, one Chinese title, one latin; a comment on the first
    a = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "登录模块重构", "custom_fields": {"tags": ["frontend"]}})
    assert a.status_code == 200, a.text
    item_a = a.json()
    b = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "bug", "title": "payment webhook retry"})
    assert b.status_code == 200, b.text
    item_b = b.json()
    c = client.post(f"/api/items/{item_a['id']}/comments", json={"body": "重构时注意兼容旧版登录接口"})
    assert c.status_code == 200, c.text

    # empty query 422
    assert client.get("/api/search", params={"q": ""}).status_code == 422

    # Chinese bigram hit on the item title
    r = client.get("/api/search", params={"q": "登录模块"}).json()
    assert [i["id"] for i in r["items"]] == [item_a["id"]]
    assert r["items"][0]["project_name"] == "搜索演示"

    # comment body hit, with the host item title for the jump link
    r = client.get("/api/search", params={"q": "兼容旧版"}).json()
    assert r["items"] == [] and len(r["comments"]) == 1
    assert r["comments"][0]["item_id"] == item_a["id"] and r["comments"][0]["item_title"] == "登录模块重构"

    # latin token hit
    r = client.get("/api/search", params={"q": "webhook"}).json()
    assert [i["id"] for i in r["items"]] == [item_b["id"]]

    # type filter
    r = client.get("/api/search", params={"q": "重构", "types": "items"}).json()
    assert r["comments"] == [] and len(r["items"]) == 1

    # soft-deleted comments drop out of the index
    client.delete(f"/api/comments/{c.json()['id']}")
    r = client.get("/api/search", params={"q": "兼容旧版"}).json()
    assert r["comments"] == []

    # rebuild replays the index identically
    projections.rebuild()
    r = client.get("/api/search", params={"q": "登录模块"}).json()
    assert [i["id"] for i in r["items"]] == [item_a["id"]]

    # outsider scoping (network mode): non-member sees nothing
    from apm import config
    from apm.domains.users import ensure_default_user
    config.settings.admin_password = "admin-pass"
    ensure_default_user()
    client.post("/api/users", json={"id": "outsider", "name": "外人", "password": "out-pass"})
    config.settings.auth_mode = "network"
    try:
        assert client.post("/api/auth/login", json={"user_id": "outsider", "password": "out-pass"}).status_code == 200
        r = client.get("/api/search", params={"q": "登录模块"}).json()
        assert r["items"] == []
        assert client.post("/api/auth/login", json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
        r = client.get("/api/search", params={"q": "登录模块"}).json()
        assert len(r["items"]) == 1
    finally:
        config.settings.auth_mode = "local"
        config.settings.admin_password = ""
