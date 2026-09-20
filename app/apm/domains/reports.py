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
from collections import deque
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, Response

from apm import config
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


@router.get("/portfolio/activity")
def portfolio_activity(project_id: str | None = None, kind: str | None = None,
                       actor: str | None = None, limit: int = 50) -> dict:
    """Cross-project activity feed (M36-I110, docs/01 §AI.1, OpenProject
    'My activity' semantics): the visible slice of the event stream IS the
    feed — no new tables, no replay, just a whitelisted read with membership
    trimming (event-sourcing dividend #7: the activity page is free)."""
    me = events.effective_actor()
    conn = db.get_conn()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (me,)).fetchone()
    return {"activities": _activity_list(conn, user, project_id, kind, actor, limit),
            "generated_at": _now().isoformat()}


def _activity_list(conn, user, project_id: str | None, kind: str | None,
                   actor: str | None, limit: int) -> list[dict]:
    """Shared activity aggregation for the JSON feed and the Atom subscription
    (M37-I115). Visible trimming + whitelist + filters, newest first."""
    from apm.domains.feed import _visible

    limit = max(1, min(limit, 200))
    placeholders = ",".join("?" for _ in ACTIVITY_EVENTS)
    sql = f"SELECT * FROM events WHERE event_type IN ({placeholders})"
    params: list = list(ACTIVITY_EVENTS)
    if project_id:
        sql += " AND project_id = ?"
        params.append(project_id)
    if actor:
        sql += " AND actor_id = ?"
        params.append(actor)
    # over-fetch then trim by visibility — the feed stays limit-sized
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit * 3)
    rows = conn.execute(sql, params).fetchall()

    pids = {r["project_id"] for r in rows if r["project_id"]}
    proj_names = {}
    if pids:
        marks = ",".join("?" for _ in pids)
        proj_names = {r["id"]: r["name"] for r in conn.execute(
            f"SELECT id, name FROM projects WHERE id IN ({marks})", tuple(pids)).fetchall()}
    item_ids = {r["agg_id"] for r in rows if r["event_type"] == "item.status_changed"}
    # comment summaries also name the item — take it from the payload
    for r in rows:
        if r["event_type"] == "comment.created":
            try:
                iid = json.loads(r["payload"]).get("item_id")
            except (TypeError, ValueError):
                continue
            if iid:
                item_ids.add(iid)
    item_titles = {}
    if item_ids:
        marks = ",".join("?" for _ in item_ids)
        item_titles = {r["id"]: r["title"] for r in conn.execute(
            f"SELECT id, title FROM items WHERE id IN ({marks})", tuple(item_ids)).fetchall()}
    actor_ids = {r["actor_id"] for r in rows if r["actor_id"]}
    actor_names = {}
    if actor_ids:
        marks = ",".join("?" for _ in actor_ids)
        actor_names = {r["id"]: r["name"] for r in conn.execute(
            f"SELECT id, name FROM users WHERE id IN ({marks})", tuple(actor_ids)).fetchall()}

    out = []
    for r in rows:
        if user is None or not _visible(r["project_id"], user):
            continue
        icon, k = ACTIVITY_EVENTS[r["event_type"]]
        if kind and k != kind:
            continue
        p = json.loads(r["payload"])
        summary = _activity_summary(r, p, item_titles)
        out.append({
            "event_id": r["id"], "ts": r["ts"], "icon": icon, "kind": k,
            "event_type": r["event_type"], "summary": summary,
            "actor_id": r["actor_id"], "actor_name": actor_names.get(r["actor_id"], r["actor_id"]),
            "project_id": r["project_id"], "project_name": proj_names.get(r["project_id"], ""),
            "agg_id": r["agg_id"],
        })
        if len(out) >= limit:
            break
    return out


ACTIVITY_EVENTS = {
    "item.created": ("🆕", "item"),
    "item.status_changed": ("🔁", "item"),
    "comment.created": ("💬", "comment"),
    "milestone.created": ("🚩", "milestone"),
    "milestone.achieved": ("🏁", "milestone"),
    "approval.requested": ("⏳", "approval"),
    "approval.granted": ("✅", "approval"),
    "approval.rejected": ("⛔", "approval"),
}


def _activity_summary(r, p: dict, item_titles: dict) -> str:
    et = r["event_type"]
    if et == "item.created":
        return f"创建了工作项「{p.get('title', '?')}」"
    if et == "item.status_changed":
        title = item_titles.get(r["agg_id"], "")
        return f"「{title}」状态变更为 {p.get('status', '?')}"
    if et == "comment.created":
        title = item_titles.get(p.get("item_id"), "")
        return f"评论了「{title}」：{(p.get('body') or '')[:40]}"
    if et == "milestone.created":
        return f"创建了里程碑「{p.get('title', '?')}」"
    if et == "milestone.achieved":
        return f"达成里程碑「{p.get('title', '?')}」"
    if et == "approval.requested":
        return f"发起{p.get('kind', '')}审批"
    if et in ("approval.granted", "approval.rejected"):
        return "批准了审批" if et == "approval.granted" else "拒绝了审批"
    return et


