"""M117 Triage 分诊域（docs/01 §DH，候选池①转正·Linear intake 语义）：
外部入流（intake/IMAP）落本体 `triage` 中间态等人决定——accept（→概念
initial_status+可选指派走 item.assigned 既有链）/decline（→概念 cancelled
组状态——按本体解析非硬编码）/snooze（items.snoozed_until 列+事件投影；
sweep 第八员到期复浮——暂缓不是丢弃）。决定全走事件链 rebuild 稳定；队列
读面复用 list_items(status=)（事件溯源红利：零新读端点）。路由住 items
id-path 白名单前缀——网络写中间件天然管辖，台账零新增（M80 语义）。"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm.core import db, events
from apm.core.projections import on

router = APIRouter(tags=["triage"])

_ACTIONS = ("accept", "decline", "snooze")


# ------------------------------------------------------------ projection
@on("item.triage_snoozed")
def _proj_triage_snoozed(conn, e):
    """snoozed_until 的唯一写者（事件链：snooze 设值/复浮与 accept 清空）。"""
    conn.execute(
        "UPDATE items SET snoozed_until = ?, updated_at = ?, version = version + 1"
        " WHERE id = ?",
        (e.payload.get("until"), e.ts, e.agg_id),
    )


# ---------------------------------------------------------------- helpers
def _concept(project_id: str, concept_id: str):
    from apm.domains.items import project_ontology

    onto = project_ontology(project_id)
    return onto.concepts.get(concept_id)


def intake_landing_status(project_id: str, concept_id: str) -> str | None:
    """M117-I357: 外部入流的落点解析——概念声明 triage 态则落 triage（等人
    决定），否则缺省 initial_status（generic.yaml 等未声明本体行为零变化）。"""
    concept = _concept(project_id, concept_id)
    if not concept:
        return None
    return "triage" if any(s["id"] == "triage" for s in concept.states) else None


def _cancelled_status(project_id: str, concept_id: str) -> str:
    concept = _concept(project_id, concept_id)
    if not concept:
        raise HTTPException(status_code=422, detail=f"unknown concept '{concept_id}'")
    for s in concept.states:
        if s["group"] == "cancelled":
            return s["id"]
    raise HTTPException(
        status_code=422,
        detail=f"concept '{concept_id}' declares no cancelled-group status to decline into")


class TriageIn(BaseModel):
    action: str
    days: int = 3
    assignee_id: str | None = None


@router.post("/items/{item_id}/triage")
def post_triage(item_id: str, body: TriageIn) -> dict:
    from apm.domains.items import change_status, get_item

    item = get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"item {item_id} not found")
    if item["status"] != "triage":
        raise HTTPException(
            status_code=409,
            detail=f"工作项不在分诊中（当前 {item['status']}）——只有 triage 态可做分诊决定")
    if body.action not in _ACTIONS:
        raise HTTPException(status_code=422, detail=f"action must be one of {_ACTIONS}")

    if body.action == "snooze":
        if not 1 <= body.days <= 30:
            raise HTTPException(status_code=422, detail="days must be 1-30")
        until = (date.today() + timedelta(days=body.days)).isoformat()
        events.emit(event_type="item.triage_snoozed", agg_type="item", agg_id=item_id,
                    project_id=item["project_id"], payload={"until": until})
        return {"item_id": item_id, "action": "snooze", "snoozed_until": until}

    if body.action == "accept":
        concept = _concept(item["project_id"], item["concept_id"])
        target = concept.initial_status() if concept else "open"
        change_status(item, target)
        if body.assignee_id:
            from apm.domains.items import _ensure_human_assignee

            _ensure_human_assignee("human", body.assignee_id)
            events.emit(
                event_type="item.assigned", agg_type="item", agg_id=item_id,
                project_id=item["project_id"],
                payload={"assignee_type": "human", "assignee_id": body.assignee_id,
                         "from_assignee_type": item["assignee_type"],
                         "from_assignee_id": item["assignee_id"]},
            )
    else:  # decline
        change_status(item, _cancelled_status(item["project_id"], item["concept_id"]))

    if item.get("snoozed_until"):
        events.emit(event_type="item.triage_snoozed", agg_type="item", agg_id=item_id,
                    project_id=item["project_id"], payload={"until": None})
    fresh = get_item(item_id)
    return {"item_id": item_id, "action": body.action,
            "status": fresh["status"],
            "snoozed_until": fresh["snoozed_until"]}
