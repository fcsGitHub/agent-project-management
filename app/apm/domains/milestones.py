"""Milestones domain (M13-I41): deadline anchors that group work items
(docs/01 §L.2 — Plane v1.16 pattern: a milestone is a date anchor, orthogonal
to time-boxed cycles). Event-sourced like every domain; progress is computed
from the linked items' status_groups, so rebuild consistency carries over.

Item linkage uses the long-idle items.milestone_id column; the timeline view
(I42) renders these anchors as diamonds on the date axis."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on

router = APIRouter(tags=["milestones"])

_GENERIC_STATUSES = ("planned", "in_progress", "achieved", "cancelled")


def _today() -> date:
    return datetime.now(timezone.utc).date()


# ------------------------------------------------------------ projections
@on("milestone.created")
def _proj_milestone_created(conn, e):
    p = e.payload
    conn.execute(
        "INSERT INTO milestones (id, project_id, title, description, due_date, status,"
        " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (e.agg_id, e.project_id, p["title"], p.get("description"),
         p["due_date"], p.get("status", "planned"), e.ts, e.ts),
    )


@on("milestone.updated")
def _proj_milestone_updated(conn, e):
    p = e.payload
    sets, params = [], []
    for key in ("title", "description", "due_date", "status"):
        if key in p:
            sets.append(f"{key} = ?")
            params.append(p[key])
    if sets:
        sets.append("updated_at = ?")
        params.extend([e.ts, e.agg_id])
        conn.execute(f"UPDATE milestones SET {', '.join(sets)} WHERE id = ?", params)


@on("milestone.deleted")
def _proj_milestone_deleted(conn, e):
    conn.execute("DELETE FROM milestones WHERE id = ?", (e.agg_id,))


# ---------------------------------------------------------------- helpers
def get_milestone(milestone_id: str) -> dict | None:
    row = db.get_conn().execute(
        "SELECT * FROM milestones WHERE id = ?", (milestone_id,)).fetchone()
    return dict(row) if row else None


def require_milestone(milestone_id: str) -> dict:
    m = get_milestone(milestone_id)
    if not m:
        raise HTTPException(status_code=422, detail=f"unknown milestone '{milestone_id}'")
    return m


def milestone_statuses(project_id: str) -> tuple[str, ...]:
    """Prefer the ontology's milestone concept states; fall back to a generic set."""
    try:
        from apm.domains.items import project_ontology
        concept = project_ontology(project_id).concept("milestone")
        ids = tuple(s["id"] for s in concept.states)
        return ids or _GENERIC_STATUSES
    except Exception:
        return _GENERIC_STATUSES


def _validate_iso_date(value: str, field: str = "due_date") -> str:
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422,
                            detail=f"{field} must be an ISO date (YYYY-MM-DD), got {value!r}")
    return value


def milestone_progress(m: dict) -> dict:
    """Linked-item progress: done ratio over non-cancelled items + overdue count
    (active items once the milestone due date has passed)."""
    rows = db.get_conn().execute(
        "SELECT status_group, COUNT(*) c FROM items WHERE milestone_id = ? GROUP BY status_group",
        (m["id"],),
    ).fetchall()
    counts = {r["status_group"]: r["c"] for r in rows}
    total = sum(v for k, v in counts.items() if k != "cancelled")
    done = counts.get("done", 0)
    overdue_items = counts.get("backlog", 0) + counts.get("todo", 0) + counts.get("in_progress", 0) \
        if date.fromisoformat(m["due_date"]) < _today() else 0
    return {
        "items_total": total,
        "items_done": done,
        "done_ratio": round(done / total, 2) if total else None,
        "overdue_items": overdue_items,
    }


# ---------------------------------------------------------------- API
class MilestoneIn(BaseModel):
    title: str
    due_date: str
    description: str | None = None


class MilestonePatch(BaseModel):
    title: str | None = None
    description: str | None = None
    due_date: str | None = None
    status: str | None = None


@router.post("/projects/{project_id}/milestones")
def post_milestone(project_id: str, body: MilestoneIn) -> dict:
    from apm.domains.projects import require_project

    require_project(project_id)
    _validate_iso_date(body.due_date)
    mid = new_id("ms")
    events.emit(
        event_type="milestone.created",
        agg_type="milestone",
        agg_id=mid,
        project_id=project_id,
        payload={"title": body.title, "description": body.description,
                 "due_date": body.due_date, "status": "planned"},
    )
    m = get_milestone(mid)  # type: ignore[return-value]
    m["progress"] = milestone_progress(m)
    return m


@router.get("/projects/{project_id}/milestones")
def list_milestones(project_id: str) -> dict:
    rows = db.get_conn().execute(
        "SELECT * FROM milestones WHERE project_id = ? ORDER BY due_date, created_at",
        (project_id,),
    ).fetchall()
    return {"milestones": [{**dict(m), "progress": milestone_progress(dict(m))}
                           for m in rows]}


