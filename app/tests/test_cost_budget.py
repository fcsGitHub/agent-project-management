"""M66-I200 run 成本预算护栏（docs/01 §BK.3，LiteLLM 软阈+硬顶范式的
项目域翻译）：start_run 事前预检当月 runs 投影 SUM(estimated_cost_usd)——
runs 自 M44 已记账（红利再现：护栏只是读侧比对，零新表零埋点）；
≥预算 402 硬顶拒绝（automation 派发路径既有 HTTPException 兜底承接），
≥80% 软阈 warning 随响应。预算=项目设置走 project.updated 链。"""
from __future__ import annotations

import pytest

from apm import config
from apm.core import db, events


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


def _mk_project(client, name: str, budget: float | None) -> str:
    pid = client.post("/api/projects",
                      json={"name": name, "ontology": "software-dev",
                            "requirement": "预算"}).json()["id"]
    if budget is not None:
        r = client.patch(f"/api/projects/{pid}", json={"cost_budget_usd": budget})
        assert r.status_code == 200
    return pid


def _seed_cost(pid: str, run_id: str, cost: float) -> None:
    """Deterministic ledger: requested → started → tokens (cost)."""
    events.emit(event_type="run.requested", agg_type="run", agg_id=run_id,
                project_id=pid, actor_type="human", actor_id="u_admin",
                payload={"agent_role": "planner-agent", "instruction": "x",
                         "conversation_id": f"conv_{run_id}"})
    events.emit(event_type="run.started", agg_type="run", agg_id=run_id,
                project_id=pid, actor_type="system", actor_id="runtime",
                payload={})
    events.emit(event_type="run.tokens_recorded", agg_type="run", agg_id=run_id,
                project_id=pid, actor_type="system", actor_id="runtime",
                payload={"input_tokens": 100, "output_tokens": 50,
                         "estimated_cost_usd": cost})


def _real_conv(client, pid: str) -> str:
    return client.post("/api/conversations",
                       json={"project_id": pid, "kind": "executing",
                             "instruction": "真实起跑"}).json()["id"]


def test_hard_cap_blocks_new_run_with_402(client, tmp_data, isolated_ontologies):
    pid = _mk_project(client, "硬顶项目", budget=0.05)
    _seed_cost(pid, "r_cb1", cost=0.04)
    _seed_cost(pid, "r_cb2", cost=0.03)  # month spend 0.07 ≥ 0.05

    budget = client.get(f"/api/projects/{pid}/cost-budget").json()
    assert budget["cost_budget_usd"] == 0.05
    assert budget["month_spend_usd"] == pytest.approx(0.07)
    assert budget["ratio"] >= 1

    cid = _real_conv(client, pid)
    r = client.post("/api/runs", json={"conversation_id": cid,
                                       "agent_role": "planner-agent", "wait": True})
    assert r.status_code == 402
    assert "预算" in r.json()["detail"]
    # no new run entered the ledger — the gate fires before any emit
    n = db.get_conn().execute(
        "SELECT COUNT(*) AS n FROM runs WHERE project_id = ?", (pid,)).fetchone()["n"]
    assert n == 2


def test_soft_threshold_warns_but_allows(client, tmp_data, isolated_ontologies):
    pid = _mk_project(client, "软阈项目", budget=0.10)
    _seed_cost(pid, "r_cb3", cost=0.09)  # 90% — warn band

    cid = _real_conv(client, pid)
    r = client.post("/api/runs", json={"conversation_id": cid,
                                       "agent_role": "planner-agent", "wait": True})
    assert r.status_code == 200
    run = r.json()
    assert run["budget_warning"]["month_spend_usd"] == pytest.approx(0.09)
    assert run["budget_warning"]["cost_budget_usd"] == 0.10


def test_no_budget_no_warning_and_rebuild_stable(client, tmp_data, isolated_ontologies):
    pid = _mk_project(client, "无预算项目", budget=None)
    _seed_cost(pid, "r_cb4", cost=5.0)  # spend without a cap burns free

    before = client.get(f"/api/projects/{pid}/cost-budget").json()
    assert before["cost_budget_usd"] is None and before["ratio"] is None

    cid = _real_conv(client, pid)
    r = client.post("/api/runs", json={"conversation_id": cid,
                                       "agent_role": "planner-agent", "wait": True})
    assert r.status_code == 200
    assert "budget_warning" not in r.json()

    # a zero budget means the guard is off (PATCH can't express None-clear)
    client.patch(f"/api/projects/{pid}", json={"cost_budget_usd": 0.01})
    _seed_cost(pid, "r_cb5", cost=0.5)
    cid2 = _real_conv(client, pid)
    assert client.post("/api/runs", json={"conversation_id": cid2,
                                          "agent_role": "planner-agent"}).status_code == 402

    # budget setting rides project.updated — rebuild-stable
    assert client.post("/api/system/rebuild-projections").status_code == 200
    after = client.get(f"/api/projects/{pid}/cost-budget").json()
    assert after["cost_budget_usd"] == 0.01
    assert client.post("/api/runs", json={"conversation_id": cid2,
                                          "agent_role": "planner-agent"}).status_code == 402
