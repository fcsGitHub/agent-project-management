"""M63-I189 自动化 run_agent 动作（docs/01 §BH.1）：自动化规则面补上第七个
动作——规则命中即对命中工作项起真实 agent run（经 start_run 标准链，Gate/
审批/token 记账不受影响）。防环是第一设计约束（Zapier/n8n 共识：反馈环是
自动化×agent 头号事故源）——三闸：①TRIGGERS 不扩 run.* ②agent 写回与
runtime:* 事实不再触发 dispatch（果不是因）③每规则每日 ≤3 次（automation.
agent_dispatched 事件计数零新表）。"""
from __future__ import annotations

import pytest

from apm import config
from apm.core import db, events


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    return client.post("/api/projects",
                       json={"name": "自动化运行项目", "ontology": "software-dev"}).json()["id"]


def _mk_rule(client, pid: str, trigger: str = "item.updated",
             role: str = "planner-agent", instruction: str = "整理该工作项的验收标准") -> str:
    r = client.post(f"/api/projects/{pid}/automations", json={
        "name": "自动起跑", "trigger_event": trigger,
        "action": {"type": "run_agent", "agent_role": role, "instruction": instruction}})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_run_agent_rule_creates_and_validates(client, project):
    # 坏角色/坏指令在写入侧 422（fail-closed）
    assert client.post(f"/api/projects/{project}/automations", json={
        "name": "坏角色", "trigger_event": "item.updated",
        "action": {"type": "run_agent", "agent_role": "no-such-role",
                   "instruction": "x"}}).status_code == 422
    assert client.post(f"/api/projects/{project}/automations", json={
        "name": "空指令", "trigger_event": "item.updated",
        "action": {"type": "run_agent", "agent_role": "planner-agent",
                   "instruction": "  "}}).status_code == 422
    assert client.post(f"/api/projects/{project}/automations", json={
        "name": "超长指令", "trigger_event": "item.updated",
        "action": {"type": "run_agent", "agent_role": "planner-agent",
                   "instruction": "x" * 201}}).status_code == 422
    rid = _mk_rule(client, project)
    rules = client.get(f"/api/projects/{project}/automations").json()["rules"]
    assert len(rules) == 1 and rules[0]["action"]["type"] == "run_agent"
    assert client.delete(f"/api/projects/{project}/automations/{rid}").status_code == 200


def test_run_agent_dispatch_starts_real_run(client, project):
    _mk_rule(client, project)
    it = client.post(f"/api/projects/{project}/items",
                     json={"concept_id": "task", "title": "自动起跑项"}).json()
    # 人类触发 item.updated → dispatch → run 真实创建（automation 归账）
    r = client.patch(f"/api/items/{it['id']}", json={"priority": "high"})
    assert r.status_code == 200

    row = db.get_conn().execute(
        "SELECT agent_role, project_id, item_id FROM runs"
        " WHERE agent_role = 'planner-agent' ORDER BY started_at DESC LIMIT 1").fetchone()
    assert row is not None and row["project_id"] == project and row["item_id"] == it["id"]

    dispatched = client.get("/api/events", params={
        "event_type": "automation.agent_dispatched"}).json()["events"]
    assert len(dispatched) == 1
    assert dispatched[0]["payload"]["item_id"] == it["id"]
    assert dispatched[0]["payload"]["agent_role"] == "planner-agent"

    fired = client.get("/api/events", params={
        "event_type": "automation.rule_fired"}).json()["events"]
    assert fired and fired[0]["payload"]["result"]["ok"] is True

    # agent 写回（actor_type=agent）与 runtime:* 事实不再触发 dispatch——防环
    n_before = client.get("/api/events", params={
        "event_type": "automation.rule_fired"}).json()["total"]
    events.emit(event_type="item.updated", agg_type="item", agg_id=it["id"],
                project_id=project, actor_type="agent", actor_id="planner-agent:r_x",
                payload={"priority": "low"})
    events.emit(event_type="item.updated", agg_type="item", agg_id=it["id"],
                project_id=project, actor_type="system", actor_id="runtime:r_x",
                payload={"priority": "low"})
    n_after = client.get("/api/events", params={
        "event_type": "automation.rule_fired"}).json()["total"]
    assert n_after == n_before, "agent/runtime 事实不得再触发 dispatch"


def test_run_agent_daily_cap(client, project):
    _mk_rule(client, project)
    # M116-I352：工作项原子检出锁后，同一 item 不再允许并行多 run——
    # 日上限测试前提改为三个不同 item 各触发一次（断言强度不变，
    # I78 纪律：功能提升使旧前提失效属正常演进）。
    items = [client.post(f"/api/projects/{project}/items",
                         json={"concept_id": "task", "title": f"限流项{i}"}).json()
             for i in range(3)]
    for it in items:
        client.patch(f"/api/items/{it['id']}", json={"priority": "high"})
    # 前三次各起一个 run（automation.agent_dispatched 计 3）
    assert client.get("/api/events", params={
        "event_type": "automation.agent_dispatched"}).json()["total"] == 3
    # 第 4 次：日上限拒绝——不再起 run，rule_fired 结果诚实记录
    it4 = client.post(f"/api/projects/{project}/items",
                      json={"concept_id": "task", "title": "限流项4"}).json()
    client.patch(f"/api/items/{it4['id']}", json={"priority": "high"})
    assert client.get("/api/events", params={
        "event_type": "automation.agent_dispatched"}).json()["total"] == 3
    # /api/events 为 id 降序（最新在前）——第 4 次尝试的 rule_fired 在最前
    fired = client.get("/api/events", params={
        "event_type": "automation.rule_fired"}).json()["events"]
    last = fired[0]["payload"]["result"]
    assert last["ok"] is False and "每日上限" in last["detail"]


def test_run_agent_reuses_item_conversation(client, project):
    """已有会话的工作项复用该会话起 run；无会话则建自动化归账的新会话。"""
    _mk_rule(client, project)
    it = client.post(f"/api/projects/{project}/items",
                     json={"concept_id": "task", "title": "会话复用项"}).json()
    conv = client.post("/api/conversations", json={
        "project_id": project, "kind": "executing",
        "title": "既有会话", "item_id": it["id"]}).json()
    client.patch(f"/api/items/{it['id']}", json={"priority": "high"})
    row = db.get_conn().execute(
        "SELECT conversation_id FROM runs WHERE agent_role = 'planner-agent'"
        " ORDER BY started_at DESC LIMIT 1").fetchone()
    assert row["conversation_id"] == conv["id"]
    # 无会话项：新建会话按 automation 归账（conversation.created actor=automation）
    it2 = client.post(f"/api/projects/{project}/items",
                      json={"concept_id": "task", "title": "无会话项"}).json()
    client.patch(f"/api/items/{it2['id']}", json={"priority": "high"})
    convs = client.get("/api/conversations",
                       params={"project_id": project}).json()["conversations"]
    auto_conv = [c for c in convs if c.get("item_id") == it2["id"]]
    assert auto_conv and auto_conv[0]["title"].startswith("自动化 ·")
