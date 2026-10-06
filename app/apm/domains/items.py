"""Work item domain: ontology-driven types, five-bucket state machine, relations."""
from __future__ import annotations

import csv
import io
import json
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on
from apm.domains.calendar import advance_to_workday
from apm.domains.ontology import KERNEL_RELATIONS, OntologyError, load_ontology
from apm.domains.projects import can_see_concept, disabled_fields

router = APIRouter(tags=["items"])


# ------------------------------------------------------------ projections
@on("item.created")
def _proj_item_created(conn, e):
    p = e.payload
    # M118-I363: reporter_id = item.created 的 actor（intake→"intake"、
    # IMAP 已知发件人/手工创建→用户 id）——队列「报告人」显示真源。
    conn.execute(
        "INSERT INTO items (id, project_id, feature_id, parent_id, concept_id, title, status,"
        " status_group, priority, assignee_type, assignee_id, reporter_id, estimate_hours,"
        " start_date, due_date, milestone_id, custom_fields, description, labels,"
        " created_at, updated_at, version)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
        (
            e.agg_id,
            e.project_id,
            p.get("feature_id"),
            p.get("parent_id"),
            p.get("concept_id"),
            p.get("title", ""),
            p.get("status", ""),
            p.get("status_group", ""),
            p.get("priority"),
            p.get("assignee_type"),
            p.get("assignee_id"),
            e.actor_id,
            p.get("estimate_hours"),
            p.get("start_date"),
            p.get("due_date"),
            p.get("milestone_id"),
            json.dumps(p["custom_fields"], ensure_ascii=False) if p.get("custom_fields") else None,
            p.get("description"),
            json.dumps(p["labels"]) if p.get("labels") else None,
            e.ts,
            e.ts,
        ),
    )


@on("item.updated")
def _proj_item_updated(conn, e):
    p = e.payload
    sets, params = [], []
    for key in ("title", "priority", "estimate_hours", "milestone_id", "feature_id",
                "start_date", "due_date", "auto_scheduled", "parent_id", "cycle_id",
                "recurrence_days", "description"):
        if key in p:
            sets.append(f"{key} = ?")
            params.append(p[key])
    if "custom_fields" in p:
        sets.append("custom_fields = ?")
        params.append(
            json.dumps(p["custom_fields"], ensure_ascii=False) if p["custom_fields"] else None)
    if "labels" in p:  # M115-I345: whole-list overwrite, same as custom_fields
        sets.append("labels = ?")
        params.append(json.dumps(p["labels"]) if p["labels"] else None)
    if sets:
        sets.append("updated_at = ?")
        sets.append("version = version + 1")
        params.extend([e.ts, e.agg_id])
        conn.execute(f"UPDATE items SET {', '.join(sets)} WHERE id = ?", params)


@on("item.checklist_updated")
def _proj_item_checklist(conn, e):
    # M63-I191: whole-column overwrite — the payload carries the full new list
    # (custom_fields 整列覆盖纪律同款); no version bump (advisory surface).
    conn.execute("UPDATE items SET checklist = ? WHERE id = ?",
                 (e.payload.get("checklist"), e.agg_id))


@on("item.checklist_extracted")
def _proj_checklist_extracted(conn, e):
    # M64-I194: same ledger as the comment-side extraction (I67) — one table,
    # two sources, the source_item_id column tells them apart on rebuild.
    p = e.payload
    conn.execute(
        "INSERT INTO extracted_tasks (id, comment_id, item_id, project_id, text,"
        " source_item_id, created_at) VALUES (?,?,?,?,?,?,?)",
        (e.agg_id, "", p["item_id"], e.project_id, p["text"], p["source_item_id"], e.ts),
    )


@on("item.status_changed")
def _proj_item_status(conn, e):
    p = e.payload
    conn.execute(
        "UPDATE items SET status = ?, status_group = ?, updated_at = ?, version = version + 1"
        " WHERE id = ?",
        (p["status"], p["status_group"], e.ts, e.agg_id),
    )


@on("item.assigned")
def _proj_item_assigned(conn, e):
    p = e.payload
    conn.execute(
        "UPDATE items SET assignee_type = ?, assignee_id = ?,"
        " custom_fields = COALESCE(?, custom_fields), updated_at = ?, version = version + 1"
        " WHERE id = ?",
        (p.get("assignee_type"), p.get("assignee_id"),
         json.dumps(p["custom_fields"], ensure_ascii=False) if p.get("custom_fields") else None,
         e.ts, e.agg_id),
    )


# I103: archive / restore — soft delete with full reversibility (docs/01 §AF.3).
@on("item.archived")
def _proj_item_archived(conn, e):
    conn.execute("UPDATE items SET archived_at = ? WHERE id = ?", (e.ts, e.agg_id))


@on("item.restored")
def _proj_item_restored(conn, e):
    conn.execute("UPDATE items SET archived_at = NULL WHERE id = ?", (e.agg_id,))


@on("item.rescheduled")
def _proj_item_rescheduled(conn, e):
    """Auto-scheduling shift (M14-I44): explicit event, auditable follow-of."""
    p = e.payload
    conn.execute(
        "UPDATE items SET start_date = ?, due_date = ?, updated_at = ?, version = version + 1"
        " WHERE id = ?",
        (p.get("start_date"), p.get("due_date"), e.ts, e.agg_id),
    )


@on("item.related")
def _proj_item_related(conn, e):
    p = e.payload
    conn.execute(
        "INSERT INTO item_relations (id, project_id, from_item, to_item, relation_type, lag_days, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (new_id("rel"), e.project_id, p["from_item"], p["to_item"], p["relation_type"],
         p.get("lag_days"), e.ts),
    )


@on("item.relation_removed")
def _proj_item_relation_removed(conn, e):
    # I234 (docs/01 §BW.1): inverse of _proj_item_related — composite key
    # (from, to, type), so a duplicate-created pair is removed as a whole.
    p = e.payload
    conn.execute(
        "DELETE FROM item_relations WHERE from_item = ? AND to_item = ? AND relation_type = ?",
        (p["from_item"], p["to_item"], p["relation_type"]),
    )


# ---------------------------------------------------------------- helpers
def get_item(item_id: str) -> dict | None:
    row = db.get_conn().execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return _parse_cf(dict(row)) if row else None


def require_item(item_id: str) -> dict:
    item = get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"item {item_id} not found")
    return item


def require_visible_item(item_id: str) -> dict:
    """M67-I201: mutation/interaction faces on an item whose concept is hidden
    for the caller read as 404 — existence is not revealed (GitHub private
    repo semantics). Entitled callers are unaffected."""
    item = require_item(item_id)
    if not can_see_concept(item["project_id"], item["concept_id"], events.effective_actor()):
        raise HTTPException(status_code=404, detail=f"item {item_id} not found")
    return item


def project_ontology(project_id: str):
    from apm.domains.projects import require_project

    project = require_project(project_id)
    return load_ontology(project["ontology"])


