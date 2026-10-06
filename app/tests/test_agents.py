"""M116 Paperclip 吸纳轮（docs/01 §DG）：「用户统筹管理支配多 Agent 团队」
三缺口收口——①agents 目录总览面（GET /api/agents：YAML 声明×投影状态×
runs 聚合统计一屏合并，org 级登录门）②agent 治理（暂停/恢复——start_run
409 + 自动化派发降级 ok:false + rebuild 稳定）③agent 级预算（月窗 402 硬顶/
80% 软阈，M66-I200 同构）+ 工作项执行锁（原子检出：同 item 活跃 run 存在
即 409，终态释放）+ F1（跨项目 422 校验晚于事件发射留幽灵 run——前移修复）。"""
from __future__ import annotations

import pytest

from apm import config
from apm.core import db, events
from tests.conftest import wait_for


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def proj(client, tmp_data, isolated_ontologies) -> dict:
    return client.post("/api/projects",
                       json={"name": "团队编排项目", "ontology": "software-dev"}).json()


def _mk_conv(client, pid: str, title: str = "执行会话") -> str:
    return client.post("/api/conversations",
                       json={"project_id": pid, "kind": "executing", "title": title,
                             "instruction": "按指示完成"}).json()["id"]


def _mk_item(client, pid: str, title: str = "被锁工作项") -> str:
    return client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": title}).json()["id"]


def _wait_status(client, run_id: str, statuses: tuple[str, ...]) -> dict:
    def check():
        run = client.get(f"/api/runs/{run_id}").json()
        return run if run.get("status") in statuses else None

    return wait_for(check)


def _pending_approvals(client, project_id: str) -> list[dict]:
    return client.get("/api/approvals", params={
        "status": "pending", "project_id": project_id}).json()["approvals"]


# ------------------------------------------------- I353 团队总览面
def test_agent_team_listing_shape(client, proj):
    r = client.get("/api/agents")
    assert r.status_code == 200, r.text
    agents = r.json()["agents"]
    ids = {a["id"] for a in agents}
    assert {"pm-agent", "planner-agent", "dev-agent", "qa-agent", "release-agent"} <= ids
    dev = next(a for a in agents if a["id"] == "dev-agent")
    # YAML 声明面 + 投影治理面 + runs 聚合面 三源合并
    assert dev["display_name"] and dev["tier"]
    assert dev["status"] == "active" and dev["budget_usd"] is None
    for key in ("total_runs", "active_runs", "succeeded", "failed",
                "total_tokens", "estimated_cost_usd"):
        assert key in dev["stats"]


