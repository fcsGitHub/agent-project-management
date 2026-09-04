"""Gantt baselines (M23-I71, docs/01 §V.1): one active baseline per project —
a snapshot of every scheduled item's start/due (plus milestone deadlines) at
the moment of capture. Later rescheduling never touches the snapshot, so the
timeline can overlay ghost bars and show drift (Redmine #13419 semantics,
sold as plugins elsewhere; here it is core and event-sourced: setting a new
baseline replaces the old one, both visible in history)."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on

router = APIRouter(tags=["baselines"])


# ------------------------------------------------------------ projections
@on("project.baseline_set")
def _proj_baseline_set(conn, e):
    p = e.payload
    conn.execute("DELETE FROM baselines WHERE project_id = ?", (e.project_id,))
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
    _require_item_project(project_id)
    row = db.get_conn().execute(
        "SELECT snapshot, created_at FROM baselines WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    if row is None:
        return {"project_id": project_id, "baseline": None}
    return {"project_id": project_id, "baseline": json.loads(row["snapshot"]),
            "created_at": row["created_at"]}
