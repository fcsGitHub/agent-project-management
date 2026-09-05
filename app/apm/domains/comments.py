"""Work-item comments (M18-I56): event-sourced comment threads with @mention
→ notification (Plane/GitLab semantics, docs/01 §Q.1) and a participation
projection — commenting, being assigned, or being mentioned makes a user a
participant, the audience for later item-event notifications (I58).

Mentions are resolved against users.name with exact `@<name>` substring
matching (longest first), so multi-word names like "QA 王" work."""
from __future__ import annotations

import json
import re

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


@on("comment.updated")
def _proj_comment_updated(conn, e):
    """Edit (M26-I81): the *previous* body lands in comment_revisions (row id
    derived from the event id — projection ids must be deterministic), then the
    comment row gets the new body, refreshed mentions and an edited_at stamp.
    New mentions join the participant audience but never re-notify (edit noise
    suppression)."""
    p = e.payload
    conn.execute(
        "INSERT INTO comment_revisions (id, comment_id, project_id, body, edited_by, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (f"cr_{e.id}", e.agg_id, e.project_id, p["old_body"], p["editor_id"], e.ts),
    )
    conn.execute(
        "UPDATE item_comments SET body = ?, mentions = ?, edited_at = ? WHERE id = ?",
        (p["body"], p.get("mentions_json", "[]"), e.ts, e.agg_id),
    )
    _join_participants(conn, e.project_id, p.get("item_id"),
                       [(u, "mentioned") for u in json.loads(p.get("mentions_json", "[]"))])


@on("comment.participant")
def _proj_comment_participant(conn, e):
    p = e.payload
    _join_participants(conn, e.project_id, e.agg_id,
                       [(p["user_id"], p.get("source", "watch"))])


@on("item.subscribed")
def _proj_subscribed(conn, e):
    _join_participants(conn, e.project_id, e.agg_id,
                       [(e.payload["user_id"], "watch")])


@on("item.unsubscribed")
def _proj_unsubscribed(conn, e):
    # only a manual watch is removable: assignee/author/mentioned participation
    # is derived from history and would come back on rebuild anyway
    conn.execute(
        "DELETE FROM item_participants WHERE item_id = ? AND user_id = ? AND source = 'watch'",
        (e.agg_id, e.payload["user_id"]),
    )


@on("item.assigned")
def _proj_assignee_participant(conn, e):
    p = e.payload
    if p.get("assignee_type") == "human" and p.get("assignee_id"):
        _join_participants(conn, e.project_id, e.agg_id, [(p["assignee_id"], "assignee")])


@on("comment.task_extracted")
def _proj_task_extracted(conn, e):
    p = e.payload
    conn.execute(
        "INSERT INTO extracted_tasks (id, comment_id, project_id, text, item_id, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (e.agg_id, p["comment_id"], e.project_id, p["text"], p["item_id"], e.ts),
    )


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
        "SELECT id, project_id, assignee_id, title FROM items WHERE id = ?", (item_id,)).fetchone()
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
    # mention notifications ride the existing M10 channel (inbox + mailer);
    # the summary carries the item title (id as fallback) so the inbox is readable
    item_ref = f"「{item['title']}」" if item.get("title") else item_id
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
        "SELECT c.*, u.name AS author_name FROM item_comments c"
        " LEFT JOIN users u ON u.id = c.author_id"
        " WHERE c.item_id = ? AND c.deleted_at IS NULL ORDER BY c.created_at",
        (item_id,),
    ).fetchall()
    participants = db.get_conn().execute(
        "SELECT user_id, source FROM item_participants WHERE item_id = ? ORDER BY created_at",
        (item_id,),
    ).fetchall()
    extracted = db.get_conn().execute(
        "SELECT e.comment_id, e.text, e.item_id, i.title AS item_title"
        " FROM extracted_tasks e JOIN items i ON i.id = e.item_id"
        " WHERE e.comment_id IN (SELECT id FROM item_comments WHERE item_id = ?)",
        (item_id,),
    ).fetchall()
    return {"comments": [dict(r) for r in rows],
            "participants": [dict(r) for r in participants],
            "extracted": [dict(r) for r in extracted]}


