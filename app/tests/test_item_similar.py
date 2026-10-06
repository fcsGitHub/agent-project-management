"""M115-I346 创建防重提示（docs/01 §DF，Linear 吸纳轮——similar issues
typeahead）：GET /projects/{id}/items/similar 复用 items_search FTS5
（_match_expr 引号纪律），归档项与隐匿概念不出提示（M67 可见性纪律）。"""
from __future__ import annotations

import pytest

from apm import config


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def proj(client, tmp_data, isolated_ontologies) -> str:
    return client.post("/api/projects",
                       json={"name": "防重项目", "ontology": "software-dev"}).json()["id"]


def _mk_item(client, proj: str, title: str) -> dict:
    r = client.post(f"/api/projects/{proj}/items", json={"concept_id": "task", "title": title})
    assert r.status_code == 200, r.text
    return r.json()


def test_similar_suggests_by_title_keywords(client, proj):
    a = _mk_item(client, proj, "登录页 OAuth 重构")
    b = _mk_item(client, proj, "登录页样式调整")
    _mk_item(client, proj, "计费模块升级")
    r = client.get(f"/api/projects/{proj}/items/similar", params={"title": "登录页"})
    assert r.status_code == 200, r.text
    ids = [s["id"] for s in r.json()["suggestions"]]
    assert set(ids) == {a["id"], b["id"]}
    top = r.json()["suggestions"][0]
    # project_id/description/labels 随行——前端 onPickExisting 直达 QuickEditModal
    # 时表单初始值完整（I347 走查发现：缺 project_id 会让标签区误显「无标签」）
    assert {"id", "title", "status", "status_group", "concept_id",
            "project_id", "description", "labels"} <= set(top)

    # OR 语义：自然连续输入「登录页重构」的 4 个 bigram 不要求全部命中
    # （索引里标题中段的空格会打断 CJK 连续串——AND 语义会零命中）
    r2 = client.get(f"/api/projects/{proj}/items/similar",
                    params={"title": "登录页重构"}).json()
    ids2 = [s["id"] for s in r2["suggestions"]]
    assert a["id"] in ids2 and b["id"] in ids2


def test_similar_excludes_archived(client, proj):
    a = _mk_item(client, proj, "部署脚本修复")
    _mk_item(client, proj, "部署文档补全")
    client.post(f"/api/items/{a['id']}/archive")
    r = client.get(f"/api/projects/{proj}/items/similar", params={"title": "部署"}).json()
    assert all(s["id"] != a["id"] for s in r["suggestions"])


def test_similar_excludes_hidden_concepts(client, proj, monkeypatch):
    """隐匿概念的标题不给无权者看（M67-I201 存在性不泄露）。"""
    client.post("/api/users", json={"id": "owner-z", "name": "Owner 张", "password": "z-pass-1"})
    client.post("/api/users", json={"id": "dev-w", "name": "开发王", "password": "w-pass-1"})
    client.post(f"/api/projects/{proj}/members", json={"user_id": "owner-z", "role": "owner"})
    client.post(f"/api/projects/{proj}/members", json={"user_id": "dev-w", "role": "contributor"})
    assert client.patch(f"/api/projects/{proj}",
                        json={"concept_visibility": {"bug": "owner"}}).status_code == 200
    secret = client.post(f"/api/projects/{proj}/items",
                         json={"concept_id": "bug", "title": "机密登录缺陷"}).json()
    _mk_item(client, proj, "登录页文案修订")

    monkeypatch.setattr(config.settings, "auth_mode", "network")
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    assert client.post("/api/auth/login", json={"user_id": "dev-w", "password": "w-pass-1"}).status_code == 200
    r = client.get(f"/api/projects/{proj}/items/similar", params={"title": "登录"}).json()
    ids = [s["id"] for s in r["suggestions"]]
    assert secret["id"] not in ids

    # owner 自己能看到
    assert client.post("/api/auth/login", json={"user_id": "owner-z", "password": "z-pass-1"}).status_code == 200
    r2 = client.get(f"/api/projects/{proj}/items/similar", params={"title": "登录"}).json()
    assert secret["id"] in [s["id"] for s in r2["suggestions"]]


def test_similar_short_query_returns_empty(client, proj):
    r = client.get(f"/api/projects/{proj}/items/similar", params={"title": "登"})
    assert r.status_code == 200 and r.json()["suggestions"] == []
