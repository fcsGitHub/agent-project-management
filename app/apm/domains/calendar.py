"""Working calendar (M34-I104, docs/01 §AG.1): OpenProject 12.3 lets admins
define global non-working days (holidays) on top of the work week, and
auto-scheduled work packages skip them when their dates land on one; manually
scheduled packages are untouched. AgentPM's minimal face: `calendar.holiday_*`
events project into `non_working_days` (in drop_projections — rebuild
reproduces them) and `advance_to_workday` is the single landing-date helper
that M14's auto-schedule propagation defers to. Manual items never reach that
branch, so hand-set dates keep OpenProject's "manual" semantics for free."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm.core import db, events
from apm.core.projections import on
from apm.domains.members import is_instance_admin

router = APIRouter(tags=["calendar"])


# ---------------------------------------------------------------- projectors
@on("calendar.holiday_added")
def _proj_holiday_added(conn, e):
    conn.execute(
        "INSERT INTO non_working_days (date, note, created_at) VALUES (?,?,?)"
        " ON CONFLICT(date) DO UPDATE SET note = excluded.note",
        (e.agg_id, e.payload.get("note"), e.ts),
    )


@on("calendar.holiday_removed")
def _proj_holiday_removed(conn, e):
    conn.execute("DELETE FROM non_working_days WHERE date = ?", (e.agg_id,))


# ---------------------------------------------------------------- helper
def advance_to_workday(d: date, conn=None) -> date:
    """`d` itself if it is a working day, else the next one (skips
    Sat/Sun plus projected non-working days; year-capped against an
    all-holidays calendar)."""
    conn = conn or db.get_conn()
    for _ in range(370):
        if d.weekday() < 5 and not conn.execute(
            "SELECT 1 FROM non_working_days WHERE date = ?", (d.isoformat(),)
        ).fetchone():
            return d
        d += timedelta(days=1)
    return d


# ---------------------------------------------------------------- admin API
def _require_admin() -> None:
    if not is_instance_admin(events.effective_actor()):
        raise HTTPException(status_code=403, detail="admin role required for the working calendar")


class HolidayIn(BaseModel):
    date: str
    note: str | None = None


@router.get("/calendar/holidays")
def list_holidays() -> dict:
    rows = db.get_conn().execute(
        "SELECT date, note, created_at FROM non_working_days ORDER BY date"
    ).fetchall()
    return {"holidays": [dict(r) for r in rows]}


@router.post("/calendar/holidays")
def add_holiday(body: HolidayIn) -> dict:
    _require_admin()
    try:
        day = date.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"invalid date: {body.date!r}")
    if db.get_conn().execute(
        "SELECT 1 FROM non_working_days WHERE date = ?", (body.date,)
    ).fetchone():
        raise HTTPException(status_code=409, detail=f"{body.date} is already a non-working day")
    events.emit(
        event_type="calendar.holiday_added", agg_type="holiday", agg_id=day.isoformat(),
        actor_type="human", actor_id=events.effective_actor(),
        payload={"note": body.note},
    )
    return {"date": body.date, "note": body.note}


@router.delete("/calendar/holidays/{day}")
def remove_holiday(day: str) -> dict:
    _require_admin()
    try:
        day = date.fromisoformat(day).isoformat()
    except ValueError:
        raise HTTPException(status_code=422, detail=f"invalid date: {day!r}")
    if not db.get_conn().execute(
        "SELECT 1 FROM non_working_days WHERE date = ?", (day,)
    ).fetchone():
        raise HTTPException(status_code=404, detail=f"{day} is not a non-working day")
    events.emit(
        event_type="calendar.holiday_removed", agg_type="holiday", agg_id=day,
        actor_type="human", actor_id=events.effective_actor(),
        payload={},
    )
    return {"removed": day}
