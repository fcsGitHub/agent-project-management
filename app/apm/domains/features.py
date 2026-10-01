"""Feature domain: the middle navigation layer (project → feature → conversation)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm.core import db, events
from apm.core.events import utcnow
from apm.core.ids import new_id
from apm.core.projections import on

router = APIRouter(tags=["features"])


# ------------------------------------------------------------ projections
@on("feature.created")
def _proj_feature_created(conn, e):
    p = e.payload
    conn.execute(
        "INSERT INTO features (id, project_id, title, brief, status, sort_order, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (
            e.agg_id,
            e.project_id,
            p.get("title", ""),
            p.get("brief"),
            p.get("status", "active"),
            p.get("sort_order", 0),
            e.ts,
            e.ts,
        ),
    )


@on("feature.updated")
def _proj_feature_updated(conn, e):
    p = e.payload
    sets, params = [], []
    for key in ("title", "brief", "status"):
        if key in p:
            sets.append(f"{key} = ?")
            params.append(p[key])
    if sets:
        sets.append("updated_at = ?")
        params.append(e.ts)
        params.append(e.agg_id)
        conn.execute(f"UPDATE features SET {', '.join(sets)} WHERE id = ?", params)


@on("feature.archived")
def _proj_feature_archived(conn, e):
    conn.execute(
        "UPDATE features SET status = 'archived', updated_at = ? WHERE id = ?", (e.ts, e.agg_id)
    )


# ---------------------------------------------------------------- helpers
def get_feature(feature_id: str) -> dict | None:
    row = db.get_conn().execute("SELECT * FROM features WHERE id = ?", (feature_id,)).fetchone()
    return dict(row) if row else None


def require_feature(feature_id: str) -> dict:
    f = get_feature(feature_id)
    if not f:
        raise HTTPException(status_code=404, detail=f"feature {feature_id} not found")
    return f


def create_feature(
    *,
    project_id: str,
    title: str,
    brief: str | None = None,
    actor_type: str = "human",
    actor_id: str | None = None,
    sort_order: int = 0,
) -> dict:
    fid = new_id("f")
    events.emit(
        event_type="feature.created",
        agg_type="feature",
        agg_id=fid,
        project_id=project_id,
        actor_type=actor_type,
        actor_id=actor_id,
        payload={"title": title, "brief": brief, "status": "active", "sort_order": sort_order},
    )
    return get_feature(fid)  # type: ignore[return-value]


# ------------------------------------------------------------------ models
class FeatureIn(BaseModel):
    title: str
    brief: str | None = None


class FeaturePatch(BaseModel):
    title: str | None = None
    brief: str | None = None
    status: str | None = None


@router.post("/projects/{project_id}/features")
def post_feature(project_id: str, body: FeatureIn) -> dict:
    from apm.domains.projects import require_project

    require_project(project_id)
    feature = create_feature(project_id=project_id, title=body.title, brief=body.brief)
    return feature


@router.get("/projects/{project_id}/features")
def list_features(project_id: str) -> dict:
    rows = db.get_conn().execute(
        "SELECT * FROM features WHERE project_id = ? AND status != 'archived'"
        " ORDER BY sort_order, created_at",
        (project_id,),
    ).fetchall()
    return {"features": [dict(r) for r in rows]}


@router.get("/features/{feature_id}")
def get_feature_detail(feature_id: str, include: str = "items,conversations,artifacts") -> dict:
    feature = require_feature(feature_id)
    includes = {s.strip() for s in include.split(",") if s.strip()}
    if "items" in includes:
        from apm.domains.items import list_items

        feature["items"] = list_items(project_id=feature["project_id"], feature_id=feature_id)
    if "conversations" in includes:
        from apm.domains.conversations import list_conversations

        feature["conversations"] = list_conversations(
            project_id=feature["project_id"], feature_id=feature_id
        )
    if "artifacts" in includes:
        from apm.content.artifacts import list_artifacts

        feature["artifacts"] = list_artifacts(feature["project_id"])
    return feature


@router.patch("/features/{feature_id}")
def patch_feature(feature_id: str, body: FeaturePatch) -> dict:
    feature = require_feature(feature_id)
    from apm.domains.members import require_project_write
    require_project_write(feature["project_id"])  # M80-I240
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    if not changes:
        return feature
    events.emit(
        event_type="feature.updated",
        agg_type="feature",
        agg_id=feature_id,
        project_id=feature["project_id"],
        payload=changes,
    )
    return get_feature(feature_id)  # type: ignore[return-value]


@router.post("/features/{feature_id}/archive")
def archive_feature(feature_id: str) -> dict:
    feature = require_feature(feature_id)
    from apm.domains.members import require_project_write
    require_project_write(feature["project_id"])  # M80-I240
    events.emit(
        event_type="feature.archived",
        agg_type="feature",
        agg_id=feature_id,
        project_id=feature["project_id"],
    )
    return get_feature(feature_id)  # type: ignore[return-value]
