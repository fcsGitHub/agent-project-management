"""Event log query API + projection rebuild + NDJSON export (M13-I43)."""
from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from apm.core import db, events, projections

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


@router.get("/projects/{project_id}/events/export")
def export_events(project_id: str) -> StreamingResponse:
    """Supplementary data exit (docs/01 §L.3 — GitLab lesson: exports are a
    supplement, not a backup). Streams the project's event log as NDJSON in
    append order, each line carrying its prev_event_id so the receiver can
    verify chain continuity; a final checksum line covers the whole stream."""
    conn = db.get_conn()
    if not conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone():
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"unknown project '{project_id}'")

    def gen():
        rows = conn.execute(
            "SELECT * FROM events WHERE project_id = ? ORDER BY id ASC", (project_id,)
        ).fetchall()
        digest = hashlib.sha256()
        count = 0
        first_prev = None
        last_id = None
        broken = 0
        for row in rows:
            d = dict(row)
            line = {
                "id": d["id"],
                "ts": d["ts"],
                "event_type": d["event_type"],
                "agg_type": d["agg_type"],
                "agg_id": d["agg_id"],
                "project_id": d["project_id"],
                "actor_type": d["actor_type"],
                "actor_id": d["actor_id"],
                "payload": json.loads(d["payload"] or "{}"),
                "prev_event_id": d.get("prev_event_id"),
            }
            # prev_event_id links into the GLOBAL append-only log; a per-project
            # export may legitimately start mid-chain or skip other projects'
            # events, so gaps are expected — only order and self-links matter.
            if count == 0:
                first_prev = d.get("prev_event_id")
            elif d.get("prev_event_id") != last_id:
                broken += 1
            last_id = d["id"]
            count += 1
            data = json.dumps(line, ensure_ascii=False)
            digest.update(data.encode())
            yield data + "\n"
        yield json.dumps({
            "checksum_line": {"events": count, "sha256": digest.hexdigest(),
                              "first_prev_event_id": first_prev, "gaps": broken},
        }, ensure_ascii=False) + "\n"

    return StreamingResponse(
        gen(),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="events-{project_id}.ndjson"'},
    )