@router.get("/portfolio/activity.atom")
def portfolio_activity_atom(key: str, request: Request) -> Response:
    """Atom subscription for the cross-project activity feed (M37-I115,
    docs/01 §AJ.3): the URL IS the credential — same feed_key model as the
    M11 per-user feeds and iCal. Hand-written Atom, zero dependencies."""
    import xml.sax.saxutils as sx

    from apm.domains.feed import _user_by_feed_key

    user = _user_by_feed_key(key)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid feed key")
    conn = db.get_conn()
    acts = _activity_list(conn, user, None, None, None, 50)
    base = str(request.base_url).rstrip("/")
    entries = []
    for a in acts:
        title = sx.escape(f"{a['actor_name']} {a['summary']} · {a['project_name']}")
        entries.append(
            f"  <entry>\n"
            f"    <id>urn:apm:activity/{a['project_id']}/{a['event_id']}</id>\n"
            f"    <title>{title}</title>\n"
            f"    <updated>{a['ts']}</updated>\n"
            f"    <link href=\"{base}/#/p/{a['project_id']}/board\"/>\n"
            f"    <author><name>{sx.escape(a['actor_name'])}</name></author>\n"
            f"  </entry>"
        )
    xml = (
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n"
        "<feed xmlns=\"http://www.w3.org/2005/Atom\">\n"
        "  <id>urn:apm:activity</id>\n"
        "  <title>AgentPM 项目动态</title>\n"
        + (f"  <updated>{acts[0]['ts']}</updated>\n" if acts else "")
        + "\n".join(entries) + "\n</feed>"
    )
    return Response(content=xml, media_type="application/atom+xml")


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
    # I111: flag members whose active time-off stretch covers today
    on_leave = {r["user_id"] for r in conn.execute(
        "SELECT user_id FROM user_time_off WHERE cancelled_at IS NULL"
        " AND start_date <= ? AND end_date >= ?", (today_s, today_s)).fetchall()}
    # I118: flag overloaded members — strictly more active items than the
    # threshold. Detection only (the MS Project auto-leveling antipattern is
    # deliberately not replicated; humans rebalance, the page just warns).
    from apm import config as _cfg
    threshold = max(1, _cfg.settings.workload_overload_threshold)
    for p in rows:
        p["on_leave"] = p["user_id"] in on_leave
        p["overloaded"] = p["active"] > threshold
    return {"members": rows, "today": today_s, "generated_at": _now().isoformat(),
            "overload_threshold": threshold}


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


@router.get("/projects/{project_id}/health/history")
def health_history(project_id: str, days: int = 30) -> dict:
    """Health score over time (M30-I93, docs/01 §AC.2): the I92 composite
    recomputed at ~5-day sample points by replaying item and approval events —
    the same event-sourcing dividend as the milestone burndown, zero tables.
    Staleness uses last touch (created or last status change) as a replay
    approximation of updated_at."""
    from apm.domains.projects import require_project

    require_project(project_id)
    days = max(7, min(days, 90))
    conn = db.get_conn()
    today = _now().date()
    start = today - timedelta(days=days - 1)
    points = [start + timedelta(days=i) for i in range(0, days, 5)]
    if points[-1] != today:
        points.append(today)

    evs = conn.execute(
        "SELECT agg_id, event_type, payload, ts FROM events"
        " WHERE project_id = ? AND event_type IN"
        " ('item.created','item.updated','item.status_changed',"
        "  'approval.requested','approval.granted','approval.rejected')"
        " ORDER BY id",
        (project_id,),
    ).fetchall()

    items: dict[str, dict] = {}
    done_arrival: dict[str, str] = {}
    pending_gates = 0

    def apply(e) -> None:
        nonlocal pending_gates
        p = json.loads(e["payload"])
        et = e["event_type"]
        if et == "item.created":
            items[e["agg_id"]] = {"due": p.get("due_date"),
                                  "group": p.get("status_group", ""),
                                  "touch": e["ts"][:10]}
        elif et == "item.updated" and e["agg_id"] in items:
            if "due_date" in p:
                items[e["agg_id"]]["due"] = p["due_date"]
        elif et == "item.status_changed" and e["agg_id"] in items:
            items[e["agg_id"]]["group"] = p.get("status_group", "")
            items[e["agg_id"]]["touch"] = e["ts"][:10]
            if p.get("status_group") == "done" and e["agg_id"] not in done_arrival:
                done_arrival[e["agg_id"]] = e["ts"][:10]
        elif et == "approval.requested":
            pending_gates += 1
        elif et in ("approval.granted", "approval.rejected"):
            pending_gates = max(pending_gates - 1, 0)

    series = []
    ei = 0
    for point in points:
        point_s = point.isoformat()
        while ei < len(evs) and evs[ei]["ts"][:10] <= point_s:
            apply(evs[ei])
            ei += 1
        stale_cut = (point - timedelta(days=STALE_DAYS)).isoformat()
        week_start = (point - timedelta(days=6)).isoformat()
        active_items = [s for s in items.values() if s["group"] not in ("done", "cancelled")]
        active = len(active_items)
        overdue = sum(1 for s in active_items if s["due"] and s["due"] < point_s)
        stale = sum(1 for s in active_items if s["touch"] <= stale_cut)
        done_7d = sum(1 for d in done_arrival.values() if week_start <= d <= point_s)
        f = {"active": active, "overdue": overdue, "stale": stale,
             "done_7d": done_7d, "gates": pending_gates}
        series.append({"date": point_s, "score": _health_score(f),
                       "active": active, "overdue": overdue, "gates": pending_gates})
    return {"project_id": project_id, "days": days, "series": series,
            "generated_at": _now().isoformat()}


