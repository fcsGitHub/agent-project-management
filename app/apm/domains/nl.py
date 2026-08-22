"""NL command layer (UI-Agent L1): intent → app API actions (docs/06 §5).

L1 scope: navigation / filtering / selection / bulk approve. The parser is a
deterministic rule engine over the ontology entity dictionary — the "replay"
implementation of the UI-Agent; an openai_compat model path can replace it
behind the same interface later (capability seam).
"""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm import config
from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on

router = APIRouter(tags=["nl"])

PAGE_WORDS: list[tuple[str, str]] = [
    ("看板", "/p/{pid}/board"), ("任务板", "/p/{pid}/board"), ("board", "/p/{pid}/board"),
    ("图", "/p/{pid}/graph"), ("流程图", "/p/{pid}/graph"), ("graph", "/p/{pid}/graph"),
    ("对话", "/p/{pid}/conversations"), ("会话", "/p/{pid}/conversations"),
    ("轨迹", "/p/{pid}/runs"), ("运行", "/p/{pid}/runs"), ("runs", "/p/{pid}/runs"),
    ("资产", "/assets"), ("资产库", "/assets"),
    ("审计", "/p/{pid}/audit"), ("日志", "/p/{pid}/audit"),
    ("本体", "/p/{pid}/ontology"),
    ("审批", "/p/{pid}/approvals"), ("审批中心", "/p/{pid}/approvals"),
    ("仪表盘", "/p/{pid}"), ("dashboard", "/p/{pid}"), ("首页", "/p/{pid}"),
]

PRIORITY_WORDS = [
    (("高优先级", "高优", "重要的", "high"), "high"),
    (("中优先级", "中优", "medium"), "medium"),
    (("低优先级", "低优", "不重要的", "low"), "low"),
]


class UICommandIn(BaseModel):
    utterance: str
    page_state: dict | None = None


class UICommandConfirm(BaseModel):
    pass


# ------------------------------------------------------------ projections
@on("ui_command.executed")
def _proj_ui_command(conn, e):
    p = e.payload
    conn.execute(
        "INSERT OR REPLACE INTO ui_commands (id, utterance, page_state, actions, status, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (
            e.agg_id,
            p.get("utterance", ""),
            json.dumps(p.get("page_state") or {}, ensure_ascii=False),
            json.dumps(p.get("actions") or [], ensure_ascii=False),
            p.get("status", "executed"),
            e.ts,
        ),
    )


# ------------------------------------------------------------------ parser
def parse(utterance: str, page_state: dict | None) -> list[dict]:
    """Rules (L1). Each action: {action, label, params, read_only}."""
    text = utterance.strip()
    actions: list[dict] = []
    pid = (page_state or {}).get("project_id", "")

    # navigation
    for word, tpl in PAGE_WORDS:
        if re.search(rf"(打开|切换到|去|进入|看看?|显示)\s*[项目]?\s*{word}|^{word}$", text):
            actions.append({
                "action": "navigate",
                "label": f"打开{word}页",
                "params": {"path": tpl.format(pid=pid)},
                "read_only": True,
            })
            break

    # priority filter
    for words, value in PRIORITY_WORDS:
        if any(w in text for w in words) and any(k in text for k in ("只看", "过滤", "筛选", "显示")):
            actions.append({
                "action": "set_filter",
                "label": f"过滤：只看{value}优先级任务",
                "params": {"priority": value},
                "read_only": True,
            })
            break
        if any(w in text for w in words) and not actions:
            actions.append({
                "action": "set_filter",
                "label": f"过滤：只看{value}优先级任务",
                "params": {"priority": value},
                "read_only": True,
            })
            break

    # assignee filter (agent roles)
    for role in ("dev-agent", "planner-agent", "pm-agent", "release-agent", "qa-agent", "architect-agent"):
        if role in text or role.replace("-agent", "") in text:
            actions.append({
                "action": "set_filter",
                "label": f"过滤：只看 {role} 的卡片",
                "params": {"assignee": role},
                "read_only": True,
            })
            break

    # bulk approve (write)
    if re.search(r"(批量|全部|所有).{0,6}(批准|通过|审批)", text) or re.search(r"(批准|通过).{0,4}(全部|所有)", text):
        actions.append({
            "action": "bulk_approve",
            "label": "批量批准当前待审批项",
            "params": {"project_id": pid},
            "read_only": False,
        })

    return actions


