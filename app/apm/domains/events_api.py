"""Event log query API + projection rebuild + NDJSON export/import (M13/M14)."""
from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

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
    from apm.domains.members import is_instance_admin

    if not is_instance_admin(events.effective_actor()):
        raise HTTPException(status_code=403, detail="admin role required for projection rebuild")
    projections.ensure_handlers_registered()
    n = projections.rebuild()
    from apm.domains.users import ensure_default_user

    ensure_default_user()  # 重建后恢复引导管理员（凭据/admin 列不进事件流）
    return {"status": "ok", "events_replayed": n}


@router.get("/projects/{project_id}/audit.csv")
def export_audit_csv(project_id: str, days: int = 90):
    """M41-I127 (docs/01 §AN.3, Jira native audit-CSV semantics): the audit
    page is for humans, the export is for auditors — admin-only, date-window
    filtered, full event stream as streaming CSV. The event stream IS the
    audit log (append-only), so this is a window over it, not a new ledger."""
    import csv
    import io
    from datetime import timedelta

    from apm.domains.members import is_instance_admin
    from apm.domains.projects import require_project

    if not is_instance_admin(events.effective_actor()):
        raise HTTPException(status_code=403, detail="admin role required for audit export")
    require_project(project_id)
    days = max(1, min(days, 3650))
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT id, ts, actor_type, actor_id, event_type, agg_type, agg_id, payload"
        " FROM events WHERE project_id = ? AND substr(ts, 1, 10) >= ? ORDER BY id",
        (project_id, cutoff)).fetchall()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "ts", "actor_type", "actor_id", "event_type",
                     "agg_type", "agg_id", "payload"])
    for r in rows:
        writer.writerow([r["id"], r["ts"], r["actor_type"], r["actor_id"],
                         r["event_type"], r["agg_type"], r["agg_id"],
                         r["payload"][:200]])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="audit-{project_id}.csv"'},
    )


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


class ImportIn(BaseModel):
    """NDJSON payload exactly as produced by /events/export (M14-I45)."""
    data: str


@router.post("/projects/{project_id}/events/import")
def import_events(project_id: str, body: ImportIn) -> dict:
    """Restore a per-project event export (docs/01 §M.3). Integrity rests on
    the export checksum (raw-line sha256) and monotonic ids; ids must be free
    in the target database (any conflict → 409 — restore targets an empty/new
    instance, same pragmatism as GitLab's version compatibility window).
    Imported events re-chain onto the target's global log head, then a full
    rebuild re-folds every projection (live == replay re-established)."""
    conn = db.get_conn()
    exists = conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not exists and '"project.created"' not in body.data:
        # restore into an empty database is the supported scenario — the
        # payload must carry the project's own creation event
        raise HTTPException(status_code=422,
                            detail="target project does not exist and payload lacks its project.created")

    lines = [l for l in body.data.splitlines() if l.strip()]
    if len(lines) < 2:
        raise HTTPException(status_code=422, detail="payload must contain event lines and a checksum line")
    try:
        checksum = json.loads(lines[-1]).get("checksum_line")
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="checksum line is not valid JSON")
    if not isinstance(checksum, dict):
        raise HTTPException(status_code=422, detail="missing checksum line")

    digest = hashlib.sha256()
    parsed: list[dict] = []
    for raw in lines[:-1]:
        digest.update(raw.encode())
        try:
            ev = json.loads(raw)
        except json.JSONDecodeError:
            raise HTTPException(status_code=422, detail=f"invalid NDJSON line: {raw[:60]}")
        for key in ("id", "ts", "event_type", "agg_type", "agg_id", "project_id",
                    "actor_type", "actor_id", "payload", "prev_event_id"):
            if key not in ev:
                raise HTTPException(status_code=422, detail=f"event missing field '{key}'")
        if ev["project_id"] != project_id:
            raise HTTPException(status_code=422,
                                detail=f"event {ev['id']} belongs to project '{ev['project_id']}'")
        if parsed and ev["id"] <= parsed[-1]["id"]:
            raise HTTPException(status_code=422, detail="event ids must strictly increase")
        parsed.append(ev)
    if checksum.get("events") != len(parsed) or checksum.get("sha256") != digest.hexdigest():
        raise HTTPException(status_code=422, detail="checksum mismatch — export integrity cannot be verified")

    conflicts = conn.execute(
        f"SELECT COUNT(*) c FROM events WHERE id IN ({','.join('?' * len(parsed))})",
        [e["id"] for e in parsed],
    ).fetchone()["c"]
    if conflicts:
        raise HTTPException(status_code=409,
                            detail=f"{conflicts} event id(s) already exist — restore requires an empty/new database")

    with db.tx() as tx:
        head = tx.execute("SELECT id FROM events ORDER BY id DESC LIMIT 1").fetchone()
        prev_id = head["id"] if head else 0
        for ev in parsed:
            tx.execute(
                "INSERT INTO events (id, ts, actor_type, actor_id, project_id, agg_type,"
                " agg_id, event_type, payload, prev_event_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (ev["id"], ev["ts"], ev["actor_type"], ev["actor_id"], project_id,
                 ev["agg_type"], ev["agg_id"], ev["event_type"],
                 json.dumps(ev["payload"], ensure_ascii=False), prev_id),
            )
            prev_id = ev["id"]

    projections.ensure_handlers_registered()
    rebuilt = projections.rebuild()
    return {"imported": len(parsed), "rebuilt": rebuilt}