@router.get("/projects/{project_id}/baseline-curve")
def baseline_curve(project_id: str, baseline_id: str | None = None,
                   compare: str | None = None) -> dict:
    """Baseline S-curve (M34-I106 + M36-I112, docs/01 §AI.3, EVM semantics):
    PV accrues each baseline item's weight by its planned due (weight =
    estimate_hours, falling back to 1.0 for pre-I106 snapshots), EV accrues by
    the replayed first-arrival day of done, AC accrues actual logged minutes
    on baseline items (replayed from time.logged minus soft-deleted entries).
    `compare=<baseline_id>` overlays a second baseline's PV curve — the
    multi-baseline overlay MS Project needs an Excel export for. SPI = EV/PV
    at the last sample; PV=0 is an honest None."""
    from apm.domains.projects import require_project

    require_project(project_id)
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT id, snapshot, created_at FROM baselines"
        " WHERE project_id = ? ORDER BY created_at, id", (project_id,)).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="no baseline set for this project")
    row = rows[-1] if not baseline_id else next(
        (r for r in rows if r["id"] == baseline_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="unknown baseline")
    snap = json.loads(row["snapshot"])["items"]
    # weight = estimate_hours when the snapshot carries it, else 1.0 per item
    weights: dict[str, float] = {}
    planned_due: dict[str, str] = {}
    for item_id, entry in snap.items():
        weights[item_id] = float(entry[2]) if len(entry) > 2 and entry[2] else 1.0
        if entry[1]:
            planned_due[item_id] = entry[1]

    # EV: first-arrival day of done per baseline item, replayed
    first_done: dict[str, str] = {}
    if snap:
        for e in conn.execute(
            "SELECT agg_id, payload, ts FROM events"
            " WHERE project_id = ? AND event_type = 'item.status_changed' ORDER BY id",
            (project_id,),
        ).fetchall():
            if e["agg_id"] not in weights or e["agg_id"] in first_done:
                continue
            if json.loads(e["payload"]).get("status_group") == "done":
                first_done[e["agg_id"]] = e["ts"][:10]

    # AC (I112): logged minutes on baseline items by spent_on, replayed from
    # time.logged and excluding entries soft-deleted via time.deleted
    deleted_entries = {e["agg_id"] for e in conn.execute(
        "SELECT agg_id FROM events"
        " WHERE project_id = ? AND event_type = 'time.deleted'",
        (project_id,)).fetchall()}
    ac_logs: list[tuple[str, int]] = []  # (spent_on, minutes)
    if weights:
        for e in conn.execute(
            "SELECT agg_id, payload FROM events"
            " WHERE project_id = ? AND event_type = 'time.logged' ORDER BY id",
            (project_id,),
        ).fetchall():
            if e["agg_id"] in deleted_entries:
                continue
            p = json.loads(e["payload"])
            if p.get("item_id") in weights:
                ac_logs.append((p.get("spent_on") or "9999", p.get("minutes") or 0))

    total = sum(weights.values())
    start = (row["created_at"] or "")[:10]
    points = _now().date()
    today = points.isoformat()
    begin = date.fromisoformat(min([start, today])) if start else points
    span = max((points - begin).days, 1)
    sample_days = [begin + timedelta(days=i) for i in range(0, span, 5)]
    if sample_days[-1] != points:
        sample_days.append(points)

    def pv_on(day_s: str) -> float:
        return sum(w for iid, w in weights.items()
                   if planned_due.get(iid, "9999") <= day_s)

    def ev_on(day_s: str) -> float:
        return sum(weights[iid] for iid, d in first_done.items() if d <= day_s)

    def ac_on(day_s: str) -> float:
        return sum(m for d, m in ac_logs if d <= day_s) / 60.0

    samples = []
    for pday in sample_days:
        ds = pday.isoformat()
        samples.append({"date": ds, "pv": round(pv_on(ds), 2),
                        "ev": round(ev_on(ds), 2), "ac": round(ac_on(ds), 2)})
    pv_total, ev_last = samples[-1]["pv"], samples[-1]["ev"]
    spi = round(ev_last / pv_total, 3) if pv_total > 0 else None

    # I112: a second baseline's PV overlaid on the same sample points
    compare_data = None
    if compare:
        crow = next((r for r in rows if r["id"] == compare and r["id"] != row["id"]), None)
        if crow is None:
            raise HTTPException(status_code=404, detail="unknown compare baseline")
        csnap = json.loads(crow["snapshot"])["items"]
        cw: dict[str, float] = {}
        cdue: dict[str, str] = {}
        for item_id, entry in csnap.items():
            cw[item_id] = float(entry[2]) if len(entry) > 2 and entry[2] else 1.0
            if entry[1]:
                cdue[item_id] = entry[1]

        def cpv_on(day_s: str) -> float:
            return sum(w for iid, w in cw.items()
                       if cdue.get(iid, "9999") <= day_s)

        compare_data = {
            "baseline_id": crow["id"], "created_at": crow["created_at"],
            "pv_total": round(sum(cw.values()), 2),
            "samples": [{"date": d.isoformat(), "pv": round(cpv_on(d.isoformat()), 2)}
                        for d in sample_days],
        }
    return {"project_id": project_id, "baseline_id": row["id"],
            "created_at": row["created_at"], "total": round(total, 2),
            "samples": samples, "pv_total": pv_total, "ev_last": ev_last,
            "ac_last": samples[-1]["ac"], "spi": spi,
            "compare": compare_data,
            "weights": "estimate_hours, fallback 1.0 for pre-I106 snapshots"}


@router.get("/projects/{project_id}/critical-path")
def critical_path(project_id: str) -> dict:
    """CPM (M33-I101, docs/01 §AF.1): a backward pass over the scheduled
    dependency DAG computes each item's latest finish; zero-float items form
    the critical chain. Done/cancelled items and their edges are out of scope
    (the chain is about future risk); a dependency cycle yields an honest
    cycle flag instead of a partial chain. Pure projection computation."""
    from apm.domains.projects import require_project

    require_project(project_id)
    conn = db.get_conn()
    items = conn.execute(
        "SELECT id, title, start_date, due_date FROM items"
        " WHERE project_id = ? AND start_date IS NOT NULL AND due_date IS NOT NULL"
        " AND archived_at IS NULL"
        " AND COALESCE(status_group, '') NOT IN ('done', 'cancelled')",
        (project_id,)).fetchall()
    ids = {r["id"] for r in items}
    rels = conn.execute(
        "SELECT from_item, to_item, COALESCE(lag_days, 0) AS lag FROM item_relations"
        " WHERE project_id = ? AND relation_type = 'depends_on'",
        (project_id,)).fetchall()

    succ: dict[str, list[tuple[str, int]]] = {}
    indeg: dict[str, int] = {i: 0 for i in ids}
    for r in rels:
        if r["from_item"] in ids and r["to_item"] in ids:
            succ.setdefault(r["from_item"], []).append((r["to_item"], int(r["lag"])))
            indeg[r["to_item"]] = indeg.get(r["to_item"], 0) + 1

    # Kahn topo order; items trapped in a cycle never surface
    queue = deque(sorted(i for i, d in indeg.items() if d == 0))
    order: list[str] = []
    indeg_c = dict(indeg)
    while queue:
        n = queue.popleft()
        order.append(n)
        for m, _lag in succ.get(n, []):
            indeg_c[m] -= 1
            if indeg_c[m] == 0:
                queue.append(m)
    if len(order) < len(ids):
        return {"project_id": project_id, "cycle": True, "chain": [], "float": {}}
    if not order:
        return {"project_id": project_id, "cycle": False, "chain": [],
                "float": {}, "generated_at": _now().isoformat()}

    info = {r["id"]: dict(r) for r in items}
    max_due = max(date.fromisoformat(info[i]["due_date"]) for i in order)
    dur = {nid: (date.fromisoformat(info[nid]["due_date"])
                 - date.fromisoformat(info[nid]["start_date"])).days + 1
           for nid in order}
    latest: dict[str, date] = {}
    for nid in reversed(order):
        succs = succ.get(nid, [])
        if succs:
            # latest_finish[n] = min over successors m of
            # latest_finish[m] - duration(m) - lag   (successor's span eaten first)
            latest[nid] = min(
                latest[m] - timedelta(days=dur[m] + lag)
                for m, lag in succs)
        else:
            latest[nid] = max_due
    float_days = {nid: (latest[nid] - date.fromisoformat(info[nid]["due_date"])).days
                  for nid in order}
    # float <= 0 is critical (negative float = the schedule is already blown)
    chain = [nid for nid in order if float_days.get(nid) <= 0]
    return {"project_id": project_id, "cycle": False, "chain": chain,
            "float": float_days, "generated_at": _now().isoformat()}


@router.get("/projects/{project_id}/cost-report")
def cost_report(project_id: str) -> dict:
    """M40-I122 (docs/01 §AM.1, OpenProject Time and cost semantics): labor
    cost = logged minutes × the member's hourly rate, derived on the fly from
    the time-entry projection — never a second ledger. Members without a rate
    contribute hours but zero cost (stated, not hidden). The budget is set in
    hours; the burn ratio compares spent hours against it.
    M46-I139 多币种：费率带币种（users.currency），按全局手工汇率表折算
    基准币汇总；未配汇率的币种诚实标注「未折算」，不假装精确。"""
    from apm import config as cfg
    from apm.domains.projects import require_project

    require_project(project_id)
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT t.user_id AS uid, u.name AS uname, u.hourly_rate AS rate,"
        " u.currency AS currency, SUM(t.minutes) AS minutes"
        " FROM item_time_entries t LEFT JOIN users u ON u.id = t.user_id"
        " WHERE t.project_id = ? AND t.deleted_at IS NULL"
        " GROUP BY t.user_id ORDER BY minutes DESC", (project_id,)).fetchall()
    base = (cfg.settings.base_currency or "CNY").upper()
    rates = {k.upper(): float(v) for k, v in (cfg.settings.fx_rates or {}).items()}
    unconverted: list[dict] = []
    by_user = []
    for r in rows:
        cost_native = round((r["minutes"] or 0) / 60 * (r["rate"] or 0), 2)
        cur = (r["currency"] or base).upper()
        fx = 1.0 if cur == base else rates.get(cur)
        if fx is None:
            unconverted.append({"user_id": r["uid"], "currency": cur})
            cost_base = cost_native  # 未折算：原样计入并显式披露
        else:
            cost_base = round(cost_native * fx, 2)
        by_user.append({
            "user_id": r["uid"], "user_name": (r["uname"] or r["uid"]),
            "hours": round((r["minutes"] or 0) / 60, 2),
            "rate": r["rate"], "currency": r["currency"],
            "cost": cost_base, "cost_native": cost_native,
            "fx_rate": fx,
        })
    spent_hours = round(sum(u["hours"] for u in by_user), 2)
    labor_cost = round(sum(u["cost"] for u in by_user), 2)
    # I142 双轨：material/unit costs（expense 行项）与 labor 并列；金额经
    # I139 汇率表折算基准币；预算仍小时口径，费用轨并排展示不混算。
    exp_rows = conn.execute(
        "SELECT id, description, qty, unit_price, currency, spent_on, vendor, item_id"
        " FROM expense_entries WHERE project_id = ? AND deleted_at IS NULL"
        " ORDER BY spent_on, id", (project_id,)).fetchall()
    expenses = []
    expense_cost = 0.0
    exp_unconverted: list[dict] = []
    for r in exp_rows:
        native = round((r["qty"] or 0) * (r["unit_price"] or 0), 2)
        cur = (r["currency"] or base).upper()
        fx = 1.0 if cur == base else rates.get(cur)
        if fx is None:
            exp_unconverted.append({"id": r["id"], "currency": cur})
            cost_base = native
        else:
            cost_base = round(native * fx, 2)
        expense_cost += cost_base
        expenses.append({
            "id": r["id"], "description": r["description"], "qty": r["qty"],
            "unit_price": r["unit_price"], "currency": r["currency"],
            "spent_on": r["spent_on"], "vendor": r["vendor"], "item_id": r["item_id"],
            "cost_native": native, "fx_rate": fx, "cost": cost_base,
        })
    expense_cost = round(expense_cost, 2)
    budget = conn.execute(
        "SELECT budget_hours FROM projects WHERE id = ?", (project_id,)).fetchone()["budget_hours"]
    burn_ratio = round(spent_hours / budget, 4) if budget else None
    return {
        "project_id": project_id,
        "base_currency": base,
        "by_user": by_user,
        "unconverted": unconverted,
        "expenses": expenses,
        "expense_unconverted": exp_unconverted,
        "labor_cost": labor_cost,
        "expense_cost": expense_cost,
        "spent_hours": spent_hours,
        "total_cost": round(labor_cost + expense_cost, 2),
        "budget_hours": budget,
        "burn_ratio": burn_ratio,
        "over_budget": bool(budget and spent_hours > budget),
        "generated_at": _now().isoformat(),
    }


