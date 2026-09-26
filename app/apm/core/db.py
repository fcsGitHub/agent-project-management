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
        _open(data_dir / "apm.db").close()  # create the file for this thread
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
        # Lightweight migration: 存量库补 items.auto_scheduled（M14-I44）。
        if "auto_scheduled" not in cols:
            conn.execute("ALTER TABLE items ADD COLUMN auto_scheduled INTEGER NOT NULL DEFAULT 0")
        # Lightweight migration: 存量库补 projects.field_overrides（M7-I25）。
        pcols = {r["name"] for r in conn.execute("PRAGMA table_info(projects)").fetchall()}
        if "field_overrides" not in pcols:
            conn.execute("ALTER TABLE projects ADD COLUMN field_overrides TEXT")
        # Lightweight migration: 存量库补 saved_views.is_default（M16-I52）。
        if any(r[0] == "saved_views" for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()):
            vcols = {r["name"] for r in conn.execute("PRAGMA table_info(saved_views)").fetchall()}
            if "is_default" not in vcols:
                conn.execute("ALTER TABLE saved_views ADD COLUMN is_default INTEGER NOT NULL DEFAULT 0")
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
        # Lightweight migration: 存量库补 users.quiet_start/quiet_end（M56-I169）。
        if "quiet_start" not in ucols:
            conn.execute("ALTER TABLE users ADD COLUMN quiet_start TEXT")
        if "quiet_end" not in ucols:
            conn.execute("ALTER TABLE users ADD COLUMN quiet_end TEXT")
        # Lightweight migration: 存量库补 item_relations.lag_days（M25-I78）。
        if any(r[0] == "item_relations" for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()):
            rcols = {r["name"] for r in conn.execute("PRAGMA table_info(item_relations)").fetchall()}
            if "lag_days" not in rcols:
                conn.execute("ALTER TABLE item_relations ADD COLUMN lag_days INTEGER")
        # I103: 存量库补 items.archived_at（工作项归档/回收站）。
        icols2 = {r["name"] for r in conn.execute("PRAGMA table_info(items)").fetchall()}
        if "archived_at" not in icols2:
            conn.execute("ALTER TABLE items ADD COLUMN archived_at TEXT")
        # I117: 存量库补 user_time_off.delegate（休假代理转派）。
        if any(r[0] == "user_time_off" for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()):
            toff_cols = {r["name"] for r in conn.execute("PRAGMA table_info(user_time_off)").fetchall()}
            if "delegate" not in toff_cols:
                conn.execute("ALTER TABLE user_time_off ADD COLUMN delegate TEXT")
        # I119: 存量库补 items.cycle_id（Cycles 迭代时间盒）。
        if "cycle_id" not in icols2:
            conn.execute("ALTER TABLE items ADD COLUMN cycle_id TEXT")
        # I133: 存量库补 items.recurrence_days（完成自动重建节拍）。
        if "recurrence_days" not in icols2:
            conn.execute("ALTER TABLE items ADD COLUMN recurrence_days INTEGER")
        # I122: 存量库补 users.hourly_rate / projects.budget_hours（成本与预算）。
        ucols2 = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "hourly_rate" not in ucols2:
            conn.execute("ALTER TABLE users ADD COLUMN hourly_rate REAL")
        # I139: 存量库补 users.currency（费率币种，成本报表折算基准币）。
        if "currency" not in ucols2:
            conn.execute("ALTER TABLE users ADD COLUMN currency TEXT")
        pcols2 = {r["name"] for r in conn.execute("PRAGMA table_info(projects)").fetchall()}
        if "budget_hours" not in pcols2:
            conn.execute("ALTER TABLE projects ADD COLUMN budget_hours REAL")
        # Lightweight migration: 存量库补 item_comments.edited_at（M26-I81）。
        if any(r[0] == "item_comments" for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()):
            ccols = {r["name"] for r in conn.execute("PRAGMA table_info(item_comments)").fetchall()}
            if "edited_at" not in ccols:
                conn.execute("ALTER TABLE item_comments ADD COLUMN edited_at TEXT")
        # M24-I76: baselines 多条化——存量表带 project_id UNIQUE 约束则重建去约束。
        if any(r[0] == "baselines" for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()):
            unique_on_project = any(
                i["unique"] and [c["name"] for c in conn.execute(
                    f"PRAGMA index_info({i['name']})").fetchall()] == ["project_id"]
                for i in conn.execute("PRAGMA index_list(baselines)").fetchall()
            )
            if unique_on_project:
                conn.execute(
                    "CREATE TABLE baselines_new (id TEXT PRIMARY KEY, project_id TEXT NOT NULL,"
                    " snapshot TEXT NOT NULL, created_at TEXT NOT NULL)")
                conn.execute(
                    "INSERT INTO baselines_new (id, project_id, snapshot, created_at)"
                    " SELECT id, project_id, snapshot, created_at FROM baselines")
                conn.execute("DROP TABLE baselines")
                conn.execute("ALTER TABLE baselines_new RENAME TO baselines")
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_baselines_project ON baselines(project_id)")
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
