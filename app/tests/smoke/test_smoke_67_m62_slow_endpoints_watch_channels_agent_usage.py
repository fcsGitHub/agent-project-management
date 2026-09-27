"""Smoke 67 (M62): measure accurately → route correctly → account clearly —
① the endpoint-latency ring buckets record real requests per template route
and the slow-endpoint view reads them back; ② a watch rule with a channel
override reroutes delivery (in-app suppressed, override visible on the fact),
and resetting to follow-global restores it; ③ the agent-usage aggregation
reconciles against the runs ledger booked via events."""
from __future__ import annotations

import pytest

from apm import config
from apm.core import db, events
from apm.runtime import perf


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.mark.smoke
def test_smoke_67_m62_slow_endpoints_watch_channels_agent_usage(client, tmp_data,
                                                                 isolated_ontologies):
    # --- ① 慢端点观测：真实请求按模板路由入账，读侧可见 ------------------------
    p = client.post("/api/projects",
                    json={"name": "冒烟性能观测", "ontology": "software-dev",
                          "requirement": "observe"}).json()
    pid = p["id"]
    s = client.get("/api/system/slow-endpoints").json()
    assert s["threshold_ms"] > 0
    paths = {e["path"] for e in s["endpoints"]}
    assert "/api/projects" in paths, f"请求应按模板路径记账: {paths}"

    # --- ② 渠道覆盖与回退：仅邮件规则静默站内，回退后恢复 ----------------------
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert client.post(f"/api/projects/{pid}/watch-rules",
                       json={"event_type": "item.created",
                             "channels": ["email"]}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    client.post(f"/api/projects/{pid}/items",
                json={"concept_id": "task", "title": "仅邮件动态"})
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    notes = client.get("/api/notifications").json()["notifications"]
    assert not [n for n in notes if n["kind"] == "watch"]  # 站内被覆盖掉
    # 回退全局 → 站内恢复
    assert client.patch(f"/api/projects/{pid}/watch-rules/item.created",
                        json={"channels": []}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    client.post(f"/api/projects/{pid}/items",
                json={"concept_id": "task", "title": "回全局动态"})
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    wk = [n for n in client.get("/api/notifications").json()["notifications"]
          if n["kind"] == "watch"]
    assert len(wk) >= 1, "回退全局后站内应恢复"

    # --- ③ 用量聚合对账 runs 记账 ----------------------------------------------
    for i, (role, outcome, tin, tout, cost) in enumerate([
        ("smoke-planner", "succeeded", 200, 100, 0.02),
        ("smoke-planner", "failed", 50, 25, 0.005),
        ("smoke-coder", "succeeded", 20, 60, 0.004),
    ]):
        rid = f"r_smoke67_{i}"
        events.emit(event_type="run.requested", agg_type="run", agg_id=rid,
                    project_id=pid, actor_type="human", actor_id="u_admin",
                    payload={"agent_role": role, "instruction": "x",
                             "conversation_id": f"conv_{rid}"})
        events.emit(event_type="run.started", agg_type="run", agg_id=rid,
                    project_id=pid, actor_type="system", actor_id="runtime",
                    payload={})
        events.emit(event_type="run.tokens_recorded", agg_type="run", agg_id=rid,
                    project_id=pid, actor_type="system", actor_id="runtime",
                    payload={"input_tokens": tin, "output_tokens": tout,
                             "estimated_cost_usd": cost})
        if outcome == "succeeded":
            events.emit(event_type="run.succeeded", agg_type="run", agg_id=rid,
                        project_id=pid, actor_type="system", actor_id="runtime",
                        payload={"outcome": "done", "output": {}})
        else:
            events.emit(event_type="run.failed", agg_type="run", agg_id=rid,
                        project_id=pid, actor_type="system", actor_id="runtime",
                        payload={"error": "boom"})

    u = client.get("/api/portfolio/agent-usage").json()
    by_role = {r["agent_role"]: r for r in u["roles"]}
    planner = by_role["smoke-planner"]
    assert planner["runs"] == 2 and planner["success_rate"] == 0.5
    assert planner["input_tokens"] == 250 and planner["output_tokens"] == 125
    assert planner["cost_usd"] == 0.025
    # 对账：聚合输入 token = runs 投影合计（同账本两侧）
    ledger_in = db.get_conn().execute(
        "SELECT COALESCE(SUM(total_input_tokens), 0) AS n FROM runs"
        " WHERE agent_role = 'smoke-planner'").fetchone()["n"]
    assert planner["input_tokens"] == ledger_in
    assert u["totals"]["runs"] >= 3 and u["totals"]["cost_usd"] >= 0.029

    perf.reset()
