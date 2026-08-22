"""Scheduler: readiness-based dispatch + post-approval continuation.

The only component allowed to start runs on its own (docs/02 §4): reacts to
gate approvals (auto-chaining PRD→WBS) and exposes batch start for items whose
depends_on blockers are all done.
"""
from __future__ import annotations

from apm.core import db
from apm.runtime.engine import start_run


def on_run_succeeded(run_id: str, decision: dict) -> None:
    """Auto-chain after a gate approval (flow 0 step 7: PRD approved → planner)."""
    if (decision or {}).get("decision") != "approved":
        return
    from apm.runtime.engine import get_run

    run = get_run(run_id)
    if not run:
        return
    next_role = ROLE_CHAIN_FOR(run)
    if not next_role:
        return
    from apm.domains.conversations import create_conversation, get_conversation

    conv = get_conversation(run["conversation_id"]) or {}
    feature_id = conv.get("feature_id")
    title = "计划确认" if next_role == "planner-agent" else f"{next_role} 接续"
    new_conv = create_conversation(
        project_id=run["project_id"] or "",
        feature_id=feature_id,
        kind="drafting",
        title=title,
        instruction="基于已批准的 PRD 起草 WBS 并请求计划确认",
        actor_type="system",
        actor_id="orchestrator",
    )
    start_run(
        conversation_id=new_conv["id"],
        agent_role=next_role,
        graph_node_id=run.get("graph_node_id"),
        actor_type="system",
        actor_id="orchestrator",
    )


def ROLE_CHAIN_FOR(run: dict) -> str | None:
    from apm.orchestrator.state_machine import ROLE_CHAIN

    return ROLE_CHAIN.get(run.get("agent_role") or "")


def blockers_for(item_id: str) -> list[dict]:
    """Items this item depends_on (from_item → to_item semantics)."""
    rows = db.get_conn().execute(
        "SELECT ir.*, i.title, i.status, i.status_group FROM item_relations ir"
        " JOIN items i ON i.id = ir.to_item"
        " WHERE ir.from_item = ? AND ir.relation_type = 'depends_on'",
        (item_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def ready_reason(item: dict) -> str | None:
    """None when ready to start; otherwise a human-readable blocker reason."""
    if item.get("assignee_type") != "agent" or not item.get("assignee_id"):
        return "未指派 Agent 角色"
    if item.get("status_group") == "done":
        return "已完成"
    if item.get("status_group") == "in_progress":
        return "进行中"
    for b in blockers_for(item["id"]):
        if b["status_group"] != "done":
            return f"被 {b['title']}（{b['status']}）阻塞"
    return None


def start_item(item: dict, actor_type: str = "human", actor_id: str = "u_admin") -> dict:
    """Create (or reuse) an executing conversation and launch the assigned agent."""
    from apm.domains.conversations import create_conversation, get_conversation

    role = item.get("assignee_id") or "dev-agent"
    existing = db.get_conn().execute(
        "SELECT c.* FROM conversations c JOIN runs r ON r.conversation_id = c.id"
        " WHERE c.item_id = ? AND r.status IN ('running', 'interrupted')"
        " ORDER BY c.updated_at DESC LIMIT 1",
        (item["id"],),
    ).fetchone()
    if existing:
        return {"item_id": item["id"], "run_id": None, "conversation_id": existing["id"],
                "reused": True}
    conv = create_conversation(
        project_id=item["project_id"],
        feature_id=item.get("feature_id"),
        kind="executing",
        title=f"{item['title']} 执行",
        instruction=f"为 {item['title']} 生成实现并自测",
        item_id=item["id"],
        actor_type=actor_type,
        actor_id=actor_id,
    )
    run = start_run(
        conversation_id=conv["id"],
        agent_role=role,
        item_id=item["id"],
        graph_node_id=item["id"],
        actor_type=actor_type,
        actor_id=actor_id,
    )
    return {"item_id": item["id"], "run_id": run["id"], "conversation_id": conv["id"],
            "reused": False}


def batch_start(item_ids: list[str], actor_type: str = "human", actor_id: str = "u_admin") -> dict:
    from apm.domains.items import get_item

    started, skipped = [], []
    for iid in item_ids:
        item = get_item(iid)
        if not item:
            skipped.append({"item_id": iid, "reason": "不存在"})
            continue
        reason = ready_reason(item)
        if reason:
            skipped.append({"item_id": iid, "reason": reason})
            continue
        started.append(start_item(item, actor_type=actor_type, actor_id=actor_id))
    return {"started": started, "skipped": skipped}