def get_comment(comment_id: str) -> dict:
    row = db.get_conn().execute(
        "SELECT c.*, u.name AS author_name FROM item_comments c"
        " LEFT JOIN users u ON u.id = c.author_id"
        " WHERE c.id = ?", (comment_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"unknown comment '{comment_id}'")
    return dict(row)


@router.patch("/comments/{comment_id}")
def edit_comment(comment_id: str, body: CommentIn) -> dict:
    """Edit own comment (M26-I81): author-only (stricter than delete — no
    admin override). The old body is preserved as a revision via the
    comment.updated event; new mentions join the audience without re-notifying."""
    c = get_comment(comment_id)
    if c["deleted_at"]:
        raise HTTPException(status_code=404, detail=f"unknown comment '{comment_id}'")
    if events.effective_actor() != c["author_id"]:
        raise HTTPException(status_code=403, detail="only the author can edit a comment")
    new_body = body.body.strip()
    if not new_body:
        raise HTTPException(status_code=422, detail="comment body must not be empty")
    editor = events.effective_actor()
    editor_row = db.get_conn().execute(
        "SELECT name FROM users WHERE id = ?", (editor,)).fetchone()
    editor_name = editor_row["name"] if editor_row else editor
    mentions = [(uid, name) for uid, name in _parse_mentions(new_body) if uid != editor]
    events.emit(
        event_type="comment.updated",
        agg_type="comment",
        agg_id=comment_id,
        project_id=c["project_id"],
        payload={
            "item_id": c["item_id"],
            "body": new_body,
            "old_body": c["body"],
            "editor_id": editor,
            "editor_name": editor_name,
            "mentions_json": json.dumps([u for u, _ in mentions]),
        },
    )
    return get_comment(comment_id)


@router.get("/comments/{comment_id}/revisions")
def list_comment_revisions(comment_id: str) -> dict:
    """Revision history (Redmine comment_edit_history plugin semantics, native
    here): each edit's previous body with editor and timestamp, newest first."""
    c = get_comment(comment_id)
    _gate(c["project_id"])
    rows = db.get_conn().execute(
        "SELECT r.*, u.name AS editor_name FROM comment_revisions r"
        " LEFT JOIN users u ON u.id = r.edited_by"
        " WHERE r.comment_id = ? ORDER BY r.rowid DESC",
        (comment_id,),
    ).fetchall()
    return {"comment_id": comment_id, "revisions": [dict(r) for r in rows]}


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


@router.post("/items/{item_id}/subscription")
def subscribe_item(item_id: str) -> dict:
    """Manual watch (M18-I58): the actor joins the item's participant audience
    until they unsubscribe. assignee/author/mentioned participation is derived
    and unaffected."""
    item = _require_item(item_id)
    _gate(item["project_id"])
    user_id = events.effective_actor()
    events.emit(
        event_type="item.subscribed",
        agg_type="item",
        agg_id=item_id,
        project_id=item["project_id"],
        payload={"user_id": user_id},
    )
    return {"item_id": item_id, "user_id": user_id, "subscribed": True}


@router.delete("/items/{item_id}/subscription")
def unsubscribe_item(item_id: str) -> dict:
    item = _require_item(item_id)
    _gate(item["project_id"])
    user_id = events.effective_actor()
    events.emit(
        event_type="item.unsubscribed",
        agg_type="item",
        agg_id=item_id,
        project_id=item["project_id"],
        payload={"user_id": user_id},
    )
    return {"item_id": item_id, "user_id": user_id, "subscribed": False}


# ------------------------------------------------------------ extraction (I67)
_TASK_LINE = re.compile(r"^\s*[-*]\s+\[[ xX]\]\s+(.+?)\s*$")


class ExtractIn(BaseModel):
    text: str
    concept_id: str = "task"


@router.post("/comments/{comment_id}/extract-task")
def extract_task(comment_id: str, body: ExtractIn) -> dict:
    """Turn a task-list item of a comment into a real work item (M21-I67,
    GitHub tasklist→sub-issue semantics: the text is *extracted*, the stored
    comment body stays byte-identical — comments are not a status carrier)."""
    c = get_comment(comment_id)
    item = _require_item(c["item_id"])
    _gate(item["project_id"])
    text = body.text.strip()
    task_texts = [m.group(1) for line in c["body"].splitlines()
                  if (m := _TASK_LINE.match(line))]
    if text not in task_texts:
        raise HTTPException(status_code=422, detail="text is not a task-list item of this comment")
    dup = db.get_conn().execute(
        "SELECT 1 FROM extracted_tasks WHERE comment_id = ? AND text = ?",
        (comment_id, text)).fetchone()
    if dup:
        raise HTTPException(status_code=409, detail="this task-list item was already extracted")

    from apm.domains.items import create_item
    created = create_item(project_id=item["project_id"], concept_id=body.concept_id, title=text)
    extraction_id = new_id("et")
    events.emit(
        event_type="comment.task_extracted",
        agg_type="comment_extraction",
        agg_id=extraction_id,
        project_id=item["project_id"],
        payload={"comment_id": comment_id, "item_id": created["id"], "text": text},
    )
    return {"extraction_id": extraction_id, "item": created, "text": text}
