"""M115-I345 标签域（docs/01 §DF，Linear 吸纳轮——ontology custom_fields 是
重武器，日常分拣需要 Linear 同款轻量标签）：项目级 labels CRUD（颜色+重名
409）+ items.labels JSON 多值挂接（create/patch 校验同项目、[] 清空）+
board group_by=labels 扇出（多标签一物多列）+ list_items label 过滤 +
label.deleted 投影侧从 items 摘除（重放确定性）。"""
from __future__ import annotations

import json

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
                       json={"name": "标签项目", "ontology": "software-dev"}).json()["id"]


def _mk(client, pid: str, name: str, color: str | None = None) -> dict:
    body: dict = {"name": name}
    if color:
        body["color"] = color
    r = client.post(f"/api/projects/{pid}/labels", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_label_crud_and_usage_count(client, proj):
    l1 = _mk(client, proj, "缺陷", "#d43")
    assert l1["name"] == "缺陷" and l1["color"] == "#d43" and l1["id"].startswith("label_")
    dup = client.post(f"/api/projects/{proj}/labels", json={"name": "缺陷"})
    assert dup.status_code == 409
    p = client.patch(f"/api/projects/{proj}/labels/{l1['id']}", json={"name": "Bug", "color": "#c00"})
    assert p.status_code == 200 and p.json()["name"] == "Bug"

    it = client.post(f"/api/projects/{proj}/items",
                     json={"concept_id": "task", "title": "挂标签项", "labels": [l1["id"]]}).json()
    listed = client.get(f"/api/projects/{proj}/labels").json()["labels"]
    row = next(x for x in listed if x["id"] == l1["id"])
    assert row["usage"] == 1

    d = client.delete(f"/api/projects/{proj}/labels/{l1['id']}")
    assert d.status_code == 200
    assert [x["id"] for x in client.get(f"/api/projects/{proj}/labels").json()["labels"]] == []
    got = client.get(f"/api/items/{it['id']}").json()
    assert got["labels"] == []  # deleted label pulled out of items
    assert client.delete(f"/api/projects/{proj}/labels/{l1['id']}").status_code == 404


def test_label_validation(client, proj):
    other = client.post("/api/projects",
                        json={"name": "别的项目", "ontology": "software-dev"}).json()["id"]
    foreign = _mk(client, other, "外来标签")
    for bad in ({"name": ""}, {"name": "x" * 61}):
        assert client.post(f"/api/projects/{proj}/labels", json=bad).status_code == 422
    # 跨项目挂标签 422（外键同项目语义，M114-I339 惯例）
    r = client.post(f"/api/projects/{proj}/items",
                    json={"concept_id": "task", "title": "越权标签", "labels": [foreign["id"]]})
    assert r.status_code == 422
    assert "another project" in r.json()["detail"]
    it = client.post(f"/api/projects/{proj}/items",
                     json={"concept_id": "task", "title": "未知标签", "labels": ["label_nope"]})
    assert it.status_code == 422


def test_item_labels_roundtrip_and_rebuild(client, proj):
    l1 = _mk(client, proj, "前端")["id"]
    l2 = _mk(client, proj, "后端")["id"]
    it = client.post(f"/api/projects/{proj}/items",
                     json={"concept_id": "task", "title": "往返项", "labels": [l1, l2]}).json()
    assert it["labels"] == [l1, l2]
    p = client.patch(f"/api/items/{it['id']}", json={"labels": [l2]})
    assert p.status_code == 200 and p.json()["labels"] == [l2]
    p2 = client.patch(f"/api/items/{it['id']}", json={"labels": []})
    assert p2.status_code == 200 and p2.json()["labels"] == []
    client.patch(f"/api/items/{it['id']}", json={"labels": [l1]})
    assert client.post("/api/system/rebuild-projections").status_code == 200
    got = client.get(f"/api/items/{it['id']}").json()
    assert got["labels"] == [l1]  # rebuild 原样重放


def test_board_group_by_labels_fanout(client, proj):
    l1 = _mk(client, proj, "前端", "#3b8")["id"]
    l2 = _mk(client, proj, "后端", "#83b")["id"]
    a = client.post(f"/api/projects/{proj}/items",
                    json={"concept_id": "task", "title": "A 仅前端", "labels": [l1]}).json()
    b = client.post(f"/api/projects/{proj}/items",
                    json={"concept_id": "task", "title": "B 双标签", "labels": [l1, l2]}).json()
    c = client.post(f"/api/projects/{proj}/items",
                    json={"concept_id": "task", "title": "C 无标签"}).json()
    board = client.get(f"/api/projects/{proj}/board",
                       params={"group_by": "labels"}).json()
    groups = {g["id"]: g for g in board["groups"]}
    assert board["group_by"] == "labels" and board["field"] is None
    assert [it["id"] for it in groups[l1]["items"]] == [a["id"], b["id"]]
    assert [it["id"] for it in groups[l2]["items"]] == [b["id"]]
    assert [it["id"] for it in groups["_none"]["items"]] == [c["id"]]
    assert groups[l1]["name"] == "前端" and groups[l1]["color"] == "#3b8"
    assert groups["_none"]["name"] == "未标签"


def test_list_items_label_filter(client, proj):
    l1 = _mk(client, proj, "筛选一")["id"]
    l2 = _mk(client, proj, "筛选二")["id"]
    a = client.post(f"/api/projects/{proj}/items",
                    json={"concept_id": "task", "title": "A", "labels": [l1]}).json()
    b = client.post(f"/api/projects/{proj}/items",
                    json={"concept_id": "task", "title": "B", "labels": [l1, l2]}).json()
    _ = client.post(f"/api/projects/{proj}/items", json={"concept_id": "task", "title": "C"})
    r1 = client.get(f"/api/projects/{proj}/items", params={"label": l1}).json()
    assert sorted(x["id"] for x in r1["items"]) == sorted([a["id"], b["id"]])
    r2 = client.get(f"/api/projects/{proj}/items", params={"label": l2}).json()
    assert [x["id"] for x in r2["items"]] == [b["id"]]


def test_label_write_gates(client, proj, monkeypatch):
    """viewer/非成员写 403（network 模式下中间件管辖 /projects/* 写面）。"""
    pid2 = client.post("/api/projects",
                       json={"name": "旁观项目", "ontology": "software-dev"}).json()["id"]
    client.post("/api/users", json={"id": "u_viewer", "name": "围观者", "password": "viewer-pass-1"})
    client.post("/api/users", json={"id": "u_out", "name": "外人", "password": "out-pass-1"})
    client.post(f"/api/projects/{proj}/members", json={"user_id": "u_viewer", "role": "viewer"})
    client.post(f"/api/projects/{pid2}/members", json={"user_id": "u_out", "role": "owner"})
    label = _mk(client, proj, "门禁标签")

    # M61-I184 纪律：network 模式身份必须真实登录；引导管理员密码先设再切
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    monkeypatch.setattr(config.settings, "auth_mode", "network")
    def _login(uid: str, pw: str) -> None:
        assert client.post("/api/auth/login", json={"user_id": uid, "password": pw}).status_code == 200

    _login("u_viewer", "viewer-pass-1")
    assert client.post(f"/api/projects/{proj}/labels", json={"name": "越权"}).status_code == 403
    assert client.patch(f"/api/projects/{proj}/labels/{label['id']}",
                        json={"name": "越权改"}).status_code == 403
    assert client.delete(f"/api/projects/{proj}/labels/{label['id']}").status_code == 403
    assert client.get(f"/api/projects/{proj}/labels").status_code == 200  # GET 惯性开放

    _login("u_out", "out-pass-1")
    assert client.post(f"/api/projects/{proj}/labels", json={"name": "外人"}).status_code == 403

    _login("u_admin", "admin-pass")
    assert client.post(f"/api/projects/{proj}/labels", json={"name": "管理员可建"}).status_code == 200
