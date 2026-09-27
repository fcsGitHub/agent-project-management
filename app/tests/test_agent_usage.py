"""M62-I188 Agent 用量聚合（docs/01 §BG.3，Langfuse spend 面的组织内翻译）：
runs 自 M44 已记账（tokens/estimated_cost_usd 入 runs 投影），本端点是纯读
侧聚合——按 agent_role 汇总可见项目内的 run 数/完成率/token/成本（事件溯源
红利第十四例：账本事件已在流中，聚合零埋点）。完成率=成功/(成功+失败)，
interrupted/running 不稀释；_visible 口径防泄漏；rebuild 一致。"""
from __future__ import annotations

import pytest

from apm import config
from apm.core import events


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


def _mk_project(client, name: str) -> str:
    return client.post("/api/projects",
                       json={"name": name, "ontology": "software-dev",
                             "requirement": "usage"}).json()["id"]


def _run(client, pid: str, run_id: str, role: str, outcome: str,
         tin: int = 0, tout: int = 0, cost: float = 0.0) -> None:
    """Deterministic run ledger: requested → started → tokens → terminal."""
    events.emit(event_type="run.requested", agg_type="run", agg_id=run_id,
                project_id=pid, actor_type="human", actor_id="u_admin",
                payload={"agent_role": role, "instruction": "x",
                         "conversation_id": f"conv_{run_id}"})
    events.emit(event_type="run.started", agg_type="run", agg_id=run_id,
                project_id=pid, actor_type="system", actor_id="runtime",
                payload={})
    if tin or tout or cost:
        events.emit(event_type="run.tokens_recorded", agg_type="run", agg_id=run_id,
                    project_id=pid, actor_type="system", actor_id="runtime",
                    payload={"input_tokens": tin, "output_tokens": tout,
                             "estimated_cost_usd": cost})
    if outcome == "succeeded":
        events.emit(event_type="run.succeeded", agg_type="run", agg_id=run_id,
                    project_id=pid, actor_type="system", actor_id="runtime",
                    payload={"outcome": "done", "output": {}})
    elif outcome == "failed":
        events.emit(event_type="run.failed", agg_type="run", agg_id=run_id,
                    project_id=pid, actor_type="system", actor_id="runtime",
                    payload={"error": "boom"})


def test_agent_usage_aggregates_roles(client, tmp_data, isolated_ontologies):
    pa = _mk_project(client, "用量项目A")
    _run(client, pa, "r_u1", "planner", "succeeded", tin=100, tout=50, cost=0.02)
    _run(client, pa, "r_u2", "planner", "failed", tin=80, tout=30, cost=0.01)
    _run(client, pa, "r_u3", "coder", "succeeded", tin=10, tout=90, cost=0.005)
    _run(client, pa, "r_u4", "coder", "running")  # 非终态计次不稀释完成率

    u = client.get("/api/portfolio/agent-usage").json()
    assert u["days"] == 30
    by_role = {r["agent_role"]: r for r in u["roles"]}
    planner = by_role["planner"]
    assert planner["runs"] == 2 and planner["succeeded"] == 1 and planner["failed"] == 1
    assert planner["success_rate"] == 0.5  # interrupted/running 不进分母
    assert planner["input_tokens"] == 180 and planner["output_tokens"] == 80
    assert planner["cost_usd"] == 0.03
    assert planner["projects"] == 1
    coder = by_role["coder"]
    assert coder["runs"] == 2 and coder["success_rate"] == 1.0
    assert coder["succeeded"] == 1  # running 不算成功
    # 排序：成本降序（planner 0.03 > coder 0.005）
    assert [r["agent_role"] for r in u["roles"]] == ["planner", "coder"]
    assert u["totals"]["runs"] == 4
    assert u["totals"]["cost_usd"] == 0.035
    assert u["totals"]["input_tokens"] == 190

    # rebuild 一致（纯读聚合，账本在 runs 投影里）
    from apm.core import projections
    projections.ensure_handlers_registered()
    projections.rebuild()
    u2 = client.get("/api/portfolio/agent-usage").json()
    assert u2 == u


def test_agent_usage_visible_scoped(client, tmp_data, isolated_ontologies, monkeypatch):
    p_visible = _mk_project(client, "用量可见项目")
    p_hidden = _mk_project(client, "用量隐藏项目")
    _run(client, p_visible, "r_v1", "planner", "succeeded", tin=50, tout=20, cost=0.01)
    _run(client, p_hidden, "r_h1", "planner", "succeeded", tin=500, tout=200, cost=0.9)

    # network 模式下 qa-wang 非成员：隐藏项目的成本绝不计入
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "password": "qa-pass"})
    monkeypatch.setattr(config.settings, "auth_mode", "network")
    try:
        assert client.post("/api/auth/login",
                           json={"user_id": "qa-wang", "password": "qa-pass"}).status_code == 200
        u = client.get("/api/portfolio/agent-usage").json()
        assert u["roles"] == []  # qa-wang 无可见项目 → 空（不泄漏隐藏项目记账）
        assert u["totals"]["runs"] == 0

        # 成员视角：把 qa-wang 加进可见项目后只见该项目那一笔
        # （network 模式身份由会话 cookie 决定——重新登录回 admin）
        assert client.post("/api/auth/login",
                           json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
        assert client.post(f"/api/projects/{p_visible}/members",
                           json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200
        client.post("/api/auth/login", json={"user_id": "qa-wang", "password": "qa-pass"})
        u2 = client.get("/api/portfolio/agent-usage").json()
        assert u2["totals"]["runs"] == 1
        assert u2["totals"]["cost_usd"] == 0.01  # 隐藏项目 0.9 未混入
    finally:
        config.settings.admin_password = ""


def test_agent_usage_window_and_empty(client, tmp_data, isolated_ontologies):
    # 无 run 时诚实空表
    _mk_project(client, "用量空项目")
    u = client.get("/api/portfolio/agent-usage").json()
    assert u["roles"] == [] and u["totals"]["runs"] == 0
    # days 收敛进 [1, 365]
    assert client.get("/api/portfolio/agent-usage", params={"days": 0}).json()["days"] == 1
    assert client.get("/api/portfolio/agent-usage", params={"days": 9999}).json()["days"] == 365
