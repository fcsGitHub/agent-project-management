"""Work-item time entries (M19-I59): event-sourced spent-time log (OpenProject
time-entry semantics — duration/date/note/author per work item). Plan vs actual
sits next to each other: items carry estimate_hours, the SUM of entries is the
spent side. Logging time also joins the item's participant audience (M18)."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on

router = APIRouter(tags=["timelog"])

MAX_NOTE = 500


def _assert_unlockable(project_id: str, user_id: str, *days: str | None) -> None:
    """M28-I86: an approved timesheet freezes the member's dates it covers.
    Imported lazily to avoid a timelog↔timesheet import cycle."""
    from apm.domains.timesheet import _assert_dates_unlockable
    _assert_dates_unlockable(project_id, user_id, *days)


# ------------------------------------------------------------ projections
@on("time.logged")
def _proj_time_logged(conn, e):
    p = e.payload
    conn.execute(
        "INSERT INTO item_time_entries (id, item_id, project_id, user_id, minutes,"
        " spent_on, note, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (e.agg_id, p["item_id"], e.project_id, p["user_id"], p["minutes"],
         p["spent_on"], p.get("note", ""), e.ts),
    )
    _join_time_participant(conn, e.project_id, p["item_id"], p["user_id"])


@on("time.edited")
def _proj_time_edited(conn, e):
    p = e.payload
    sets, args = [], []
    for key in ("minutes", "spent_on", "note"):
        if key in p:
            sets.append(f"{key} = ?")
            args.append(p[key])
    if not sets:
        return
    args.append(e.agg_id)
    conn.execute(f"UPDATE item_time_entries SET {', '.join(sets)} WHERE id = ?", args)


@on("time.deleted")
def _proj_time_deleted(conn, e):
    conn.execute("UPDATE item_time_entries SET deleted_at = ? WHERE id = ?", (e.ts, e.agg_id))


def _join_time_participant(conn, project_id: str, item_id: str, user_id: str) -> None:
    from apm.domains.comments import _join_participants
    _join_participants(conn, project_id, item_id, [(user_id, "time")])


# ---------------------------------------------------------------- helpers
def _require_item(item_id: str) -> dict:
    row = db.get_conn().execute(
        "SELECT id, project_id FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"unknown item '{item_id}'")
    return dict(row)


def _gate(project_id: str) -> None:
    """local mode trusted; network mode requires any project membership."""
    from apm import config
    from apm.domains.members import member_role
    if config.settings.auth_mode == "local":
        return
    if member_role(project_id, events.effective_actor()) is None:
        raise HTTPException(status_code=403, detail="not a project member")


def _entry(entry_id: str) -> dict:
    row = db.get_conn().execute(
        "SELECT t.*, u.name AS user_name FROM item_time_entries t"
        " LEFT JOIN users u ON u.id = t.user_id"
        " WHERE t.id = ?", (entry_id,)).fetchone()
    if row is None or row["deleted_at"] is not None:
        raise HTTPException(status_code=404, detail=f"unknown time entry '{entry_id}'")
    return dict(row)


def _validate_minutes(minutes: int) -> int:
    if not isinstance(minutes, int) or minutes <= 0 or minutes > 24 * 60:
        raise HTTPException(status_code=422, detail="minutes must be an integer in (0, 1440]")
    return minutes


def _validate_spent_on(spent_on: str) -> str:
    try:
        date.fromisoformat(spent_on)
    except ValueError:
        raise HTTPException(status_code=422, detail="spent_on must be an ISO date (YYYY-MM-DD)")
    return spent_on


# ---------------------------------------------------------------- API
class TimeLogIn(BaseModel):
    minutes: int
    spent_on: str
    note: str = ""

    @field_validator("note")
    @classmethod
    def note_cap(cls, v: str) -> str:
        return v[:MAX_NOTE]


class TimeEditIn(BaseModel):
    minutes: int | None = None
    spent_on: str | None = None
    note: str | None = None

    @field_validator("note")
    @classmethod
    def note_cap(cls, v: str | None) -> str | None:
        return v[:MAX_NOTE] if v is not None else None


@router.post("/items/{item_id}/time_entries")
def log_time(item_id: str, body: TimeLogIn) -> dict:
    item = _require_item(item_id)
    _gate(item["project_id"])
    user_id = events.effective_actor()
    _validate_minutes(body.minutes)
    _validate_spent_on(body.spent_on)
    _assert_unlockable(item["project_id"], user_id, body.spent_on)
    entry_id = new_id("te")
    events.emit(
        event_type="time.logged",
        agg_type="time_entry",
        agg_id=entry_id,
        project_id=item["project_id"],
        payload={
            "item_id": item_id,
            "user_id": user_id,
            "minutes": body.minutes,
            "spent_on": body.spent_on,
            "note": body.note,
        },
    )
    return get_time_entry(entry_id)


@router.get("/items/{item_id}/time_entries")
def list_time_entries(item_id: str) -> dict:
    item = _require_item(item_id)
    _gate(item["project_id"])
    rows = db.get_conn().execute(
        "SELECT t.*, u.name AS user_name FROM item_time_entries t"
        " LEFT JOIN users u ON u.id = t.user_id"
        " WHERE t.item_id = ? AND t.deleted_at IS NULL ORDER BY t.spent_on, t.created_at",
        (item_id,),
    ).fetchall()
    total = sum(r["minutes"] for r in rows)
    return {"entries": [dict(r) for r in rows],
            "total_minutes": total,
            "participants": [dict(r) for r in db.get_conn().execute(
                "SELECT user_id, source FROM item_participants WHERE item_id = ?"
                " ORDER BY created_at", (item_id,))]}


def get_time_entry(entry_id: str) -> dict:
    row = db.get_conn().execute(
        "SELECT t.*, u.name AS user_name FROM item_time_entries t"
        " LEFT JOIN users u ON u.id = t.user_id"
        " WHERE t.id = ?", (entry_id,)).fetchone()
    if row is None or row["deleted_at"] is not None:
        raise HTTPException(status_code=404, detail=f"unknown time entry '{entry_id}'")
    return dict(row)


@router.get("/time_entries/{entry_id}")
def read_time_entry(entry_id: str) -> dict:
    return get_time_entry(entry_id)


@router.patch("/time_entries/{entry_id}")
def edit_time_entry(entry_id: str, body: TimeEditIn) -> dict:
    entry = _entry(entry_id)
    _gate(entry["project_id"])
    actor = events.effective_actor()
    from apm import config
    from apm.domains.members import is_instance_admin
    if config.settings.auth_mode != "local" and actor != entry["user_id"] \
            and not is_instance_admin(actor):
        raise HTTPException(status_code=403, detail="only the author or an admin can edit")
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    if not changes:
        raise HTTPException(status_code=422, detail="nothing to update")
    if "minutes" in changes:
        _validate_minutes(changes["minutes"])
    if "spent_on" in changes:
        _validate_spent_on(changes["spent_on"])
    # lock covers both where the entry sits today and where it would move to
    _assert_unlockable(entry["project_id"], entry["user_id"],
                       entry["spent_on"], changes.get("spent_on"))
    events.emit(
        event_type="time.edited",
        agg_type="time_entry",
        agg_id=entry_id,
        project_id=entry["project_id"],
        payload=changes,
    )
    return get_time_entry(entry_id)


@router.delete("/time_entries/{entry_id}")
def delete_time_entry(entry_id: str) -> dict:
    entry = _entry(entry_id)
    _gate(entry["project_id"])
    actor = events.effective_actor()
    from apm import config
    from apm.domains.members import is_instance_admin
    if config.settings.auth_mode != "local" and actor != entry["user_id"] \
            and not is_instance_admin(actor):
        raise HTTPException(status_code=403, detail="only the author or an admin can delete")
    _assert_unlockable(entry["project_id"], entry["user_id"], entry["spent_on"])
    events.emit(
        event_type="time.deleted",
        agg_type="time_entry",
        agg_id=entry_id,
        project_id=entry["project_id"],
        payload={"item_id": entry["item_id"]},
    )
    return {"deleted": entry_id}


@router.get("/my/timelog")
def my_timelog(days: int = 28) -> dict:
    """Personal time-tracking calendar feed (docs/01 §S.1, OpenProject 16.0
    "My time tracking"): my own entries grouped by spent_on over the last N
    days. Pure projection aggregation, same own-data semantics as /my/work."""
    days = max(1, min(days, 60))
    me = events.effective_actor()
    conn = db.get_conn()
    today = date.today()
    start = (today - timedelta(days=days - 1)).isoformat()
    rows = conn.execute(
        "SELECT t.id, t.item_id, t.project_id, t.minutes, t.spent_on, t.note,"
        " t.created_at, i.title AS item_title, p.name AS project_name"
        " FROM item_time_entries t"
        " JOIN items i ON i.id = t.item_id"
        " JOIN projects p ON p.id = t.project_id"
        " WHERE t.user_id = ? AND t.deleted_at IS NULL AND t.spent_on >= ?"
        " ORDER BY t.spent_on DESC, t.created_at",
        (me, start),
    ).fetchall()
    by_day: dict[str, dict] = {}
    for r in rows:
        d = by_day.setdefault(r["spent_on"], {"date": r["spent_on"], "entries": [], "total_minutes": 0})
        d["entries"].append(dict(r))
        d["total_minutes"] += r["minutes"]
    return {
        "user_id": me,
        "days": [by_day[k] for k in sorted(by_day, reverse=True)],
        "total_minutes": sum(r["minutes"] for r in rows),
        "window": {"start": start, "end": today.isoformat(), "days": days},
    }
