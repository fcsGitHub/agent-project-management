"""Automation rules (M9-I29): per-project event×condition×action bindings in the
shape of Kanboard's Automatic Actions plus the n8n trigger-condition-action
model (docs/01 §H). The rules themselves are event-sourced (automation.rule_*)
and the executor subscribes via the post-emit hook — the event kernel is the
event source, no dispatcher of its own. Loop safety: events authored by the
engine (actor_type="automation") and any emit made while dispatching never
re-enter the engine (single-layer execution)."""
from __future__ import annotations

import json
import threading
from contextvars import ContextVar

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on
from apm.domains.items import (
    _ensure_human_assignee,
    _find_field,
    _validate_custom_fields,
    change_status,
    get_item,
    project_ontology,
)
from apm.domains.projects import require_project

router = APIRouter(tags=["automations"])

TRIGGERS = ("item.created", "item.updated", "item.status_changed", "item.assigned")
SCHEDULE_TRIGGER = "schedule:daily"  # I98: YouTrack On-schedule semantics — evaluated
# by the daily sweep, never by dispatch (not in TRIGGERS).
PRIORITIES = ("high", "medium", "low")
BUILTIN_CONDITION_FIELDS = {
    "title", "priority", "status", "status_group",
    "assignee_type", "assignee_id",
    "overdue",  # I98: derived at sweep time (due past & not done/cancelled)
}
ACTION_TYPES = ("assign", "set_priority", "set_field", "set_status", "notify",
                "create_recurring")
_valid_trigger_events = (*TRIGGERS, SCHEDULE_TRIGGER)

_dispatching: ContextVar[bool] = ContextVar("apm_automation_dispatching", default=False)
_installed = False
_scheduler_thread: threading.Thread | None = None


# ---------------------------------------------------------------- projectors
@on("automation.rule_created")
def _proj_rule_created(conn, e):
    p = e.payload
    conn.execute(
        "INSERT INTO automation_rules (id, project_id, name, trigger_event, condition_json,"
        " action_json, enabled, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (e.agg_id, e.project_id, p["name"], p["trigger_event"],
         json.dumps(p.get("condition") or {}, ensure_ascii=False),
         json.dumps(p["action"], ensure_ascii=False),
         1 if p.get("enabled", True) else 0, e.ts, e.ts),
    )


@on("automation.rule_updated")
def _proj_rule_updated(conn, e):
    p = e.payload
    sets, params = [], []
    for key in ("name", "trigger_event"):
        if key in p:
            sets.append(f"{key} = ?")
            params.append(p[key])
    if "condition" in p:
        sets.append("condition_json = ?")
        params.append(json.dumps(p["condition"] or {}, ensure_ascii=False))
    if "action" in p:
        sets.append("action_json = ?")
        params.append(json.dumps(p["action"], ensure_ascii=False))
    if "enabled" in p:
        sets.append("enabled = ?")
        params.append(1 if p["enabled"] else 0)
    if sets:
        sets.append("updated_at = ?")
        params.extend([e.ts, e.agg_id])
        conn.execute(f"UPDATE automation_rules SET {', '.join(sets)} WHERE id = ?", params)


@on("automation.rule_deleted")
def _proj_rule_deleted(conn, e):
    conn.execute("DELETE FROM automation_rules WHERE id = ?", (e.agg_id,))


# ---------------------------------------------------------------- helpers
def _rule_row(rule_id: str):
    return db.get_conn().execute(
        "SELECT * FROM automation_rules WHERE id = ?", (rule_id,)).fetchone()


def _parse_rule(row) -> dict:
    r = dict(row)
    r["condition"] = json.loads(r.pop("condition_json") or "{}")
    r["action"] = json.loads(r.pop("action_json") or "{}")
    r["enabled"] = bool(r["enabled"])
    return r


def list_rules(project_id: str) -> list[dict]:
    rows = db.get_conn().execute(
        "SELECT * FROM automation_rules WHERE project_id = ? ORDER BY created_at, id",
        (project_id,),
    ).fetchall()
    return [_parse_rule(r) for r in rows]