def create_item(
    *,
    project_id: str,
    concept_id: str,
    title: str,
    feature_id: str | None = None,
    parent_id: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    assignee_type: str | None = None,
    assignee_id: str | None = None,
    estimate_hours: float | None = None,
    start_date: str | None = None,
    due_date: str | None = None,
    milestone_id: str | None = None,
    custom_fields: dict | None = None,
    description: str | None = None,
    labels: list[str] | None = None,
    actor_type: str = "human",
    actor_id: str | None = None,
    extra_payload: dict | None = None,
) -> dict:
    onto = project_ontology(project_id)
    _validate_custom_fields(onto, concept_id, custom_fields, project_id=project_id)
    _validate_milestone(project_id, milestone_id)
    try:
        concept = onto.concept(concept_id)
        status = status or concept.initial_status()
        group = onto.validate_item_status(concept_id, status)
    except OntologyError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _validate_parent(project_id, parent_id)
    iid = new_id("i")
    payload = {
        "concept_id": concept_id,
        "title": title,
        "feature_id": feature_id,
        "parent_id": parent_id,
        "status": status,
        "status_group": group,
        "priority": priority,
        "custom_fields": custom_fields,
        "assignee_type": assignee_type,
        "assignee_id": assignee_id,
        "estimate_hours": estimate_hours,
        "start_date": start_date,
        "due_date": due_date,
        "milestone_id": milestone_id,
        "description": description,
        "labels": labels,
    }
    if extra_payload:
        payload.update(extra_payload)  # M49-I147: 审计链等调用方附加键
    events.emit(
        event_type="item.created",
        agg_type="item",
        agg_id=iid,
        project_id=project_id,
        actor_type=actor_type,
        actor_id=actor_id,
        payload=payload,
    )
    return get_item(iid)  # type: ignore[return-value]


def change_status(item: dict, new_status: str, actor_type="human", actor_id: str | None = None) -> dict:
    # actor falls back to the effective identity (M18 审阅即修：默认硬编码
    # "u_admin" 使 PATCH 状态变更的审计归因与通知的操作者排除全部失真)
    actor_id = actor_id or events.effective_actor()
    onto = project_ontology(item["project_id"])
    try:
        group = onto.validate_item_status(item["concept_id"], new_status)
        # M26-I82: optional concept-level transition whitelist (OpenProject
        # status-flow semantics, declared in the ontology; undeclared = open).
        onto.validate_transition(item["concept_id"], item["status"], new_status)
    except OntologyError as e:
        raise HTTPException(status_code=422, detail=str(e))
    # Blocked closure (M25-I78, Redmine blocked-by semantics): completing an item
    # that still has an unfinished blocker is refused — guards live inside
    # change_status so PATCH, batch-patch, NL commands and Agent tools all inherit
    # it. Cancelling the blocked item itself stays allowed (giving up ≠ finishing).
    if group == "done":
        blocker = db.get_conn().execute(
            "SELECT i.title FROM item_relations r JOIN items i ON i.id = r.from_item"
            " WHERE r.to_item = ? AND r.relation_type = 'blocks'"
            " AND i.status_group NOT IN ('done','cancelled')",
            (item["id"],),
        ).fetchone()
        if blocker is not None:
            raise HTTPException(status_code=422, detail=f"blocked by {blocker['title']}")
    events.emit(
        event_type="item.status_changed",
        agg_type="item",
        agg_id=item["id"],
        project_id=item["project_id"],
        actor_type=actor_type,
        actor_id=actor_id,
        payload={"from": item["status"], "status": new_status, "status_group": group},
    )
    return get_item(item["id"])  # type: ignore[return-value]


def list_items(
    *,
    project_id: str | None = None,
    feature_id: str | None = None,
    concept_id: str | None = None,
    status_group: str | None = None,
    status: str | None = None,
    assignee_id: str | None = None,
    priority: str | None = None,
    cycle_id: str | None = None,
    label: str | None = None,
    include_archived: bool = False,
) -> list[dict]:
    where, params = ["1=1"], []
    # I103: archived (trashed) items are excluded unless explicitly requested
    if not include_archived:
        where.append("archived_at IS NULL")
    if project_id:
        where.append("project_id = ?")
        params.append(project_id)
    if feature_id:
        where.append("feature_id = ?")
        params.append(feature_id)
    if cycle_id:  # I119: iteration filter
        where.append("cycle_id = ?")
        params.append(cycle_id)
    if concept_id:
        where.append("concept_id = ?")
        params.append(concept_id)
    if status_group:
        where.append("status_group = ?")
        params.append(status_group)
    if status:
        where.append("status = ?")
        params.append(status)
    if assignee_id:
        where.append("assignee_id = ?")
        params.append(assignee_id)
    if priority:
        where.append("priority = ?")
        params.append(priority)
    if label:  # M115-I345: label member filter (JSON list containment)
        where.append("labels LIKE ?")
        params.append(f'%"{label}"%')
    rows = db.get_conn().execute(
        f"SELECT * FROM items WHERE {' AND '.join(where)} ORDER BY created_at", params
    ).fetchall()
    items = [_parse_cf(it) for it in _with_assignee_names(dict(r) for r in rows)]

    # I128 (docs/01 §AO.1, Businessmap blocked-flag semantics): an item is
    # blocked when an unfinished blocks-blocker or an unfinished depends_on
    # prerequisite exists — the same caliber as the I78 closure guard, derived
    # here so the board shows the flag without opening any drawer.
    if items:
        ids = [i["id"] for i in items]
        marks = ",".join("?" for _ in ids)
        unfinished = "u.status_group NOT IN ('done','cancelled')"
        blocked = {r[0] for r in db.get_conn().execute(
            f"SELECT r.to_item FROM item_relations r JOIN items u ON u.id = r.from_item"
            f" WHERE r.relation_type = 'blocks' AND r.to_item IN ({marks}) AND {unfinished}",
            ids).fetchall()}
        blocked |= {r[0] for r in db.get_conn().execute(
            f"SELECT r.from_item FROM item_relations r JOIN items u ON u.id = r.to_item"
            f" WHERE r.relation_type = 'depends_on' AND r.from_item IN ({marks}) AND {unfinished}",
            ids).fetchall()}
        for it in items:
            it["blocked"] = it["id"] in blocked
    return items


BUCKET_NAMES = {
    "backlog": "待办池",
    "todo": "就绪",
    "in_progress": "进行中",
    "done": "已完成",
    "cancelled": "已取消",
}


def _find_field(onto, field_id: str) -> dict | None:
    """Locate a custom-field declaration across all concepts (first match wins)."""
    for concept in onto.concepts.values():
        for f in concept.fields:
            if f.get("id") == field_id:
                return f
    return None


def _group_key(value) -> str:
    """Canonical column key for one scalar field value (bool → filter literals)."""
    if isinstance(value, bool):
        return "true" if value else "false"  # matches the cf=true/false filter literals
    return str(value)