@router.get("/milestones/{milestone_id}")
def get_milestone_detail(milestone_id: str) -> dict:
    m = require_milestone(milestone_id)
    from apm.domains.members import require_project_read

    require_project_read(m["project_id"])  # M114-I339: 读门对齐写侧 M80-I240
    m["progress"] = milestone_progress(m)
    items = db.get_conn().execute(
        "SELECT id, title, concept_id, status, status_group, assignee_id"
        " FROM items WHERE milestone_id = ? ORDER BY created_at",
        (milestone_id,),
    ).fetchall()
    m["items"] = [dict(r) for r in items]
    return m


@router.patch("/milestones/{milestone_id}")
def patch_milestone(milestone_id: str, body: MilestonePatch) -> dict:
    m = require_milestone(milestone_id)
    from apm.domains.members import require_project_write
    require_project_write(m["project_id"])  # M80-I240
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    if not changes:
        return m
    if "due_date" in changes:
        _validate_iso_date(changes["due_date"])
    if "status" in changes:
        allowed = milestone_statuses(m["project_id"])
        if changes["status"] not in allowed:
            raise HTTPException(status_code=422,
                                detail=f"status must be one of {list(allowed)}")
    events.emit(
        event_type="milestone.updated",
        agg_type="milestone",
        agg_id=milestone_id,
        project_id=m["project_id"],
        payload=changes,
    )
    return get_milestone(milestone_id)  # type: ignore[return-value]


@router.delete("/milestones/{milestone_id}")
def delete_milestone(milestone_id: str) -> dict:
    m = require_milestone(milestone_id)
    from apm.domains.members import require_project_write
    require_project_write(m["project_id"])  # M80-I240
    events.emit(
        event_type="milestone.deleted",
        agg_type="milestone",
        agg_id=milestone_id,
        project_id=m["project_id"],
        payload={"title": m["title"]},
    )
    return {"deleted": milestone_id}


@router.get("/milestones/{milestone_id}/burndown")
def milestone_burndown(milestone_id: str) -> dict:
    """M27-I85 (docs/01 §Z.3): event-replayed burndown — remaining linked items
    per day vs an ideal line from total to zero across created→due. Jira/Taiga
    bind burndown to time-boxed sprints; we have no cycles, so the milestone is
    the anchor and the series is a pure replay of item.status_changed events
    (append-only ⇒ replay equals live, zero new tables)."""
    m = require_milestone(milestone_id)
    from apm.domains.members import require_project_read

    require_project_read(m["project_id"])  # M114-I339: 读门对齐写侧 M80-I240
    project_id = m["project_id"]
    conn = db.get_conn()
    items = conn.execute(
        "SELECT id FROM items WHERE milestone_id = ? AND status_group != 'cancelled'",
        (milestone_id,),
    ).fetchall()
    total = len(items)
    item_ids = {r["id"] for r in items}

    # first-arrival day of done per item, replayed from the event stream
    first_done: dict[str, str] = {}
    if item_ids:
        for e in conn.execute(
            "SELECT agg_id, payload, ts FROM events"
            " WHERE project_id = ? AND event_type = 'item.status_changed' ORDER BY id",
            (project_id,),
        ).fetchall():
            if e["agg_id"] not in item_ids or e["agg_id"] in first_done:
                continue
            if json.loads(e["payload"]).get("status_group") == "done":
                first_done[e["agg_id"]] = e["ts"][:10]

    start = (m["created_at"] or "")[:10]
    due = m["due_date"]
    today = _today().isoformat()
    window_days = max((date.fromisoformat(due) - date.fromisoformat(start)).days, 1) \
        if start and start < due else 1

    def remaining_on(day: str) -> int:
        return total - sum(1 for d in first_done.values() if d <= day)

    # actual line: start → min(today, due) — frozen at due once the window closes
    actual_end = min(today, due) if start and today > start else start
    series = []
    if total:
        step = max((date.fromisoformat(actual_end) - date.fromisoformat(start)).days, 0)
        for i in range(step + 1):
            day = date.fromisoformat(start) + timedelta(days=i)
            series.append({"date": day.isoformat(), "remaining": remaining_on(day.isoformat())})

    # ideal line: total → 0 across the whole window
    ideal = [
        {"date": (date.fromisoformat(start) + timedelta(days=i)).isoformat(),
         "remaining": round(total * (1 - i / window_days))}
        for i in range(window_days + 1)
    ] if total else []

    week = [(date.fromisoformat(today) - timedelta(days=k)).isoformat() for k in range(7)]
    velocity_done = sum(1 for d in first_done.values() if d in week)
    return {
        "milestone_id": m["id"], "title": m["title"], "due_date": due,
        "total": total, "remaining": total - len(first_done),
        "series": series, "ideal": ideal,
        "velocity": {"days": 7, "done": velocity_done},
    }
