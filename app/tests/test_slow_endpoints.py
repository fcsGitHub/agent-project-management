"""M62-I186 端点性能观测（docs/01 §BG.1，「先测后治」的延迟版——BF.1 姊妹
题）：ASGI 计时中间件按路径记账进内存环形桶（计数/均值/最大），超阈值样本
入有界环；遥测是运行时数据不是领域事实，绝不进事件流（token_delta 瞬态
同理——M46 裁决）；admin 门与其它系统面同口径；SQLite 索引审计发现的热点
缺索引（watch_rules post-emit hook 查询）入 schema。"""
from __future__ import annotations

import pytest

from apm import config
from apm.core import db
from apm.runtime import perf


@pytest.fixture(autouse=True)
def _restore_identity_and_perf():
    saved = config.settings.user_id
    saved_threshold = perf.SLOW_THRESHOLD_MS
    perf.reset()
    yield
    config.settings.user_id = saved
    perf.SLOW_THRESHOLD_MS = saved_threshold
    perf.reset()


def test_perf_middleware_accounts_per_route(client):
    # 同一模板路径（/api/projects/{project_id}/items）多次请求应聚合到一行，
    # 而非按原始 URL 每个实例一行（route.path 而非 scope["path"]）
    p = client.post("/api/projects",
                    json={"name": "计时项目", "ontology": "software-dev",
                          "requirement": "perf"}).json()
    for i in range(3):
        client.post(f"/api/projects/{p['id']}/items",
                    json={"concept_id": "task", "title": f"计时项{i}"})

    s = perf.snapshot()
    item_routes = [e for e in s["endpoints"] if e["path"] == "/api/projects/{project_id}/items"]
    assert len(item_routes) == 1
    assert item_routes[0]["count"] >= 3
    assert item_routes[0]["max_ms"] >= item_routes[0]["mean_ms"] > 0
    # 计时中间件外层包裹：再发一个 /health 请求，路径应带挂载前缀入账
    assert client.get("/api/health").status_code == 200
    s2 = perf.snapshot()
    health_rows = [e for e in s2["endpoints"] if e["path"] == "/api/health"]
    assert len(health_rows) == 1 and health_rows[0]["count"] >= 1


def test_perf_slow_samples_ring_and_threshold(client, monkeypatch):
    perf.SLOW_THRESHOLD_MS = 0.01  # 任何真实请求都算「慢」→ 样本环必进
    monkeypatch.setattr(perf, "SLOW_THRESHOLD_MS", 0.01)
    client.get("/api/health")
    s = perf.snapshot()
    assert s["threshold_ms"] == 0.01
    assert s["slow_samples"], "阈值 0.01ms 下 health 请求应留慢样本"
    top = s["slow_samples"][0]
    assert {"path", "method", "status", "ms", "ts"} <= set(top)
    assert top["status"] == 200


def test_perf_record_unit_and_admin_gate(client, monkeypatch):
    # 纯单元：record 直灌超阈值样本与普通样本
    perf.record("/api/x", "GET", 200, 1234.5)
    perf.record("/api/x", "GET", 200, 5.0)
    s = perf.snapshot()
    row = next(e for e in s["endpoints"] if e["path"] == "/api/x")
    assert row["count"] == 2
    assert row["max_ms"] == 1234.5
    assert row["mean_ms"] == round((1234.5 + 5.0) / 2, 1)  # snapshot 均值一位小数
    assert s["slow_samples"][0]["ms"] == 1234.5

    # admin 门：network 模式已登录非 admin 403（与 event-store-stats 同口径）
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "password": "qa-pass"})
    monkeypatch.setattr(config.settings, "auth_mode", "network")
    try:
        assert client.post("/api/auth/login",
                           json={"user_id": "qa-wang", "password": "qa-pass"}).status_code == 200
        assert client.get("/api/system/slow-endpoints").status_code == 403
        assert client.post("/api/auth/login",
                           json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
        ok = client.get("/api/system/slow-endpoints")
        assert ok.status_code == 200
        assert ok.json()["endpoints"]
    finally:
        config.settings.admin_password = ""


def test_watch_rules_hit_index_present():
    # 索引审计落点：post-emit hook 的最热写路径查询必须走索引（审计前 SCAN）
    plan = db.get_conn().execute(
        "EXPLAIN QUERY PLAN SELECT * FROM watch_rules"
        " WHERE project_id = ? AND event_type = ? AND paused = 0",
        ("p", "item.created")).fetchall()
    detail = " ".join(r[3] for r in plan)
    assert "USING INDEX idx_watch_rules_hit" in detail