@router.get("/projects/{project_id}/board")
def get_board(
    project_id: str, feature_id: str | None = None, group_by: str | None = None,
    view_id: str | None = None, cycle: str | None = None,
    swimlane_by: str | None = None,
) -> dict:
    """Board projection: five lifecycle buckets, optionally re-grouped by a custom
    field (M6-I21: `group_by=field:<id>`, default from board_defaults.group_by).
    M16-I50: `view_id` applies a saved view's definition (explicit query params win)."""
    onto = project_ontology(project_id)
    view_def: dict = {}
    if view_id:
        from apm.core import events as core_events
        from apm.domains import views as views_domain
        v = views_domain.require_view(view_id)
        if v["project_id"] != project_id:
            raise HTTPException(status_code=422, detail="view belongs to another project")
        views_domain._actor_can_read(v, core_events.effective_actor())
        view_def = v["definition"]
    elif not view_id and not group_by:
        # I52: no explicit view/group → fall back to the project default view.
        from apm.core import events as core_events
        from apm.domains import views as views_domain
        row = db.get_conn().execute(
            "SELECT id FROM saved_views WHERE project_id = ? AND is_default = 1",
            (project_id,),
        ).fetchone()
        if row:
            v = views_domain.require_view(row["id"])
            views_domain._actor_can_read(v, core_events.effective_actor())
            view_def = v["definition"]
            view_id = v["id"]
    group_by = group_by or view_def.get("group_by")
    effective = group_by or onto.board_defaults.get("group_by", "lifecycle")
    inactive = disabled_fields(project_id)
    items = list_items(
        project_id=project_id,
        feature_id=feature_id or view_def.get("feature_id"),
        concept_id=view_def.get("concept_id"),
        status_group=view_def.get("status_group"),
        status=view_def.get("status"),
        assignee_id=view_def.get("assignee_id"),
        priority=view_def.get("priority"),
        cycle_id=cycle,
    )
    if "cf" in view_def:
        items = [it for it in items if _cf_hit(it, view_def["cf"])]
    # M67-I201: hidden concepts never reach the board of a non-entitled viewer
    # (M114-I340: per-request invariants hoisted out of the per-item loop)
    _visible = _concept_visible_filter(project_id, events.effective_actor())
    items = [it for it in items if _visible(it["concept_id"])]
    _attach_spent(items)
    buckets: dict[str, list[dict]] = {b: [] for b in BUCKET_NAMES}
    for item in items:
        buckets.setdefault(item["status_group"], []).append(item)
    columns = []
    for concept in onto.concepts.values():
        for s in concept.states:
            columns.append(
                {
                    "id": f"{concept.id}:{s['id']}",
                    "concept_id": concept.id,
                    "concept_name": concept.name,
                    "status": s["id"],
                    "name": s.get("name", s["id"]),
                    "group": s["group"],
                }
            )
    resp = {
        "project_id": project_id,
        "feature_id": feature_id,
        "applied_view_id": view_id,
        "buckets": [
            {"id": b, "name": BUCKET_NAMES[b], "items": buckets.get(b, [])} for b in BUCKET_NAMES
        ],
        "columns": columns,
        "group_by": effective,
        "field": None,
        "groups": None,
        "disabled_fields": sorted(inactive),
    }
    # M65-I196: swimlane — a second grouping dimension (Taiga/Kanboard board
    # semantics). Columns stay the lifecycle buckets; within each bucket the
    # items are annotated with their lane so the frontend can render sub-rows
    # without a second query. Whitelist only; None/absent = no lanes.
    _SWIMLANE_KEYS = ("assignee_id", "feature_id", "priority")
    if swimlane_by is None and view_id:
        swimlane_by = view_def.get("swimlane_by")
    if swimlane_by:
        if swimlane_by not in _SWIMLANE_KEYS:
            raise HTTPException(
                status_code=422,
                detail=f"swimlane_by must be one of {_SWIMLANE_KEYS} or omitted")
        lanes: dict[str, list[str]] = {}
        for it in items:
            key = it.get(swimlane_by) or "（空）"
            key = str(key)
            lanes.setdefault(key, []).append(it["id"])
            it["swimlane"] = key
        resp["swimlane_by"] = swimlane_by
        resp["swimlanes"] = [
            {"id": k, "count": len(v)} for k, v in
            sorted(lanes.items(), key=lambda kv: (-len(kv[1]), kv[0]))]
    # M26-I80: WIP limits (Kanboard task-limit semantics) — soft signals only.
    # The count is deliberately project-wide (ignoring board filters) and the
    # limit rides along from board_defaults; the board never blocks transitions.
    # M114-I340: one GROUP BY instead of a second full list_items pass (which
    # repeated the assignee N+1 on every board request with WIP limits set).
    wip_limits = onto.board_defaults.get("wip_limits") or {}
    if isinstance(wip_limits, dict) and wip_limits:
        counts = {r["status_group"]: r["c"] for r in db.get_conn().execute(
            "SELECT status_group, COUNT(*) c FROM items"
            " WHERE project_id = ? AND archived_at IS NULL"
            " GROUP BY status_group", (project_id,)).fetchall()}
        resp["wip"] = {g: counts.get(g, 0) for g in wip_limits}
        resp["wip_limits"] = {g: int(v) for g, v in wip_limits.items()}
    if effective == "lifecycle":
        return resp
    if effective == "labels":  # M115-I345: label-board fan-out (multiselect
        # semantics — an item appears once per label; untagged go to 未标签).
        from apm.domains.labels import require_label as _require_label_row
        label_rows = db.get_conn().execute(
            "SELECT * FROM labels WHERE project_id = ? ORDER BY created_at, id",
            (project_id,)).fetchall()
        grouped, none_items = {}, []
        for it in items:
            lids = it.get("labels") or []
            if not lids:
                none_items.append(it)
            for lid in lids:
                grouped.setdefault(lid, []).append(it)
        groups = []
        for row in label_rows:
            if row["id"] in grouped:
                groups.append({"id": row["id"], "name": row["name"], "color": row["color"],
                               "items": grouped.pop(row["id"])})
        groups.extend(  # labels referenced but deleted from the registry (staleness guard)
            {"id": lid, "name": lid, "color": None, "items": its}
            for lid, its in sorted(grouped.items()))
        if none_items:
            groups.append({"id": "_none", "name": "未标签", "color": None, "items": none_items})
        resp["field"] = None
        resp["groups"] = groups
        return resp
    if not effective.startswith("field:"):
        raise HTTPException(status_code=422, detail=f"unknown group_by '{effective}' (lifecycle | field:<id> | labels)")
    fid = effective[len("field:") :]
    field = _find_field(onto, fid)
    if not field:
        raise HTTPException(status_code=422, detail=f"field '{fid}' is not declared in ontology")
    if fid in inactive:
        raise HTTPException(status_code=422, detail=f"field '{fid}' is disabled in this project")
    # Declared values keep their ontology order (stable columns, even when empty);
    # undeclared keys follow first-seen item order; 未设置 always last. Multiselect
    # values fan out — an item appears once per tag (label-board semantics).
    ordered = [str(v) for v in field.get("values") or []]
    grouped: dict[str, list[dict]] = {}
    none_items: list[dict] = []
    for item in items:
        val = (item.get("custom_fields") or {}).get(fid)
        if val is None or val == []:
            none_items.append(item)
            continue
        for v in val if isinstance(val, list) else [val]:
            key = _group_key(v)
            grouped.setdefault(key, []).append(item)
            if key not in ordered:
                ordered.append(key)
    column_keys = ordered + (["_none"] if none_items else [])
    resp["field"] = {"id": fid, "name": field.get("name", fid), "type": field.get("type", "string")}
    resp["groups"] = [
        {
            "id": k,
            "name": "未设置" if k == "_none" else k,
            "items": (none_items if k == "_none" else grouped.get(k, [])),
        }
        for k in column_keys
    ]
    return resp


# ------------------------------------------------------------------ models
class ItemIn(BaseModel):
    concept_id: str
    title: str
    feature_id: str | None = None
    parent_id: str | None = None
    status: str | None = None
    priority: str | None = None
    assignee_type: str | None = None
    assignee_id: str | None = None
    estimate_hours: float | None = None
    start_date: str | None = None
    due_date: str | None = None
    milestone_id: str | None = None
    custom_fields: dict | None = None
    description: str | None = None
    labels: list[str] | None = None


def _ensure_human_assignee(assignee_type: str | None, assignee_id: str | None) -> None:
    """Human assignees must be registered identities (M5-I19). Role assignees are free."""
    if assignee_type == "human" and assignee_id:
        row = db.get_conn().execute(
            "SELECT 1 FROM users WHERE id = ?", (assignee_id,)).fetchone()
        if not row:
            raise HTTPException(
                status_code=422,
                detail=f"unknown user '{assignee_id}' (register via POST /api/users)")


