"""Event log query API + projection rebuild."""
from __future__ import annotations

from fastapi import APIRouter, Query

from apm.core import events, projections

router = APIRouter(tags=["events"])


@router.get("/events")
def list_events(
    project_id: str | None = None,
    agg_type: str | None = None,
    agg_id: str | None = None,
    event_type: str | None = None,
    actor_type: str | None = None,
    actor_id: str | None = None,
    since_id: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict:
    projections.ensure_handlers_registered()
    evts, total = events.query_events(
        project_id=project_id,
        agg_type=agg_type,
        agg_id=agg_id,
        event_type=event_type,
        actor_type=actor_type,
        actor_id=actor_id,
        since_id=since_id,
        limit=limit,
        offset=offset,
    )
    return {"events": [e.as_dict() for e in evts], "total": total}


@router.post("/system/rebuild-projections")
def rebuild_projections() -> dict:
    projections.ensure_handlers_registered()
    n = projections.rebuild()
    return {"status": "ok", "events_replayed": n}