@router.get("/projects/{project_id}/forecast")
def project_forecast(project_id: str) -> dict:
    """M39-I121 (docs/01 §AL.3, Jira velocity chart + jira-agile-velocity):
    completion forecast = recent throughput extrapolated. The rate is the
    MEDIAN of weekly done-completions over the last complete ISO weeks inside
    the project's history (first arrival of done replayed from the event
    stream — the same caliber as the milestone burndown and the S-curve EV).
    Median, not mean: one freak week must not bend the projection. Fewer than
    two complete weeks of history, or a zero rate → honest null with the
    reason (the SPI precedent), never a made-up date. Pure replay, zero new
    tables — event-sourcing dividend #8."""
    import statistics

    from apm.domains.projects import require_project

    require_project(project_id)
    conn = db.get_conn()
    today = _now().date()

    active = conn.execute(
        "SELECT id, title, due_date FROM items WHERE project_id = ?"
        " AND status_group NOT IN ('done','cancelled') AND archived_at IS NULL"
        " ORDER BY due_date IS NULL, due_date, id", (project_id,)).fetchall()

    # first-arrival replay of done (I85 caliber): one date per item, earliest win
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

    created_row = conn.execute(
        "SELECT MIN(ts) AS t FROM events WHERE project_id = ?", (project_id,)).fetchone()
    created = (created_row["t"] or today.isoformat())[:10]

    # the last complete Mon–Sun weeks fully inside the project's history
    this_monday = today - timedelta(days=today.weekday())
    weeks = []
    for i in range(1, 5):
        ws = this_monday - timedelta(days=7 * i)
        we = ws + timedelta(days=6)
        if ws.isoformat() < created:
            break  # week starts before the project existed — stop counting
        weeks.append((ws.isoformat(), we.isoformat()))

    weekly = [{"week_start": ws, "week_end": we,
               "done": sum(1 for d in first_done.values() if ws <= d <= we)}
              for ws, we in weeks]

    base = {"project_id": project_id, "today": today.isoformat(),
            "weeks": weekly, "remaining": len(active)}
    if len(weekly) < 2:
        return {**base, "rate_per_week": None, "forecast": None,
                "reason": "insufficient history", "at_risk": [],
                "generated_at": _now().isoformat()}
    rate = statistics.median(w["done"] for w in weekly)
    if rate <= 0:
        return {**base, "rate_per_week": 0, "forecast": None,
                "reason": "no completion velocity", "at_risk": [],
                "generated_at": _now().isoformat()}

    from math import ceil
    finish = today + timedelta(days=ceil(len(active) / rate * 7)) if active else None
    # per-item risk: sorted by due date, item #k is projected to finish by
    # day ceil((k+1)/rate*7); an earlier due date means the plan is broken
    at_risk = []
    for idx, r in enumerate(active):
        if not r["due_date"]:
            continue
        expected = (today + timedelta(days=ceil((idx + 1) / rate * 7))).isoformat()
        if r["due_date"] < expected:
            at_risk.append({"id": r["id"], "title": r["title"],
                            "due_date": r["due_date"], "expected_by": expected})
    return {**base, "rate_per_week": rate, "forecast": finish.isoformat() if finish else None,
            "reason": None if finish else "no active items",
            "at_risk": at_risk, "generated_at": _now().isoformat()}