def _validate_item_dates(start_date: str | None, due_date: str | None) -> None:
    """Item schedule dates must be ISO calendar dates (M13-I41)."""
    for field, value in (("start_date", start_date), ("due_date", due_date)):
        if value is None:
            continue
        try:
            date.fromisoformat(value)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=422,
                detail=f"{field} must be an ISO date (YYYY-MM-DD), got {value!r}")


def _validate_milestone(project_id: str, milestone_id: str | None) -> None:
    if milestone_id:
        from apm.domains.milestones import require_milestone

        m = require_milestone(milestone_id)  # 422 on unknown
        if m["project_id"] != project_id:
            raise HTTPException(status_code=422, detail="milestone belongs to another project")


def _validate_parent(project_id: str, parent_id: str | None, *, self_id: str | None = None) -> None:
    """M24-I74: parent must exist, live in the same project, and re-parenting
    must not create a cycle (walk up the proposed ancestor chain)."""
    if not parent_id:
        return
    if self_id and parent_id == self_id:
        raise HTTPException(status_code=422, detail="item cannot be its own parent")
    parent = db.get_conn().execute(
        "SELECT id, project_id, parent_id FROM items WHERE id = ?", (parent_id,)).fetchone()
    if parent is None:
        raise HTTPException(status_code=422, detail=f"unknown parent '{parent_id}'")
    if parent["project_id"] != project_id:
        raise HTTPException(status_code=422, detail="parent belongs to another project")
    seen = {self_id} if self_id else set()
    cur = parent
    while cur is not None:
        if cur["id"] in seen:
            raise HTTPException(status_code=422, detail="parent chain would create a cycle")
        seen.add(cur["id"])
        cur = db.get_conn().execute(
            "SELECT id, parent_id FROM items WHERE id = ?",
            (cur["parent_id"],)).fetchone() if cur["parent_id"] else None


# ------------------------------------------------- auto-scheduling (M14-I44)
MAX_SCHEDULE_DEPTH = 20


def _shift_iso(value: str | None, delta_days: int) -> str | None:
    if value is None:
        return None
    try:
        return (date.fromisoformat(value) + timedelta(days=delta_days)).isoformat()
    except (TypeError, ValueError):
        return None


def propagate_reschedule(project_id: str, predecessor_id: str, old_due: str | None,
                         new_due: str | None, depth: int = 0,
                         visited: set[str] | None = None) -> int:
    """Shift auto-scheduled dependents when a predecessor's due date moves
    (docs/01 §M.1 — OpenProject 15.4 pattern: opt-in, manual by default).
    Every shift is an explicit `item.rescheduled` event; recursion follows
    the depends_on graph with a visited set (cycle-safe, depth-capped)."""
    if depth >= MAX_SCHEDULE_DEPTH or not old_due or not new_due:
        return 0
    visited = visited if visited is not None else {predecessor_id}
    old_d, new_d = date.fromisoformat(old_due), date.fromisoformat(new_due)
    delta = (new_d - old_d).days
    if delta == 0:
        return 0
    conn = db.get_conn()
    dependents = conn.execute(
        "SELECT r.from_item AS dep_id, i.project_id AS dep_project,"
        " i.start_date, i.due_date"
        " FROM item_relations r JOIN items i ON i.id = r.from_item"
        " WHERE r.to_item = ? AND r.relation_type = 'depends_on'",
        (predecessor_id,),
    ).fetchall()
    count = 0
    for dep in dependents:
        dep_id = dep["dep_id"]
        # M47-I143: 事件归属被移动项自己的项目（跨项目链上不再是调用者项目）
        dep_project = dep["dep_project"]
        if dep_id in visited or not conn.execute(
            "SELECT auto_scheduled FROM items WHERE id = ?", (dep_id,)
        ).fetchone()["auto_scheduled"]:
            continue
        visited.add(dep_id)
        new_start = _shift_iso(dep["start_date"], delta)
        new_due = _shift_iso(dep["due_date"], delta)
        if new_due is None:
            continue  # undated dependent has nothing to shift
        # M34-I104 (docs/01 §AG.1, OpenProject 12.3): auto-scheduled landing
        # dates skip non-working days; span may shrink by the skipped days —
        # the working-time span is what the shift preserves. Manual items
        # never reach this branch.
        start_d = advance_to_workday(date.fromisoformat(new_start)) if new_start else None
        due_d = advance_to_workday(date.fromisoformat(new_due))
        if start_d and start_d > due_d:
            due_d = start_d
        new_start = start_d.isoformat() if start_d else None
        new_due = due_d.isoformat()
        events.emit(
            event_type="item.rescheduled",
            agg_type="item",
            agg_id=dep_id,
            project_id=dep_project,
            payload={"follow_of": predecessor_id, "delta_days": delta,
                     "start_date": new_start, "due_date": new_due, "depth": depth + 1},
        )
        count += 1
        count += propagate_reschedule(dep_project, dep_id, dep["due_date"], new_due,
                                      depth + 1, visited)
    return count


def _parse_cf(item: dict) -> dict:
    if isinstance(item.get("custom_fields"), str):
        try:
            item["custom_fields"] = json.loads(item["custom_fields"])
        except json.JSONDecodeError:
            item["custom_fields"] = {}
    if isinstance(item.get("labels"), str):  # M115-I345: JSON id list → list
        try:
            item["labels"] = json.loads(item["labels"])
        except json.JSONDecodeError:
            item["labels"] = []
    if item.get("labels") is None:  # NULL column reads back as [] (stable shape)
        item["labels"] = []
    return item


def _with_assignee_name(item: dict) -> dict:
    if item.get("assignee_type") == "human" and item.get("assignee_id"):
        row = db.get_conn().execute(
            "SELECT name FROM users WHERE id = ?", (item["assignee_id"],)).fetchone()
        item["assignee_name"] = row["name"] if row else item["assignee_id"]
    if item.get("reporter_id"):  # M118-I363: 报告人显示名（删户兜底 raw id）
        row = db.get_conn().execute(
            "SELECT name FROM users WHERE id = ?", (item["reporter_id"],)).fetchone()
        item["reporter_name"] = row["name"] if row else item["reporter_id"]
    return item


def _with_assignee_names(items: "list[dict]") -> "list[dict]":
    """M114-I340: batch variant of _with_assignee_name — one IN query instead
    of one query per row (list_items runs on every board/list request, so the
    per-row lookup was an N+1 that scaled with the whole project, not the
    page). Deleted users fall back to the raw id, same as the single form.
    M118-I363: reporter_name rides the same users IN query (intake items keep
    the raw "intake" — the queue renders it as 外部)."""
    items = list(items)  # callers may hand a generator — iterate twice below
    ids = {it["assignee_id"] for it in items
           if it.get("assignee_type") == "human" and it.get("assignee_id")}
    ids |= {r for it in items if (r := it.get("reporter_id"))}
    names: dict[str, str] = {}
    if ids:
        marks = ",".join("?" for _ in ids)
        names = {r["id"]: r["name"] for r in db.get_conn().execute(
            f"SELECT id, name FROM users WHERE id IN ({marks})", tuple(ids)).fetchall()}
    for it in items:
        if it.get("assignee_type") == "human" and it.get("assignee_id"):
            it["assignee_name"] = names.get(it["assignee_id"], it["assignee_id"])
        if it.get("reporter_id"):
            it["reporter_name"] = names.get(it["reporter_id"], it["reporter_id"])
    return items


