"""Project cycles (M39-I119, docs/01 §AL.1): Plane Cycles and OpenProject 17.3
both treat an iteration as a date-boxed work container distinct from
versions/milestones — a sprint is not a renamed version. AgentPM's minimal
face: `cycle.*` events project into `project_cycles` (in drop_projections),
items mount by `cycle_id` through the plain item.updated path, the board
filters on it, and the daily sweep explicitly carries a finished cycle's
unfinished items into the project's next cycle (`cycle.carried_over`) —
ownership-only bookkeeping that never touches start/due dates."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on

router = APIRouter(tags=["cycles"])


# ---------------------------------------------------------------- projectors
@on("cycle.created")
def _proj_cycle_created(conn, e):
    p = e.payload
    conn.execute(
        "INSERT INTO project_cycles (id, project_id, name, start_date, end_date,"
        " cancelled_at, created_at) VALUES (?,?,?,?,?,NULL,?)",
        (e.agg_id, e.project_id, p["name"], p["start_date"], p["end_date"], e.ts),
    )


@on("cycle.updated")
def _proj_cycle_updated(conn, e):
    p = e.payload
    sets, params = [], []
    for key in ("name", "start_date", "end_date"):
        if key in p:
            sets.append(f"{key} = ?")
            params.append(p[key])
    if sets:
        params.append(e.agg_id)
        conn.execute(f"UPDATE project_cycles SET {', '.join(sets)} WHERE id = ?", params)


@on("cycle.cancelled")
def _proj_cycle_cancelled(conn, e):
    conn.execute(
        "UPDATE project_cycles SET cancelled_at = ? WHERE id = ?", (e.ts, e.agg_id))


# ---------------------------------------------------------------- helpers
def get_cycle(cycle_id: str) -> dict | None:
    row = db.get_conn().execute(
        "SELECT * FROM project_cycles WHERE id = ?", (cycle_id,)).fetchone()
    return dict(row) if row else None


def require_cycle(cycle_id: str) -> dict:
    c = get_cycle(cycle_id)
    if c is None or c["cancelled_at"]:
        raise HTTPException(status_code=404, detail=f"unknown cycle '{cycle_id}'")
    return c


def _validate_dates(start: str, end: str) -> None:
    from datetime import date as _date
    try:
        s, e = _date.fromisoformat(start), _date.fromisoformat(end)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid date")
    if end < start:
        raise HTTPException(status_code=422, detail="end_date must not precede start_date")


def _overlaps(project_id: str, start: str, end: str, exclude: str | None = None) -> bool:
    row = db.get_conn().execute(
        "SELECT 1 FROM project_cycles WHERE project_id = ? AND cancelled_at IS NULL"
        " AND id IS NOT ? AND NOT (end_date < ? OR start_date > ?) LIMIT 1",
        (project_id, exclude, start, end)).fetchone()
    return row is not None


class CycleIn(BaseModel):
    name: str
    start_date: str
    end_date: str


class CyclePatch(BaseModel):
    name: str | None = None
    start_date: str | None = None
    end_date: str | None = None


# ---------------------------------------------------------------- endpoints
@router.get("/projects/{project_id}/cycles")
def list_cycles(project_id: str) -> dict:
    rows = db.get_conn().execute(
        "SELECT * FROM project_cycles WHERE project_id = ? AND cancelled_at IS NULL"
        " ORDER BY start_date", (project_id,)).fetchall()
    return {"cycles": [dict(r) for r in rows]}


@router.post("/projects/{project_id}/cycles")
def create_cycle(project_id: str, body: CycleIn) -> dict:
    _validate_dates(body.start_date, body.end_date)
    if _overlaps(project_id, body.start_date, body.end_date):
        raise HTTPException(status_code=409, detail="overlaps an existing cycle")
    cid = new_id("cy")
    events.emit(
        event_type="cycle.created", agg_type="cycle", agg_id=cid,
        project_id=project_id, actor_type="human", actor_id=events.effective_actor(),
        payload={"name": body.name, "start_date": body.start_date,
                 "end_date": body.end_date},
    )
    return {"id": cid, "name": body.name, "start_date": body.start_date,
            "end_date": body.end_date}


@router.patch("/cycles/{cycle_id}")
def patch_cycle(cycle_id: str, body: CyclePatch) -> dict:
    c = require_cycle(cycle_id)
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    if not changes:
        return c
    start = changes.get("start_date", c["start_date"])
    end = changes.get("end_date", c["end_date"])
    _validate_dates(start, end)
    if _overlaps(c["project_id"], start, end, exclude=cycle_id):
        raise HTTPException(status_code=409, detail="overlaps an existing cycle")
    events.emit(
        event_type="cycle.updated", agg_type="cycle", agg_id=cycle_id,
        project_id=c["project_id"], actor_type="human", actor_id=events.effective_actor(),
        payload=changes,
    )
    return {**c, **changes}


@router.delete("/cycles/{cycle_id}")
def cancel_cycle(cycle_id: str) -> dict:
    c = require_cycle(cycle_id)
    events.emit(
        event_type="cycle.cancelled", agg_type="cycle", agg_id=cycle_id,
        project_id=c["project_id"], actor_type="human", actor_id=events.effective_actor(),
        payload={"name": c["name"]},
    )
    return {"cancelled": cycle_id}


# ---------------------------------------------------------------- sweep hook
def carryover_finished_cycles(conn, today: str) -> int:
    """The day after a cycle ends, its unfinished items move to the project's
    next cycle (smallest start_date after this end_date) with a
    `cycle.carried_over` fact — the fact makes re-sweeps no-ops and keeps the
    audit trail. No next cycle, or nothing unfinished: nothing happens."""
    carried = 0
    rows = conn.execute(
        "SELECT * FROM project_cycles WHERE cancelled_at IS NULL AND end_date < ?"
        " ORDER BY end_date", (today,)).fetchall()
    for c in rows:
        already = conn.execute(
            "SELECT 1 FROM events WHERE event_type = 'cycle.carried_over'"
            " AND json_extract(payload, '$.from_cycle') = ? LIMIT 1", (c["id"],)).fetchone()
        if already:
            continue
        nxt = conn.execute(
            "SELECT id FROM project_cycles WHERE project_id = ? AND cancelled_at IS NULL"
            " AND start_date > ? ORDER BY start_date LIMIT 1",
            (c["project_id"], c["end_date"])).fetchone()
        if nxt is None:
            continue
        ids = [r["id"] for r in conn.execute(
            "SELECT id FROM items WHERE cycle_id = ?"
            " AND status_group NOT IN ('done','cancelled') AND archived_at IS NULL",
            (c["id"],)).fetchall()]
        if not ids:
            continue
        for iid in ids:
            events.emit(
                event_type="item.updated", agg_type="item", agg_id=iid,
                project_id=c["project_id"], actor_type="automation", actor_id="scheduler",
                payload={"cycle_id": nxt["id"]},
            )
        events.emit(
            event_type="cycle.carried_over", agg_type="cycle", agg_id=c["id"],
            project_id=c["project_id"], actor_type="automation", actor_id="scheduler",
            payload={"from_cycle": c["id"], "to_cycle": nxt["id"],
                     "items": ids, "count": len(ids), "sweep_date": today},
        )
        carried += len(ids)
    return carried