@router.get("/projects/{project_id}/responsiveness")
def project_responsiveness(project_id: str, days: int = 30) -> dict:
    """Responsiveness metrics (M31-I97, docs/01 §AD.3 — CHAOSS Time to First
    Response): approval decision latency reads straight off the approvals
    projection (requested_at→decided_at); per-comment first-response latency
    replays the event stream (next non-author comment or status change on the
    same item). A slice with no samples is honest None, not zero."""
    from apm.domains.projects import require_project

    require_project(project_id)
    days = max(7, min(days, 90))
    conn = db.get_conn()
    since = (_now() - timedelta(days=days)).isoformat()

    def _slice(samples: list[float]) -> dict | None:
        if not samples:
            return None
        samples = sorted(samples)
        n = len(samples)
        mid = n // 2
        median = samples[mid] if n % 2 else (samples[mid - 1] + samples[mid]) / 2
        return {
            "count": n,
            "avg_h": round(sum(samples) / n, 1),
            "median_h": round(median, 1),
            "over_48h": round(sum(1 for s in samples if s > 48) / n, 3),
        }

    arows = conn.execute(
        "SELECT requested_at, decided_at FROM approvals WHERE project_id = ?"
        " AND status IN ('approved','rejected') AND decided_at IS NOT NULL"
        " AND requested_at IS NOT NULL AND decided_at >= ?",
        (project_id, since),
    ).fetchall()
    approval_samples = [
        (datetime.fromisoformat(r["decided_at"]) - datetime.fromisoformat(r["requested_at"])
         ).total_seconds() / 3600
        for r in arows
    ]

    comments = conn.execute(
        "SELECT item_id, author_id, created_at FROM item_comments"
        " WHERE project_id = ? AND deleted_at IS NULL AND created_at >= ?",
        (project_id, since),
    ).fetchall()
    timeline: dict[str, list[tuple[str, str]]] = {}
    for ev in conn.execute(
        "SELECT agg_id, event_type, payload, actor_id, ts FROM events"
        " WHERE project_id = ? AND event_type IN"
        " ('comment.created','item.status_changed') ORDER BY id",
        (project_id,),
    ):
        if ev["event_type"] == "comment.created":
            p = json.loads(ev["payload"])
            item_id = p.get("item_id") or ev["agg_id"]
            actor = p.get("author_id") or ev["actor_id"] or ""
        else:
            item_id, actor = ev["agg_id"], ev["actor_id"] or ""
        timeline.setdefault(item_id, []).append((ev["ts"], actor))

    comment_samples: list[float] = []
    unanswered = 0
    for c in comments:
        responses = [ts for ts, actor in timeline.get(c["item_id"], [])
                     if actor and actor != c["author_id"] and ts >= c["created_at"]]
        if not responses:
            unanswered += 1
            continue
        comment_samples.append(
            (datetime.fromisoformat(responses[0]) - datetime.fromisoformat(c["created_at"])
             ).total_seconds() / 3600)

    return {
        "project_id": project_id,
        "days": days,
        "approvals": _slice(approval_samples),
        "comments": _slice(comment_samples),
        "comments_unanswered": unanswered,
        "generated_at": _now().isoformat(),
    }


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


