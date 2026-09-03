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
    """Active items past a declared due date, or older than STALE_DAYS when
    the ontology carries no due field (滞留项) — reason says which."""
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
    return {"user_id": me, "items": items, "approvals": approvals, "projects": projects}
