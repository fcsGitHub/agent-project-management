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


# ---------------------------------------------------------------- burndown
@router.get("/cycles/{cycle_id}/burndown")
def cycle_burndown(cycle_id: str) -> dict:
    """M41-I125 (docs/01 §AN.1, Plane Cycles burndown + Jira burnup lesson): a
    burndown line alone hides scope change — finish 10 items while adding 10
    and the line sits flat. So this returns the burnup pair: remaining work
    per day PLUS the total-scope stair line (mounts/unmounts/carryovers all
    move it). The done first-arrival replay is the same caliber as the
    milestone burndown (I85). Pure event replay, zero new tables."""
    import json

    from datetime import date as _date, timedelta as _timedelta

    c = require_cycle(cycle_id)
    conn = db.get_conn()
    today = events.utcnow()[:10]

    # single ordered replay: scope transitions (item.updated cycle_id) and
    # resolution dates (first done/cancelled per item)
    scope_events: dict[str, list[tuple[str, bool]]] = {}
    resolved: dict[str, str] = {}
    for e in conn.execute(
        "SELECT agg_id, event_type, payload, ts FROM events"
        " WHERE project_id = ? AND event_type IN ('item.updated','item.status_changed')"
        " ORDER BY id", (c["project_id"],),
    ).fetchall():
        if e["event_type"] == "item.updated":
            p = json.loads(e["payload"])
            if "cycle_id" in p:
                scope_events.setdefault(e["agg_id"], []).append(
                    (e["ts"][:10], p["cycle_id"] == cycle_id))
        else:
            if e["agg_id"] not in resolved:
                p = json.loads(e["payload"])
                if p.get("status_group") in ("done", "cancelled"):
                    resolved[e["agg_id"]] = e["ts"][:10]

    def in_scope_on(iid: str, day: str) -> bool:
        state = False
        for d, inside in scope_events.get(iid, []):
            if d <= day:
                state = inside
        return state

    def resolved_by(iid: str, day: str) -> bool:
        d = resolved.get(iid)
        return bool(d and d <= day)

    all_items = set(scope_events) | set(resolved)
    start = _date.fromisoformat(c["start_date"])
    end = _date.fromisoformat(c["end_date"])
    last = min(_date.fromisoformat(today), end)
    series = []
    if last >= start:
        for i in range((last - start).days + 1):
            day = (start + _timedelta(days=i)).isoformat()
            in_scope = [iid for iid in all_items if in_scope_on(iid, day)]
            remaining = sum(1 for iid in in_scope if not resolved_by(iid, day))
            series.append({"date": day, "total": len(in_scope), "remaining": remaining})
    window = (end - start).days
    # ideal anchors at the first day anything was in scope (the commitment),
    # not at the window start — a cycle whose items all arrive late still gets
    # a meaningful pace line
    initial_total = next((s["total"] for s in series if s["total"] > 0), 0)
    ideal = [
        {"date": (start + _timedelta(days=i)).isoformat(),
         "remaining": round(initial_total * (1 - i / max(window, 1)))}
        for i in range(window + 1)
    ]
    return {"cycle_id": cycle_id, "name": c["name"], "start": c["start_date"],
            "end": c["end_date"], "series": series, "ideal": ideal,
            "generated_at": events.utcnow()}