def _project_ontology(project_id: str):
    return project_ontology(project_id)


def _validate_condition(onto, condition: dict) -> None:
    if not isinstance(condition, dict) or set(condition) - {"concept_id", "fields"}:
        raise HTTPException(
            status_code=422,
            detail="condition keys must be a subset of {concept_id, fields}")
    concept_id = condition.get("concept_id")
    if concept_id is not None:
        try:
            onto.concept(concept_id)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"unknown concept '{concept_id}': {e}")
    fields = condition.get("fields") or {}
    if not isinstance(fields, dict):
        raise HTTPException(status_code=422, detail="condition.fields must be an object")
    declared_ids = {f["id"] for c in onto.concepts.values() for f in c.fields}
    for k, v in fields.items():
        if k not in BUILTIN_CONDITION_FIELDS and k not in declared_ids:
            raise HTTPException(
                status_code=422,
                detail=f"condition field '{k}' is neither builtin nor declared in ontology")
        if not isinstance(v, (str, int, float, bool)):
            raise HTTPException(
                status_code=422, detail=f"condition field '{k}' value must be a scalar")


def _validate_action(onto, project_id: str, condition: dict, action: dict) -> None:
    if not isinstance(action, dict):
        raise HTTPException(status_code=422, detail="action must be an object")
    atype = action.get("type")
    if atype not in ACTION_TYPES:
        raise HTTPException(status_code=422, detail=f"action.type must be one of {ACTION_TYPES}")
    if atype == "assign":
        uid = action.get("user_id")
        if not uid or not db.get_conn().execute(
                "SELECT 1 FROM users WHERE id = ?", (uid,)).fetchone():
            raise HTTPException(status_code=422, detail=f"unknown user '{uid}'")
    elif atype == "notify":
        uid = action.get("user_id")
        if not uid or not db.get_conn().execute(
                "SELECT 1 FROM users WHERE id = ?", (uid,)).fetchone():
            raise HTTPException(status_code=422, detail=f"unknown user '{uid}'")
        message = action.get("message")
        if message is not None and (not isinstance(message, str) or len(message) > 200):
            raise HTTPException(status_code=422, detail="notify.message must be a string ≤200 chars")
    elif atype == "set_priority":
        if action.get("value") not in PRIORITIES:
            raise HTTPException(status_code=422, detail=f"priority must be one of {PRIORITIES}")
    elif atype == "set_field":
        fid = action.get("field_id")
        field = _find_field(onto, fid) if fid else None
        if not field:
            raise HTTPException(
                status_code=422, detail=f"action field '{fid}' is not declared in ontology")
        # 类型与项目级停用校验复用工作项同一条 fail-closed 路径（M6-I20/M7-I25）。
        _validate_custom_fields(onto, field_owner_concept(onto, fid), {fid: action.get("value")},
                                project_id=project_id)
    elif atype == "set_status":
        concept_id = condition.get("concept_id")
        if concept_id:  # 概念未定时退到运行时校验（动作随命中项的概念判定）
            try:
                onto.validate_item_status(concept_id, action.get("status"))
            except Exception as e:
                raise HTTPException(status_code=422, detail=f"invalid status: {e}")


def field_owner_concept(onto, field_id: str) -> str:
    """The first concept declaring `field_id` (mirrors items._find_field order)."""
    for concept in onto.concepts.values():
        if any(f.get("id") == field_id for f in concept.fields):
            return concept.id
    raise HTTPException(status_code=422, detail=f"field '{field_id}' is not declared")


