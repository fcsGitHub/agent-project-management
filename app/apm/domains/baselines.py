"""Gantt baselines (M23-I71 → M24-I76 multi-baseline, docs/01 §V.1/§W.3): each
"set baseline" appends a snapshot of every scheduled item's start/due (plus
milestone deadlines); later rescheduling never touches past snapshots, so the
timeline can overlay ghost bars from any or all baselines and show drift
(Redmine #13419 semantics, sold as plugins elsewhere). Clearing wipes the
project's baseline history."""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, HTTPException

from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on

router = APIRouter(tags=["baselines"])


# ------------------------------------------------------------ projections
@on("project.baseline_set")
def _proj_baseline_set(conn, e):
    p = e.payload
    conn.execute(
        "INSERT INTO baselines (id, project_id, snapshot, created_at) VALUES (?,?,?,?)",
        (e.agg_id, e.project_id, json.dumps(p["snapshot"], ensure_ascii=False), e.ts),
    )


@on("project.baseline_cleared")
def _proj_baseline_cleared(conn, e):
    conn.execute("DELETE FROM baselines WHERE project_id = ?", (e.project_id,))


def _snapshot(project_id: str) -> dict:
    conn = db.get_conn()
    items = conn.execute(
        "SELECT id, start_date, due_date FROM items"
        " WHERE project_id = ? AND (start_date IS NOT NULL OR due_date IS NOT NULL)"
        " ORDER BY id", (project_id,),
    ).fetchall()
    milestones = conn.execute(
        "SELECT id, due_date FROM milestones WHERE project_id = ? ORDER BY id",
        (project_id,),
    ).fetchall()
    return {
        "items": {r["id"]: [r["start_date"], r["due_date"]] for r in items},
        "milestones": {r["id"]: r["due_date"] for r in milestones},
    }


def _require_item_project(project_id: str) -> None:
    from apm.domains.projects import require_project
    require_project(project_id)


@router.post("/projects/{project_id}/baseline")
def set_baseline(project_id: str) -> dict:
    """Append a new snapshot to the baseline history (M24-I76 multi-baseline;
    older baselines are kept for comparison — MS Project multi-baseline
    semantics). The newest one is what GET /baseline returns."""
    _require_item_project(project_id)
    snapshot = _snapshot(project_id)
    events.emit(
        event_type="project.baseline_set",
        agg_type="baseline",
        agg_id=new_id("bl"),
        project_id=project_id,
        payload={"snapshot": snapshot},
    )
    return {"project_id": project_id, "baseline": snapshot}


@router.delete("/projects/{project_id}/baseline")
def clear_baseline(project_id: str) -> dict:
    _require_item_project(project_id)
    events.emit(
        event_type="project.baseline_cleared",
        agg_type="baseline",
        agg_id=new_id("bl"),
        project_id=project_id,
        payload={},
    )
    return {"project_id": project_id, "baseline": None}


@router.get("/projects/{project_id}/baseline")
def get_baseline(project_id: str) -> dict:
    """The newest baseline (backward-compatible single-baseline read)."""
    rows = _list_rows(project_id)
    if not rows:
        return {"project_id": project_id, "baseline": None}
    return {"project_id": project_id, "baseline": json.loads(rows[-1]["snapshot"]),
            "created_at": rows[-1]["created_at"], "baseline_id": rows[-1]["id"]}


@router.get("/projects/{project_id}/baselines")
def list_baselines(project_id: str) -> dict:
    rows = _list_rows(project_id)
    return {"project_id": project_id, "baselines": [
        {"id": r["id"], "created_at": r["created_at"], "snapshot": json.loads(r["snapshot"])}
        for r in rows
    ]}


def _list_rows(project_id: str) -> list:
    return db.get_conn().execute(
        "SELECT id, snapshot, created_at FROM baselines WHERE project_id = ?"
        " ORDER BY created_at, id", (project_id,),
    ).fetchall()


@router.get("/projects/{project_id}/baseline-variance")
def baseline_variance(project_id: str, baseline_id: str | None = None,
                      include_same: bool = False) -> dict:
    """Variance table (M25-I77, MS Project Variance semantics): for each
    scheduled item, current start/due minus the baseline snapshot, in days.
    Items whose dates didn't move are omitted unless include_same. Items
    created after the baseline aren't listed (no baseline to compare)."""
    _require_item_project(project_id)
    rows = _list_rows(project_id)
    if not rows:
        raise HTTPException(status_code=404, detail="no baseline set for this project")
    row = rows[-1] if not baseline_id else next((r for r in rows if r["id"] == baseline_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="unknown baseline")
    snap = json.loads(row["snapshot"])
    conn = db.get_conn()

    def dev(baseline: str | None, current: str | None) -> int | None:
        if not baseline or not current:
            return None
        return (date.fromisoformat(current) - date.fromisoformat(baseline)).days

    variances = []
    for it in conn.execute(
        "SELECT id, title, status, status_group, start_date, due_date FROM items"
        " WHERE project_id = ? AND (start_date IS NOT NULL OR due_date IS NOT NULL)"
        " ORDER BY id", (project_id,),
    ).fetchall():
        b = snap["items"].get(it["id"])
        if b is None:
            continue
        sd = dev(b[0], it["start_date"])
        dd = dev(b[1], it["due_date"])
        moved = (sd is not None and sd != 0) or (dd is not None and dd != 0)
        if not include_same and not moved:
            continue
        variances.append({
            "item_id": it["id"], "title": it["title"], "status": it["status"],
            "baseline_start": b[0], "baseline_due": b[1],
            "current_start": it["start_date"], "current_due": it["due_date"],
            "start_deviation": sd, "due_deviation": dd,
        })
    due_delays = [v["due_deviation"] for v in variances if v["due_deviation"] is not None]
    return {
        "project_id": project_id, "baseline_id": row["id"], "created_at": row["created_at"],
        "variances": variances,
        "summary": {"count": len(variances),
                    "max_due_delay": max(due_delays) if due_delays else 0},
    }