def _concept_visible_filter(project_id: str, viewer: str):
    """M114-I340: batch flavor of can_see_concept — hoists the per-request
    invariants (project row, admin flag, role, local-user check) out of the
    per-item loop that get_items/get_board run on every list read; identical
    semantics, one row of work per request instead of one get_project() per
    item. Fast path: no concept is restricted → constant-True predicate."""
    from apm import config
    from apm.domains.members import is_instance_admin, member_role
    from apm.domains.projects import get_project

    p = get_project(project_id)
    restricted = (p.get("concept_visibility") or {}) if p else {}
    if not restricted:
        return lambda concept_id: True
    if is_instance_admin(viewer) or member_role(project_id, viewer) == "owner":
        return lambda concept_id: True
    if config.settings.auth_mode == "local" and viewer == config.settings.user_id:
        return lambda concept_id: True
    return lambda concept_id: concept_id not in restricted


def _validate_custom_fields(onto, concept_id: str, cf: dict, project_id: str | None = None) -> None:
    """Custom field values must match the concept's declared fields (M6-I20);
    project-deactivated fields are refused on write (M7-I25)."""
    inactive = disabled_fields(project_id) if project_id else set()
    concept = onto.concept(concept_id)
    declared = {f["id"]: f for f in concept.fields}
    for k, v in (cf or {}).items():
        if k in inactive:
            raise HTTPException(status_code=422,
                                detail=f"custom field '{k}' is disabled in this project")
        spec = declared.get(k)
        if spec is None:
            raise HTTPException(status_code=422,
                                detail=f"custom field '{k}' not declared on concept '{concept_id}'")
        ftype = spec.get("type")
        ok = {
            "string": lambda v: isinstance(v, str),
            "date": lambda v: isinstance(v, str) and len(v) >= 8,
            "ref": lambda v: isinstance(v, str),
            "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            "boolean": lambda v: isinstance(v, bool),
            "enum": lambda v: v in (spec.get("values") or []),
            "multiselect": lambda v: isinstance(v, list) and bool(v)
            and all(x in (spec.get("values") or []) for x in v),
        }[ftype]
        if not ok(v):
            raise HTTPException(
                status_code=422,
                detail=f"custom field '{k}' (type {ftype}) invalid value: {v!r}")


class ItemPatch(BaseModel):
    title: str | None = None
    priority: str | None = None
    estimate_hours: float | None = None
    status: str | None = None
    assignee_type: str | None = None
    assignee_id: str | None = None
    feature_id: str | None = None
    milestone_id: str | None = None
    start_date: str | None = None
    due_date: str | None = None
    auto_scheduled: bool | None = None
    custom_fields: dict | None = None
    parent_id: str | None = None  # re-parent (M24-I74); clearing not supported
    cycle_id: str | None = None  # I119: iteration mount (mount/retarget only)
    recurrence_days: int | None = None  # I133: respawn N days after completion
    description: str | None = None  # I343: Linear-style issue body ("" clears)
    labels: list[str] | None = None  # I345: whole-list overwrite; [] clears, omitted keeps


class RelationIn(BaseModel):
    to_item: str
    relation_type: str
    lag_days: int | None = None


@router.post("/projects/{project_id}/items")
def post_item(project_id: str, body: ItemIn) -> dict:
    # M67-I201: creating an item of a restricted concept requires entitlement —
    # the project itself is visible, so 403 (not 404) is honest here
    if not can_see_concept(project_id, body.concept_id, events.effective_actor()):
        raise HTTPException(status_code=403, detail=f"concept '{body.concept_id}' 在本项目仅 Owner 可见可写")
    _ensure_human_assignee(body.assignee_type, body.assignee_id)
    _validate_item_dates(body.start_date, body.due_date)
    _validate_milestone(project_id, body.milestone_id)
    if body.labels:  # M115-I345: same-project FK discipline
        from apm.domains.labels import validate_item_labels
        validate_item_labels(project_id, body.labels)
    return create_item(
        project_id=project_id,
        concept_id=body.concept_id,
        title=body.title,
        feature_id=body.feature_id,
        parent_id=body.parent_id,
        status=body.status,
        priority=body.priority,
        assignee_type=body.assignee_type,
        assignee_id=body.assignee_id,
        estimate_hours=body.estimate_hours,
        start_date=body.start_date,
        due_date=body.due_date,
        milestone_id=body.milestone_id,
        custom_fields=body.custom_fields,
        description=body.description,
        labels=body.labels,
    )


def _cf_hit(it: dict, cf: str) -> bool:
    """Single cf filter term "field:value" — multiselect containment (M6-I20)."""
    field, _, expected = cf.partition(":")
    got = (it.get("custom_fields") or {}).get(field)
    if isinstance(got, list):
        return expected in got
    return got == expected or (isinstance(got, bool) and expected in ("true", "false")
                               and got == (expected == "true"))


def _attach_spent(items: list[dict]) -> None:
    """M19-I59: spent-time totals ride along (plan vs actual on cards/lists)."""
    if not items:
        return
    ids = [it["id"] for it in items]
    marks = ",".join("?" * len(ids))
    spent = {r["item_id"]: r["total"] for r in db.get_conn().execute(
        f"SELECT item_id, SUM(minutes) total FROM item_time_entries"
        f" WHERE item_id IN ({marks}) AND deleted_at IS NULL GROUP BY item_id", ids)}
    for it in items:
        it["spent_minutes"] = spent.get(it["id"], 0)


