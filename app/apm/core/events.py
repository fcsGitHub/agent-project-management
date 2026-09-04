"""Event kernel: append-only event log + projector application + bus publish.

The single write path for the whole system: every state change (human, agent,
system, ui_agent) becomes one event here. Projections are updated inline by the
same handlers used on rebuild, so live and replay share one fold function.
"""
from __future__ import annotations

import json
import sqlite3
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from apm.core import db
from apm.core.bus import event_bus
from apm import config

Handler = Callable[[sqlite3.Connection, "Event"], None]
PostEmitHook = Callable[["Event"], None]
EmitGuard = Callable[[str, str], None]

# Post-emit hooks (M9-I29): side-channel consumers that run after an event is
# appended, folded and broadcast — the automation engine subscribes here instead
# of polling. Hooks must never break the write path; failures are logged only.
_post_emit_hooks: list[PostEmitHook] = []

# Pre-emit guards (M22-I69): veto a write before it hits the log — the archived
# project read-only gate lives here. Unlike post-emit hooks, a guard error
# propagates so the endpoint returns an HTTP error. Guards never run during
# rebuild (replay inserts directly, bypassing emit).
_emit_guards: list[EmitGuard] = []


def add_post_emit_hook(fn: PostEmitHook) -> None:
    if fn not in _post_emit_hooks:
        _post_emit_hooks.append(fn)


def add_emit_guard(fn: EmitGuard) -> None:
    if fn not in _emit_guards:
        _emit_guards.append(fn)

# Request-scoped actor (M8-I28): the auth middleware sets the logged-in user;
# FastAPI endpoints run in threadpools that inherit this context, so every
# emit attributes to the session identity without threading a parameter
# through the whole domain layer. Unset → local-mode fallback (settings.user_id).
_actor_ctx: ContextVar[str | None] = ContextVar("apm_actor_id", default=None)


def set_current_actor(user_id: str | None):
    return _actor_ctx.set(user_id)


def reset_current_actor(token) -> None:
    _actor_ctx.reset(token)


def effective_actor() -> str:
    """The identity behind the current operation (session > local default)."""
    return _actor_ctx.get() or config.settings.user_id


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass
class Event:
    id: int
    ts: str
    actor_type: str
    actor_id: str
    project_id: str
    agg_type: str
    agg_id: str
    event_type: str
    payload: dict[str, Any]
    prev_event_id: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ts": self.ts,
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
            "project_id": self.project_id,
            "agg_type": self.agg_type,
            "agg_id": self.agg_id,
            "event_type": self.event_type,
            "payload": self.payload,
            "prev_event_id": self.prev_event_id,
        }


def row_to_event(row: sqlite3.Row) -> Event:
    return Event(
        id=row["id"],
        ts=row["ts"],
        actor_type=row["actor_type"],
        actor_id=row["actor_id"],
        project_id=row["project_id"],
        agg_type=row["agg_type"],
        agg_id=row["agg_id"],
        event_type=row["event_type"],
        payload=json.loads(row["payload"]),
        prev_event_id=row["prev_event_id"],
    )


def emit(
    *,
    event_type: str,
    agg_type: str,
    agg_id: str,
    project_id: str = "",
    actor_type: str = "human",
    actor_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> Event:
    """Append one event, fold it into projections, then broadcast on the bus."""
    from apm.core import projections

    actor_id = actor_id or effective_actor()  # 会话身份（M8-I28）> 本地默认（M5-I19）

    for guard in _emit_guards:
        guard(event_type, project_id)

    with db.tx() as conn:
        prev = conn.execute("SELECT id FROM events ORDER BY id DESC LIMIT 1").fetchone()
        prev_id = prev["id"] if prev else 0
        cur = conn.execute(
            "INSERT INTO events (ts, actor_type, actor_id, project_id, agg_type, agg_id,"
            " event_type, payload, prev_event_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                utcnow(),
                actor_type,
                actor_id,
                project_id,
                agg_type,
                agg_id,
                event_type,
                json.dumps(payload or {}, ensure_ascii=False),
                prev_id,
            ),
        )
        row = conn.execute("SELECT * FROM events WHERE id = ?", (cur.lastrowid,)).fetchone()
        event = row_to_event(row)
        projections.apply(conn, event)
    event_bus.publish(event.as_dict())
    for hook in _post_emit_hooks:
        try:
            hook(event)
        except Exception:  # 自动化引擎故障绝不能拖垮写入路径（M9-I29）
            import logging

            logging.getLogger(__name__).exception(
                "post-emit hook failed after %s #%s", event.event_type, event.id
            )
    return event


def query_events(
    *,
    project_id: str | None = None,
    agg_type: str | None = None,
    agg_id: str | None = None,
    event_type: str | None = None,
    actor_type: str | None = None,
    actor_id: str | None = None,
    since_id: int = 0,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Event], int]:
    where, params = ["id > ?"], [since_id]
    if project_id:
        where.append("project_id = ?")
        params.append(project_id)
    if agg_type:
        where.append("agg_type = ?")
        params.append(agg_type)
    if agg_id:
        where.append("agg_id = ?")
        params.append(agg_id)
    if event_type:
        where.append("event_type = ?")
        params.append(event_type)
    if actor_type:
        where.append("actor_type = ?")
        params.append(actor_type)
    if actor_id:
        where.append("actor_id = ?")
        params.append(actor_id)
    clause = " AND ".join(where)
    conn = db.get_conn()
    total = conn.execute(f"SELECT COUNT(*) c FROM events WHERE {clause}", params).fetchone()["c"]
    rows = conn.execute(
        f"SELECT * FROM events WHERE {clause} ORDER BY id DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    return [row_to_event(r) for r in rows], total


def get_event(event_id: int) -> Event | None:
    row = db.get_conn().execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    return row_to_event(row) if row else None
