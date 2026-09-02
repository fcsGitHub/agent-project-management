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