@router.get("/projects/{project_id}/items")
def get_items(
    project_id: str,
    feature_id: str | None = None,
    concept_id: str | None = None,
    status_group: str | None = None,
    status: str | None = None,
    assignee_id: str | None = None,
    priority: str | None = None,
    cycle: str | None = None,
    cf: str | None = None,
    view_id: str | None = None,
    parent: str | None = None,
    descendants: str | None = None,
    label: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> dict:
    base: dict = {}
    if view_id:  # M16-I50: saved view supplies base filters; explicit params win
        from apm.core import events as core_events
        from apm.domains import views as views_domain
        v = views_domain.require_view(view_id)
        if v["project_id"] != project_id:
            raise HTTPException(status_code=422, detail="view belongs to another project")
        views_domain._actor_can_read(v, core_events.effective_actor())
        base = {k: v["definition"][k] for k in
                ("feature_id", "concept_id", "status_group", "status", "assignee_id", "priority", "cf")
                if k in v["definition"]}
    # M117-I357: status 显式参数补接线——E2E 走查抓获半传静默忽略（此前只有
    # 保存视图路径能带 status，?status= 被 FastAPI 直接丢弃——R1 留观②同族）。
    explicit = {"feature_id": feature_id, "concept_id": concept_id, "status_group": status_group,
                "status": status, "assignee_id": assignee_id, "priority": priority, "cf": cf}
    merged = {**base, **{k: v for k, v in explicit.items() if v is not None}}
    items = list_items(
        project_id=project_id,
        feature_id=merged.get("feature_id"),
        concept_id=merged.get("concept_id"),
        status_group=merged.get("status_group"),
        status=merged.get("status"),
        assignee_id=merged.get("assignee_id"),
        priority=merged.get("priority"),
        cycle_id=cycle,
        label=label,
    )
    if merged.get("cf"):
        items = [it for it in items if _cf_hit(it, merged["cf"])]
    # M24-I74 hierarchy scopes (explicit params only — not part of saved views)
    if parent:
        items = [it for it in items if it["parent_id"] == parent]
    if descendants:
        children: dict[str, list[str]] = {}
        for it in items:
            children.setdefault(it["parent_id"], []).append(it["id"])
        keep, stack = set(), [descendants]
        while stack:
            for ch in children.get(stack.pop(), []):
                if ch not in keep:
                    keep.add(ch)
                    stack.append(ch)
        items = [it for it in items if it["id"] in keep]
    # M25-I79 pagination (docs/01 §X.3, GitLab offset guidance): unbounded by
    # default — only an explicit limit slices (clamped 1-200); offset rides
    # along. total counts the fully filtered set in both modes, so clients can
    # drive "load more" against it.
    # M67-I201: concept-level visibility — hidden concepts drop from the list
    # for non-entitled viewers (total reflects the filtered set).
    # M114-I340: invariants hoisted out of the per-item loop.
    _visible = _concept_visible_filter(project_id, events.effective_actor())
    items = [it for it in items if _visible(it["concept_id"])]
    total = len(items)
    if limit is not None:
        offset = max(0, offset or 0)
        items = items[offset:offset + max(1, min(200, limit))]
    _attach_spent(items)
    return {"items": items, "total": total}


@router.get("/projects/{project_id}/items/similar")
def similar_items(project_id: str, title: str, exclude_id: str | None = None,
                  limit: int = 5) -> dict:
    """M115-I346 duplicate-guard typeahead (docs/01 §DF, Linear similar-issues
    semantics): FTS5 over titles/descriptions (items_search, _match_expr
    quoting discipline). <2 chars → empty (typeahead, not an error). Archived
    items never surface; hidden concepts stay hidden per M67 visibility."""
    from apm.domains.assets import _bigrams

    query = (title or "").strip()
    if len(query) < 2:
        return {"suggestions": []}
    # Typeahead semantics: OR the quoted bigrams (implicit AND would zero out
    # natural partial titles like「登录页重构」when the indexed title inserts
    # a space mid-run); FTS5 rank orders the hits so dense matches surface first.
    expr = " OR ".join('"%s"' % t.replace('"', '""') for t in _bigrams(query).split())
    conn = db.get_conn()
    me = events.effective_actor()
    out: list[dict] = []
    for r in conn.execute(
        "SELECT s.item_id FROM items_search s JOIN items i ON i.id = s.item_id"
        " WHERE items_search MATCH ? AND i.project_id = ? AND i.archived_at IS NULL"
        " ORDER BY rank LIMIT ?",
        (expr, project_id, max(1, min(20, limit)) * 4),
    ).fetchall():
        iid = r["item_id"]
        if exclude_id and iid == exclude_id:
            continue
        row = conn.execute(
            "SELECT id, project_id, title, status, status_group, concept_id, priority,"
            " description, labels FROM items WHERE id = ?",
            (iid,)).fetchone()
        if row and can_see_concept(project_id, row["concept_id"], me):
            out.append(dict(row))
        if len(out) >= max(1, min(10, limit)):
            break
    return {"suggestions": out}


@router.get("/items/{item_id}")
def get_item_detail(item_id: str) -> dict:
    item = require_item(item_id)
    # M67-I201: a hidden concept makes the item itself invisible (404 — not
    # 403, existence is not revealed)
    if not can_see_concept(item["project_id"], item["concept_id"], events.effective_actor()):
        raise HTTPException(status_code=404, detail=f"item {item_id} not found")
    rels = db.get_conn().execute(
        "SELECT * FROM item_relations WHERE from_item = ? OR to_item = ?",
        (item_id, item_id),
    ).fetchall()
    item["relations"] = [dict(r) for r in rels]
    row = db.get_conn().execute(
        "SELECT COALESCE(SUM(minutes), 0) total FROM item_time_entries"
        " WHERE item_id = ? AND deleted_at IS NULL", (item_id,)).fetchone()
    item["spent_minutes"] = row["total"]
    return _parse_cf(_with_assignee_name(item))


# ---------------------------------------------------------------- I103: trash
@router.post("/items/{item_id}/archive")
def archive_item(item_id: str) -> dict:
    """I103 (docs/01 §AF.3): soft delete — the item leaves every view but stays
    fully restorable from the trash (event-sourced, nothing is ever lost)."""
    item = require_visible_item(item_id)
    if item.get("archived_at"):
        raise HTTPException(status_code=409, detail="item already archived")
    events.emit(
        event_type="item.archived", agg_type="item", agg_id=item_id,
        project_id=item["project_id"],
        actor_type="human", actor_id=events.effective_actor(),
        payload={"title": item["title"]},
    )
    return {"ok": True}


@router.post("/items/{item_id}/restore")
def restore_item(item_id: str) -> dict:
    item = require_visible_item(item_id)
    if not item.get("archived_at"):
        raise HTTPException(status_code=409, detail="item is not archived")
    events.emit(
        event_type="item.restored", agg_type="item", agg_id=item_id,
        project_id=item["project_id"],
        actor_type="human", actor_id=events.effective_actor(),
        payload={"title": item["title"]},
    )
    return {"ok": True}


@router.get("/projects/{project_id}/trash")
def trash_items(project_id: str) -> dict:
    from apm.domains.projects import require_project

    require_project(project_id)
    rows = db.get_conn().execute(
        "SELECT id, title, concept_id, status, archived_at FROM items"
        " WHERE project_id = ? AND archived_at IS NOT NULL ORDER BY archived_at DESC",
        (project_id,)).fetchall()
    # M67-I201: the trash is a read face too — hidden concepts stay hidden
    _visible = _concept_visible_filter(project_id, events.effective_actor())
    return {"items": [dict(r) for r in rows if _visible(r["concept_id"])]}


@router.patch("/items/{item_id}")
def patch_item(item_id: str, body: ItemPatch) -> dict:
    item = require_visible_item(item_id)
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    if "labels" in changes and changes["labels"]:  # M115-I345: [] clears (passes)
        from apm.domains.labels import validate_item_labels
        validate_item_labels(item["project_id"], changes["labels"])
    if "custom_fields" in changes:
        onto = project_ontology(item["project_id"])
        _validate_custom_fields(onto, item["concept_id"], changes["custom_fields"],
                                project_id=item["project_id"])
    if "start_date" in changes or "due_date" in changes:
        _validate_item_dates(changes.get("start_date", item.get("start_date")),
                             changes.get("due_date", item.get("due_date")))
    if "milestone_id" in changes:
        _validate_milestone(item["project_id"], changes["milestone_id"])
    if "cycle_id" in changes:  # I119: cycle must exist and belong to this project
        if changes["cycle_id"] == "":
            changes["cycle_id"] = None  # empty string clears the mount
        else:
            from apm.domains.cycles import require_cycle
            cyc = require_cycle(changes["cycle_id"])
            if cyc["project_id"] != item["project_id"]:
                raise HTTPException(status_code=422, detail="cycle belongs to another project")
    if "parent_id" in changes:
        _validate_parent(item["project_id"], changes["parent_id"], self_id=item_id)
    if "auto_scheduled" in changes:
        changes["auto_scheduled"] = 1 if changes["auto_scheduled"] else 0
    if "status" in changes:
        new_status = changes.pop("status")
        item = change_status(item, new_status, actor_id=events.effective_actor())
    if "assignee_type" in changes or "assignee_id" in changes:
        _ensure_human_assignee(
            changes.get("assignee_type", item["assignee_type"]),
            changes.get("assignee_id", item["assignee_id"]))
        events.emit(
            event_type="item.assigned",
            agg_type="item",
            agg_id=item_id,
            project_id=item["project_id"],
            payload={
                "assignee_type": changes.pop("assignee_type", item["assignee_type"]),
                "assignee_id": changes.pop("assignee_id", item["assignee_id"]),
                # M115-I344: 活动流转派显示需要前值（投影只读白名单键，额外键安全）
                "from_assignee_type": item["assignee_type"],
                "from_assignee_id": item["assignee_id"],
            },
        )
    if changes:
        # M115-I344: `_old` carries previous values for the per-item activity
        # feed — projections read a whitelist of keys, so the extra key rides
        # along in the stream and replays verbatim on rebuild.
        payload = {**changes, "_old": {k: item.get(k) for k in changes}}
        events.emit(
            event_type="item.updated",
            agg_type="item",
            agg_id=item_id,
            project_id=item["project_id"],
            payload=payload,
        )
    # auto-scheduling: a moved due date shifts opt-in dependents (M14-I44)
    if "due_date" in changes:
        propagate_reschedule(item["project_id"], item_id,
                             item.get("due_date"), changes["due_date"])
    return get_item(item_id)  # type: ignore[return-value]


# ------------------------------------------------------------- M63-I191: checklist
class ChecklistItemIn(BaseModel):
    text: str
    done: bool = False
    # M64-I194: spawn marker (present → rendered as "→任务" link). Round-trips
    # through the full-list overwrite: clients must echo it back.
    extracted: str | None = None


class ChecklistIn(BaseModel):
    items: list[ChecklistItemIn]


@router.patch("/items/{item_id}/checklist")
def patch_checklist(item_id: str, body: ChecklistIn) -> dict:
    """In-item checklist (M63-I191, docs/01 §BH.3 — GitHub tasklist semantics
    minus the sub-issue conversion: the checklist's value is staying lightweight).
    Full-list submit, whole-column overwrite (custom_fields discipline, M6-I20);
    one `item.checklist_updated` fact carries the entire new state. Advisory
    only — checklist progress never feeds health/完成率 semantics."""
    item = require_visible_item(item_id)
    if len(body.items) > 20:
        raise HTTPException(status_code=422, detail="checklist supports at most 20 items")
    norm: list[dict] = []
    for ci in body.items:
        text = ci.text.strip()
        if not text or len(text) > 200:
            raise HTTPException(status_code=422, detail="checklist item text must be 1-200 chars")
        row = {"text": text, "done": ci.done}
        if ci.extracted:
            row["extracted"] = ci.extracted
        norm.append(row)
    payload = json.dumps(norm, ensure_ascii=False)
    events.emit(
        event_type="item.checklist_updated",
        agg_type="item",
        agg_id=item_id,
        project_id=item["project_id"],
        payload={"checklist": payload},
    )
    done = sum(1 for ci in norm if ci["done"])
    return {"item_id": item_id, "checklist": norm, "done": done, "total": len(norm)}


class ChecklistExtractIn(BaseModel):
    index: int


@router.post("/items/{item_id}/checklist/extract")
def extract_checklist_task(item_id: str, body: ChecklistExtractIn) -> dict:
    """Turn a checklist item into a real work item (M64-I194 — the BH.5
    follow-up with the GitLab #363613 evidence: conversion must be an explicit
    click, which this endpoint is; the checklist entry is marked with the
    spawned item id, `done` stays orthogonal). Same-chain as I67's
    comment-side extraction: extracted_tasks gains a source_item_id dimension,
    same-item same-text is idempotent-409, and the whole path is
    create_item's full validation chain."""
    item = require_visible_item(item_id)
    try:
        cl: list[dict] = json.loads(item.get("checklist") or "[]")
    except ValueError:
        cl = []
    if not 0 <= body.index < len(cl):
        raise HTTPException(status_code=422, detail="index out of range")
    entry = cl[body.index]
    text = str(entry.get("text", "")).strip()
    if not text:
        raise HTTPException(status_code=422, detail="checklist item has no text")
    if entry.get("extracted"):
        raise HTTPException(status_code=409, detail=f"already extracted to {entry['extracted']}")
    dup = db.get_conn().execute(
        "SELECT 1 FROM extracted_tasks WHERE source_item_id = ? AND text = ?",
        (item_id, text)).fetchone()
    if dup:
        raise HTTPException(status_code=409, detail="this checklist item was already extracted")

    created = create_item(project_id=item["project_id"], concept_id="task", title=text)
    extraction_id = new_id("et")
    events.emit(
        event_type="item.checklist_extracted",
        agg_type="item_extraction",
        agg_id=extraction_id,
        project_id=item["project_id"],
        payload={"source_item_id": item_id, "item_id": created["id"],
                 "text": text, "index": body.index},
    )
    # mark the entry with the spawned item id — full-list overwrite discipline
    cl[body.index] = {**entry, "extracted": created["id"]}
    events.emit(
        event_type="item.checklist_updated",
        agg_type="item",
        agg_id=item_id,
        project_id=item["project_id"],
        payload={"checklist": json.dumps(cl, ensure_ascii=False)},
    )
    return {"extraction_id": extraction_id, "item": created,
            "text": text, "checklist": cl}


class BatchPatchIn(BaseModel):
    ids: list[str]
    patch: ItemPatch


@router.post("/projects/{project_id}/items/batch-patch")
def batch_patch_items(project_id: str, body: BatchPatchIn) -> dict:
    """Bulk edit (M22-I70, Plane bulk-bar semantics): the same patch applied to
    many items. Each item goes through patch_item so every change emits its own
    item.updated/item.status_changed/item.assigned event — the audit trail and
    automations see a batch exactly like N hand edits. Failures are reported
    per item; one bad item never rolls back the others."""
    if not body.ids:
        raise HTTPException(status_code=422, detail="ids must not be empty")
    results: list[dict] = []
    for iid in body.ids:
        try:
            row = db.get_conn().execute(
                "SELECT project_id FROM items WHERE id = ?", (iid,)).fetchone()
            if row is None or row["project_id"] != project_id:
                raise HTTPException(status_code=404, detail=f"item '{iid}' not in this project")
            patch_item(iid, body.patch)
            results.append({"id": iid, "ok": True})
        except HTTPException as e:
            results.append({"id": iid, "ok": False, "error": str(e.detail)})
    return {"results": results, "updated": sum(1 for r in results if r["ok"])}


@router.post("/items/{item_id}/relations")
def post_relation(item_id: str, body: RelationIn) -> dict:
    item = require_visible_item(item_id)
    target = require_item(body.to_item)
    onto = project_ontology(item["project_id"])
    valid = set(onto.relation_ids())
    if body.relation_type not in valid:
        raise HTTPException(
            status_code=422,
            detail=f"relation '{body.relation_type}' not allowed (kernel: {KERNEL_RELATIONS})",
        )
    if item["project_id"] != target["project_id"]:
        # M47-I143（docs/01 §AR.3，OpenProject 跨项目 relations 语义）：允许
        # 跨项目建链——关系跟着工作项走；事件仍聚合在 from 侧项目（append-only
        # 单写者不变）；建链要求双方项目当前用户可读，写门禁仍是 from 侧角色。
        from apm.core.events import effective_actor as _actor
        from apm.domains.members import is_instance_admin, member_role

        me = _actor()
        for pid in {item["project_id"], target["project_id"]}:
            if not (is_instance_admin(me) or member_role(pid, me)):
                raise HTTPException(
                    status_code=403,
                    detail=f"both projects must be readable to link them (not a member of {pid})")
    events.emit(
        event_type="item.related",
        agg_type="item",
        agg_id=item_id,
        project_id=item["project_id"],
        payload={"from_item": item_id, "to_item": body.to_item, "relation_type": body.relation_type,
                 "lag_days": body.lag_days},
    )
    # M27-I83 (docs/01 §Z.1, OpenProject 15.4 semantics): an explicit non-zero
    # lag on a depends_on relation immediately realigns an auto-scheduled
    # dependent — successor start = predecessor due + 1 + lag (negative lag =
    # lead overlap). None/0 keep the item's hand-set dates (opt-in, backward
    # compatible); later shifts propagate relatively, preserving the lag gap.
    if body.relation_type == "depends_on" and body.lag_days:
        succ = db.get_conn().execute(
            "SELECT auto_scheduled, start_date, due_date FROM items WHERE id = ?", (item_id,)
        ).fetchone()
        if succ["auto_scheduled"] and target["due_date"] and succ["due_date"]:
            base = date.fromisoformat(target["due_date"]) + timedelta(days=1 + body.lag_days)
            span = (date.fromisoformat(succ["due_date"]) - date.fromisoformat(succ["start_date"])).days \
                if succ["start_date"] else None
            # M34-I104: landing dates skip non-working days (docs/01 §AG.1).
            start_d = advance_to_workday(base)
            due_d = advance_to_workday(base + timedelta(days=span)) if span is not None else start_d
            if start_d > due_d:
                due_d = start_d
            new_start = start_d.isoformat()
            new_due = due_d.isoformat()
            events.emit(
                event_type="item.rescheduled",
                agg_type="item",
                agg_id=item_id,
                project_id=item["project_id"],
                payload={"follow_of": target["id"], "delta_days": None,
                         "start_date": new_start, "due_date": new_due,
                         "lag_days": body.lag_days, "depth": 1},
            )
            propagate_reschedule(item["project_id"], item_id, succ["due_date"], new_due,
                                 depth=1, visited={target["id"], item_id})
    return get_item_detail(item_id)


@router.delete("/items/{item_id}/relations")
def delete_relation(item_id: str, to_item: str, relation_type: str) -> dict:
    """I234 (docs/01 §BW.1): the removal face of item relations — creation
    (M17-I62) shipped without one, so a mistaken dependency was permanent.
    Composite key (from, to, type) locates the row (its surrogate `rel_*` id
    is minted inside the projection, unknown to callers); either side of the
    pair may bring the delete. Dates are NOT touched — removing a constraint
    is not a reschedule (Jira unlink semantics); the audit trail is the
    item.relation_removed fact itself."""
    require_visible_item(item_id)
    require_item(to_item)
    row = db.get_conn().execute(
        "SELECT * FROM item_relations WHERE relation_type = ?"
        " AND ((from_item = ? AND to_item = ?) OR (from_item = ? AND to_item = ?))",
        (relation_type, item_id, to_item, to_item, item_id)).fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"relation between {item_id} and {to_item} ({relation_type}) not found")
    # The removal fact lands in the from-side project (same ledger as
    # item.related — append-only single-writer preserved), so the from-side
    # project's write gate governs wherever the request came in.
    from apm.core.events import effective_actor as _actor
    from apm.domains.members import is_instance_admin, member_role

    me = _actor()
    if not (is_instance_admin(me) or member_role(row["project_id"], me)):
        raise HTTPException(
            status_code=403,
            detail=f"removal requires membership of the from-side project ({row['project_id']})")
    events.emit(
        event_type="item.relation_removed",
        agg_type="item",
        agg_id=row["from_item"],
        project_id=row["project_id"],
        payload={"from_item": row["from_item"], "to_item": row["to_item"],
                 "relation_type": relation_type},
    )
    return get_item_detail(item_id)


