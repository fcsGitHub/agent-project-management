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
    # M58-I174 (docs/01 §BC): agent-run outcomes join the watchable set —
    # completion/failure are the notify-worthy moments (Superset/Solo/Devin
    # consensus; CI failure-first discipline). run.interrupted stays out: a
    # gate pause already notifies via approval.requested, and dual copies
    # would break the M55 noise budget. Process facts (requested/started/
    # tokens/spans) remain bookkeeping, not news.
    "run.succeeded", "run.failed",
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


@on("watch.updated")
def _proj_watch_updated(conn, e):
    # M57-I171: in-place edit / pause (Zapier toggle semantics — paused keeps
    # the config). Full-row upsert; created_at survives via COALESCE.
    conn.execute(
        "INSERT INTO watch_rules (user_id, project_id, event_type, condition_json, paused, created_at)"
        " VALUES (?,?,?,?,?,COALESCE((SELECT created_at FROM watch_rules"
        "  WHERE user_id = ? AND project_id = ? AND event_type = ?), ?))"
        " ON CONFLICT(user_id, project_id, event_type) DO UPDATE SET"
        " condition_json=excluded.condition_json, paused=excluded.paused",
        (e.payload["user_id"], e.project_id, e.payload["event_type"],
         e.payload.get("condition_json"), 1 if e.payload.get("paused") else 0,
         e.payload["user_id"], e.project_id, e.payload["event_type"], e.ts),
    )


class WatchIn(BaseModel):
    event_type: str
    # M55-I165: optional payload conditions — flat dict, top-level payload
    # field → primitive expected value, ALL pairs must match (equality) for
    # the rule to deliver. No expression engine: flat equality covers the
    # 80% (「只关注完成」「只看新建」) without JEXL-style over-engineering.
    condition: dict = {}


class WatchTemplateRule(BaseModel):
    event_type: str
    condition: dict = {}


class WatchImportIn(BaseModel):
    rules: list[WatchTemplateRule]


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


def _parse_condition(condition_json: str | None) -> dict:
    if not condition_json:
        return {}
    import json
    try:
        cond = json.loads(condition_json)
    except Exception:
        return {}
    return cond if isinstance(cond, dict) else {}


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


class WatchPatchIn(BaseModel):
    # M57-I171: both optional — omit a field to keep it unchanged.
    condition: dict | None = None
    paused: bool | None = None


@router.patch("/projects/{project_id}/watch-rules/{event_type}")
def patch_watch_rule(project_id: str, event_type: str, body: WatchPatchIn) -> dict:
    """In-place edit / pause (M57-I171, docs/01 §BB.1): change the condition or
    toggle paused without the delete+recreate dance — the rule's identity and
    created_at survive, one `watch.updated` fact carries the full new state,
    and paused rules simply stop matching at the hook (config preserved)."""
    me = _require_member(project_id)
    conn = db.get_conn()
    row = conn.execute(
        "SELECT condition_json, paused FROM watch_rules"
        " WHERE user_id = ? AND project_id = ? AND event_type = ?",
        (me, project_id, event_type)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="not watching")
    cond_json = _serialize_condition(body.condition) \
        if body.condition is not None else row["condition_json"]
    paused = bool(row["paused"]) if body.paused is None else body.paused
    events.emit(
        event_type="watch.updated", agg_type="project", agg_id=project_id,
        project_id=project_id,
        payload={"user_id": me, "event_type": event_type,
                 "condition_json": cond_json, "paused": paused},
    )
    return {"project_id": project_id, "user_id": me,
            "event_type": event_type, "paused": paused}


@router.get("/watch-rules")
def list_watch_rules() -> dict:
    """Own-data across projects — the bell-prefs management view."""
    me = events.effective_actor()
    rows = db.get_conn().execute(
        "SELECT w.project_id AS project_id, w.event_type AS event_type,"
        " w.created_at AS created_at, COALESCE(p.name, w.project_id) AS project_name,"
        " w.condition_json AS condition, w.paused AS paused"
        " FROM watch_rules w LEFT JOIN projects p ON p.id = w.project_id"
        " WHERE w.user_id = ? ORDER BY w.created_at DESC", (me,)).fetchall()
    return {"rules": [dict(r) for r in rows]}


