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


@router.get("/search")
def search(q: str, types: str = "items,comments") -> dict:
    """Cross-project keyword search, scoped to the caller's visible projects
    (`_visible`, same裁剪 as the Atom/iCal feeds). Empty query → 422."""
    query = q.strip()
    if not query:
        raise HTTPException(status_code=422, detail="q must not be empty")
    wanted = {t.strip() for t in types.split(",") if t.strip()} & {"items", "comments"}
    if not wanted:
        raise HTTPException(status_code=422, detail="types must include items and/or comments")
    me = events.effective_actor()
    user = db.get_conn().execute("SELECT * FROM users WHERE id = ?", (me,)).fetchone()
    if user is None:
        raise HTTPException(status_code=404, detail=f"unknown user '{me}'")
    from apm.domains.feed import _visible

    match = _bigrams(query)
    conn = db.get_conn()
    out: dict[str, list] = {"items": [], "comments": []}
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
            if row and _visible(row["project_id"], user):
                out["items"].append(dict(row))
    if "comments" in wanted:
        for r in conn.execute(
            "SELECT comment_id FROM comments_search WHERE comments_search MATCH ?"
            " ORDER BY rank LIMIT 50",
            (match,),
        ).fetchall():
            row = conn.execute(
                "SELECT c.id, c.body, c.item_id, c.project_id, i.title AS item_title,"
                " p.name AS project_name FROM item_comments c"
                " JOIN items i ON i.id = c.item_id"
                " JOIN projects p ON p.id = c.project_id"
                " WHERE c.id = ? AND c.deleted_at IS NULL",
                (r["comment_id"],),
            ).fetchone()
            if row and _visible(row["project_id"], user):
                out["comments"].append(dict(row))
    return {"q": query, **out}
