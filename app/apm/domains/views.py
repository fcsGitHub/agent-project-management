"""Saved views domain (M16-I50): persisted filter/group combinations for the
board and item lists — the Community-edition equivalent of OpenProject custom
queries (docs/01 §O.1). A view definition is a whitelist of the *existing*
list_items/cf parameters plus an optional board group_by, so executing a view
reuses the one true filter path (no second query implementation).

Event-sourced like every domain; visibility follows M8 semantics — private
views are owner/admin-only, public views are readable by project members."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on

router = APIRouter(tags=["views"])

# definition keys whitelist — everything else is rejected (fail-closed)
_ALLOWED_KEYS = ("concept_id", "status_group", "status", "assignee_id", "priority", "cf", "group_by")
_STATUS_GROUPS = ("backlog", "todo", "in_progress", "done", "cancelled")


# ------------------------------------------------------------ projections
@on("view.created")
def _proj_view_created(conn, e):
    p = e.payload
    conn.execute(
        "INSERT INTO saved_views (id, project_id, name, owner_id, is_public, definition,"
        " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (e.agg_id, e.project_id, p["name"], p.get("owner_id"),
         1 if p.get("is_public") else 0, p["definition"], e.ts, e.ts),
    )


@on("view.updated")
def _proj_view_updated(conn, e):
    p = e.payload
    sets, params = [], []
    for key in ("name", "is_public", "definition"):
        if key in p:
            sets.append(f"{key} = ?")
            params.append(1 if (key == "is_public" and p[key]) else p[key])
    if sets:
        sets.append("updated_at = ?")
        params.extend([e.ts, e.agg_id])
        conn.execute(f"UPDATE saved_views SET {', '.join(sets)} WHERE id = ?", params)


@on("view.deleted")
def _proj_view_deleted(conn, e):
    conn.execute("DELETE FROM saved_views WHERE id = ?", (e.agg_id,))


@on("view.made_default")
def _proj_view_made_default(conn, e):
    """One default per project; replay-safe because clear-then-set is ordered."""
    conn.execute("UPDATE saved_views SET is_default = 0 WHERE project_id = ?", (e.project_id,))
    conn.execute("UPDATE saved_views SET is_default = 1 WHERE id = ?", (e.agg_id,))


# ---------------------------------------------------------------- helpers
def get_view(view_id: str) -> dict | None:
    row = db.get_conn().execute(
        "SELECT * FROM saved_views WHERE id = ?", (view_id,)).fetchone()
    return dict(row) if row else None


def require_view(view_id: str) -> dict:
    v = get_view(view_id)
    if not v:
        raise HTTPException(status_code=404, detail=f"unknown view '{view_id}'")
    v["definition"] = json.loads(v["definition"])
    return v


def _validate_definition(definition: dict) -> dict:
    """Whitelist keys, validate value shapes; ontology/field existence is checked
    with project context in _validate_definition_for_project."""
    if not isinstance(definition, dict):
        raise HTTPException(status_code=422, detail="definition must be an object")
    unknown = sorted(set(definition) - set(_ALLOWED_KEYS))
    if unknown:
        raise HTTPException(status_code=422,
                            detail=f"unknown definition keys {unknown}; allowed: {list(_ALLOWED_KEYS)}")
    for key, value in definition.items():
        if not isinstance(value, str) or not value:
            raise HTTPException(status_code=422, detail=f"definition.{key} must be a non-empty string")
    if "status_group" in definition and definition["status_group"] not in _STATUS_GROUPS:
        raise HTTPException(status_code=422,
                            detail=f"status_group must be one of {list(_STATUS_GROUPS)}")
    if "cf" in definition and ":" not in definition["cf"]:
        raise HTTPException(status_code=422, detail="definition.cf must be 'field:value'")
    return definition


def _validate_definition_for_project(project_id: str, definition: dict) -> dict:
    _validate_definition(definition)
    if "group_by" in definition and definition["group_by"] != "lifecycle":
        from apm.domains.items import _find_field, disabled_fields, project_ontology
        if not definition["group_by"].startswith("field:"):
            raise HTTPException(status_code=422,
                                detail=f"definition.group_by must be 'lifecycle' or 'field:<id>'")
        fid = definition["group_by"][len("field:"):]
        onto = project_ontology(project_id)
        if not _find_field(onto, fid):
            raise HTTPException(status_code=422, detail=f"field '{fid}' is not declared in ontology")
        if fid in disabled_fields(project_id):
            raise HTTPException(status_code=422, detail=f"field '{fid}' is disabled in this project")
    if "cf" in definition:
        from apm.domains.items import _find_field, disabled_fields, project_ontology
        fid = definition["cf"].partition(":")[0]
        if not _find_field(project_ontology(project_id), fid):
            raise HTTPException(status_code=422, detail=f"field '{fid}' is not declared in ontology")
        if fid in disabled_fields(project_id):
            raise HTTPException(status_code=422, detail=f"field '{fid}' is disabled in this project")
    return definition


def _actor_can_read(view: dict, actor: str) -> None:
    from apm import config
    from apm.domains.members import is_instance_admin, member_role
    if config.settings.auth_mode == "local":
        return  # 单机可信语义（与 M11 feed 裁剪一致）
    if is_instance_admin(actor):
        return
    role = member_role(view["project_id"], actor)
    if role is None:
        raise HTTPException(status_code=403, detail="not a project member")
    if not view["is_public"] and view["owner_id"] != actor:
        raise HTTPException(status_code=403, detail="private view is owner-only")


def _require_view_writer(view: dict, actor: str) -> None:
    from apm import config
    from apm.domains.members import is_instance_admin
    if config.settings.auth_mode == "local":
        return
    if is_instance_admin(actor) or view["owner_id"] == actor:
        return
    raise HTTPException(status_code=403, detail="only the view owner or an instance admin can modify it")


# ---------------------------------------------------------------- API
class ViewIn(BaseModel):
    name: str
    definition: dict
    is_public: bool = False


class ViewPatch(BaseModel):
    name: str | None = None
    definition: dict | None = None
    is_public: bool | None = None


@router.post("/projects/{project_id}/views")
def post_view(project_id: str, body: ViewIn) -> dict:
    from apm import config
    from apm.domains.members import check_project_write
    from apm.domains.projects import require_project

    require_project(project_id)
    actor = events.effective_actor()
    if config.settings.auth_mode != "local":
        allowed, _role = check_project_write(project_id, actor)
        if not allowed:
            raise HTTPException(status_code=403, detail="viewers cannot create views")
    _validate_definition_for_project(project_id, body.definition)
    vid = new_id("vw")
    events.emit(
        event_type="view.created",
        agg_type="view",
        agg_id=vid,
        project_id=project_id,
        payload={
            "name": body.name,
            "owner_id": actor,
            "is_public": body.is_public,
            "definition": json.dumps(body.definition, ensure_ascii=False, sort_keys=True),
        },
    )
    return get_view(vid)  # type: ignore[return-value]


@router.get("/projects/{project_id}/views")
def list_views(project_id: str) -> dict:
    """Readable views: local mode → all; network → public for members, private
    adds owner/admin-only rows (filtered out rather than 403, list semantics)."""
    from apm import config
    from apm.domains.members import is_instance_admin, member_role

    actor = events.effective_actor()
    rows = db.get_conn().execute(
        "SELECT * FROM saved_views WHERE project_id = ? ORDER BY name, created_at",
        (project_id,),
    ).fetchall()
    out = []
    for r in rows:
        v = dict(r)
        v["definition"] = json.loads(v["definition"])
        if config.settings.auth_mode != "local":
            admin = is_instance_admin(actor)
            role = member_role(project_id, actor)
            if not admin and role is None:
                raise HTTPException(status_code=403, detail="not a project member")
            if not v["is_public"] and v["owner_id"] != actor and not admin:
                continue
        out.append(v)
    return {"views": out}


@router.get("/views/{view_id}")
def get_view_detail(view_id: str) -> dict:
    v = require_view(view_id)
    _actor_can_read(v, events.effective_actor())
    return v


@router.patch("/views/{view_id}")
def patch_view(view_id: str, body: ViewPatch) -> dict:
    v = require_view(view_id)
    _require_view_writer(v, events.effective_actor())
    changes = {k: val for k, val in body.model_dump().items() if val is not None}
    if not changes:
        return v
    if "definition" in changes:
        _validate_definition_for_project(v["project_id"], changes["definition"])
        changes["definition"] = json.dumps(changes["definition"], ensure_ascii=False, sort_keys=True)
    events.emit(
        event_type="view.updated",
        agg_type="view",
        agg_id=view_id,
        project_id=v["project_id"],
        payload=changes,
    )
    return require_view(view_id)


@router.delete("/views/{view_id}")
def delete_view(view_id: str) -> dict:
    v = require_view(view_id)
    _require_view_writer(v, events.effective_actor())
    events.emit(
        event_type="view.deleted",
        agg_type="view",
        agg_id=view_id,
        project_id=v["project_id"],
        payload={"name": v["name"]},
    )
    return {"deleted": view_id}


@router.post("/views/{view_id}/make-default")
def make_default_view(view_id: str) -> dict:
    """Project-wide default: boards without an explicit view land here (I52)."""
    v = require_view(view_id)
    _actor_can_read(v, events.effective_actor())
    events.emit(
        event_type="view.made_default",
        agg_type="view",
        agg_id=view_id,
        project_id=v["project_id"],
        payload={},
    )
    return require_view(view_id)