def candidates() -> list[str]:
    return [
        "只看高优先级任务", "只看 dev-agent 的卡片", "打开看板", "打开审计页",
        "打开资产库", "批量批准全部待审批", "打开项目图",
    ]


# -------------------------------------------------------------------- API
@router.post("/ui_commands")
def post_ui_command(body: UICommandIn) -> dict:
    page_state = dict(body.page_state or {})
    if "project_id" not in page_state:
        route = str(page_state.get("route", ""))
        m = re.search(r"/p/([^/]+)", route)
        if m:
            page_state["project_id"] = m.group(1)
    actions = parse(body.utterance, page_state)
    if not actions:
        raise HTTPException(
            status_code=422,
            detail={"message": "无法解析该指令（L1 级：导航/过滤/批量审批）", "candidates": candidates()},
        )
    requires_confirmation = any(not a["read_only"] for a in actions)
    cmd_id = new_id("uic")
    status_value = "pending_confirm" if requires_confirmation else "executed"
    if not requires_confirmation:
        events.emit(
            event_type="ui_command.executed",
            agg_type="ui_command",
            agg_id=cmd_id,
            project_id=page_state.get("project_id", ""),
            actor_type="ui_agent",
            actor_id=f"ui-agent:on_behalf_of={config.settings.user_id}",
            payload={
                "utterance": body.utterance,
                "page_state": page_state,
                "actions": actions,
                "status": status_value,
            },
        )
    else:
        db.get_conn().execute(
            "INSERT INTO ui_commands (id, utterance, page_state, actions, status, created_at)"
            " VALUES (?,?,?,?,?,datetime('now'))",
            (cmd_id, body.utterance, json.dumps(page_state, ensure_ascii=False),
             json.dumps(actions, ensure_ascii=False), status_value),
        )
        db.get_conn().commit()
    return {
        "id": cmd_id,
        "actions": actions,
        "requires_confirmation": requires_confirmation,
        "reply": f"已解析 {len(actions)} 个动作" + ("，写操作需确认" if requires_confirmation else ""),
    }


@router.post("/ui_commands/{cmd_id}/confirm")
def confirm_ui_command(cmd_id: str) -> dict:
    row = db.get_conn().execute(
        "SELECT * FROM ui_commands WHERE id = ?", (cmd_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="ui_command not found")
    if row["status"] != "pending_confirm":
        raise HTTPException(status_code=422, detail=f"command is {row['status']}")
    actions = json.loads(row["actions"])
    page_state = json.loads(row["page_state"] or "{}")
    results = []
    for a in actions:
        if a["action"] == "bulk_approve":
            from apm.domains.approvals import decide, DecisionIn
            from apm.orchestrator.gates import pending_approvals

            pid = a["params"].get("project_id") or page_state.get("project_id")
            approved = 0
            for apr in pending_approvals(pid or None):
                try:
                    decide(apr["id"], DecisionIn(decision="approved", comment="ui_command 批量批准"))
                    approved += 1
                except HTTPException:
                    pass
            results.append({"action": "bulk_approve", "approved": approved})
    events.emit(
        event_type="ui_command.executed",
        agg_type="ui_command",
        agg_id=cmd_id,
        project_id=page_state.get("project_id", ""),
        actor_type="ui_agent",
        actor_id=f"ui-agent:on_behalf_of={config.settings.user_id}",
        payload={
            "utterance": row["utterance"],
            "page_state": page_state,
            "actions": actions,
            "results": results,
            "status": "executed",
        },
    )
    return {"status": "executed", "results": results}
