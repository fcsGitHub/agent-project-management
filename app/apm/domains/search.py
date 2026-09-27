"""Global search (M22-I68, docs/01 §U.1): FTS5 index over item titles (plus
custom-field text) and comment bodies so any content is findable from ⌘K
(OpenProject global-search semantics). Chinese is indexed as character bigrams
(same scheme as the asset index, docs/09 §5 — SQLite FTS5 has no CJK
tokenizer). These handlers are registered AFTER the items/comments projectors
(import order in domains/__init__), so each event first updates the projection
row this module then reads — live appends and rebuilds stay identical."""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, HTTPException

from apm.core import db, events
from apm.core.projections import on
from apm.domains.assets import _bigrams

router = APIRouter(tags=["search"])


def _reindex_item(conn, item_id: str) -> None:
    row = conn.execute("SELECT title, custom_fields FROM items WHERE id = ?", (item_id,)).fetchone()
    conn.execute("DELETE FROM items_search WHERE item_id = ?", (item_id,))
    if row is None:
        return
    cf_text = " ".join(str(v) for v in _cf_values(row["custom_fields"]))
    conn.execute("INSERT INTO items_search (item_id, text) VALUES (?, ?)",
                 (item_id, _bigrams(f"{row['title']} {cf_text}")))


def _cf_values(custom_fields) -> list[str]:
    if not custom_fields:
        return []
    try:
        data = json.loads(custom_fields)
    except (TypeError, ValueError):
        return []
    return [v for v in data.values() if isinstance(v, (str, int, float, bool))]


def _reindex_comment(conn, comment_id: str) -> None:
    row = conn.execute(
        "SELECT body, deleted_at FROM item_comments WHERE id = ?", (comment_id,)).fetchone()
    conn.execute("DELETE FROM comments_search WHERE comment_id = ?", (comment_id,))
    if row is None or row["deleted_at"] is not None:
        return
    conn.execute("INSERT INTO comments_search (comment_id, text) VALUES (?, ?)",
                 (comment_id, _bigrams(row["body"])))


# registered after items/comments projectors → reads fresh projection rows
@on("item.created", "item.updated")
def _proj_search_item(conn, e):
    _reindex_item(conn, e.agg_id)


@on("comment.created", "comment.deleted")
def _proj_search_comment(conn, e):
    _reindex_comment(conn, e.agg_id)


def _reindex_message(conn, message_id: str) -> None:
    # M61-I184: conversations register before this module, so the messages row
    # is fresh when this runs (live appends and rebuild replay share the order).
    row = conn.execute(
        "SELECT content FROM messages WHERE id = ?", (message_id,)).fetchone()
    conn.execute("DELETE FROM messages_search WHERE message_id = ?", (message_id,))
    if row is None:
        return
    conn.execute("INSERT INTO messages_search (message_id, text) VALUES (?, ?)",
                 (message_id, _bigrams(row["content"])))


@on("message.created")
def _proj_search_message(conn, e):
    _reindex_message(conn, e.agg_id)


@router.get("/search")
def search(q: str, types: str = "items,comments") -> dict:
    """Cross-project keyword search, scoped to the caller's visible projects
    (`_visible`, same裁剪 as the Atom/iCal feeds). Empty query → 422.
    M61-I184 adds `conversations`: message bodies (forgotten-conversation
    problem, docs/01 §BF.3 — ChatGPT/Claude sidebar search matches titles
    only; the event stream already holds every message, so indexing it is
    event-sourcing dividend #13)."""
    query = q.strip()
    if not query:
        raise HTTPException(status_code=422, detail="q must not be empty")
    wanted = {t.strip() for t in types.split(",") if t.strip()} & {"items", "comments", "conversations"}
    if not wanted:
        raise HTTPException(status_code=422, detail="types must include items and/or comments")
    me = events.effective_actor()
    user = db.get_conn().execute("SELECT * FROM users WHERE id = ?", (me,)).fetchone()
    if user is None:
        raise HTTPException(status_code=404, detail=f"unknown user '{me}'")
    from apm.domains.feed import _visible
    from apm.domains.projects import can_see_concept

    match = _bigrams(query)
    conn = db.get_conn()
    out: dict[str, list] = {"items": [], "comments": [], "conversations": []}
    if "items" in wanted:
        for r in conn.execute(
            "SELECT item_id FROM items_search WHERE items_search MATCH ? ORDER BY rank LIMIT 50",
            (match,),
        ).fetchall():
            row = conn.execute(
                "SELECT i.id, i.title, i.status, i.status_group, i.concept_id,"
                " i.project_id, p.name AS project_name FROM items i"
                " JOIN projects p ON p.id = i.project_id WHERE i.id = ?",
                (r["item_id"],),
            ).fetchone()
            if row and _visible(row["project_id"], user) \
                    and can_see_concept(row["project_id"], row["concept_id"], user["id"]):
                out["items"].append(dict(row))
    if "comments" in wanted:
        for r in conn.execute(
            "SELECT comment_id FROM comments_search WHERE comments_search MATCH ?"
            " ORDER BY rank LIMIT 50",
            (match,),
        ).fetchall():
            row = conn.execute(
                "SELECT c.id, c.body, c.item_id, c.project_id, i.title AS item_title,"
                " i.concept_id AS item_concept_id,"
                " p.name AS project_name FROM item_comments c"
                " JOIN items i ON i.id = c.item_id"
                " JOIN projects p ON p.id = c.project_id"
                " WHERE c.id = ? AND c.deleted_at IS NULL",
                (r["comment_id"],),
            ).fetchone()
            if row and _visible(row["project_id"], user) \
                    and can_see_concept(row["project_id"], row["item_concept_id"], user["id"]):
                out["comments"].append({k: v for k, v in dict(row).items()
                                        if k != "item_concept_id"})
    if "conversations" in wanted:
        for r in conn.execute(
            "SELECT message_id FROM messages_search WHERE messages_search MATCH ?"
            " ORDER BY rank LIMIT 50",
            (match,),
        ).fetchall():
            row = conn.execute(
                "SELECT m.id AS message_id, m.conversation_id, c.title AS conversation_title,"
                " c.kind AS conversation_kind, c.project_id, p.name AS project_name,"
                " m.role, m.actor_type, m.actor_id, m.created_at,"
                " substr(m.content, 1, 120) AS snippet"
                " FROM messages m"
                " JOIN conversations c ON c.id = m.conversation_id"
                " JOIN projects p ON p.id = c.project_id"
                " WHERE m.id = ?",
                (r["message_id"],),
            ).fetchone()
            if row and _visible(row["project_id"], user):
                out["conversations"].append(dict(row))
    return {"q": query, **out}
