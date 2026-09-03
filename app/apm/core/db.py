"""SQLite access layer.

One file-backed database in WAL mode with a connection per thread: readers run
concurrently, writers serialize through the ``tx`` lock (SQLite single-writer).
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from apm import config

_lock = threading.RLock()
_local = threading.local()
_generation = 0  # bumped by test resets so stale thread connections reopen


def get_conn() -> sqlite3.Connection:
    global _generation
    conn = getattr(_local, "conn", None)
    if conn is None or getattr(_local, "generation", -1) != _generation:
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass
        conn = _open(config.settings.db_path)
        _local.conn = conn
        _local.generation = _generation
    return conn


def _open(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def reset_for_tests(data_dir: Path) -> None:
    global _generation
    with _lock:
        _generation += 1
        conn = getattr(_local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass
            _local.conn = None
        _open(data_dir / "apm.db")  # create the file for this thread
        _local.conn = None  # reopened lazily per thread at new generation


def init_db() -> None:
    from apm.core import schema

    with _lock:
        conn = get_conn()
        schema.create_all(conn)
        # Lightweight migration: 存量库补 items.custom_fields（M6-I20）。
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(items)").fetchall()}
        if "custom_fields" not in cols:
            conn.execute("ALTER TABLE items ADD COLUMN custom_fields TEXT")
        # Lightweight migration: 存量库补 items 起止日期（M13-I41）。
        if "start_date" not in cols:
            conn.execute("ALTER TABLE items ADD COLUMN start_date TEXT")
        if "due_date" not in cols:
            conn.execute("ALTER TABLE items ADD COLUMN due_date TEXT")
        # Lightweight migration: 存量库补 projects.field_overrides（M7-I25）。
        pcols = {r["name"] for r in conn.execute("PRAGMA table_info(projects)").fetchall()}
        if "field_overrides" not in pcols:
            conn.execute("ALTER TABLE projects ADD COLUMN field_overrides TEXT")
        # Lightweight migration: 存量库补 users 凭据列（M8-I26）。
        ucols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "password_hash" not in ucols:
            conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
        if "is_admin" not in ucols:
            conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
        # Lightweight migration: 存量库补 users.feed_key（M11-I36）。
        if "feed_key" not in ucols:
            conn.execute("ALTER TABLE users ADD COLUMN feed_key TEXT")
        # Lightweight migration: 存量库补 users.email_notify（M11-I37）。
        if "email_notify" not in ucols:
            conn.execute("ALTER TABLE users ADD COLUMN email_notify INTEGER NOT NULL DEFAULT 1")
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