# ------------------------------------------------------- status report (I148)
def _collect_status_metrics(conn, project, today: str) -> dict:
    """I150: data-collection half of the report core — one dict with every
    number the Markdown needs, shared by the manual endpoint and the sweep's
    weekly pass (and by I152, which diffs it against last period)."""
    pid = project["id"]
    funnel = {b: 0 for b in BUCKET_NAMES}
    for r in conn.execute(
        "SELECT status_group, COUNT(*) c FROM items WHERE project_id = ? AND archived_at IS NULL"
        " GROUP BY status_group", (pid,)).fetchall():
        if r["status_group"] in funnel:
            funnel[r["status_group"]] = r["c"]
    done_pct = round(funnel["done"] * 100 / max(sum(funnel.values()), 1))
    overdue = conn.execute(
        "SELECT COUNT(*) c FROM items WHERE project_id = ? AND due_date IS NOT NULL"
        " AND due_date < ? AND status_group NOT IN ('done','cancelled') AND archived_at IS NULL",
        (pid, today)).fetchone()["c"]
    gates_pending = conn.execute(
        "SELECT COUNT(*) c FROM approvals WHERE project_id = ? AND status = 'pending'",
        (pid,)).fetchone()["c"]
    risks_open = conn.execute(
        "SELECT COUNT(*) c FROM risks WHERE project_id = ? AND status != 'closed'",
        (pid,)).fetchone()["c"]
    timelog = conn.execute(
        "SELECT COALESCE(SUM(minutes), 0) m FROM item_time_entries"
        " WHERE project_id = ? AND deleted_at IS NULL", (pid,)).fetchone()["m"]
    expense_cost = conn.execute(
        "SELECT COALESCE(SUM(qty * unit_price), 0) c FROM expense_entries"
        " WHERE project_id = ? AND deleted_at IS NULL", (pid,)).fetchone()["c"]
    recent_done = [
        r["t"] for r in conn.execute(
            "SELECT i.title AS t FROM events e JOIN items i ON i.id = e.agg_id"
            " WHERE e.project_id = ? AND e.event_type = 'item.status_changed'"
            " AND json_extract(e.payload, '$.status_group') = 'done'"
            " ORDER BY e.id DESC LIMIT 5", (pid,)).fetchall()
    ]
    return {"funnel": funnel, "done_pct": done_pct, "overdue": overdue,
            "gates_pending": gates_pending, "risks_open": risks_open,
            "timelog": timelog, "expense_cost": expense_cost,
            "budget_hours": project["budget_hours"], "recent_done": recent_done}