def _validate_rule(project_id: str, trigger_event: str, condition: dict, action: dict) -> None:
    if trigger_event not in _valid_trigger_events:
        raise HTTPException(status_code=422, detail=f"trigger_event must be one of {_valid_trigger_events}")
    onto = _project_ontology(project_id)
    _validate_condition(onto, condition)
    if action.get("type") == "create_recurring":
        concept_id = action.get("concept_id")
        if not concept_id or concept_id not in onto.concepts:
            raise HTTPException(status_code=422, detail="create_recurring needs a valid action.concept_id")
        title = action.get("title")
        if not title or not isinstance(title, str) or len(title) > 200:
            raise HTTPException(status_code=422, detail="create_recurring needs action.title (≤200 chars)")
        return
    _validate_action(onto, project_id, condition, action)


def _condition_matches(rule: dict, item: dict) -> bool:
    cond = rule["condition"]
    if cond.get("concept_id") and item.get("concept_id") != cond["concept_id"]:
        return False
    cf = item.get("custom_fields") or {}
    if isinstance(cf, str):
        cf = json.loads(cf or "{}")
    for k, expected in (cond.get("fields") or {}).items():
        got = cf.get(k) if k not in BUILTIN_CONDITION_FIELDS else item.get(k)
        if isinstance(got, list):
            if expected not in got:
                return False
        elif got != expected:
            return False
    return True


def _execute_action(rule: dict, item: dict) -> dict:
    """Run one rule action with explicit automation attribution. Emits follow the
    same fold path as human edits; validation failures are captured, not raised."""
    act = rule["action"]
    atype, rid = act["type"], rule["id"]
    try:
        if atype == "assign":
            _ensure_human_assignee("human", act["user_id"])
            events.emit(
                event_type="item.assigned", agg_type="item", agg_id=item["id"],
                project_id=item["project_id"], actor_type="automation", actor_id=rid,
                payload={"assignee_type": "human", "assignee_id": act["user_id"]},
            )
            return {"type": atype, "ok": True, "detail": f"已指派给 {act['user_id']}"}
        if atype == "set_priority":
            events.emit(
                event_type="item.updated", agg_type="item", agg_id=item["id"],
                project_id=item["project_id"], actor_type="automation", actor_id=rid,
                payload={"priority": act["value"]},
            )
            return {"type": atype, "ok": True, "detail": f"优先级置为 {act['value']}"}
        if atype == "set_field":
            # 投影对 custom_fields 是整列覆盖（M6-I20 踩坑记录），必须合并现值。
            merged = dict(item.get("custom_fields") or {})
            merged[act["field_id"]] = act["value"]
            events.emit(
                event_type="item.updated", agg_type="item", agg_id=item["id"],
                project_id=item["project_id"], actor_type="automation", actor_id=rid,
                payload={"custom_fields": merged},
            )
            return {"type": atype, "ok": True,
                    "detail": f"字段 {act['field_id']} 置为 {act['value']!r}"}
        if atype == "set_status":
            change_status(item, act["status"], actor_type="automation", actor_id=rid)
            return {"type": atype, "ok": True, "detail": f"状态置为 {act['status']}"}
        if atype == "notify":
            summary = act.get("message") or f"规则「{rule['name']}」已触发"
            events.emit(
                event_type="notification.sent", agg_type="item", agg_id=item["id"],
                project_id=item["project_id"], actor_type="automation", actor_id=rid,
                payload={"user_id": act["user_id"], "summary": summary, "kind": "rule_notify"},
            )
            return {"type": atype, "ok": True, "detail": f"已通知 {act['user_id']}：{summary}"}
        return {"type": atype, "ok": False, "detail": f"未知动作类型 {atype}"}
    except HTTPException as e:
        return {"type": atype, "ok": False, "detail": f"动作被拒绝：{e.detail}"}


