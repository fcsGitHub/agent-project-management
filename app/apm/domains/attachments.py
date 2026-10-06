"""Item attachments (M40-I123, docs/01 §AM.2, Redmine files/-directory
semantics): binaries live on disk under data_dir/attachments/{project_id}/,
only metadata is projected — the attachments table sits in drop_projections
so a rebuild reproduces every row from the events, while the files themselves
stay outside the event stream (same split as the artifacts git repo). Upload
is multipart with a conservative per-file ceiling (Jira DC's 10 MB default);
delete is a soft removal — the disk file survives, only the metadata row is
flagged removed."""
from __future__ import annotations

import re

from fastapi import APIRouter, File, HTTPException, UploadFile

from apm import config
from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on
from apm.domains.items import require_item

router = APIRouter(tags=["attachments"])


# ---------------------------------------------------------------- projectors
@on("item.attachment_added")
def _proj_attachment_added(conn, e):
    p = e.payload
    conn.execute(
        "INSERT INTO attachments (id, project_id, item_id, filename, size, mime,"
        " stored_path, uploader, created_at, removed_at) VALUES (?,?,?,?,?,?,?,?,?,NULL)"
        " ON CONFLICT(id) DO NOTHING",
        (e.agg_id, e.project_id, p["item_id"], p["filename"], p["size"], p.get("mime"),
         p["stored_path"], p.get("uploader"), e.ts),
    )


@on("item.attachment_removed")
def _proj_attachment_removed(conn, e):
    conn.execute(
        "UPDATE attachments SET removed_at = ? WHERE id = ?", (e.ts, e.agg_id))


# ---------------------------------------------------------------- helpers
_SAFE = re.compile(r"[^\w.\-]+")


def _store_path(project_id: str, attachment_id: str, filename: str):
    safe = _SAFE.sub("_", filename)[-80:] or "file.bin"
    directory = config.settings.data_dir / "attachments" / project_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{attachment_id}_{safe}"


# ---------------------------------------------------------------- endpoints
@router.get("/items/{item_id}/attachments")
def list_attachments(item_id: str) -> dict:
    item = require_item(item_id)
    from apm.domains.members import require_project_read

    require_project_read(item["project_id"])  # M114-I339: 读面文件元数据也是项目数据
    rows = db.get_conn().execute(
        "SELECT id, filename, size, mime, uploader, created_at FROM attachments"
        " WHERE item_id = ? AND removed_at IS NULL ORDER BY id", (item_id,)).fetchall()
    return {"attachments": [dict(r) for r in rows]}


@router.post("/items/{item_id}/attachments")
async def add_attachment(item_id: str, file: UploadFile = File(...)) -> dict:
    item = require_item(item_id)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="empty file")
    limit = config.settings.attachment_max_mb * 1024 * 1024
    if len(data) > limit:
        raise HTTPException(
            status_code=413,
            detail=f"file exceeds the {config.settings.attachment_max_mb} MB attachment limit")
    aid = new_id("at")
    filename = file.filename or "file.bin"
    # I130 extension allowlist (Jira 9.15 semantics): empty config = all allowed
    allowed = [e.strip().lower().lstrip(".") for e in
               (config.settings.attachment_allowed_ext or "").split(",") if e.strip()]
    if allowed:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in allowed:
            raise HTTPException(
                status_code=415,
                detail=f"file type .{ext} is not allowed (allowed: {', '.join(allowed)})")
    stored = _store_path(item["project_id"], aid, filename)
    stored.write_bytes(data)
    events.emit(
        event_type="item.attachment_added", agg_type="attachment", agg_id=aid,
        project_id=item["project_id"], actor_type="human",
        actor_id=events.effective_actor(),
        payload={"item_id": item_id, "filename": filename, "size": len(data),
                 "mime": file.content_type, "uploader": events.effective_actor(),
                 "stored_path": str(stored.relative_to(config.settings.data_dir))},
    )
    return {"id": aid, "filename": filename, "size": len(data), "mime": file.content_type}


@router.get("/items/{item_id}/attachments/{attachment_id}")
def download_attachment(item_id: str, attachment_id: str):
    item = require_item(item_id)
    from apm.domains.members import require_project_read

    require_project_read(item["project_id"])  # M114-I339: 文件本体不得跨项目下载
    row = db.get_conn().execute(
        "SELECT filename, stored_path FROM attachments"
        " WHERE id = ? AND item_id = ? AND removed_at IS NULL",
        (attachment_id, item_id)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="no such attachment")
    path = config.settings.data_dir / row["stored_path"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="attachment file missing on disk")
    from fastapi.responses import FileResponse
    return FileResponse(path, filename=row["filename"])


@router.delete("/items/{item_id}/attachments/{attachment_id}")
def remove_attachment(item_id: str, attachment_id: str) -> dict:
    require_item(item_id)
    row = db.get_conn().execute(
        "SELECT id, filename, project_id FROM attachments"
        " WHERE id = ? AND item_id = ? AND removed_at IS NULL",
        (attachment_id, item_id)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="no such attachment")
    events.emit(
        event_type="item.attachment_removed", agg_type="attachment", agg_id=attachment_id,
        project_id=row["project_id"], actor_type="human",
        actor_id=events.effective_actor(),
        payload={"item_id": item_id, "filename": row["filename"]},
    )
    return {"removed": attachment_id}