def _render_status_lines(project, today: str, m: dict) -> list[str]:
    """I150: rendering half of the report core — pure function of the
    metrics dict, no queries (manual and weekly share the exact layout)."""
    funnel, done_pct = m["funnel"], m["done_pct"]
    overdue, gates_pending = m["overdue"], m["gates_pending"]
    timelog, expense_cost = m["timelog"], m["expense_cost"]
    budget_hours = m["budget_hours"]
    lines = [
        f"# 项目状态报告 · {project['name']}",
        f"（生成于 {today} · 覆盖全部活跃工作项）", "",
        "## 总体健康", "",
        f"- 工作项漏斗：待办 {funnel['backlog']} · 就绪 {funnel['todo']} · 进行中 {funnel['in_progress']}"
        f" · 完成 {funnel['done']} · 取消 {funnel['cancelled']}（完成度约 {done_pct}%）",
        f"- 超期未结：**{overdue}** 项 · 挂起 Gate：**{gates_pending}** 个 · 开放风险：**{m['risks_open']}** 条",
        f"- 工时投入 {round(timelog / 60, 1)}h"
        + (f" / 预算 {budget_hours}h（消耗 {round(timelog / 60 / budget_hours * 100)}%）" if budget_hours else "")
        + f" · 费用行合计 {round(expense_cost, 2)}",
        "",
        "## 最近完成", "",
    ]
    lines += [f"- {t}" for t in m["recent_done"]] or ["-（暂无）"]
    lines += ["", "## 待办与建议", "",
              f"- {gates_pending} 个 Gate 待审批，先清审批墙" if gates_pending
              else "- 审批墙干净，可推进新一批任务",
              f"- 关注 {overdue} 项超期工作的原因归类（排期过满 / 依赖阻塞 / 范围蔓延）" if overdue
              else "- 无超期项，节奏健康"]
    return lines


