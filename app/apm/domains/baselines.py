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
    # I106: each entry carries [start, due, estimate_hours] — EVM weighting for
    # the baseline S-curve; pre-I106 snapshots hold [start, due] and curve
    # parsing falls back to weight 1.0 per item (count semantics).
    items = conn.execute(
        "SELECT id, start_date, due_date, estimate_hours FROM items"
        " WHERE project_id = ? AND (start_date IS NOT NULL OR due_date IS NOT NULL)"
        " AND archived_at IS NULL"  # M65-I197: archived items leave the plan
        " ORDER BY id", (project_id,),
    ).fetchall()
    milestones = conn.execute(
        "SELECT id, due_date FROM milestones WHERE project_id = ? ORDER BY id",
        (project_id,),
    ).fetchall()
    return {
        "items": {r["id"]: [r["start_date"], r["due_date"], r["estimate_hours"]]
                  for r in items},
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


@router.get("/projects/{project_id}/baselines/compare")
def compare_baselines(project_id: str, a: str, b: str) -> dict:
    """M65-I197 (docs/01 §BJ.3 — MS Project multi-baseline diff semantics: the
    value of many baselines is comparing them, not storing them). Item-level
    diff between any two snapshots: date shifts in days, items only in one of
    the two. Read-only projection over the M24 baselines store."""
    _require_item_project(project_id)
    rows = {r["id"]: r for r in _list_rows(project_id)}
    for want, label in ((a, "a"), (b, "b")):
        if want not in rows:
            raise HTTPException(status_code=404, detail=f"unknown baseline '{label}'")
    sa = json.loads(rows[a]["snapshot"])["items"]
    sb = json.loads(rows[b]["snapshot"])["items"]

    def _iso(v: str | None):
        return date.fromisoformat(v) if v else None

    shifted, unchanged = [], []
    for item_id, va in sa.items():
        if item_id not in sb:
            continue  # counted as removed
        vb = sb[item_id]
        a_start, a_due, b_start, b_due = (_iso(va[0]), _iso(va[1]), _iso(vb[0]), _iso(vb[1]))
        s_shift = (b_start - a_start).days if (a_start and b_start) else None
        d_shift = (b_due - a_due).days if (a_due and b_due) else None
        entry = {"item_id": item_id,
                 "a_start": va[0], "a_due": va[1], "b_start": vb[0], "b_due": vb[1],
                 "start_shift_days": s_shift, "due_shift_days": d_shift}
        if s_shift in (None, 0) and d_shift in (None, 0):
            unchanged.append(entry)
        else:
            shifted.append(entry)
    shifted.sort(key=lambda e: -(abs(e["due_shift_days"] or 0)))
    removed = sorted(set(sa) - set(sb))
    added = sorted(set(sb) - set(sa))
    return {
        "project_id": project_id, "a": a, "b": b,
        "a_created_at": rows[a]["created_at"], "b_created_at": rows[b]["created_at"],
        "summary": {"total": len(sa), "shifted": len(shifted),
                    "unchanged": len(unchanged), "removed": len(removed), "added": len(added)},
        "shifted": shifted, "unchanged": unchanged,
        "removed": removed, "added": added,
    }


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
