"""M119-I366 依赖图批量关系读面（docs/01 §DK）：GET /projects/{pid}/relations
一次返回项目内全部工作项关系——DependencyGraphPage 此前为拼关系面要给每个
工作项各打一次 GET /items/{id}（N+1×整项目规模，M114-I340 批量家族同款收口，
依赖图页每次打开≈100 项×1 查）。口径与图面同源：回收站项的关系不还魂
（M118-I361 族）、隐藏概念项不借关系边泄露存在性（M67-I201 家族）、跨项目
对端只出 id 不出标题（M47-I143：可读性由前端 getItem 404→🔒 兜住）。"""
from __future__ import annotations

import pytest

from apm import config
from apm.core import projections


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "关系读面", "ontology": "software-dev", "requirement": "I366"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _mk(client, pid, title, concept="task"):
    r = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": concept, "title": title})
    assert r.status_code == 200, r.text
    return r.json()


def _link(client, frm, to, kind="depends_on", lag=None):
    body: dict = {"to_item": to["id"], "relation_type": kind}
    if lag is not None:
        body["lag_days"] = lag
    assert client.post(f"/api/items/{frm['id']}/relations", json=body).status_code == 200


def test_bulk_relations_gate_and_shape(client, pid):
    a = _mk(client, pid, "依赖方")
    b = _mk(client, pid, "前置")
    c = _mk(client, pid, "阻塞者")
    _link(client, a, b, lag=2)
    _link(client, c, a, kind="blocks")

    out = client.get(f"/api/projects/{pid}/relations").json()
    assert out["project_id"] == pid
    rels = {(r["from_item"], r["to_item"], r["relation_type"]): r for r in out["relations"]}
    assert rels[(a["id"], b["id"], "depends_on")]["lag_days"] == 2
    assert rels[(c["id"], a["id"], "blocks")]["lag_days"] is None

    # 门禁矩阵：非成员 403 / 匿名也 403（M76 惯例——项目级读门按成员制，
    # 匿名与外人同判，不存在「登录即可读」的中间档）
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    assert client.post("/api/users", json={"id": "outsider", "name": "外人",
                                           "password": "out-pass"}).status_code == 200
    config.settings.auth_mode = "network"
    try:
        assert client.post("/api/auth/login",
                           json={"user_id": "outsider", "password": "out-pass"}).status_code == 200
        assert client.get(f"/api/projects/{pid}/relations").status_code == 403
        client.cookies.clear()
        assert client.get(f"/api/projects/{pid}/relations").status_code == 403
    finally:
        config.settings.auth_mode = "local"


def test_bulk_relations_hides_archived_and_hidden_concepts(client, pid, monkeypatch):
    a = _mk(client, pid, "公开依赖方")
    b = _mk(client, pid, "公开前置")
    _link(client, a, b)
    secret = _mk(client, pid, "机密缺陷", concept="bug")
    _link(client, a, secret)
    dead = _mk(client, pid, "回收站前置")
    _link(client, a, dead)
    assert client.post(f"/api/items/{dead['id']}/archive").status_code == 200
    assert client.patch(f"/api/projects/{pid}",
                        json={"concept_visibility": {"bug": "owner"}}).status_code == 200

    # 隐藏概念 + 回收站的关系边对贡献者整体隐去（存在性不借边泄露）
    # （造用户与入会都在切 network 之前——POST /users 网络模式仅管理员且匿名
    # 无法加成员，smoke 77 教训）
    client.post("/api/users", json={"id": "dev-wang", "name": "开发王",
                                    "password": "wang-pass"})
    client.post(f"/api/projects/{pid}/members",
                json={"user_id": "dev-wang", "role": "contributor"})
    monkeypatch.setattr(config.settings, "auth_mode", "network")
    client.post("/api/auth/login", json={"user_id": "dev-wang", "password": "wang-pass"})
    rels = client.get(f"/api/projects/{pid}/relations").json()["relations"]
    assert [(r["from_item"], r["to_item"]) for r in rels] == [(a["id"], b["id"])]

    # owner（实例管理员 u_admin）全见；rebuild 后口径不变
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    client.post("/api/auth/login",
                json={"user_id": config.settings.user_id, "password": "admin-pass"})
    assert len(client.get(f"/api/projects/{pid}/relations").json()["relations"]) == 2
    projections.rebuild()
    rels = client.get(f"/api/projects/{pid}/relations").json()["relations"]
    assert {(r["from_item"], r["to_item"]) for r in rels} == {(a["id"], b["id"]), (a["id"], secret["id"])}


def test_graph_task_nodes_carry_assignee_display_name(client, pid):
    it = _mk(client, pid, "带指派的任务")
    client.post("/api/users", json={"id": "u-wang", "name": "小王", "password": "wang-pass"})
    assert client.patch(f"/api/items/{it['id']}",
                        json={"assignee_type": "human", "assignee_id": "u-wang"}).status_code == 200
    node = next(n for n in client.get(f"/api/projects/{pid}/graph").json()["nodes"]
                if n["id"] == it["id"])
    assert node["assignee_id"] == "u-wang"
    assert node["assignee_name"] == "小王"
    assert node["assignee_type"] == "human"