@router.get("/watch-rules/export")
def export_watch_rules() -> dict:
    """Own rules as a project-agnostic template (M56-I168, docs/01 §BA.1):
    distinct {event_type, condition} pairs with user/project stripped, so the
    JSON re-applies to any project the importer is a member of. Jira ships no
    filter/subscription export at all — rules being events makes this native."""
    me = events.effective_actor()
    rows = db.get_conn().execute(
        "SELECT event_type, condition_json FROM watch_rules WHERE user_id = ?"
        " ORDER BY created_at DESC", (me,)).fetchall()
    seen: dict[tuple[str, tuple], None] = {}
    for r in rows:
        cond = _parse_condition(r["condition_json"])
        seen.setdefault((r["event_type"], tuple(sorted(cond.items()))), None)
    return {"version": 1, "rules": [
        {"event_type": et, "condition": dict(pairs)} for et, pairs in seen]}


@router.post("/projects/{project_id}/watch-rules/import")
def import_watch_rules(project_id: str, body: WatchImportIn) -> dict:
    """Apply a shared template (M56-I168): fill what's missing, keep what's
    there — an existing rule (user×project×event_type) is never clobbered,
    matching the projection's ON CONFLICT DO NOTHING semantics; the count
    report makes the outcome honest. Re-validation runs the same whitelist +
    condition serializer as the manual add path."""
    me = _require_member(project_id)
    if len(body.rules) > 50:
        raise HTTPException(status_code=422, detail="template supports at most 50 rules")
    conn = db.get_conn()
    imported = skipped = 0
    for i, rule in enumerate(body.rules):
        if rule.event_type not in WATCHABLE_EVENTS:
            raise HTTPException(
                status_code=422,
                detail=f"rules[{i}]: event_type must be one of {WATCHABLE_EVENTS}")
        try:
            cond_json = _serialize_condition(rule.condition)
        except HTTPException as e:
            raise HTTPException(status_code=422, detail=f"rules[{i}]: {e.detail}")
        if conn.execute(
                "SELECT 1 FROM watch_rules WHERE user_id = ? AND project_id = ? AND event_type = ?",
                (me, project_id, rule.event_type)).fetchone():
            skipped += 1  # already watching this event type — template won't clobber
            continue
        events.emit(
            event_type="watch.added", agg_type="project", agg_id=project_id,
            project_id=project_id,
            payload={"user_id": me, "event_type": rule.event_type,
                     "condition_json": cond_json})
        imported += 1
    return {"imported": imported, "skipped": skipped}


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
            " WHERE project_id = ? AND event_type = ? AND paused = 0"
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
        # context for the summary: item title when the event is item-scoped;
        # for run outcomes carry the actionable detail itself (CI "actionable
        # context" consensus — error first line / outcome·artifact, M58-I174)
        run_ctx = ""
        if event.event_type.startswith("run."):
            p = event.payload or {}
            if event.event_type == "run.failed":
                err = str(p.get("error") or "")[:80]
                run_ctx = f"：{err}" if err else ""
            else:
                out = p.get("output") or {}
                bits = " · ".join(str(b) for b in (out.get("outcome"), out.get("artifact")) if b)
                run_ctx = f"：{bits[:80]}" if bits else ""
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
            if event.event_type.startswith("run."):
                verb = "失败" if event.event_type == "run.failed" else "完成"
                core = f"agent 运行{verb}{run_ctx}"
            else:
                suffix = f"「{title}」" if title else ""
                core = f"有新动态：{event.event_type}{suffix}"
            extra: dict = {}
            if event.event_type.startswith("run."):
                # M58-I175: the bell deep-links to the run drawer (CI "link to
                # the logs" semantics)
                extra["run_id"] = event.agg_id
            events.emit(
                event_type="notification.sent", agg_type="project",
                agg_id=event.project_id, project_id=event.project_id,
                payload={"user_id": uid, "kind": "watch",
                         "summary": f"关注的项目「{pname}」{core}", **extra},
            )
    except Exception:  # the hook must never break the write path
        logging.getLogger("apm.watch").exception("watch hook failed after #%s", event.id)
