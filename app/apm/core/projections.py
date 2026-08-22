"""Projector registry: fold(events) → read models.

Live appends and full rebuilds run the exact same handlers, so the current
state is always equal to the replay of history (verified in smoke baseline).
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Callable

from apm.core import schema
from apm.core.events import Event

Handler = Callable[[sqlite3.Connection, Event], None]

_handlers: dict[str, list[Handler]] = defaultdict(list)


def on(*event_types: str) -> Callable[[Handler], Handler]:
    """Register a projection handler for one or more event types."""

    def deco(fn: Handler) -> Handler:
        for t in event_types:
            _handlers[t].append(fn)
        return fn

    return deco


def apply(conn: sqlite3.Connection, event: Event) -> None:
    for handler in _handlers.get(event.event_type, ()):
        handler(conn, event)


def rebuild() -> int:
    """Drop every projection and replay the whole event log through handlers."""
    from apm.core.db import get_conn

    conn = get_conn()
    schema.drop_projections(conn)
    count = 0
    for row in conn.execute("SELECT * FROM events ORDER BY id ASC").fetchall():
        from apm.core.events import row_to_event

        apply(conn, row_to_event(row))
        count += 1
    conn.commit()
    return count


# Importing the domain modules registers their handlers. Keep this list
# synchronized with the domain packages (import-order independent).
def ensure_handlers_registered() -> None:
    import apm.domains  # noqa: F401  (re-exports domain registrations)