# ------------------------------------------------- CSV import/export (M24-I75)
IMPORT_FIELDS = ["title", "concept_id", "status", "priority", "start_date",
                 "due_date", "estimate_hours", "parent_title"]


class CsvImportIn(BaseModel):
    csv: str


@router.post("/projects/{project_id}/items/import")
def import_items(project_id: str, body: CsvImportIn) -> dict:
    """Bulk import (M24-I75, Redmine import semantics): first row is the header
    (fixed field names — see /items/import-template), each following row goes
    through create_item with full validation. parent_title references an
    existing item or an earlier row of the same file. Failures are reported
    per line; valid lines still import (no batch rollback)."""
    from apm.domains.projects import require_project
    require_project(project_id)
    reader = csv.DictReader(io.StringIO(body.csv))
    if not reader.fieldnames or "title" not in reader.fieldnames:
        raise HTTPException(status_code=422, detail="first row must be a header containing 'title'")
    known: dict[str, str] = {}
    for it in list_items(project_id=project_id):
        known.setdefault(it["title"], it["id"])
    results: list[dict] = []
    created = 0
    for line, row in enumerate(reader, start=2):
        title = (row.get("title") or "").strip()
        if not title:
            results.append({"line": line, "title": "", "ok": False, "error": "empty title"})
            continue
        parent_title = (row.get("parent_title") or "").strip() or None
        parent_id = known.get(parent_title) if parent_title else None
        if parent_title and not parent_id:
            results.append({"line": line, "title": title, "ok": False,
                            "error": f"unknown parent_title '{parent_title}'"})
            continue
        try:
            estimate = row.get("estimate_hours") or None
            s_date = (row.get("start_date") or "").strip() or None
            d_date = (row.get("due_date") or "").strip() or None
            _validate_item_dates(s_date, d_date)  # date validation lives outside create_item
            item = create_item(
                project_id=project_id,
                concept_id=(row.get("concept_id") or "").strip() or "task",
                title=title,
                status=(row.get("status") or "").strip() or None,
                priority=(row.get("priority") or "").strip() or None,
                start_date=s_date,
                due_date=d_date,
                estimate_hours=float(estimate) if estimate else None,
                parent_id=parent_id,
            )
            known[title] = item["id"]
            created += 1
            results.append({"line": line, "title": title, "ok": True, "item_id": item["id"]})
        except HTTPException as e:
            results.append({"line": line, "title": title, "ok": False, "error": str(e.detail)})
        except (ValueError, TypeError) as e:
            # e.g. estimate_hours not numeric — a data error, still per-line
            results.append({"line": line, "title": title, "ok": False, "error": str(e) or "invalid value"})
    return {"created": created, "failed": len(results) - created, "results": results}


