"""Work-item comments (M18-I56): event-sourced comment threads with @mention
→ notification (Plane/GitLab semantics, docs/01 §Q.1) and a participation
projection — commenting, being assigned, or being mentioned makes a user a
participant, the audience for later item-event notifications (I58).

Mentions are resolved against users.name with exact `@<name>` substring
matching (longest first), so multi-word names like "QA 王" work."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on

router = APIRouter(tags=["comments"])


# ------------------------------------------------------------ projections
@on("comment.created")
def _proj_comment_created(conn, e):
    p = e.payload
    conn.execute(
        "INSERT INTO item_comments (id, item_id, project_id, author_id, body, mentions,"
        " created_at) VALUES (?,?,?,?,?,?,?)",
        (e.agg_id, e.payload.get("item_id"), e.project_id, p["author_id"],
         p["body"], p.get("mentions_json", "[]"), e.ts),
    )
    _join_participants(conn, e.project_id, e.payload.get("item_id"),
                       [(p["author_id"], "author")] +
                       [(u, "mentioned") for u in json.loads(p.get("mentions_json", "[]"))])


@on("comment.deleted")
def _proj_comment_deleted(conn, e):
    conn.execute("UPDATE item_comments SET deleted_at = ? WHERE id = ?", (e.ts, e.agg_id))


@on("comment.participant")
def _proj_comment_participant(conn, e):
    p = e.payload
    _join_participants(conn, e.project_id, e.agg_id,
                       [(p["user_id"], p.get("source", "watch"))])


@on("item.assigned")
def _proj_assignee_participant(conn, e):
    p = e.payload
    if p.get("assignee_type") == "human" and p.get("assignee_id"):
        _join_participants(conn, e.project_id, e.agg_id, [(p["assignee_id"], "assignee")])


def _join_participants(conn, project_id, item_id, pairs):
    for user_id, source in pairs:
        if not user_id or not item_id:
            continue
        conn.execute(
            "INSERT INTO item_participants (item_id, project_id, user_id, source, created_at)"
            " VALUES (?,?,?,?,?)"
            " ON CONFLICT(item_id, user_id) DO NOTHING",
            (item_id, project_id, user_id, source, events.utcnow()),
        )


# ---------------------------------------------------------------- helpers
def _parse_mentions(body: str) -> list[tuple[str, str]]:
    """`@<name>` exact matches against users.name, longest name first.
    Returns (user_id, name) pairs in first-mention order, self excluded later."""
    rows = db.get_conn().execute("SELECT id, name FROM users ORDER BY LENGTH(name) DESC").fetchall()
    found: list[tuple[str, str]] = []
    rest = body
    for r in rows:
        token = f"@{r['name']}"
        if token in rest:
            found.append((r["id"], r["name"]))
            rest = rest.replace(token, "")
    return found


def _require_item(item_id: str) -> dict:
    row = db.get_conn().execute(
        "SELECT id, project_id, assignee_id FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"unknown item '{item_id}'")
    return dict(row)


def _gate(project_id: str) -> None:
    """local mode trusted; network mode requires any project membership."""
    from apm import config
    from apm.domains.members import member_role
    if config.settings.auth_mode == "local":
        return
    if member_role(project_id, events.effective_actor()) is None:
        raise HTTPException(status_code=403, detail="not a project member")


# ---------------------------------------------------------------- API
class CommentIn(BaseModel):
    body: str


@router.post("/items/{item_id}/comments")
def post_comment(item_id: str, body: CommentIn) -> dict:
    item = _require_item(item_id)
    _gate(item["project_id"])
    author = events.effective_actor()
    mentions = [(uid, name) for uid, name in _parse_mentions(body.body) if uid != author]
    author_row = db.get_conn().execute(
        "SELECT name FROM users WHERE id = ?", (author,)).fetchone()
    author_name = author_row["name"] if author_row else author
    cid = new_id("cm")
    events.emit(
        event_type="comment.created",
        agg_type="comment",
        agg_id=cid,
        project_id=item["project_id"],
        payload={
            "item_id": item_id,
            "author_id": author,
            "body": body.body,
            "mentions_json": json.dumps([u for u, _ in mentions]),
            "author_name": author_name,
        },
    )
    # mention notifications ride the existing M10 channel (inbox + mailer)
    item_ref = f"{item_id}"
    for uid, name in mentions:
        events.emit(
            event_type="notification.sent",
            agg_type="item",
            agg_id=item_id,
            project_id=item["project_id"],
            payload={"user_id": uid, "kind": "mention",
                     "summary": f"{author_name} 在工作项 {item_ref} 的评论中提到了你"},
        )
    return get_comment(cid)


@router.get("/items/{item_id}/comments")
def list_comments(item_id: str) -> dict:
    item = _require_item(item_id)
    _gate(item["project_id"])
    rows = db.get_conn().execute(
        "SELECT * FROM item_comments WHERE item_id = ? AND deleted_at IS NULL ORDER BY created_at",
        (item_id,),
    ).fetchall()
    participants = db.get_conn().execute(
        "SELECT user_id, source FROM item_participants WHERE item_id = ? ORDER BY created_at",
        (item_id,),
    ).fetchall()
    return {"comments": [dict(r) for r in rows],
            "participants": [dict(r) for r in participants]}


def get_comment(comment_id: str) -> dict:
    row = db.get_conn().execute(
        "SELECT * FROM item_comments WHERE id = ?", (comment_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"unknown comment '{comment_id}'")
    return dict(row)


@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: str) -> dict:
    c = get_comment(comment_id)
    from apm import config
    from apm.domains.members import is_instance_admin
    actor = events.effective_actor()
    if config.settings.auth_mode != "local" and actor != c["author_id"] \
            and not is_instance_admin(actor):
        raise HTTPException(status_code=403, detail="only the author or an admin can delete")
    events.emit(
        event_type="comment.deleted",
        agg_type="comment",
        agg_id=comment_id,
        project_id=c["project_id"],
        payload={"item_id": c["item_id"]},
    )
    return {"deleted": comment_id}