# ---------------------------------------------------------------- retrospective
@router.get("/cycles/{cycle_id}/retrospective")
def cycle_retrospective(cycle_id: str) -> dict:
    """M48-I145 (docs/01 §AS.2, retrospective data pack): one page for the
    cycle review ritual — commitment vs completion (the I129 caliber), late
    joiners (scope mounted after the commitment day), overdue newcomers, agent
    run participation, top blocking dependencies and the velocity delta vs
    the previous completed cycle. Pure projection replay, zero new tables;
    an empty cycle states its emptiness honestly instead of faking numbers."""
    import json

    from datetime import date as _date

    c = require_cycle(cycle_id)
    conn = db.get_conn()
    start, end = c["start_date"], c["end_date"]

    scope_events: dict[str, list[tuple[str, bool]]] = {}
    resolved: dict[str, str] = {}
    for e in conn.execute(
        "SELECT agg_id, event_type, payload, ts FROM events"
        " WHERE project_id = ? AND event_type IN ('item.updated','item.status_changed')"
        " ORDER BY id", (c["project_id"],),
    ).fetchall():
        if e["event_type"] == "item.updated":
            p = json.loads(e["payload"])
            if "cycle_id" in p:
                scope_events.setdefault(e["agg_id"], []).append(
                    (e["ts"][:10], p["cycle_id"] == cycle_id))
        else:
            if e["agg_id"] not in resolved:
                p = json.loads(e["payload"])
                if p.get("status_group") in ("done", "cancelled"):
                    resolved[e["agg_id"]] = e["ts"][:10]

    def in_scope_on(iid: str, day: str) -> bool:
        state = False
        for d, inside in scope_events.get(iid, []):
            if d <= day:
                state = inside
        return state

    def resolved_by(iid: str, day: str) -> bool:
        d = resolved.get(iid)
        return bool(d and d <= day)

    all_items = set(scope_events) | set(resolved)
    commitment_day = next(
        (day for day in sorted({d for hist in scope_events.values() for d, inside in hist})
         if any(in_scope_on(iid, day) for iid in all_items)), None)
    if commitment_day is None:
        return {"cycle_id": cycle_id, "name": c["name"], "start": start, "end": end,
                "committed": 0, "completed": 0, "completion_rate": None,
                "carried_in": [], "overdue_new": [], "runs": None,
                "top_blockers": [], "prev_completed": None,
                "reason": "empty scope", "generated_at": events.utcnow()}
    committed_ids = [iid for iid in all_items if in_scope_on(iid, commitment_day)]
    completed = sum(1 for iid in committed_ids if resolved_by(iid, end))
    # 拖入：commitment 日之后才进入 scope 的项（晚到者显性化）
    carried_in = [
        {"id": iid, "title": _item_title(conn, iid)}
        for iid in sorted(all_items)
        if iid not in committed_ids
        and any(inside for d, inside in scope_events.get(iid, []))
    ]
    # 周期内创建且到期未结的新增超期
    overdue_new = [
        {"id": r["id"], "title": r["title"], "due_date": r["due_date"]}
        for r in conn.execute(
            "SELECT id, title, due_date FROM items WHERE project_id = ?"
            " AND substr(created_at, 1, 10) BETWEEN ? AND ?"
            " AND due_date IS NOT NULL AND due_date < ?"
            " AND status_group NOT IN ('done','cancelled') AND archived_at IS NULL",
            (c["project_id"], start, end, end)).fetchall()
    ]
    # run 参与（started_at 落在窗口内）
    runs_row = conn.execute(
        "SELECT COUNT(*) AS n,"
        " SUM(CASE WHEN status = 'succeeded' THEN 1 ELSE 0 END) AS ok,"
        " COALESCE(SUM(total_input_tokens), 0) AS tin,"
        " COALESCE(SUM(total_output_tokens), 0) AS tout"
        " FROM runs WHERE project_id = ? AND substr(started_at, 1, 10) BETWEEN ? AND ?",
        (c["project_id"], start, end)).fetchone()
    runs_stat = {"count": runs_row["n"], "succeeded": runs_row["ok"] or 0,
                 "input_tokens": runs_row["tin"], "output_tokens": runs_row["tout"]}
    # top 阻塞者：被周期内 items 的 blocks 关系指名最多的前置项
    cycle_items = [iid for iid in all_items
                   if any(inside for d, inside in scope_events.get(iid, []))]
    top_blockers = []
    if cycle_items:
        marks = ",".join("?" * len(cycle_items))
        for r in conn.execute(
            f"SELECT from_item AS blocker, COUNT(*) AS n FROM item_relations"
            f" WHERE relation_type = 'blocks' AND to_item IN ({marks})"
            f" GROUP BY from_item ORDER BY n DESC LIMIT 5", cycle_items).fetchall():
            top_blockers.append({"id": r["blocker"], "title": _item_title(conn, r["blocker"]),
                                 "blocks": r["n"]})
    # 速率对比：上一个已完成周期的 completed 数（同口径）
    prev = conn.execute(
        "SELECT id FROM project_cycles WHERE project_id = ? AND cancelled_at IS NULL"
        " AND end_date < ? ORDER BY end_date DESC LIMIT 1", (c["project_id"], start)).fetchone()
    prev_completed = _completed_count(conn, c["project_id"], prev["id"]) if prev else None
    return {
        "cycle_id": cycle_id, "name": c["name"], "start": start, "end": end,
        "committed": len(committed_ids), "completed": completed,
        "completion_rate": round(completed / len(committed_ids), 4) if committed_ids else None,
        "carried_in": carried_in, "overdue_new": overdue_new,
        "runs": runs_stat, "top_blockers": top_blockers,
        "prev_completed": prev_completed,
        "generated_at": events.utcnow(),
    }