@router.get("/projects/{project_id}/items/import-template")
def import_template(project_id: str) -> Response:
    from apm.domains.projects import require_project
    require_project(project_id)
    sample = (
        ",".join(IMPORT_FIELDS) + "\n"
        "搭建登录页,task,,high,2026-09-10,2026-09-12,4,\n"
        "兼容旧接口,task,,,2026-09-13,,2,搭建登录页\n"
    )
    return Response(content=sample, media_type="text/csv; charset=utf-8")


@router.get("/projects/{project_id}/items.csv")
def export_items_csv(project_id: str) -> Response:
    from apm.domains.projects import require_project
    require_project(project_id)
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT i.*, p.title AS parent_title FROM items i"
        " LEFT JOIN items p ON p.id = i.parent_id"
        " WHERE i.project_id = ? AND i.archived_at IS NULL ORDER BY i.created_at", (project_id,),
    ).fetchall()
    # M67-I201: hidden concepts don't appear in exports either
    viewer = events.effective_actor()
    rows = [r for r in rows if can_see_concept(project_id, r["concept_id"], viewer)]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(IMPORT_FIELDS + ["assignee_id", "status_group"])
    for it in rows:
        writer.writerow([
            it["title"], it["concept_id"], it["status"], it["priority"] or "",
            it["start_date"] or "", it["due_date"] or "", it["estimate_hours"] or "",
            it["parent_title"] or "", it["assignee_id"] or "", it["status_group"],
        ])
    # BOM so Excel opens UTF-8 Chinese correctly
    return Response(content="\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8")