def dispatch(event: events.Event) -> None:
    """Post-emit hook: match enabled rules for this project+event and run them.
    Never raises; automation-authored events and dispatch-time emits are skipped
    (single-layer execution, docs/10 §M9)."""
    if event.actor_type == "automation" or _dispatching.get():
        return
    if not event.project_id or event.event_type not in TRIGGERS or event.agg_type != "item":
        return
    rows = db.get_conn().execute(
        "SELECT * FROM automation_rules WHERE project_id = ? AND trigger_event = ? AND enabled = 1"
        " ORDER BY created_at, id",
        (event.project_id, event.event_type),
    ).fetchall()
    if not rows:
        return
    item = get_item(event.agg_id)
    if item is None:
        return
    for row in rows:
        rule = _parse_rule(row)
        if not _condition_matches(rule, item):
            continue
        token = _dispatching.set(True)
        try:
            result = _execute_action(rule, item)
            events.emit(
                event_type="automation.rule_fired", agg_type="automation_rule",
                agg_id=rule["id"], project_id=event.project_id,
                actor_type="automation", actor_id=rule["id"],
                payload={
                    "rule_name": rule["name"],
                    "trigger_event": event.event_type,
                    "trigger_event_id": event.id,
                    "item_id": item["id"],
                    "item_title": item["title"],
                    "result": result,
                },
            )
        finally:
            _dispatching.reset(token)


def install_automation_engine() -> None:
    """Idempotent: wire the executor into the event kernel (called in lifespan)."""
    global _installed
    if not _installed:
        events.add_post_emit_hook(dispatch)
        _installed = True


# ---------------------------------------------------------------- I98: daily sweep
def _is_overdue(item: dict, today: str) -> bool:
    return bool(item.get("due_date")) and item["due_date"] < today and \
        item.get("status_group") not in ("done", "cancelled")


def _execute_recurring(rule: dict) -> dict:
    """create_recurring: emit a real item.created (automation-authored) so the
    recurring card is a first-class item with full audit and projections."""
    act = rule["action"]
    payload: dict = {"concept_id": act["concept_id"], "title": act["title"]}
    if act.get("assignee_id"):
        payload["assignee_type"] = "human"
        payload["assignee_id"] = act["assignee_id"]
    events.emit(
        event_type="item.created", agg_type="item", agg_id=new_id("i"),
        project_id=rule["project_id"], actor_type="automation", actor_id=rule["id"],
        payload=payload,
    )
    return {"type": "create_recurring", "ok": True, "detail": f"已创建「{act['title']}」"}


def _notify_due_soon(conn, today: str) -> int:
    """I105 (docs/01 §AG.2, Plane/Linear semantics): the sweep's built-in
    due-date reminder — the scheduling engine's first-class citizen app. One
    `item.due_soon_notified` per item per day (idempotent via the event
    stream itself, so force re-sweeps never duplicate); recipients resolve
    and both channels gate it downstream as kind "due_soon"."""
    from datetime import date as _date, timedelta as _timedelta

    from apm import config
    window = max(0, config.settings.due_soon_days)
    horizon = (_date.fromisoformat(today) + _timedelta(days=window)).isoformat()
    rows = conn.execute(
        "SELECT i.id, i.title, i.due_date, i.assignee_id, i.project_id"
        " FROM items i JOIN projects p ON p.id = i.project_id"
        " WHERE i.due_date IS NOT NULL AND i.due_date >= ? AND i.due_date <= ?"
        "   AND i.status_group NOT IN ('done', 'cancelled') AND i.archived_at IS NULL"
        "   AND i.assignee_type = 'human' AND i.assignee_id IS NOT NULL"
        "   AND COALESCE(p.status, '') != 'archived'",
        (today, horizon)).fetchall()
    notified = 0
    for r in rows:
        already = conn.execute(
            "SELECT 1 FROM events WHERE event_type = 'item.due_soon_notified'"
            " AND agg_id = ? AND substr(ts, 1, 10) = ? LIMIT 1",
            (r["id"], today)).fetchone()
        if already:
            continue
        events.emit(
            event_type="item.due_soon_notified", agg_type="item", agg_id=r["id"],
            project_id=r["project_id"], actor_type="automation", actor_id="scheduler",
            payload={"title": r["title"], "due_date": r["due_date"],
                     "assignee_id": r["assignee_id"], "sweep_date": today},
        )
        notified += 1
    return notified


