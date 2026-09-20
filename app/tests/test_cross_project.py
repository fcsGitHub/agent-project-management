"""M47-I143 跨项目依赖：OpenProject 跨项目 relations 语义——关系跟着工作项
走（事件聚合 from 侧项目），建链要求双方项目可读，排期传播（I44）与 lag 对
齐（I83）沿跨项目关系链生效，依赖图为不可读一侧提供 🔒 外部依赖占位节点。"""
from __future__ import annotations

import pytest

from apm import config
from apm.core import db


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


def _mk_project_with_task(client, name: str, title: str, auto=True) -> tuple[str, str]:
    pid = client.post("/api/projects",
                      json={"name": name, "ontology": "software-dev"}).json()["id"]
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": title}).json()
    if auto:
        client.patch(f"/api/items/{it['id']}", json={"auto_scheduled": True})
    return pid, it["id"]


def test_cross_project_relation_allowed_and_attributed(client, tmp_data, isolated_ontologies):
    pa, ia = _mk_project_with_task(client, "上游项目", "上游交付")
    pb, ib = _mk_project_with_task(client, "下游项目", "下游实现")
    r = client.post(f"/api/items/{ib}/relations",
                    json={"to_item": ia, "relation_type": "depends_on"})
    assert r.status_code == 200, r.text
    # 事件聚合在 from 侧项目（下游）
    ev = client.get("/api/events", params={"event_type": "item.related"}).json()["events"]
    assert ev and ev[0]["project_id"] == pb


def test_cross_project_propagation_shifts_dependent(client, tmp_data, isolated_ontologies):
    """锚定周一网格（I34 纪律）：上游 due 周一→+7 下周一，下游 auto_scheduled
    跨项目顺延 +7，落点保持工作日。"""
    from datetime import datetime, timedelta, timezone

    def _day(offset: int) -> str:
        base = (datetime.now(timezone.utc) + timedelta(days=7)).date()
        base += timedelta(days=(7 - base.weekday()) % 7)  # 下一个周一
        return (base + timedelta(days=offset)).isoformat()

    pa, ia = _mk_project_with_task(client, "上游项目", "上游交付")
    pb, ib = _mk_project_with_task(client, "下游项目", "下游实现")
    client.patch(f"/api/items/{ia}", json={"due_date": _day(0)})  # 先有旧值（I44 语义：移动才传播）
    client.patch(f"/api/items/{ib}", json={"start_date": _day(0), "due_date": _day(4)})
    assert client.post(f"/api/items/{ib}/relations",
                       json={"to_item": ia, "relation_type": "depends_on"}).status_code == 200
    # 上游 due +7 → 下游自动顺延 +7
    client.patch(f"/api/items/{ia}", json={"due_date": _day(7)})
    dep = client.get(f"/api/items/{ib}").json()
    assert dep["start_date"] == _day(7)
    assert dep["due_date"] == _day(11)
    # 传播事件聚合在各自项目（rescheduled 记在下游项）
    ev = client.get("/api/events", params={"event_type": "item.rescheduled",
                                           "project_id": pb}).json()["events"]
    assert len(ev) >= 1


def test_relation_requires_both_projects_readable(client, tmp_data, isolated_ontologies):
    """非成员不可把不属于自己的项目链进来（network 语义；local 模式单管理员
    天然全可读，故本测试显式走成员身份矩阵）。"""
    from apm.domains.users import ensure_default_user

    saved_mode = config.settings.auth_mode
    saved_pw = config.settings.admin_password
    config.settings.admin_password = "admin-pass"
    ensure_default_user()
    pa, ia = _mk_project_with_task(client, "公开项目", "上游")
    pb, ib = _mk_project_with_task(client, "私有项目", "下游")
    # qa 只加入 pa（from 侧），未加入 pb（to 侧）
    client.post(f"/api/projects/{pa}/members", json={"user_id": "qa-link", "role": "contributor"})
    config.settings.auth_mode = "network"
    try:
        assert client.post("/api/auth/login",
                           json={"user_id": "qa-link", "password": "qa-link"}).status_code in (200, 401)
        # qa-link 无密码登录不了——用 admin 建号后登录
        assert client.post("/api/auth/login",
                           json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
        client.post("/api/users", json={"id": "qa-link", "name": "QA 链", "password": "qa-pass"})
        assert client.post("/api/auth/login",
                           json={"user_id": "qa-link", "password": "qa-pass"}).status_code == 200
        r = client.post(f"/api/items/{ib}/relations",
                        json={"to_item": ia, "relation_type": "depends_on"})
        assert r.status_code == 403
    finally:
        config.settings.auth_mode = saved_mode
        config.settings.admin_password = saved_pw


def test_graph_external_placeholder_node(client, tmp_data, isolated_ontologies):
    pa, ia = _mk_project_with_task(client, "上游项目", "上游交付")
    pb, ib = _mk_project_with_task(client, "下游项目", "下游实现")
    client.post(f"/api/items/{ib}/relations",
                json={"to_item": ia, "relation_type": "depends_on"})
    graph = client.get(f"/api/projects/{pb}/graph").json()
    ext = next((n for n in graph["nodes"] if n["id"] == ia), None)
    assert ext is not None and ext.get("external") is True
    assert ext["label"] == "上游交付"  # 管理员（local 默认）可读 → 显示真实标题
    assert any(e["source"] == ib and e["target"] == ia for e in graph["edges"])