def _item_title(conn, item_id: str) -> str:
    row = conn.execute("SELECT title FROM items WHERE id = ?", (item_id,)).fetchone()
    return row["title"] if row else item_id


def _completed_count(conn, project_id: str, cycle_id: str) -> int:
    """I129 口径：committed 集（首非零 scope 日）中窗口内首达完成的数量。"""
    import json

    scope_events: dict[str, list[tuple[str, bool]]] = {}
    resolved: dict[str, str] = {}
    c = get_cycle(cycle_id)
    for e in conn.execute(
        "SELECT agg_id, event_type, payload, ts FROM events"
        " WHERE project_id = ? AND event_type IN ('item.updated','item.status_changed')"
        " ORDER BY id", (project_id,),
    ).fetchall():
        if e["event_type"] == "item.updated":
            p = json.loads(e["payload"])
            if "cycle_id" in p:
                scope_events.setdefault(e["agg_id"], []).append(
                    (e["ts"][:10], p["cycle_id"] == cycle_id))
        else:
            if e["agg_id"] not in resolved:
                p = json.loads(e["payload"])
                if p.get("status_group") in ("done", "cancelled"):
                    resolved[e["agg_id"]] = e["ts"][:10]

    def in_scope_on(iid: str, day: str) -> bool:
        state = False
        for d, inside in scope_events.get(iid, []):
            if d <= day:
                state = inside
        return state

    def resolved_by(iid: str, day: str) -> bool:
        d = resolved.get(iid)
        return bool(d and d <= day)

    all_items = set(scope_events) | set(resolved)
    commitment_day = next(
        (day for day in sorted({d for hist in scope_events.values() for d, inside in hist})
         if any(in_scope_on(iid, day) for iid in all_items)), None)
    if commitment_day is None:
        return 0
    committed = [iid for iid in all_items if in_scope_on(iid, commitment_day)]
    return sum(1 for iid in committed if resolved_by(iid, c["end_date"]))


@router.get("/projects/{project_id}/velocity")
def project_velocity(project_id: str) -> dict:
    """M42-I129 (docs/01 §AO.2, Jira velocity chart): committed vs completed
    per completed cycle — committed is the first non-zero scope total inside
    the window (the I125 commitment-day anchor), completed is the number of
    those items first resolved within the cycle window. Average line across
    cycles. No completed cycles → honest empty (SPI precedent)."""
    import json

    from datetime import date as _date, timedelta as _timedelta

    from apm.domains.projects import require_project

    require_project(project_id)
    conn = db.get_conn()
    require_project(project_id)
    today = events.utcnow()[:10]
    cycles = conn.execute(
        "SELECT * FROM project_cycles WHERE project_id = ? AND cancelled_at IS NULL"
        " AND end_date < ? ORDER BY end_date", (project_id, today)).fetchall()
    out = []
    for c in cycles:
        scope_events: dict[str, list[tuple[str, bool]]] = {}
        resolved: dict[str, str] = {}
        for e in conn.execute(
            "SELECT agg_id, event_type, payload, ts FROM events"
            " WHERE project_id = ? AND event_type IN ('item.updated','item.status_changed')"
            " ORDER BY id", (project_id,),
        ).fetchall():
            if e["event_type"] == "item.updated":
                p = json.loads(e["payload"])
                if "cycle_id" in p:
                    scope_events.setdefault(e["agg_id"], []).append(
                        (e["ts"][:10], p["cycle_id"] == c["id"]))
            elif e["agg_id"] not in resolved:
                p = json.loads(e["payload"])
                if p.get("status_group") in ("done", "cancelled"):
                    resolved[e["agg_id"]] = e["ts"][:10]

        def total_on(day: str) -> int:
            return sum(1 for iid, hist in scope_events.items()
                       if any(d <= day and inside for d, inside in hist))

        days = []
        cursor = _date.fromisoformat(c["start_date"])
        last = _date.fromisoformat(min(c["end_date"], today))
        while cursor <= last:
            days.append(cursor.isoformat())
            cursor += _timedelta(days=1)
        committed = next((total_on(d) for d in days if total_on(d) > 0), 0)
        in_scope = set(scope_events)
        completed = sum(1 for iid, d in resolved.items()
                        if iid in in_scope and c["start_date"] <= d <= c["end_date"])
        out.append({"cycle_id": c["id"], "name": c["name"],
                    "start_date": c["start_date"], "end_date": c["end_date"],
                    "committed": committed, "completed": completed})
    average = round(sum(o["completed"] for o in out) / len(out), 2) if out else None
    return {"project_id": project_id, "cycles": out, "average_completed": average,
            "generated_at": events.utcnow()}


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