def _delegate_time_off(conn, today: str) -> int:
    """I117 (docs/01 §AK.2, Atlassian "on leave until" automation): on the
    first day of a delegated time-off stretch the vacationer's active items in
    shared projects move to the delegate; on the last day they move back. Both
    moves are plain `item.assigned` events — the payload records
    original_assignee/delegate_off for the audit trail, the assignee
    notification fires through the existing channel. Idempotent by
    construction: each move only fires while the current assignee still
    matches the expected side, so force re-sweeps are no-ops and manual
    re-assignments during the stretch are never yanked."""
    moved = 0
    for off in conn.execute(
            "SELECT * FROM user_time_off WHERE delegate IS NOT NULL"
            " AND cancelled_at IS NULL AND ? IN (start_date, end_date)",
            (today,)).fetchall():
        first_day = today == off["start_date"]
        if first_day:
            rows = conn.execute(
                "SELECT i.id, i.project_id FROM items i"
                " JOIN project_members pm ON pm.project_id = i.project_id AND pm.user_id = ?"
                " WHERE i.assignee_id = ? AND i.status_group NOT IN ('done','cancelled')"
                " AND i.archived_at IS NULL",
                (off["delegate"], off["user_id"])).fetchall()
            extra = {"original_assignee": off["user_id"], "delegate_off": off["id"]}
        else:
            # move back only what this stretch delegated — identified by the
            # delegate_off marker on the first-day events, and only while the
            # item still sits with the delegate
            rows = conn.execute(
                "SELECT DISTINCT e.agg_id AS id, i.project_id FROM events e"
                " JOIN items i ON i.id = e.agg_id"
                " WHERE e.event_type = 'item.assigned'"
                " AND json_extract(e.payload, '$.delegate_off') = ?"
                " AND i.assignee_id = ?",
                (off["id"], off["delegate"])).fetchall()
            extra = {"delegate_off": off["id"]}
        for r in rows:
            events.emit(
                event_type="item.assigned", agg_type="item", agg_id=r["id"],
                project_id=r["project_id"], actor_type="automation", actor_id="scheduler",
                payload={"assignee_type": "human",
                         "assignee_id": off["delegate"] if first_day else off["user_id"],
                         **extra},
            )
            moved += 1
    return moved


def _remind_pending_approvals(conn, today: str) -> int:
    """I126/I130 (docs/01 §AN.2/§AO.3, ServiceNow timer→reminder→escalate):
    gate approvals pending longer than approval_reminder_days get an owner
    nudge — one `approval.pending_reminded` per approval per day (event-stream
    idempotent, same shape as the due_soon reminder). Past 2× the window the
    event carries escalated=true so instance admins are pulled in too."""
    from datetime import date as _date, timedelta as _timedelta

    from apm import config

    window = max(1, config.settings.approval_reminder_days)
    cutoff = (_date.fromisoformat(today) - _timedelta(days=window)).isoformat()
    rows = conn.execute(
        "SELECT id, project_id, kind, requested_at FROM approvals"
        " WHERE status = 'pending' AND requested_at IS NOT NULL"
        " AND project_id != '' AND substr(requested_at, 1, 10) <= ?",
        (cutoff,)).fetchall()
    reminded = 0
    for r in rows:
        already = conn.execute(
            "SELECT 1 FROM events WHERE event_type = 'approval.pending_reminded'"
            " AND agg_id = ? AND substr(ts, 1, 10) = ? LIMIT 1",
            (r["id"], today)).fetchone()
        if already:
            continue
        days = (_date.fromisoformat(today)
                - _date.fromisoformat(r["requested_at"][:10])).days
        escalated = days >= window * 2
        events.emit(
            event_type="approval.pending_reminded", agg_type="approval", agg_id=r["id"],
            project_id=r["project_id"], actor_type="automation", actor_id="scheduler",
            payload={"kind": r["kind"], "requested_at": r["requested_at"][:10],
                     "days_pending": days, "escalated": escalated},
        )
        reminded += 1
    return reminded


