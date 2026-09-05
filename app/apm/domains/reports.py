"""Reports domain (M12-I38): read-only aggregates over existing projections.

No new tables and no new events — every number here is a query over the
items/approvals/events projections (docs/01 §K.1: OpenProject treats saved
queries + widgets as the report layer; the event-sourced core already holds
the data, so reports need zero ETL). Rebuild consistency carries over by
construction: there is nothing to project and nothing to replay.

口径 definitions (docs/12 §9):
- funnel     item counts per status_group, zero-filled in BUCKET_NAMES order;
- gates      approvals with status='pending' (阶段门/工件审批);
- overdue    active items (not done/cancelled) whose `due` custom field is
             earlier than today, or — when no due field is present — whose
             age exceeds STALE_DAYS days (滞留项);
- throughput per-day counts of item.created and done-transitions
             (item.status_changed → status_group='done') over the last
             THROUGHPUT_DAYS days.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Response

from apm.core import db, events
from apm.domains.items import BUCKET_NAMES
from apm.domains.members import is_instance_admin, member_role
from apm.domains.milestones import milestone_progress

router = APIRouter(tags=["reports"])

STALE_DAYS = 14
THROUGHPUT_DAYS = 14
_DUE_KEYS = ("due", "due_date", "deadline")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _active_where() -> str:
    return "status_group NOT IN ('done','cancelled')"


def _parse_due(value) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _overdue_rows(project_id: str | None = None) -> list[dict]:
    """Active items past their due date, or older than STALE_DAYS when no due
    date exists (滞留项) — reason says which. Due resolution order (docs/12 §9):
    item.due_date first, then a `due` custom field, then age-based staleness."""
    conn = db.get_conn()
    today = _now().date()
    stale_cutoff = (_now() - timedelta(days=STALE_DAYS)).isoformat()
    sql = (
        "SELECT i.*, p.name AS project_name FROM items i"
        " JOIN projects p ON p.id = i.project_id"
        f" WHERE i.{_active_where()}"
    )
    params: list = []
    if project_id:
        sql += " AND i.project_id = ?"
        params.append(project_id)
    rows = conn.execute(sql + " ORDER BY i.created_at", params).fetchall()
    out = []
    for r in rows:
        cf = {}
        try:
            cf = json.loads(r["custom_fields"] or "{}")
        except (TypeError, ValueError):
            pass
        due = _parse_due(r["due_date"])
        if due is None:
            due = next((d for k in _DUE_KEYS if (d := _parse_due(cf.get(k)))), None)
        if due is not None:
            if due >= today:
                continue
            reason = f"超期 {(today - due).days} 天"
        elif r["created_at"][:10] > stale_cutoff[:10]:
            continue
        else:
            reason = f"滞留超 {STALE_DAYS} 天"
        out.append({**dict(r), "reason": reason})
    return out


@router.get("/projects/{project_id}/report.csv")
def project_report_csv(project_id: str) -> Response:
    """CSV export of the same numbers as /report (docs/12 §9): one
    section,key,title,reason,value table so spreadsheets can filter by section."""
    rep = project_report(project_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["section", "key", "title", "reason", "value"])
    for bucket, n in rep["funnel"].items():
        w.writerow(["funnel", bucket, "", "", n])
    for concept, n in rep["concepts"].items():
        w.writerow(["concept", concept, "", "", n])
    w.writerow(["throughput", "created_total", "", "", rep["throughput"]["created_total"]])
    w.writerow(["throughput", "done_total", "", "", rep["throughput"]["done_total"]])
    for it in rep["overdue"]:
        w.writerow(["overdue", it["id"], it["title"], it["reason"], ""])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="report-{project_id}.csv"'},
    )


@router.get("/projects/{project_id}/report")
def project_report(project_id: str) -> dict:
    conn = db.get_conn()
    if not conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone():
        raise HTTPException(status_code=404, detail=f"unknown project '{project_id}'")

    funnel = {b: 0 for b in BUCKET_NAMES}
    for r in conn.execute(
        "SELECT status_group, COUNT(*) c FROM items WHERE project_id = ? GROUP BY status_group",
        (project_id,),
    ).fetchall():
        if r["status_group"] in funnel:
            funnel[r["status_group"]] = r["c"]

    concepts = {r["concept_id"]: r["c"] for r in conn.execute(
        "SELECT concept_id, COUNT(*) c FROM items WHERE project_id = ? GROUP BY concept_id",
        (project_id,),
    ).fetchall()}

    gates = []
    for r in conn.execute(
        "SELECT id, kind, run_id, item_id, conversation_id, requested_at, payload_snapshot"
        " FROM approvals WHERE project_id = ? AND status = 'pending' ORDER BY requested_at",
        (project_id,),
    ).fetchall():
        g = dict(r)
        try:
            g["payload_snapshot"] = json.loads(g["payload_snapshot"] or "{}")
        except (TypeError, ValueError):
            g["payload_snapshot"] = {}
        gates.append(g)

    since = (_now() - timedelta(days=THROUGHPUT_DAYS)).isoformat()
    created = {r["d"]: r["c"] for r in conn.execute(
        "SELECT date(ts) d, COUNT(*) c FROM events"
        " WHERE project_id = ? AND event_type = 'item.created' AND ts >= ? GROUP BY d",
        (project_id, since),
    ).fetchall()}
    done = {r["d"]: r["c"] for r in conn.execute(
        "SELECT date(ts) d, COUNT(*) c FROM events"
        " WHERE project_id = ? AND event_type = 'item.status_changed'"
        " AND json_extract(payload, '$.status_group') = 'done' AND ts >= ? GROUP BY d",
        (project_id, since),
    ).fetchall()}
    days = []
    for i in range(THROUGHPUT_DAYS - 1, -1, -1):
        d = (_now().date() - timedelta(days=i)).isoformat()
        days.append({"date": d, "created": created.get(d, 0), "done": done.get(d, 0)})

    return {
        "project_id": project_id,
        "funnel": funnel,
        "concepts": concepts,
        "gates_pending": gates,
        "overdue": _overdue_rows(project_id),
        "throughput": {
            "days": THROUGHPUT_DAYS,
            "series": days,
            "created_total": sum(created.values()),
            "done_total": sum(done.values()),
        },
    }


@router.get("/portfolio/report")
def portfolio_report() -> dict:
    """Cross-project portfolio overview (M23-I72, docs/01 §V.2): one row per
    project visible to the caller plus a totals row — the Community-edition
    stand-in for OpenProject's Enterprise portfolio dashboards. Pure
    projection aggregation, zero ETL (M12 principle)."""
    me = events.effective_actor()
    conn = db.get_conn()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (me,)).fetchone()
    from apm.domains.feed import _visible
    today = _now().date().isoformat()
    projects = []
    totals = {"items_active": 0, "done": 0, "gates_pending": 0, "overdue": 0, "timelog_minutes": 0}
    if user is not None:
        for p in conn.execute(
            "SELECT id, name, ontology FROM projects WHERE status != 'archived' ORDER BY created_at"
        ).fetchall():
            if not _visible(p["id"], user):
                continue
            funnel = {b: 0 for b in BUCKET_NAMES}
            for r in conn.execute(
                "SELECT status_group, COUNT(*) c FROM items WHERE project_id = ? GROUP BY status_group",
                (p["id"],),
            ).fetchall():
                if r["status_group"] in funnel:
                    funnel[r["status_group"]] = r["c"]
            gates = conn.execute(
                "SELECT COUNT(*) c FROM approvals WHERE project_id = ? AND status = 'pending'",
                (p["id"],),
            ).fetchone()["c"]
            overdue = conn.execute(
                "SELECT COUNT(*) c FROM items WHERE project_id = ?"
                " AND due_date IS NOT NULL AND due_date < ? AND " + _active_where(),
                (p["id"], today),
            ).fetchone()["c"]
            minutes = conn.execute(
                "SELECT COALESCE(SUM(minutes), 0) m FROM item_time_entries"
                " WHERE project_id = ? AND deleted_at IS NULL",
                (p["id"],),
            ).fetchone()["m"]
            active = sum(v for k, v in funnel.items() if k not in ("done", "cancelled"))
            projects.append({
                "project_id": p["id"], "name": p["name"], "ontology": p["ontology"],
                "funnel": funnel, "items_active": active, "gates_pending": gates,
                "overdue": overdue, "timelog_minutes": minutes,
            })
    for row in projects:
        totals["items_active"] += row["items_active"]
        totals["done"] += row["funnel"]["done"]
        totals["gates_pending"] += row["gates_pending"]
        totals["overdue"] += row["overdue"]
        totals["timelog_minutes"] += row["timelog_minutes"]
    return {"projects": projects, "totals": totals, "generated_at": _now().isoformat()}


@router.get("/portfolio/roadmap")
def portfolio_roadmap() -> dict:
    """Cross-project milestone roadmap (M27-I84, docs/01 §Z.2): milestones of
    every project visible to the caller, ordered by due date — one row per
    project, one bar per milestone with done progress and an overdue flag.
    GitLab restricts its roadmap to group scope and cross-project views are a
    years-open request (epic #1105); here the same _visible three-layer check
    as /portfolio/report makes it a pure projection query."""
    me = events.effective_actor()
    conn = db.get_conn()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (me,)).fetchone()
    from apm.domains.feed import _visible
    today = _now().date().isoformat()
    rows = []
    if user is not None:
        for p in conn.execute(
            "SELECT id, name FROM projects WHERE status != 'archived' ORDER BY created_at"
        ).fetchall():
            if not _visible(p["id"], user):
                continue
            ms = conn.execute(
                "SELECT id, title, due_date, status FROM milestones"
                " WHERE project_id = ? ORDER BY due_date",
                (p["id"],),
            ).fetchall()
            if not ms:
                continue
            milestones = []
            for m in ms:
                prog = milestone_progress(dict(m))
                finished = m["status"] in ("done", "achieved")
                milestones.append({
                    "id": m["id"], "title": m["title"], "due_date": m["due_date"],
                    "status": m["status"],
                    "overdue": bool(m["due_date"] < today and not finished),
                    "progress": prog,
                })
            rows.append({"project_id": p["id"], "name": p["name"], "milestones": milestones})
    return {"projects": rows, "today": today, "generated_at": _now().isoformat()}


@router.get("/portfolio/workload")
def portfolio_workload() -> dict:
    """Cross-project member workload (M28-I87, docs/01 §AA.2): for every
    caller-visible project, aggregate per assignee — active items, overdue,
    and time logged in the last 7 days. OpenProject's resource planner views
    are member-centric; the portfolio report is project-centric, this is the
    member slice over the same _visible scope (pure projection, zero tables)."""
    me = events.effective_actor()
    conn = db.get_conn()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (me,)).fetchone()
    from apm.domains.feed import _visible
    today = _now().date()
    week_ago = (today - timedelta(days=6)).isoformat()
    today_s = today.isoformat()
    people: dict[str, dict] = {}
    if user is not None:
        for p in conn.execute(
            "SELECT id, name FROM projects WHERE status != 'archived' ORDER BY created_at"
        ).fetchall():
            if not _visible(p["id"], user):
                continue
            rows = conn.execute(
                "SELECT i.assignee_id AS uid, u.name AS uname,"
                " SUM(CASE WHEN i.status_group NOT IN ('done','cancelled') THEN 1 ELSE 0 END) AS active,"
                " SUM(CASE WHEN i.status_group NOT IN ('done','cancelled')"
                "   AND i.due_date IS NOT NULL AND i.due_date < ? THEN 1 ELSE 0 END) AS overdue"
                " FROM items i LEFT JOIN users u ON u.id = i.assignee_id"
                " WHERE i.project_id = ? AND i.assignee_type = 'human' AND i.assignee_id IS NOT NULL"
                " GROUP BY i.assignee_id",
                (today_s, p["id"]),
            ).fetchall()
            for r in rows:
                person = people.setdefault(r["uid"], {
                    "user_id": r["uid"], "user_name": r["uname"] or r["uid"],
                    "active": 0, "overdue": 0, "minutes_7d": 0,
                    "projects": {},
                })
                person["active"] += r["active"] or 0
                person["overdue"] += r["overdue"] or 0
                person["projects"][p["name"]] = person["projects"].get(p["name"], 0) + (r["active"] or 0)
            # 7-day logged time within THIS project only — time in projects the
            # caller cannot see must never leak into the workload numbers
            for r in conn.execute(
                "SELECT user_id AS uid, SUM(minutes) AS mins FROM item_time_entries"
                " WHERE project_id = ? AND deleted_at IS NULL AND spent_on >= ?"
                " GROUP BY user_id",
                (p["id"], week_ago),
            ).fetchall():
                person = people.get(r["uid"])
                if person is not None and r["mins"]:
                    person["minutes_7d"] += r["mins"]
    # members with neither active work nor recent logged time are not "load"
    rows = sorted((p for p in people.values() if p["active"] or p["minutes_7d"]),
                  key=lambda x: (-x["active"], -x["minutes_7d"], x["user_name"]))
    return {"members": rows, "today": today_s, "generated_at": _now().isoformat()}


def _health_factors(project_id: str, conn) -> dict:
    """Raw factor values for one project — active/overdue/stale item counts,
    done-first-arrival count inside the last 7 days (replayed from the event
    stream, same caliber as the milestone burndown) and pending approvals."""
    today = _now().date()
    stale_cutoff = (today - timedelta(days=STALE_DAYS)).isoformat()
    week_ago = (today - timedelta(days=6)).isoformat()
    row = conn.execute(
        "SELECT COUNT(*) AS active,"
        " SUM(CASE WHEN due_date IS NOT NULL AND due_date < ? THEN 1 ELSE 0 END) AS overdue,"
        " SUM(CASE WHEN updated_at < ? THEN 1 ELSE 0 END) AS stale"
        " FROM items WHERE project_id = ? AND status_group NOT IN ('done','cancelled')",
        (today.isoformat(), stale_cutoff, project_id),
    ).fetchone()
    done_7d = 0
    first_done: dict[str, str] = {}
    for e in conn.execute(
        "SELECT agg_id, payload, ts FROM events"
        " WHERE project_id = ? AND event_type = 'item.status_changed' ORDER BY id",
        (project_id,),
    ).fetchall():
        if e["agg_id"] in first_done:
            continue
        if json.loads(e["payload"]).get("status_group") == "done":
            first_done[e["agg_id"]] = e["ts"][:10]
            if week_ago <= e["ts"][:10] <= today.isoformat():
                done_7d += 1
    gates = conn.execute(
        "SELECT COUNT(*) c FROM approvals WHERE project_id = ? AND status = 'pending'",
        (project_id,),
    ).fetchone()["c"]
    return {"active": row["active"], "overdue": row["overdue"] or 0,
            "stale": row["stale"] or 0, "done_7d": done_7d, "gates": gates}


def _health_score(f: dict) -> float | None:
    """0-100 composite (docs/01 §AC.1): each factor contributes its full weight
    when healthy — 40 overdue, 20 stale, 30 throughput momentum (capped at 1),
    10 gate-pending. Projects with no active work score None (nothing to be
    healthy about yet)."""
    active = f["active"]
    if not active:
        return None
    overdue_rate = f["overdue"] / active
    stale_rate = f["stale"] / active
    momentum = min(f["done_7d"] / active, 1)
    gate_rate = min(f["gates"] / active, 1)
    score = (40 * (1 - overdue_rate) + 20 * (1 - stale_rate)
             + 30 * momentum + 10 * (1 - gate_rate))
    return round(max(score, 0), 1)


@router.get("/portfolio/health")
def portfolio_health() -> dict:
    """Cross-project health scores (M30-I92, docs/01 §AC.1): one 0-100 number
    per caller-visible project so managers see which project needs attention
    without adding up raw counters themselves. Same _visible scope, pure
    projection, sorted worst-first."""
    me = events.effective_actor()
    conn = db.get_conn()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (me,)).fetchone()
    from apm.domains.feed import _visible
    rows = []
    if user is not None:
        for p in conn.execute(
            "SELECT id, name FROM projects WHERE status != 'archived' ORDER BY created_at"
        ).fetchall():
            if not _visible(p["id"], user):
                continue
            f = _health_factors(p["id"], conn)
            rows.append({
                "project_id": p["id"], "name": p["name"],
                "score": _health_score(f), "factors": f,
            })
    rows.sort(key=lambda r: (r["score"] is None, r["score"] if r["score"] is not None else 0))
    return {"projects": rows, "generated_at": _now().isoformat()}


@router.get("/projects/{project_id}/timelog_report")
def timelog_report(project_id: str, days: int = 14) -> dict:
    """M19-I61: project time report — per-user totals + per-day trend, read
    straight off the item_time_entries projection (same numbers as the item
    drawer totals by construction; the tests reconcile them). Plane ships no
    project-level time analytics at all (docs/01 §R.3, GH #8045)."""
    days = max(1, min(days, 90))
    conn = db.get_conn()
    if not conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone():
        raise HTTPException(status_code=404, detail=f"unknown project '{project_id}'")

    total = conn.execute(
        "SELECT COALESCE(SUM(minutes), 0) t FROM item_time_entries"
        " WHERE project_id = ? AND deleted_at IS NULL", (project_id,)).fetchone()["t"]
    by_user = [dict(r) for r in conn.execute(
        "SELECT t.user_id, u.name AS user_name, SUM(t.minutes) AS minutes"
        " FROM item_time_entries t LEFT JOIN users u ON u.id = t.user_id"
        " WHERE t.project_id = ? AND t.deleted_at IS NULL"
        " GROUP BY t.user_id ORDER BY minutes DESC", (project_id,))]
    logged = {r["d"]: r["c"] for r in conn.execute(
        "SELECT spent_on d, SUM(minutes) c FROM item_time_entries"
        " WHERE project_id = ? AND deleted_at IS NULL GROUP BY d", (project_id,))}
    today = _now().date()
    series = [{"date": (today - timedelta(days=i)).isoformat(),
               "minutes": logged.get((today - timedelta(days=i)).isoformat(), 0)}
              for i in range(days - 1, -1, -1)]
    return {
        "project_id": project_id,
        "total_minutes": total,
        "by_user": by_user,
        "by_day": series,
        "window_days": days,
    }


@router.get("/my/work")
def my_work() -> dict:
    """Cross-project "my page" (docs/01 §K.1). Assignment is authorization:
    an assignee always sees their own active items. Gates show up for users
    holding decision rights (project owner or instance admin) — the same
    recipients approval.requested notifications go to."""
    me = events.effective_actor()
    conn = db.get_conn()
    items = [dict(r) for r in conn.execute(
        "SELECT i.*, p.name AS project_name FROM items i"
        " JOIN projects p ON p.id = i.project_id"
        " WHERE i.assignee_type = 'human' AND i.assignee_id = ?"
        f" AND i.{_active_where()}"
        " ORDER BY i.updated_at DESC LIMIT 50",
        (me,),
    ).fetchall()]
    approvals = []
    for r in conn.execute(
        "SELECT a.id, a.project_id, a.kind, a.run_id, a.item_id, a.requested_at,"
        " p.name AS project_name FROM approvals a"
        " JOIN projects p ON p.id = a.project_id"
        " WHERE a.status = 'pending' ORDER BY a.requested_at",
    ).fetchall():
        if member_role(r["project_id"], me) == "owner" or is_instance_admin(me):
            approvals.append(dict(r))
    pids = sorted({it["project_id"] for it in items} | {a["project_id"] for a in approvals})
    projects = []
    for pid in pids:
        row = conn.execute("SELECT id, name FROM projects WHERE id = ?", (pid,)).fetchone()
        if row:
            projects.append(dict(row))
    # M19-I61: personal minimal face — minutes logged by me this ISO week
    week_start = (_now().date() - timedelta(days=_now().date().weekday())).isoformat()
    week_minutes = conn.execute(
        "SELECT COALESCE(SUM(minutes), 0) m FROM item_time_entries"
        " WHERE user_id = ? AND deleted_at IS NULL AND spent_on >= ?",
        (me, week_start),
    ).fetchone()["m"]
    return {"user_id": me, "items": items, "approvals": approvals, "projects": projects,
            "week_minutes": week_minutes}


@router.get("/my/schedule")
def my_schedule() -> dict:
    """Personal cross-project schedule (M29-I89, docs/01 §AB.1): every item
    assigned to the caller that carries a date, with project names — the data
    source for the drag-to-reschedule month calendar. Own-data caliber (same
    as /my/work): assignment is authorization."""
    me = events.effective_actor()
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT i.id, i.title, i.status_group, i.priority, i.start_date, i.due_date,"
        " i.project_id, p.name AS project_name"
        " FROM items i JOIN projects p ON p.id = i.project_id"
        " WHERE i.assignee_type = 'human' AND i.assignee_id = ?"
        " AND i.project_id IN (SELECT id FROM projects WHERE status != 'archived')"
        " AND (i.start_date IS NOT NULL OR i.due_date IS NOT NULL)"
        " ORDER BY COALESCE(i.due_date, i.start_date)",
        (me,),
    ).fetchall()
    return {"items": [dict(r) for r in rows], "today": _now().date().isoformat()}
