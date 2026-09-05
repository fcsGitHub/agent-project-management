"""Timesheet submission & approval (M28-I86, docs/01 §AA.1): period-based
log → submit → approve/reject workflow with a lock on approval (Redmine
plugin semantics — Redmineflux/Easy8; native in none of the OSS core tools).
An approved timesheet freezes the member's entries inside the period: further
log/edit/delete touching those dates is 409 "timesheet locked". Everything is
event-sourced (timesheet.submitted/approved/rejected) so the projection —
including the lock — replays deterministically."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on

router = APIRouter(tags=["timesheet"])

MAX_REASON = 300


# ------------------------------------------------------------ projections
@on("timesheet.submitted")
def _proj_timesheet_submitted(conn, e):
    # INSERT OR REPLACE: a resubmission reuses the rejected row's id and resets
    # it to a clean submitted state (stale decided_by/reason must not survive)
    p = e.payload
    conn.execute(
        "INSERT OR REPLACE INTO timesheets (id, project_id, user_id, period_start,"
        " period_end, total_minutes, entry_count, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (e.agg_id, e.project_id, p["user_id"], p["period_start"], p["period_end"],
         p["total_minutes"], p["entry_count"], "submitted", e.ts, e.ts),
    )


@on("timesheet.approved")
def _proj_timesheet_approved(conn, e):
    p = e.payload
    conn.execute(
        "UPDATE timesheets SET status = 'approved', decided_by = ?, decided_at = ?,"
        " updated_at = ? WHERE id = ?",
        (p["decided_by"], e.ts, e.ts, e.agg_id),
    )


@on("timesheet.rejected")
def _proj_timesheet_rejected(conn, e):
    p = e.payload
    conn.execute(
        "UPDATE timesheets SET status = 'rejected', decided_by = ?, decided_at = ?,"
        " reason = ?, updated_at = ? WHERE id = ?",
        (p["decided_by"], e.ts, p.get("reason", ""), e.ts, e.agg_id),
    )


# ---------------------------------------------------------------- helpers
def _validate_iso(d: str, field: str) -> str:
    try:
        date.fromisoformat(d)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail=f"{field} must be an ISO date (YYYY-MM-DD)")
    return d


def _period_overlaps_locked(project_id: str, user_id: str,
                            period_start: str, period_end: str) -> bool:
    """A pending-overlap check for new submissions: an approved timesheet of the
    same member/project whose window intersects [period_start, period_end]
    makes the new submission meaningless (its dates are already frozen)."""
    row = db.get_conn().execute(
        "SELECT 1 FROM timesheets WHERE project_id = ? AND user_id = ?"
        " AND status = 'approved' AND period_start <= ? AND period_end >= ? LIMIT 1",
        (project_id, user_id, period_end, period_start),
    ).fetchone()
    return row is not None


def _assert_dates_unlockable(project_id: str, user_id: str, *days: str | None) -> None:
    """The lock guard: every date the write path touches (an entry's current or
    new spent_on) must fall outside any approved period of the same member."""
    for d in days:
        if not d:
            continue
        row = db.get_conn().execute(
            "SELECT period_start, period_end FROM timesheets WHERE project_id = ?"
            " AND user_id = ? AND status = 'approved'"
            " AND period_start <= ? AND period_end >= ? LIMIT 1",
            (project_id, user_id, d, d),
        ).fetchone()
        if row is not None:
            raise HTTPException(
                status_code=409,
                detail=f"timesheet locked: {d} falls inside the approved period "
                       f"{row['period_start']}..{row['period_end']}")


def _require_timesheet(ts_id: str) -> dict:
    row = db.get_conn().execute(
        "SELECT * FROM timesheets WHERE id = ?", (ts_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"unknown timesheet '{ts_id}'")
    return dict(row)


def _require_approver(project_id: str) -> None:
    """Only the project owner (or an instance admin) decides on timesheets."""
    from apm import config
    from apm.domains.members import is_instance_admin, member_role
    actor = events.effective_actor()
    if is_instance_admin(actor) or config.settings.auth_mode == "local":
        return
    if member_role(project_id, actor) != "owner":
        raise HTTPException(status_code=403, detail="only the project owner can decide timesheets")


def _is_approver(project_id: str) -> bool:
    from apm import config
    from apm.domains.members import is_instance_admin, member_role
    actor = events.effective_actor()
    if is_instance_admin(actor) or config.settings.auth_mode == "local":
        return True
    return member_role(project_id, actor) == "owner"


# ---------------------------------------------------------------- API
class SubmitIn(BaseModel):
    project_id: str
    period_start: str
    period_end: str

    @field_validator("period_end")
    @classmethod
    def _iso(cls, v: str) -> str:
        return _validate_iso(v, "period_end")

    @field_validator("period_start")
    @classmethod
    def _iso2(cls, v: str) -> str:
        return _validate_iso(v, "period_start")


class RejectIn(BaseModel):
    reason: str = ""

    @field_validator("reason")
    @classmethod
    def reason_cap(cls, v: str) -> str:
        return v[:MAX_REASON]


@router.post("/me/timesheets/submit")
def submit_timesheet(body: SubmitIn) -> dict:
    from apm.domains.projects import require_project
    from apm.domains.timelog import _gate

    require_project(body.project_id)
    _gate(body.project_id)
    me = events.effective_actor()
    if body.period_start > body.period_end:
        raise HTTPException(status_code=422, detail="period_start must be <= period_end")
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT COALESCE(SUM(minutes), 0) AS total, COUNT(*) AS cnt FROM item_time_entries"
        " WHERE project_id = ? AND user_id = ? AND deleted_at IS NULL"
        " AND spent_on >= ? AND spent_on <= ?",
        (body.project_id, me, body.period_start, body.period_end),
    ).fetchone()
    if rows["cnt"] == 0:
        raise HTTPException(status_code=422, detail="no time entries in this period")
    existing = conn.execute(
        "SELECT id, status FROM timesheets WHERE project_id = ? AND user_id = ?"
        " AND period_start = ? AND period_end = ?",
        (body.project_id, me, body.period_start, body.period_end),
    ).fetchone()
    if existing is not None:
        if existing["status"] in ("submitted", "approved"):
            raise HTTPException(status_code=409,
                                detail=f"timesheet for this period is already {existing['status']}")
        # rejected → resubmission reuses the row via a fresh submitted event
        events.emit(
            event_type="timesheet.submitted", agg_type="timesheet", agg_id=existing["id"],
            project_id=body.project_id,
            payload={"user_id": me, "period_start": body.period_start,
                     "period_end": body.period_end, "total_minutes": rows["total"],
                     "entry_count": rows["cnt"], "resubmitted": True},
        )
        return _require_timesheet(existing["id"])
    if _period_overlaps_locked(body.project_id, me, body.period_start, body.period_end):
        raise HTTPException(status_code=409,
                            detail="period overlaps an approved (locked) timesheet")
    ts_id = new_id("ts")
    events.emit(
        event_type="timesheet.submitted", agg_type="timesheet", agg_id=ts_id,
        project_id=body.project_id,
        payload={"user_id": me, "period_start": body.period_start,
                 "period_end": body.period_end, "total_minutes": rows["total"],
                 "entry_count": rows["cnt"]},
    )
    return _require_timesheet(ts_id)  # type: ignore[return-value]


@router.get("/me/timesheets")
def my_timesheets() -> dict:
    """The caller's own submissions across all projects (MyTimePage panel)."""
    me = events.effective_actor()
    rows = db.get_conn().execute(
        "SELECT t.*, p.name AS project_name FROM timesheets t"
        " LEFT JOIN projects p ON p.id = t.project_id"
        " WHERE t.user_id = ? ORDER BY t.created_at DESC",
        (me,),
    ).fetchall()
    return {"timesheets": [dict(r) for r in rows]}