def _respawn_recurring(conn, today: str) -> int:
    """I133 (docs/01 §AP.3, YouTrack reset-workflow semantics): a task with
    recurrence_days=N respawns as a fresh copy N days after its completion —
    completion-driven cadence, complementary to the calendar-driven
    create_recurring. The respawn is a real item.created (full validation
    chain) whose follow-up `item.respawned` fact makes re-sweeps idempotent;
    assignee, cycle and the recurrence itself carry over to the new card."""
    from datetime import date as _date, timedelta as _timedelta

    from apm.domains.items import create_item

    spawned = 0
    rows = conn.execute(
        "SELECT i.*, MIN(substr(h.ts, 1, 10)) AS done_day FROM items i"
        " JOIN events h ON h.agg_id = i.id AND h.event_type = 'item.status_changed'"
        " AND json_extract(h.payload, '$.status_group') = 'done'"
        " WHERE i.recurrence_days IS NOT NULL AND i.recurrence_days > 0"
        " AND i.status_group = 'done'"
        " GROUP BY i.id HAVING MIN(substr(h.ts, 1, 10)) <= ?",
        (today,)).fetchall()
    for src in rows:
        due_day = (_date.fromisoformat(src["done_day"])
                   + _timedelta(days=src["recurrence_days"])).isoformat()
        if due_day > today:
            continue
        already = conn.execute(
            "SELECT 1 FROM events WHERE event_type = 'item.respawned'"
            " AND json_extract(payload, '$.respawn_of') = ? LIMIT 1",
            (src["id"],)).fetchone()
        if already:
            continue
        new_item = create_item(
            project_id=src["project_id"], concept_id=src["concept_id"],
            title=src["title"], priority=src["priority"],
            estimate_hours=src["estimate_hours"],
            actor_type="automation", actor_id="scheduler",
        )
        if src["assignee_id"]:
            events.emit(
                event_type="item.assigned", agg_type="item", agg_id=new_item["id"],
                project_id=src["project_id"], actor_type="automation",
                actor_id="scheduler",
                payload={"assignee_type": src["assignee_type"] or "human",
                         "assignee_id": src["assignee_id"]},
            )
        if src["cycle_id"]:
            events.emit(
                event_type="item.updated", agg_type="item", agg_id=new_item["id"],
                project_id=src["project_id"], actor_type="automation",
                actor_id="scheduler", payload={"cycle_id": src["cycle_id"]},
            )
        if src["recurrence_days"]:
            events.emit(
                event_type="item.updated", agg_type="item", agg_id=new_item["id"],
                project_id=src["project_id"], actor_type="automation",
                actor_id="scheduler",
                payload={"recurrence_days": src["recurrence_days"]},
            )
        events.emit(
            event_type="item.respawned", agg_type="item", agg_id=new_item["id"],
            project_id=src["project_id"], actor_type="automation", actor_id="scheduler",
            payload={"respawn_of": src["id"], "title": src["title"],
                     "recurrence_days": src["recurrence_days"]},
        )
        spawned += 1
    return spawned


