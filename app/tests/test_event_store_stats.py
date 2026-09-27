"""M61-I183 事件表体积观测（docs/01 §BF.1，先测后治）：事件日志只增是事件
溯源的本质（§K.3 裁决：归档=导出非删除，任何删除都断 live==replay 链），治理
基线是纯读观测——多大/什么类型在涨/最老多老。统计不是投影：rebuild 前后
不变；非 admin 403（与 rebuild 端点同口径）。"""
from __future__ import annotations

import pytest

from apm import config
from apm.core import db


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


def _table_count() -> int:
    return db.get_conn().execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]


def test_event_store_stats_reconciles(client):
    # 空库也不炸：初始库零事件时 oldest/newest 诚实为 None
    empty = client.get("/api/system/event-store-stats").json()
    assert empty["total_events"] == _table_count()
    assert empty["db_bytes"] > 0
    assert empty["oldest_ts"] is None or empty["newest_ts"] is None or empty["oldest_ts"] <= empty["newest_ts"]
    assert sum(d["count"] for d in empty["distribution"]) == empty["total_events"]

    p = client.post("/api/projects",
                    json={"name": "观测项目", "ontology": "software-dev",
                          "requirement": "stats"}).json()
    it = client.post(f"/api/projects/{p['id']}/items",
                     json={"concept_id": "task", "title": "观测项"}).json()
    client.patch(f"/api/items/{it['id']}", json={"status": "in_progress"})

    s = client.get("/api/system/event-store-stats").json()
    assert s["total_events"] == _table_count() > empty["total_events"]
    # 分布行计数求和=总数；排序按计数降序
    assert sum(d["count"] for d in s["distribution"]) == s["total_events"]
    counts = [d["count"] for d in s["distribution"]]
    assert counts == sorted(counts, reverse=True)
    types = {(d["agg_type"], d["event_type"]) for d in s["distribution"]}
    assert ("project", "project.created") in types
    assert ("item", "item.status_changed") in types
    assert s["oldest_ts"] is not None and s["newest_ts"] is not None
    assert s["oldest_ts"] <= s["newest_ts"]


def test_event_store_stats_requires_admin(client, monkeypatch):
    # 与 rebuild 同口径：network 模式下已登录的非 admin 403
    # （qa-wang 非成员非管理员；登录走真实会话而非本地身份回退）
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "password": "qa-pass"})
    monkeypatch.setattr(config.settings, "auth_mode", "network")
    try:
        assert client.post("/api/auth/login",
                           json={"user_id": "qa-wang", "password": "qa-pass"}).status_code == 200
        assert client.get("/api/system/event-store-stats").status_code == 403
        assert client.post("/api/auth/login",
                           json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
        assert client.get("/api/system/event-store-stats").status_code == 200
    finally:
        config.settings.admin_password = ""


def test_event_store_stats_stable_after_rebuild(client):
    p = client.post("/api/projects",
                    json={"name": "重建对照项目", "ontology": "software-dev",
                          "requirement": "rebuild"}).json()
    before = client.get("/api/system/event-store-stats").json()

    # 走真实重建端点（内部会恢复引导管理员；裸调 projections.rebuild 会连
    # users 投影一起清掉，admin 身份随投影消失）
    assert client.post("/api/system/rebuild-projections").status_code == 200

    after = client.get("/api/system/event-store-stats").json()
    # 统计是纯读不参与投影：事件流本身不动，统计必须逐字段一致
    assert after == before
