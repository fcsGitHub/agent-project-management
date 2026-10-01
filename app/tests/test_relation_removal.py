"""M78-I234 依赖关系解除面（docs/01 §BW.1，Jira 删链语义）：创建（M17-I62）
有解（POST /items/{id}/relations + item.related）而无解——误建依赖永久无法
移除（半截链第十一例变体：创建面在·解除面从未设计）。DELETE /items/{id}/
relations 用复合键（from,to,type）定位（rel_* 代理键在投影内铸造、调用方不
可知）；关系对任一侧都可发起解除；解除事实聚合在 from 侧项目（与
item.related 同账本）；日期不动——移除约束不等于重排（Jira unlink 语义）。"""
from __future__ import annotations

import pytest

from apm import config
from apm.core import events, projections


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


def _mk_two_items(client) -> tuple[str, str, str]:
    pid = client.post("/api/projects",
                      json={"name": "解除演示", "ontology": "software-dev"}).json()["id"]
    a = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "前置项"}).json()["id"]
    b = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "后继项"}).json()["id"]
    return pid, a, b


def _rel_count(client, iid: str) -> int:
    return len(client.get(f"/api/items/{iid}").json()["relations"])


def test_remove_roundtrip_rebuild_and_relink(client, tmp_data, isolated_ontologies):
    pid, a, b = _mk_two_items(client)
    assert client.post(f"/api/items/{b}/relations",
                       json={"to_item": a, "relation_type": "depends_on"}).status_code == 200
    assert _rel_count(client, b) == 1

    # from 侧路径解除（b depends_on a → b 是 from）
    r = client.delete(f"/api/items/{b}/relations",
                      params={"to_item": a, "relation_type": "depends_on"})
    assert r.status_code == 200, r.text
    assert _rel_count(client, b) == 0
    assert _rel_count(client, a) == 0

    # 解除事实在流上且聚合 from 侧项目
    ev = client.get("/api/events", params={"event_type": "item.relation_removed"}).json()["events"]
    assert ev and ev[0]["project_id"] == pid
    assert ev[0]["payload"]["from_item"] == b and ev[0]["payload"]["to_item"] == a

    # rebuild 一致：重放后关系仍不存在（投影 DELETE handler 存活）
    projections.ensure_handlers_registered()
    projections.rebuild()
    assert _rel_count(client, b) == 0

    # 创建面仍活着：解除后可重建同一关系
    assert client.post(f"/api/items/{b}/relations",
                       json={"to_item": a, "relation_type": "depends_on"}).status_code == 200
    assert _rel_count(client, b) == 1


def test_remove_via_to_side_and_matrix(client, tmp_data, isolated_ontologies):
    pid, a, b = _mk_two_items(client)
    client.post(f"/api/items/{b}/relations",
                json={"to_item": a, "relation_type": "depends_on"})

    # 任一侧可发起：从 to 侧（前置项 a 的抽屉）解除同一关系
    r = client.delete(f"/api/items/{a}/relations",
                      params={"to_item": b, "relation_type": "depends_on"})
    assert r.status_code == 200, r.text
    assert _rel_count(client, b) == 0
    # 重复解除 404（不存在即 404，幂等缺席语义）
    assert client.delete(f"/api/items/{a}/relations",
                         params={"to_item": b, "relation_type": "depends_on"}).status_code == 404

    # 矩阵：未知 item 404 / 关系不存在 404 / 缺查询参数 422 / 未知类型 404
    assert client.delete("/api/items/nonexistent/relations",
                         params={"to_item": a, "relation_type": "depends_on"}).status_code == 404
    assert client.delete(f"/api/items/{a}/relations",
                         params={"to_item": b, "relation_type": "blocks"}).status_code == 404
    assert client.delete(f"/api/items/{a}/relations").status_code == 422

    # blocks 同型可解（关系类型不走 depends_on 特判）
    client.post(f"/api/items/{a}/relations",
                json={"to_item": b, "relation_type": "blocks"})
    assert client.delete(f"/api/items/{b}/relations",
                         params={"to_item": a, "relation_type": "blocks"}).status_code == 200
    assert _rel_count(client, b) == 0


def test_remove_cross_project_gated_on_from_side(client, tmp_data, isolated_ontologies):
    """跨项目解除：事实聚合 from 侧项目 → from 侧写门禁治理（M47-I143 镜像）。
    network 模式（本地模式可信写入不经过中间件——M60 教训）：路径侧项目成员
    （中间件放行）但非 from 侧成员 → 端点显式 403；补齐 from 侧成员 → 200。"""
    pa = client.post("/api/projects",
                     json={"name": "上游项目", "ontology": "software-dev"}).json()["id"]
    pb = client.post("/api/projects",
                     json={"name": "下游项目", "ontology": "software-dev"}).json()["id"]
    ia = client.post(f"/api/projects/{pa}/items",
                     json={"concept_id": "task", "title": "上游交付"}).json()["id"]
    ib = client.post(f"/api/projects/{pb}/items",
                     json={"concept_id": "task", "title": "下游实现"}).json()["id"]
    assert client.post(f"/api/items/{ib}/relations",
                       json={"to_item": ia, "relation_type": "depends_on"}).status_code == 200

    client.post("/api/users", json={"id": "qa-li", "name": "QA 李", "password": "qa-pass"})
    # qa-li 只入路径侧项目 pa（ia 的所属）；from 侧 pb 故意不入
    client.post(f"/api/projects/{pa}/members", json={"user_id": "qa-li", "role": "contributor"})

    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    config.settings.auth_mode = "network"
    try:
        client.post("/api/auth/login", json={"user_id": "qa-li", "password": "qa-pass"})
        # 中间件放行（pa 成员），端点显式检查 from 侧（pb 非成员）→ 403
        r = client.delete(f"/api/items/{ia}/relations",
                          params={"to_item": ib, "relation_type": "depends_on"})
        assert r.status_code == 403, r.text
        assert _rel_count(client, ib) == 1  # 事实未落

        # 补齐 from 侧成员 → 200（contributor 即可解除，无需专用删链权限——§BW.1）
        client.post("/api/auth/login", json={"user_id": "u_admin", "password": "admin-pass"})
        client.post(f"/api/projects/{pb}/members", json={"user_id": "qa-li", "role": "contributor"})
        client.post("/api/auth/login", json={"user_id": "qa-li", "password": "qa-pass"})
        assert client.delete(f"/api/items/{ia}/relations",
                             params={"to_item": ib, "relation_type": "depends_on"}).status_code == 200
        assert _rel_count(client, ib) == 0
    finally:
        config.settings.auth_mode = "local"
        config.settings.user_id = "u_admin"
    # 事件聚合在 from 侧项目（下游 pb，与 item.related 同账本）
    ev = client.get("/api/events", params={"event_type": "item.relation_removed"}).json()["events"]
    assert ev and ev[0]["project_id"] == pb