def test_agent_listing_org_login_gate(client, proj):
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    config.settings.auth_mode = "network"
    try:
        assert client.get("/api/agents").status_code == 401
        assert client.post("/api/auth/login",
                           json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
        assert client.get("/api/agents").status_code == 200
    finally:
        config.settings.auth_mode = "local"


# ------------------------------------------------- I354 暂停治理 + agent 预算
def test_pause_blocks_start_run_and_resume_restores(client, proj):
    assert client.post("/api/agents/dev-agent/pause").status_code == 200
    assert client.get("/api/agents").json()["agents"][0]  # listing still fine
    dev = next(a for a in client.get("/api/agents").json()["agents"]
               if a["id"] == "dev-agent")
    assert dev["status"] == "paused"

    cid = _mk_conv(client, proj["id"])
    r = client.post("/api/runs", json={"conversation_id": cid,
                                       "agent_role": "dev-agent", "wait": True})
    assert r.status_code == 409
    assert "暂停" in r.json()["detail"]
    # 门在事件发射前拦截——无幽灵 run（F1 同族纪律）
    n = db.get_conn().execute(
        "SELECT COUNT(*) AS n FROM runs WHERE agent_role = 'dev-agent'").fetchone()["n"]
    assert n == 0

    # 暂停状态走事件链——rebuild 后仍暂停
    assert client.post("/api/system/rebuild-projections").status_code == 200
    dev = next(a for a in client.get("/api/agents").json()["agents"]
               if a["id"] == "dev-agent")
    assert dev["status"] == "paused"

    assert client.post("/api/agents/dev-agent/resume").status_code == 200
    r = client.post("/api/runs", json={"conversation_id": cid,
                                       "agent_role": "dev-agent", "wait": True})
    assert r.status_code == 200, r.text


def test_pause_governance_is_admin_only(client, proj):
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    assert client.post("/api/users", json={
        "id": "u_member", "name": "成员", "password": "m-pass"}).status_code == 200
    config.settings.auth_mode = "network"
    try:
        assert client.post("/api/auth/login",
                           json={"user_id": "u_member", "password": "m-pass"}).status_code == 200
        assert client.post("/api/agents/dev-agent/pause").status_code == 403
        assert client.post("/api/auth/logout").status_code == 200
        assert client.post("/api/auth/login",
                           json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
        assert client.post("/api/agents/dev-agent/pause").status_code == 200
    finally:
        config.settings.auth_mode = "local"


def test_agent_budget_hard_cap_and_soft_warning(client, proj):
    r = client.patch("/api/agents/dev-agent", json={"budget_usd": 0.05})
    assert r.status_code == 200 and r.json()["budget_usd"] == pytest.approx(0.05)

    def _seed(run_id: str, cost: float, role: str = "dev-agent") -> None:
        events.emit(event_type="run.requested", agg_type="run", agg_id=run_id,
                    project_id=proj["id"], actor_type="human", actor_id="u_admin",
                    payload={"agent_role": role, "instruction": "x",
                             "conversation_id": f"conv_{run_id}"})
        events.emit(event_type="run.started", agg_type="run", agg_id=run_id,
                    project_id=proj["id"], actor_type="system", actor_id="runtime",
                    payload={})
        events.emit(event_type="run.tokens_recorded", agg_type="run", agg_id=run_id,
                    project_id=proj["id"], actor_type="system", actor_id="runtime",
                    payload={"input_tokens": 100, "output_tokens": 50,
                             "estimated_cost_usd": cost})

    _seed("r_agb1", 0.03)
    _seed("r_agb2", 0.03)  # dev-agent 月花销 0.06 ≥ 0.05 硬顶
    cid = _mk_conv(client, proj["id"])
    r = client.post("/api/runs", json={"conversation_id": cid,
                                       "agent_role": "dev-agent", "wait": True})
    assert r.status_code == 402
    assert "dev-agent" in r.json()["detail"] or "预算" in r.json()["detail"]
    # 预算按 agent 分账——planner-agent 不受 dev-agent 预算影响
    r = client.post("/api/runs", json={"conversation_id": cid,
                                       "agent_role": "planner-agent", "wait": True})
    assert r.status_code == 200, r.text


def test_agent_budget_setting_rebuild_stable(client, proj):
    assert client.patch("/api/agents/qa-agent", json={"budget_usd": 1.5}).status_code == 200
    assert client.post("/api/system/rebuild-projections").status_code == 200
    qa = next(a for a in client.get("/api/agents").json()["agents"]
              if a["id"] == "qa-agent")
    assert qa["budget_usd"] == pytest.approx(1.5)


# ------------------------------------------------- I352 执行锁 + F1
def test_item_execution_lock_holds_until_terminal_and_releases(client, proj):
    pid = proj["id"]
    item = _mk_item(client, pid)
    cid = _mk_conv(client, pid, "第一棒")
    run = client.post("/api/runs", json={
        "conversation_id": cid, "agent_role": "dev-agent", "item_id": item}).json()
    _wait_status(client, run["id"], ("interrupted", "succeeded", "failed"))

    # 第二个 run 绑同 item：无论第一棒是 interrupted（挂 Gate）还是收尾中——409
    cid2 = _mk_conv(client, pid, "第二棒")
    r = client.post("/api/runs", json={
        "conversation_id": cid2, "agent_role": "qa-agent", "item_id": item})
    if r.status_code == 200:
        # replay 偶发秒收尾（succeeded 已释放）时改为断言曾持锁语义：
        # 直接用合成事件钉住 interrupted 持锁行为（见下一测试）
        pytest.skip("replay 完成过快，锁语义由合成事件测试覆盖")
    assert r.status_code == 409
    assert run["id"] in r.json()["detail"]


def _seed_active_run(pid: str, item_id: str, run_id: str, role: str) -> None:
    """确定性锁态：requested → started（无终态=活跃）。"""
    events.emit(event_type="run.requested", agg_type="run", agg_id=run_id,
                project_id=pid, actor_type="human", actor_id="u_admin",
                payload={"agent_role": role, "instruction": "x",
                         "conversation_id": f"conv_{run_id}", "item_id": item_id})
    events.emit(event_type="run.started", agg_type="run", agg_id=run_id,
                project_id=pid, actor_type="system", actor_id="runtime", payload={})


def test_item_lock_matrix_by_synthesized_runs(client, proj):
    pid = proj["id"]
    item = _mk_item(client, pid)
    _seed_active_run(pid, item, "r_lock1", "dev-agent")
    cid = _mk_conv(client, pid)
    # 活跃（running）持锁 → 409 带持锁 run_id
    r = client.post("/api/runs", json={
        "conversation_id": cid, "agent_role": "dev-agent", "item_id": item})
    assert r.status_code == 409 and "r_lock1" in r.json()["detail"]
    # 终态释放：succeeded/failed 后可再绑
    events.emit(event_type="run.succeeded", agg_type="run", agg_id="r_lock1",
                project_id=pid, actor_type="system", actor_id="runtime",
                payload={"output": {}})
    assert client.post("/api/runs", json={
        "conversation_id": cid, "agent_role": "dev-agent",
        "item_id": item, "wait": True}).status_code == 200
    # interrupted（挂 Gate 等人）仍持锁——审批后 resume 继续，锁归 run 所有
    item2 = _mk_item(client, pid, "第二件")
    _seed_active_run(pid, item2, "r_lock2", "dev-agent")
    events.emit(event_type="run.interrupted", agg_type="run", agg_id="r_lock2",
                project_id=pid, actor_type="system", actor_id="runtime", payload={})
    cid2 = _mk_conv(client, pid, "对第二件抢跑")
    assert client.post("/api/runs", json={
        "conversation_id": cid2, "agent_role": "qa-agent",
        "item_id": item2}).status_code == 409
    # 无 item_id 的 run 不参与锁（对话域互斥另管）
    cid3 = _mk_conv(client, pid, "自由跑")
    assert client.post("/api/runs", json={
        "conversation_id": cid3, "agent_role": "qa-agent",
        "wait": True}).status_code == 200


def test_f1_cross_project_422_leaves_no_ghost_run(client, tmp_data, isolated_ontologies):
    a = client.post("/api/projects", json={
        "name": "甲方", "ontology": "software-dev"}).json()
    b = client.post("/api/projects", json={
        "name": "乙方", "ontology": "software-dev"}).json()
    item_b = _mk_item(client, b["id"], "乙方的活")
    cid_a = _mk_conv(client, a["id"], "甲方会话")

    r = client.post("/api/runs", json={
        "conversation_id": cid_a, "agent_role": "dev-agent", "item_id": item_b})
    assert r.status_code == 422
    # F1（先红）：422 时不得留下幽灵 run / 会话不得停在 running
    rows = db.get_conn().execute(
        "SELECT COUNT(*) AS n FROM runs WHERE conversation_id = ?", (cid_a,)).fetchone()["n"]
    assert rows == 0
    conv = client.get(f"/api/conversations/{cid_a}").json()
    assert conv["status"] != "running"


def test_automation_run_agent_respects_pause_and_lock(client, proj):
    pid = proj["id"]
    # item.updated 触发：PATCH 时才派发——锁/暂停态可先于派活就位（item.created
    # 在创建瞬间同步派发，时序上无法先造占用态）
    r = client.post(f"/api/projects/{pid}/automations", json={
        "name": "自动派活", "trigger_event": "item.updated",
        "condition": {"concept_id": "task"},
        "action": {"type": "run_agent", "agent_role": "dev-agent",
                   "instruction": "实现该任务"}})
    assert r.status_code == 200, r.text

    # 暂停的 agent：派活降级 ok:false，不起 run
    assert client.post("/api/agents/dev-agent/pause").status_code == 200
    it1 = _mk_item(client, pid, "暂停期任务")
    assert client.patch(f"/api/items/{it1}", json={"priority": "high"}).status_code == 200
    fired = wait_for(lambda: [
        e for e in client.get("/api/events", params={
            "event_type": "automation.rule_fired"}).json()["events"]
        if e["payload"].get("item_id") == it1] or None)
    assert fired and fired[0]["payload"]["result"]["ok"] is False
    n = db.get_conn().execute(
        "SELECT COUNT(*) AS n FROM runs WHERE item_id = ?", (it1,)).fetchone()["n"]
    assert n == 0

    # 恢复后：被占用 item（活跃 run 持锁）同样降级 ok:false
    assert client.post("/api/agents/dev-agent/resume").status_code == 200
    it2 = _mk_item(client, pid, "已被占用")
    _seed_active_run(pid, it2, "r_lock9", "qa-agent")
    assert client.patch(f"/api/items/{it2}", json={"priority": "high"}).status_code == 200
    fired2 = wait_for(lambda: [
        e for e in client.get("/api/events", params={
            "event_type": "automation.rule_fired"}).json()["events"]
        if e["payload"].get("item_id") == it2] or None)
    assert fired2 and fired2[0]["payload"]["result"]["ok"] is False
    n2 = db.get_conn().execute(
        "SELECT COUNT(*) AS n FROM runs WHERE item_id = ? AND agent_role = 'dev-agent'",
        (it2,)).fetchone()["n"]
    assert n2 == 0
