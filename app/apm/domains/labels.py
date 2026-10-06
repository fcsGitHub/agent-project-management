"""Labels domain (M115-I345, docs/01 §DF — Linear 吸纳轮): project-scoped
lightweight tags with a color, applied to items as a JSON id list on the item
row. Ontology custom_fields stay the typed/heavy path; labels are the everyday
sorting device (Linear labels semantics, minus workspace scope — AgentPM has
no team layer). All writes live under /projects/{pid}/labels so the network
write middleware covers membership; GET stays open per the M76 project-domain
read convention. Deletion fans out through the projection: label.deleted both
drops the row and pulls the id out of every item — replay-safe."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on

router = APIRouter(tags=["labels"])

MAX_NAME = 60


# ------------------------------------------------------------ projections
@on("label.created")
def _proj_label_created(conn, e):
    p = e.payload
    conn.execute(
        "INSERT INTO labels (id, project_id, name, color, created_at) VALUES (?,?,?,?,?)",
        (e.agg_id, e.project_id, p["name"], p.get("color"), e.ts),
    )


@on("label.updated")
def _proj_label_updated(conn, e):
    p = e.payload
    sets, params = [], []
    for key in ("name", "color"):
        if key in p:
            sets.append(f"{key} = ?")
            params.append(p[key])
    if sets:
        params.append(e.agg_id)
        conn.execute(f"UPDATE labels SET {', '.join(sets)} WHERE id = ?", params)


def _pull_label(conn, project_id: str, label_id: str) -> None:
    """Remove a deleted label id from every item's JSON list (LIKE prefilter +
    exact JSON membership so the `_` wildcard in ids can never false-match)."""
    rows = conn.execute(
        "SELECT id, labels FROM items WHERE project_id = ? AND labels LIKE ?",
        (project_id, f'%"{label_id}"%')).fetchall()
    for row in rows:
        try:
            ids = json.loads(row["labels"])
        except (TypeError, ValueError):
            continue
        if not isinstance(ids, list) or label_id not in ids:
            continue
        keep = [x for x in ids if x != label_id]
        conn.execute("UPDATE items SET labels = ? WHERE id = ?",
                     (json.dumps(keep) if keep else None, row["id"]))


@on("label.deleted")
def _proj_label_deleted(conn, e):
    conn.execute("DELETE FROM labels WHERE id = ?", (e.agg_id,))
    _pull_label(conn, e.project_id, e.agg_id)


# ------------------------------------------------------------ helpers
def require_label(label_id: str) -> dict:
    row = db.get_conn().execute("SELECT * FROM labels WHERE id = ?", (label_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"unknown label '{label_id}'")
    return dict(row)


def validate_item_labels(project_id: str, label_ids: list[str] | None) -> None:
    """Every referenced label must exist and belong to the same project
    (cross-project FK → 422, same convention as milestones/cycles/parent)."""
    if not label_ids:
        return
    for lid in label_ids:
        row = db.get_conn().execute(
            "SELECT project_id FROM labels WHERE id = ?", (lid,)).fetchone()
        if row is None:
            raise HTTPException(status_code=422, detail=f"unknown label '{lid}'")
        if row["project_id"] != project_id:
            raise HTTPException(status_code=422, detail="label belongs to another project")


# ------------------------------------------------------------ models
class LabelIn(BaseModel):
    name: str
    color: str | None = None


class LabelPatch(BaseModel):
    name: str | None = None
    color: str | None = None


def _clean_name(name: str | None) -> str:
    name = (name or "").strip()
    if not name or len(name) > MAX_NAME:
        raise HTTPException(status_code=422, detail=f"name must be 1..{MAX_NAME} chars")
    return name


def _color_or_none(color: str | None) -> str | None:
    if color is None:
        return None
    color = color.strip()
    if not color:
        return None
    if len(color) > 20:
        raise HTTPException(status_code=422, detail="color too long (hex or short token)")
    return color


# ------------------------------------------------------------ endpoints
@router.get("/projects/{project_id}/labels")
def list_labels(project_id: str) -> dict:
    rows = db.get_conn().execute(
        "SELECT * FROM labels WHERE project_id = ? ORDER BY created_at, id",
        (project_id,)).fetchall()
    counts: dict[str, int] = {}
    for row in db.get_conn().execute(
            "SELECT labels FROM items WHERE project_id = ? AND labels IS NOT NULL",
            (project_id,)).fetchall():
        try:
            ids = json.loads(row["labels"])
        except (TypeError, ValueError):
            continue
        for lid in ids if isinstance(ids, list) else []:
            counts[lid] = counts.get(lid, 0) + 1
    return {"labels": [
        {**dict(r), "usage": counts.get(r["id"], 0)} for r in rows
    ]}


@router.post("/projects/{project_id}/labels")
def create_label(project_id: str, body: LabelIn) -> dict:
    name = _clean_name(body.name)
    color = _color_or_none(body.color)
    conn = db.get_conn()
    if conn.execute("SELECT 1 FROM labels WHERE project_id = ? AND name = ?",
                    (project_id, name)).fetchone():
        raise HTTPException(status_code=409, detail=f"label '{name}' already exists")
    lid = new_id("label")
    events.emit(
        event_type="label.created",
        agg_type="label",
        agg_id=lid,
        project_id=project_id,
        payload={"name": name, "color": color},
    )
    return require_label(lid)


@router.patch("/projects/{project_id}/labels/{label_id}")
def patch_label(project_id: str, label_id: str, body: LabelPatch) -> dict:
    label = require_label(label_id)
    if label["project_id"] != project_id:
        raise HTTPException(status_code=404, detail=f"unknown label '{label_id}'")
    changes: dict = {}
    if body.name is not None:
        changes["name"] = _clean_name(body.name)
    if body.color is not None:
        changes["color"] = _color_or_none(body.color)
    if not changes:
        raise HTTPException(status_code=422, detail="nothing to update")
    if "name" in changes:
        if db.get_conn().execute(
                "SELECT 1 FROM labels WHERE project_id = ? AND name = ? AND id != ?",
                (project_id, changes["name"], label_id)).fetchone():
            raise HTTPException(status_code=409, detail=f"label '{changes['name']}' already exists")
    events.emit(
        event_type="label.updated",
        agg_type="label",
        agg_id=label_id,
        project_id=project_id,
        payload=changes,
    )
    return require_label(label_id)


@router.delete("/projects/{project_id}/labels/{label_id}")
def delete_label(project_id: str, label_id: str) -> dict:
    label = require_label(label_id)
    if label["project_id"] != project_id:
        raise HTTPException(status_code=404, detail=f"unknown label '{label_id}'")
    events.emit(
        event_type="label.deleted",
        agg_type="label",
        agg_id=label_id,
        project_id=project_id,
        payload={"name": label["name"]},
    )
    return {"ok": True, "id": label_id}
