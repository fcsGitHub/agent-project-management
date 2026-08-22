"""SQLite access layer.

Single-writer SQLite (stdlib sqlite3). One shared connection guarded by an
RLock; all schema objects live in :mod:`apm.core.schema`.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from apm import config

_conn: sqlite3.Connection | None = None
_lock = threading.RLock()


def get_conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            _conn = _open(config.settings.db_path)
        return _conn


def _open(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def reset_for_tests(data_dir: Path) -> None:
    """Point the singleton at a fresh temp database (test isolation)."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = _open(data_dir / "apm.db")


def init_db() -> None:
    from apm.core import schema

    with _lock:
        conn = get_conn()
        schema.create_all(conn)
        conn.commit()


class tx:
    """Serialized write transaction: `with tx() as conn: ...` commits on exit."""

    def __enter__(self) -> sqlite3.Connection:
        _lock.acquire()
        self.conn = get_conn()
        return self.conn

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is None:
                self.conn.commit()
            else:
                self.conn.rollback()
        finally:
            _lock.release()
