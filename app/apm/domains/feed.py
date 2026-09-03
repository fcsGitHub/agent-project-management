"""Atom subscription feeds (M11-I36): per-user feed keys let any reader follow
a project's event stream without a cookie (Redmine pattern, docs/01 §J.2).
Feed output is filtered by the key owner's visibility — Redmine once leaked
private projects into a global feed (#20173); here visibility is computed from
project membership for every request. The feed key is user runtime state
(viewable/rotatable by the owner, like webhook secrets)."""
from __future__ import annotations

import secrets as pysecrets
import xml.sax.saxutils as sx

from fastapi import APIRouter, HTTPException, Response

from apm import config
from apm.core import db, events
from apm.domains.members import ROLES, is_instance_admin, member_role

router = APIRouter(tags=["feed"])


def _user_by_feed_key(key: str):
    if not key:
        return None
    return db.get_conn().execute(
        "SELECT * FROM users WHERE feed_key = ?", (key,)).fetchone()


def _user_row(user_id: str):
    return db.get_conn().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


@router.get("/me/feed-key")
def get_feed_key() -> dict:
    """The caller's own feed key (generated on first view), plus ready-made URLs."""
    user_id = events.effective_actor()
    row = _user_row(user_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"unknown user '{user_id}'")
    key = row["feed_key"]
    created = False
    if not key:
        key = pysecrets.token_hex(20)
        conn = db.get_conn()
        conn.execute("UPDATE users SET feed_key = ? WHERE id = ?", (key, user_id))
        conn.commit()
        created = True
    return {"user_id": user_id, "feed_key": key, "created": created}


@router.post("/me/feed-key/rotate")
def rotate_feed_key() -> dict:
    user_id = events.effective_actor()
    key = pysecrets.token_hex(20)
    conn = db.get_conn()
    conn.execute("UPDATE users SET feed_key = ? WHERE id = ?", (key, user_id))
    conn.commit()
    return {"user_id": user_id, "feed_key": key}


def _visible(project_id: str, user) -> bool:
    """Membership-based visibility (#20173 lesson): admins see all; users must
    hold a project role; in local mode the single configured user is implicit."""
    if is_instance_admin(user["id"]):
        return True
    if member_role(project_id, user["id"]) in ROLES:
        return True
    return config.settings.auth_mode == "local" and user["id"] == config.settings.user_id


@router.get("/projects/{project_id}/feed.atom")
def project_feed(project_id: str, key: str, response: Response) -> Response:
    user = _user_by_feed_key(key)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid feed key")
    if not _visible(project_id, user):
        events.emit(
            event_type="access.denied", agg_type="project", agg_id=project_id,
            project_id=project_id, actor_type="human", actor_id=user["id"],
            payload={"user_id": user["id"], "path": f"/api/projects/{project_id}/feed.atom",
                     "summary": f"feed 订阅被拒绝：{user['id']} @ {project_id}"},
        )
        raise HTTPException(status_code=403, detail="forbidden")
    evs, _ = events.query_events(project_id=project_id, limit=30)
    project_name = db.get_conn().execute(
        "SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone()
    feed_updated = evs[0].ts if evs else ""
    entries = []
    for e in evs:
        title = sx.escape(f"#{e.id} {e.event_type} {e.payload.get('title') or e.payload.get('summary') or ''}".strip())
        entries.append(
            f"  <entry>\n"
            f"    <id>urn:apm:event/{project_id}/{e.id}</id>\n"
            f"    <title>{title}</title>\n"
            f"    <updated>{e.ts}</updated>\n"
            f"    <author><name>{sx.escape(e.actor_id)}</name></author>\n"
            f"    <content type=\"text\">{sx.escape(json_brief(e.payload))}</content>\n"
            f"  </entry>"
        )
    xml = (
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n"
        "<feed xmlns=\"http://www.w3.org/2005/Atom\">\n"
        f"  <id>urn:apm:project/{project_id}</id>\n"
        f"  <title>{sx.escape(project_name['name'] if project_name else project_id)}</title>\n"
        + (f"  <updated>{feed_updated}</updated>\n" if feed_updated else "")
        + "\n".join(entries) + "\n</feed>"
    )
    response.media_type = "application/atom+xml"
    return Response(content=xml, media_type="application/atom+xml")


def json_brief(payload: dict) -> str:
    parts = []
    for k in ("title", "status", "path", "summary", "to"):
        if payload.get(k):
            parts.append(f"{k}: {payload[k]}")
    return "; ".join(parts) if parts else ""
