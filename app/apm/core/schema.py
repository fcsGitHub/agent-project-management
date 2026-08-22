"""DDL for the event log (source of truth) and projection tables (cache)."""
from __future__ import annotations

import sqlite3

EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS events (
  id            INTEGER PRIMARY KEY,
  ts            TEXT NOT NULL,
  actor_type    TEXT NOT NULL,
  actor_id      TEXT NOT NULL,
  project_id    TEXT NOT NULL,
  agg_type      TEXT NOT NULL,
  agg_id        TEXT NOT NULL,
  event_type    TEXT NOT NULL,
  payload       TEXT NOT NULL,
  prev_event_id INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_project ON events(project_id, id);
CREATE INDEX IF NOT EXISTS idx_events_agg ON events(agg_type, agg_id, id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type, id);

-- Immutability enforced by triggers (04 §2: append-only, no UPDATE/DELETE).
CREATE TRIGGER IF NOT EXISTS trg_events_no_update
BEFORE UPDATE ON events
BEGIN
  SELECT RAISE(ABORT, 'events are append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_events_no_delete
BEFORE DELETE ON events
BEGIN
  SELECT RAISE(ABORT, 'events are append-only');
END;
"""

PROJECTIONS_DDL = """
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  ontology TEXT NOT NULL,
  template TEXT NOT NULL,
  status TEXT NOT NULL,
  charter TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS features (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  title TEXT NOT NULL,
  brief TEXT,
  status TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  feature_id TEXT,
  kind TEXT NOT NULL,
  title TEXT,
  status TEXT NOT NULL,
  item_id TEXT,
  run_id TEXT,
  parent_conversation_id TEXT,
  seed_length INTEGER,
  instruction TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  parent_id TEXT,
  role TEXT NOT NULL,
  actor_type TEXT,
  actor_id TEXT,
  content TEXT NOT NULL,
  span_id TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, created_at);

CREATE TABLE IF NOT EXISTS prompt_layers (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  level TEXT NOT NULL,
  feature_id TEXT,
  agent_role TEXT,
  git_path TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  updated_by TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  feature_id TEXT,
  parent_id TEXT,
  concept_id TEXT,
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  status_group TEXT NOT NULL,
  priority TEXT,
  assignee_type TEXT,
  assignee_id TEXT,
  estimate_hours REAL,
  milestone_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_items_project ON items(project_id);
CREATE INDEX IF NOT EXISTS idx_items_feature ON items(feature_id);

CREATE TABLE IF NOT EXISTS item_relations (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  from_item TEXT NOT NULL,
  to_item TEXT NOT NULL,
  relation_type TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  project_id TEXT,
  feature_id TEXT,
  item_id TEXT,
  conversation_id TEXT NOT NULL,
  agent_role TEXT,
  graph_node_id TEXT,
  status TEXT NOT NULL,
  thread_id TEXT NOT NULL,
  input TEXT,
  output TEXT,
  started_at TEXT,
  ended_at TEXT,
  total_input_tokens INTEGER NOT NULL DEFAULT 0,
  total_output_tokens INTEGER NOT NULL DEFAULT 0,
  estimated_cost_usd REAL NOT NULL DEFAULT 0,
  error TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id);
CREATE INDEX IF NOT EXISTS idx_runs_conv ON runs(conversation_id);

CREATE TABLE IF NOT EXISTS spans (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  parent_id TEXT,
  span_kind TEXT NOT NULL,
  name TEXT NOT NULL,
  ts_start TEXT,
  ts_end TEXT,
  status TEXT,
  attributes TEXT,
  io TEXT
);
CREATE INDEX IF NOT EXISTS idx_spans_run ON spans(run_id);

CREATE TABLE IF NOT EXISTS approvals (
  id TEXT PRIMARY KEY,
  project_id TEXT,
  run_id TEXT,
  item_id TEXT,
  conversation_id TEXT,
  kind TEXT NOT NULL,
  payload_snapshot TEXT NOT NULL,
  status TEXT NOT NULL,
  requested_at TEXT,
  decided_at TEXT,
  reviewer_id TEXT,
  comment TEXT
);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);

CREATE TABLE IF NOT EXISTS assets (
  id TEXT PRIMARY KEY,
  library_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  tags TEXT,
  owner_id TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  git_path TEXT NOT NULL,
  commit_sha TEXT NOT NULL,
  citation_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS asset_links (
  id TEXT PRIMARY KEY,
  asset_id TEXT NOT NULL,
  type TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_ref TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_asset_links_asset ON asset_links(asset_id);

CREATE TABLE IF NOT EXISTS ui_commands (
  id TEXT PRIMARY KEY,
  utterance TEXT NOT NULL,
  page_state TEXT,
  actions TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""

FTS_DDL = """
-- Asset full-text index; Chinese indexed as character bigrams (docs/09 §5).
CREATE VIRTUAL TABLE IF NOT EXISTS assets_fts USING fts5(asset_id UNINDEXED, text);
"""


def create_all(conn: sqlite3.Connection) -> None:
    conn.executescript(EVENTS_DDL)
    conn.executescript(PROJECTIONS_DDL)
    conn.executescript(FTS_DDL)


def drop_projections(conn: sqlite3.Connection) -> None:
    """Used by rebuild-projections: wipe caches, replay events through projectors."""
    for table in (
        "ui_commands",
        "asset_links",
        "assets",
        "approvals",
        "spans",
        "runs",
        "item_relations",
        "items",
        "prompt_layers",
        "messages",
        "conversations",
        "features",
        "projects",
    ):
        conn.execute(f"DELETE FROM {table}")
