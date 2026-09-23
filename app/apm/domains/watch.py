"""User-defined watch rules (M54-I162, docs/01 §AY): 「人 × 项目 × 事件类型」
self-built notification rules — Jira filter subscription + GitHub custom
watch semantics on an event-sourced substrate. Rules are data, not code: a
`watch.added/removed` fact changes who gets notified, never the event stream.
Consumption is a post-emit hook (the mailer.enqueue mechanism): a matching
rule emits `notification.sent` kind=watch, and the existing projector applies
the per-kind channel pref while the mailer applies the email gate — two
channels, zero new ones. The whitelist deliberately excludes the notify
machinery itself so a watch can never recurse."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm.core import db, events
from apm.core.projections import on

router = APIRouter(tags=["watch"])

# Whitelist: the event types a user may watch. notification.sent / email.* /
# watch.* are excluded — a watch must never match the notify machinery
# (recursion) or plumbing facts nobody subscribes to.
WATCHABLE_EVENTS = (
    "item.created", "item.updated", "item.status_changed", "item.assigned",
    "comment.created",
    "approval.requested", "approval.decided",
    "risk.created", "risk.updated", "risk.closed",
    "expense.recorded",
    "attachment.created",
    "artifact.report_generated",
)


@on("watch.added")
def _proj_watch_added(conn, e):
    conn.execute(
        "INSERT INTO watch_rules (user_id, project_id, event_type, condition_json, created_at)"
        " VALUES (?,?,?,?,?) ON CONFLICT(user_id, project_id, event_type) DO NOTHING",
        (e.payload["user_id"], e.project_id, e.payload["event_type"],
         e.payload.get("condition_json"), e.ts),
    )


@on("watch.removed")
def _proj_watch_removed(conn, e):
    conn.execute(
        "DELETE FROM watch_rules WHERE user_id = ? AND project_id = ? AND event_type = ?",
        (e.payload["user_id"], e.project_id, e.payload["event_type"]),
    )


class WatchIn(BaseModel):
    event_type: str
    # M55-I165: optional payload conditions — flat dict, top-level payload
    # field → primitive expected value, ALL pairs must match (equality) for
    # the rule to deliver. No expression engine: flat equality covers the
    # 80% (「只关注完成」「只看新建」) without JEXL-style over-engineering.
    condition: dict = {}


_PRIMITIVES = (str, int, float, bool)


def _serialize_condition(condition: dict) -> str:
    if not isinstance(condition, dict):
        raise HTTPException(status_code=422, detail="condition must be an object")
    if len(condition) > 5:
        raise HTTPException(status_code=422, detail="condition supports at most 5 pairs")
    for k, v in condition.items():
        if not isinstance(k, str) or isinstance(v, (dict, list)) or v is None \
                or not isinstance(v, _PRIMITIVES):
            raise HTTPException(
                status_code=422,
                detail="condition values must be flat primitives (str/int/float/bool)")
    import json
    return json.dumps(condition, ensure_ascii=False) if condition else ""


def _require_member(project_id: str) -> str:
    from apm.domains.members import member_role
    from apm.domains.projects import require_project

    require_project(project_id)
    me = events.effective_actor()
    if not member_role(project_id, me):
        raise HTTPException(status_code=403, detail="project membership required")
    return me


@router.post("/projects/{project_id}/watch-rules")
def add_watch_rule(project_id: str, body: WatchIn) -> dict:
    me = _require_member(project_id)
    if body.event_type not in WATCHABLE_EVENTS:
        raise HTTPException(status_code=422,
                            detail=f"event_type must be one of {WATCHABLE_EVENTS}")
    conn = db.get_conn()
    if conn.execute(
            "SELECT 1 FROM watch_rules WHERE user_id = ? AND project_id = ? AND event_type = ?",
            (me, project_id, body.event_type)).fetchone():
        raise HTTPException(status_code=409, detail="already watching this event type")
    events.emit(
        event_type="watch.added", agg_type="project", agg_id=project_id,
        project_id=project_id,
        payload={"user_id": me, "event_type": body.event_type,
                 "condition_json": _serialize_condition(body.condition)},
    )
    return {"project_id": project_id, "user_id": me,
            "event_type": body.event_type, "watching": True}


@router.delete("/projects/{project_id}/watch-rules/{event_type}")
def remove_watch_rule(project_id: str, event_type: str) -> dict:
    me = _require_member(project_id)
    conn = db.get_conn()
    if not conn.execute(
            "SELECT 1 FROM watch_rules WHERE user_id = ? AND project_id = ? AND event_type = ?",
            (me, project_id, event_type)).fetchone():
        raise HTTPException(status_code=404, detail="not watching")
    events.emit(
        event_type="watch.removed", agg_type="project", agg_id=project_id,
        project_id=project_id,
        payload={"user_id": me, "event_type": event_type},
    )
    return {"project_id": project_id, "user_id": me,
            "event_type": event_type, "watching": False}


@router.get("/watch-rules")
def list_watch_rules() -> dict:
    """Own-data across projects — the bell-prefs management view."""
    me = events.effective_actor()
    rows = db.get_conn().execute(
        "SELECT w.project_id AS project_id, w.event_type AS event_type,"
        " w.created_at AS created_at, COALESCE(p.name, w.project_id) AS project_name,"
        " w.condition_json AS condition"
        " FROM watch_rules w LEFT JOIN projects p ON p.id = w.project_id"
        " WHERE w.user_id = ? ORDER BY w.created_at DESC", (me,)).fetchall()
    return {"rules": [dict(r) for r in rows]}


_hook_installed = False


def install_watcher() -> None:
    """Idempotent: wire the post-emit hook that turns matching watch rules
    into notification.sent facts (called in lifespan)."""
    global _hook_installed
    if _hook_installed:
        return
    _hook_installed = True
    events.add_post_emit_hook(_on_event)


def _on_event(event: events.Event) -> None:
    try:
        if event.event_type not in WATCHABLE_EVENTS or not event.project_id:
            return
        conn = db.get_conn()
        matched = [(r["user_id"], r["condition_json"]) for r in conn.execute(
            "SELECT user_id, condition_json FROM watch_rules"
            " WHERE project_id = ? AND event_type = ?"
            " ORDER BY user_id", (event.project_id, event.event_type)).fetchall()]
        if not matched:
            return
        # I165: subscription-side payload filter — ALL condition pairs must
        # equal the payload values; empty condition = match everything
        def _hit(condition_json: str | None) -> bool:
            if not condition_json:
                return True
            import json
            try:
                cond = json.loads(condition_json)
            except Exception:
                return True  # 写入侧已校验；防御坏数据不吞通知
            return all(event.payload.get(k) == v for k, v in cond.items())
        matched = [(uid, cj) for uid, cj in matched if _hit(cj)]
        if not matched:
            return
        # context for the summary: item title when the event is item-scoped
        title = None
        if event.event_type.startswith("item."):
            row = conn.execute("SELECT title FROM items WHERE id = ?",
                               (event.agg_id,)).fetchone()
            title = row["title"] if row else None
        name_row = conn.execute("SELECT name FROM projects WHERE id = ?",
                                (event.project_id,)).fetchone()
        pname = name_row["name"] if name_row else event.project_id
        seen: set[str] = set()
        for uid, _cj in matched:
            if uid in seen:
                continue  # 多规则命中单份（同一事件同一用户）
            seen.add(uid)
            if event.actor_id == uid:
                continue  # 自事件抑制：自己动作的结果不提醒自己
            suffix = f"「{title}」" if title else ""
            events.emit(
                event_type="notification.sent", agg_type="project",
                agg_id=event.project_id, project_id=event.project_id,
                payload={"user_id": uid, "kind": "watch",
                         "summary": f"关注的项目「{pname}」有新动态：{event.event_type} {suffix}"},
            )
    except Exception:  # the hook must never break the write path
        logging.getLogger("apm.watch").exception("watch hook failed after #%s", event.id)
