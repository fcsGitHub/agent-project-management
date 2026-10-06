"""Smoke 68 (M63): orchestration & noise-reduction on one line — ① an
automation rule with the run_agent action starts a real run when a human
edits an item; ② agent-authored/runtime facts do NOT re-trigger dispatch and
the 4th same-day trigger is honestly capped; ③ a member on "mentions_only"
keeps mention/assignment while participant noise is muted; ④ the item
checklist roundtrips (full-list overwrite, advisory version semantics)."""
from __future__ import annotations

import json

import pytest

from apm import config
from apm.core import db, events


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.mark.smoke
def test_smoke_68_m63_run_agent_notify_level_checklist(client, tmp_data,
                                                       isolated_ontologies):
    p = client.post("/api/projects",
                    json={"name": "冒烟编排降噪", "ontology": "software-dev"}).json()
    pid = p["id"]

    # --- ① run_agent：人类触发 → 真实 run 创建（automation 归账） --------------
    assert client.post(f"/api/projects/{pid}/automations", json={
        "name": "高优自动起跑", "trigger_event": "item.updated",
        "action": {"type": "run_agent", "agent_role": "planner-agent",
                   "instruction": "整理验收标准"}}).status_code == 200
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "编排项"}).json()
    client.patch(f"/api/items/{it['id']}", json={"priority": "high"})
    run_row = db.get_conn().execute(
        "SELECT agent_role, item_id FROM runs WHERE agent_role = 'planner-agent'"
        " ORDER BY started_at DESC LIMIT 1").fetchone()
    assert run_row is not None and run_row["item_id"] == it["id"]
    dispatched = client.get("/api/events", params={
        "event_type": "automation.agent_dispatched"}).json()["events"]
    assert dispatched[0]["payload"]["run_id"]

    # --- ② 防环：agent/runtime 事实不触发 dispatch；第 4 次触达日上限 -----------
    n_before = client.get("/api/events", params={
        "event_type": "automation.rule_fired"}).json()["total"]
    events.emit(event_type="item.updated", agg_type="item", agg_id=it["id"],
                project_id=pid, actor_type="agent", actor_id="planner-agent:r_x",
                payload={"priority": "low"})
    events.emit(event_type="item.updated", agg_type="item", agg_id=it["id"],
                project_id=pid, actor_type="system", actor_id="runtime:r_x",
                payload={"priority": "low"})
    assert client.get("/api/events", params={
        "event_type": "automation.rule_fired"}).json()["total"] == n_before
    # 同日内补满 3 次真实触发 → 第 4 次诚实拒绝（M116-I352：工作项原子检出锁后
    # 重复触发改用不同工作项——同 item 连打会先撞执行锁 409 而非日上限）
    for i in range(2):
        it_n = client.post(f"/api/projects/{pid}/items",
                           json={"concept_id": "task", "title": f"编排项补{i}"}).json()
        client.patch(f"/api/items/{it_n['id']}", json={"priority": "high"})
    it4 = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "task", "title": "编排项4"}).json()
    client.patch(f"/api/items/{it4['id']}", json={"priority": "high"})
    fired = client.get("/api/events", params={
        "event_type": "automation.rule_fired"}).json()["events"]
    assert fired[0]["payload"]["result"]["ok"] is False
    assert "每日上限" in fired[0]["payload"]["result"]["detail"]

    # --- ③ 通知降级：mentions_only 静参与面，提及照达 ---------------------------
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200
    it2 = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "task", "title": "降噪项"}).json()
    client.patch(f"/api/items/{it2['id']}",
                 json={"assignee_type": "human", "assignee_id": "qa-wang"})
    client.patch(f"/api/items/{it2['id']}", json={"status": "ready"})
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    client.post("/api/notifications/read", json={"all": True})
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    assert client.patch(f"/api/projects/{pid}/members/qa-wang/notify-level",
                        json={"level": "mentions_only"}).status_code == 200
    client.patch(f"/api/items/{it2['id']}", json={"status": "in_progress"})  # 参与面静音
    client.post(f"/api/items/{it2['id']}/comments", json={"body": "看一下 @QA 王"})
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    unread = [n for n in client.get("/api/notifications").json()["notifications"]
              if not n["read"]]
    kinds = [n["kind"] for n in unread]
    assert "item" not in kinds and "comment" not in kinds  # 参与面静音
    assert "mention" in kinds                              # 提及照达
    client.post("/api/session/identity", json={"user_id": "u_admin"})

    # --- ④ 检查清单 roundtrip：全量覆盖 + advisory（不推 version） --------------
    v0 = client.get(f"/api/items/{it2['id']}").json()["version"]
    assert client.patch(f"/api/items/{it2['id']}/checklist", json={"items": [
        {"text": "写部署文档", "done": True},
        {"text": "核对回滚", "done": False},
    ]}).status_code == 200
    got = client.get(f"/api/items/{it2['id']}").json()
    cl = json.loads(got["checklist"])
    assert cl[0]["done"] is True and cl[1]["done"] is False
    assert got["version"] == v0  # advisory：版本不 bump
    cl[1]["done"] = True
    assert client.patch(f"/api/items/{it2['id']}/checklist",
                        json={"items": cl}).status_code == 200
    assert client.post("/api/system/rebuild-projections").status_code == 200
    got2 = client.get(f"/api/items/{it2['id']}").json()
    assert json.loads(got2["checklist"])[1]["done"] is True  # rebuild 复现