def run_daily_sweep(force: bool = False) -> dict:
    """I98 (docs/01 §AE.1, YouTrack On-schedule semantics): evaluate every
    enabled `schedule:daily` rule once per day. Idempotency is a fact of the
    event stream — a `automation.swept` heartbeat with today's date means the
    sweep already ran (survives restarts and replays, zero new tables)."""
    conn = db.get_conn()
    today = events.utcnow()[:10]
    if not force:
        seen = conn.execute(
            "SELECT 1 FROM events WHERE event_type = 'automation.swept'"
            " AND substr(ts, 1, 10) = ? LIMIT 1", (today,)).fetchone()
        if seen:
            return {"swept": False, "date": today, "fired": 0, "created": 0,
                    "notified": 0, "delegated": 0, "carried": 0, "reminded": 0,
                    "respawned": 0}

    fired = created = notified = delegated = carried = reminded = 0
    rules = conn.execute(
        "SELECT * FROM automation_rules WHERE trigger_event = ? AND enabled = 1",
        (SCHEDULE_TRIGGER,)).fetchall()
    for row in rules:
        rule = _parse_rule(row)
        if rule["action"].get("type") == "create_recurring":
            result = _execute_recurring(rule)
            created += 1
        else:
            result = None
            for it in conn.execute(
                    "SELECT i.* FROM items i JOIN projects p ON p.id = i.project_id"
                    " WHERE i.project_id = ? AND COALESCE(p.status, '') != 'archived'",
                    (rule["project_id"],)).fetchall():
                item = dict(it)
                item["overdue"] = _is_overdue(item, today)  # derived, sweep-only field
                if not _condition_matches(rule, item):
                    continue
                result = _execute_action(rule, item)
                fired += 1
        if result is None:
            continue
        events.emit(
            event_type="automation.rule_fired", agg_type="automation_rule",
            agg_id=rule["id"], project_id=rule["project_id"],
            actor_type="automation", actor_id=rule["id"],
            payload={"rule_name": rule["name"], "trigger_event": SCHEDULE_TRIGGER,
                     "sweep_date": today, "result": result},
        )
    notified += _notify_due_soon(conn, today)
    delegated += _delegate_time_off(conn, today)
    carried = 0
    from apm.domains.cycles import carryover_finished_cycles
    carried += carryover_finished_cycles(conn, today)
    reminded += _remind_pending_approvals(conn, today)
    respawned = _respawn_recurring(conn, today)
    events.emit(
        event_type="automation.swept", agg_type="automation", agg_id="sweep",
        project_id="", actor_type="automation", actor_id="scheduler",
        payload={"date": today, "fired": fired, "created": created,
                 "notified": notified, "delegated": delegated, "carried": carried,
                 "reminded": reminded, "respawned": respawned},
    )
    return {"swept": True, "date": today, "fired": fired, "created": created,
            "notified": notified, "delegated": delegated, "carried": carried,
            "reminded": reminded, "respawned": respawned}


def _scheduler_loop() -> None:
    """Production ticker: wake up once a minute; the heartbeat check makes the
    actual sweep idempotent, so polling frequency is irrelevant to correctness.
    The I107 mailbox pass rides the same wake-up (its own imap_seen projection
    makes it idempotent per Message-ID)."""
    import logging
    import time

    logger = logging.getLogger("apm.automations")
    while True:
        time.sleep(60)
        try:
            run_daily_sweep()
        except Exception:  # the scheduler must survive anything
            logger.exception("daily sweep failed")
        try:
            from apm.domains.imap_in import poll_inbox
            poll_inbox()
        except Exception:
            logger.exception("imap poll failed")


def install_scheduler() -> None:
    """Idempotent: start the daily-sweep ticker thread (called in lifespan)."""
    global _scheduler_thread
    if _scheduler_thread is None or not _scheduler_thread.is_alive():
        _scheduler_thread = threading.Thread(target=_scheduler_loop,
                                             name="apm-scheduler", daemon=True)
        _scheduler_thread.start()


# ---------------------------------------------------------------- API
class RuleIn(BaseModel):
    name: str
    trigger_event: str
    condition: dict = {}
    action: dict
    enabled: bool = True


class RulePatch(BaseModel):
    name: str | None = None
    trigger_event: str | None = None
    condition: dict | None = None
    action: dict | None = None
    enabled: bool | None = None


@router.get("/projects/{project_id}/automations")
def get_rules(project_id: str) -> dict:
    require_project(project_id)
    return {"rules": list_rules(project_id)}


@router.post("/projects/{project_id}/automations")
def create_rule(project_id: str, body: RuleIn) -> dict:
    require_project(project_id)
    _validate_rule(project_id, body.trigger_event, body.condition, body.action)
    rid = new_id("ar")
    events.emit(
        event_type="automation.rule_created", agg_type="automation_rule", agg_id=rid,
        project_id=project_id,
        payload={"name": body.name, "trigger_event": body.trigger_event,
                 "condition": body.condition, "action": body.action,
                 "enabled": body.enabled},
    )
    return _parse_rule(_rule_row(rid))