def _commit_report(project_id: str, lines: list[str], *, prefix: str,
                   actor_type: str, actor_id: str, payload: dict) -> dict:
    """I150: shared write+audit tail — file into the project git repo, then
    the artifact.report_generated fact (payload_extra merged in by callers)."""
    from apm.content import gitrepo
    from apm.core.ids import new_id

    stamp = _now().strftime("%Y%m%d-%H%M%S")
    rel = f"artifacts/reports/{prefix}-{stamp}-{new_id('r')[-6:]}.md"
    nl = chr(10)
    sha = gitrepo.write_file(
        project_id, rel, nl.join(lines) + nl,
        message=f"status report {stamp}", actor_type=actor_type, actor_id=actor_id)
    events.emit(
        event_type="artifact.report_generated", agg_type="artifact", agg_id=rel,
        project_id=project_id, actor_type=actor_type, actor_id=actor_id,
        payload={"path": rel, "commit": sha, **payload,
                 "summary": payload.get("summary", f"生成状态报告 → {rel}")},
    )
    return {"path": rel, "commit": sha}


@router.post("/projects/{project_id}/status-report")
def generate_status_report(project_id: str, ai_summary: bool = False) -> dict:
    """M49-I148 (docs/01 §AT.2, Monday/TeamGantt "auto-compile a draft, human
    polishes" semantics): assemble the platform's own projections into a
    Markdown status report and commit it as an artifact — the git artifact
    channel inherits version history, diff and the audit trail for free, no
    new tables. Optional ai_summary adds a plain-language paragraph via the
    cheap-tier model (any failure degrades to the data-only report)."""
    from apm.domains.projects import require_project

    require_project(project_id)
    conn = db.get_conn()
    project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    today = _now().date().isoformat()
    m = _collect_status_metrics(conn, project, today)
    lines = _render_status_lines(project, today, m)

    ai_note = None
    if ai_summary and config.settings.provider_mode != "replay":
        try:
            from apm.runtime.provider import get_provider

            c = get_provider().complete(
                role="pm-agent", node="summarize",
                messages=[
                    {"role": "system", "content": "根据项目状态数据写一段不超过 120 字的中文总结，"
                     "先给总体判断，再点出最需要注意的一件事。"},
                    {"role": "user", "content": chr(10).join(lines)},
                ],
                context={"model": config.settings.ui_agent_model},
            )
            if c.text:
                lines += ["", "## AI 摘要", "", c.text.strip()]
                ai_note = c.text.strip()[:60] + "…"
        except Exception:
            ai_note = None  # 降级：纯数据版照常交付

    out = _commit_report(project_id, lines, prefix="status",
                         actor_type="human", actor_id=events.effective_actor(),
                         payload={"ai_summary": bool(ai_note)})
    out["ai_summary"] = ai_note
    return out


def write_weekly_status_report(project_id: str, today: str, week: str) -> dict:
    """M50-I150 (docs/01 §AU.1): the sweep's weekly pass entry — same assembly
    core as the manual endpoint, automation actor, and the payload carries
    source/week (per-project per-week heartbeat, zero new tables) plus the
    structured metrics I152 diffs against next period. AI summary stays off
    here: scheduled reports must not spend tokens nobody asked for."""
    conn = db.get_conn()
    project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        return {}
    m = _collect_status_metrics(conn, project, today)
    lines = _render_status_lines(project, today, m)
    metrics = {"done_pct": m["done_pct"], "overdue": m["overdue"],
               "gates": m["gates_pending"], "risks": m["risks_open"],
               "expense_cost": round(m["expense_cost"], 2),
               "timelog_h": round(m["timelog"] / 60, 1)}
    out = _commit_report(project_id, lines, prefix="status",
                         actor_type="automation", actor_id="scheduler",
                         payload={"source": "weekly", "week": week,
                                  "metrics": metrics,
                                  "summary": f"周报已生成 → 第 {week} 期"})
    out["metrics"] = metrics
    return out