@router.get("/projects/{project_id}/timesheets")
def list_timesheets(project_id: str) -> dict:
    from apm.domains.timelog import _gate

    _gate(project_id)
    rows = db.get_conn().execute(
        "SELECT t.*, u.name AS user_name, p.name AS project_name FROM timesheets t"
        " LEFT JOIN users u ON u.id = t.user_id"
        " LEFT JOIN projects p ON p.id = t.project_id"
        " WHERE t.project_id = ? ORDER BY t.created_at DESC",
        (project_id,),
    ).fetchall()
    return {"timesheets": [dict(r) for r in rows],
            "can_approve": _is_approver(project_id)}


@router.post("/timesheets/{ts_id}/approve")
def approve_timesheet(ts_id: str) -> dict:
    ts = _require_timesheet(ts_id)
    if ts["status"] != "submitted":
        raise HTTPException(status_code=409,
                            detail=f"timesheet is {ts['status']}, not submitted")
    _require_approver(ts["project_id"])
    events.emit(
        event_type="timesheet.approved", agg_type="timesheet", agg_id=ts_id,
        project_id=ts["project_id"],
        payload={"decided_by": events.effective_actor()},
    )
    return _require_timesheet(ts_id)  # type: ignore[return-value]


@router.post("/timesheets/{ts_id}/reject")
def reject_timesheet(ts_id: str, body: RejectIn) -> dict:
    ts = _require_timesheet(ts_id)
    if ts["status"] != "submitted":
        raise HTTPException(status_code=409,
                            detail=f"timesheet is {ts['status']}, not submitted")
    _require_approver(ts["project_id"])
    events.emit(
        event_type="timesheet.rejected", agg_type="timesheet", agg_id=ts_id,
        project_id=ts["project_id"],
        payload={"decided_by": events.effective_actor(), "reason": body.reason},
    )
    return _require_timesheet(ts_id)  # type: ignore[return-value]