@router.patch("/projects/{project_id}/automations/{rule_id}")
def patch_rule(project_id: str, rule_id: str, body: RulePatch) -> dict:
    require_project(project_id)
    row = _rule_row(rule_id)
    if not row or row["project_id"] != project_id:
        raise HTTPException(status_code=404, detail=f"rule {rule_id} not found")
    current = _parse_rule(row)
    merged = {
        "name": body.name if body.name is not None else current["name"],
        "trigger_event": body.trigger_event if body.trigger_event is not None else current["trigger_event"],
        "condition": body.condition if body.condition is not None else current["condition"],
        "action": body.action if body.action is not None else current["action"],
        "enabled": body.enabled if body.enabled is not None else current["enabled"],
    }
    _validate_rule(project_id, merged["trigger_event"], merged["condition"], merged["action"])
    payload = {k: v for k, v in merged.items() if v != current.get(k)}
    events.emit(
        event_type="automation.rule_updated", agg_type="automation_rule", agg_id=rule_id,
        project_id=project_id, payload=payload,
    )
    return _parse_rule(_rule_row(rule_id))


@router.delete("/projects/{project_id}/automations/{rule_id}")
def delete_rule(project_id: str, rule_id: str) -> dict:
    require_project(project_id)
    row = _rule_row(rule_id)
    if not row or row["project_id"] != project_id:
        raise HTTPException(status_code=404, detail=f"rule {rule_id} not found")
    events.emit(
        event_type="automation.rule_deleted", agg_type="automation_rule", agg_id=rule_id,
        project_id=project_id, payload={"name": row["name"]},
    )
    return {"rule_id": rule_id, "deleted": True}


@router.post("/projects/{project_id}/automations/{rule_id}/test")
def test_rule(project_id: str, rule_id: str) -> dict:
    """Dry-run (M9-I30 前端「测试运行」的后端): evaluate the rule against the most
    recent matching trigger event's item — report what WOULD happen, execute nothing."""
    require_project(project_id)
    row = _rule_row(rule_id)
    if not row or row["project_id"] != project_id:
        raise HTTPException(status_code=404, detail=f"rule {rule_id} not found")
    rule = _parse_rule(row)
    evs, _ = events.query_events(
        project_id=project_id, event_type=rule["trigger_event"], agg_type="item", limit=1)
    if not evs:
        return {"matched": False, "reason": "项目中还没有该触发类型的事件"}
    item = get_item(evs[0].agg_id)
    if item is None:
        return {"matched": False, "reason": "触发事件对应的工作项已不存在"}
    if not _condition_matches(rule, item):
        return {"matched": False, "reason": "最近一条触发事件不满足规则条件",
                "item_id": item["id"], "item_title": item["title"]}
    return {"matched": True, "item_id": item["id"], "item_title": item["title"],
            "action": rule["action"]}


@router.get("/projects/{project_id}/automations/{rule_id}/runs")
def rule_history(project_id: str, rule_id: str) -> dict:
    require_project(project_id)
    row = _rule_row(rule_id)
    if not row or row["project_id"] != project_id:
        raise HTTPException(status_code=404, detail=f"rule {rule_id} not found")
    evs, total = events.query_events(
        project_id=project_id, agg_type="automation_rule", agg_id=rule_id,
        event_type="automation.rule_fired", limit=50)
    return {"runs": [
        {"event_id": e.id, "ts": e.ts, **e.payload} for e in evs], "total": total}


class SweepIn(BaseModel):
    force: bool = False


@router.post("/automations/sweep")
def post_sweep(body: SweepIn) -> dict:
    """Manual trigger for the I98 daily sweep (the background ticker calls
    run_daily_sweep() without force on its own cadence)."""
    return run_daily_sweep(force=body.force)
