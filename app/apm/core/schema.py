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
  field_overrides TEXT,
  budget_hours REAL,
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

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT,
  password_hash TEXT,
  is_admin INTEGER NOT NULL DEFAULT 0,
  feed_key TEXT,
  email_notify INTEGER NOT NULL DEFAULT 1,
  hourly_rate REAL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_members (
  project_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  role TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (project_id, user_id)
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
  start_date TEXT,
  due_date TEXT,
  auto_scheduled INTEGER NOT NULL DEFAULT 0,
  custom_fields TEXT,
  milestone_id TEXT,
  cycle_id TEXT,
  recurrence_days INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  archived_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_items_project ON items(project_id);
CREATE INDEX IF NOT EXISTS idx_items_feature ON items(feature_id);

CREATE TABLE IF NOT EXISTS item_relations (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  from_item TEXT NOT NULL,
  to_item TEXT NOT NULL,
  relation_type TEXT NOT NULL,
  lag_days INTEGER,
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

CREATE TABLE IF NOT EXISTS automation_rules (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  name TEXT NOT NULL,
  trigger_event TEXT NOT NULL,
  condition_json TEXT NOT NULL DEFAULT '{}',
  action_json TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_automation_rules_project ON automation_rules(project_id);

CREATE TABLE IF NOT EXISTS webhooks (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  url TEXT NOT NULL,
  secret TEXT NOT NULL DEFAULT '',
  events_json TEXT NOT NULL DEFAULT '[]',
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_webhooks_project ON webhooks(project_id);

CREATE TABLE IF NOT EXISTS notifications (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  summary TEXT NOT NULL,
  ref_event_id INTEGER,
  read INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, read);

-- I96: per-kind notification preference (runtime state, NOT an event projection —
-- deliberately absent from drop_projections so rebuilds keep user preferences,
-- same semantics as users.email_notify/feed_key). Missing row = fully on.
CREATE TABLE IF NOT EXISTS notification_prefs (
  user_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  inapp INTEGER NOT NULL DEFAULT 1,
  email INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, kind)
);

CREATE TABLE IF NOT EXISTS milestones (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  due_date TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_milestones_project ON milestones(project_id);

CREATE TABLE IF NOT EXISTS saved_views (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  name TEXT NOT NULL,
  owner_id TEXT,
  is_public INTEGER NOT NULL DEFAULT 0,
  is_default INTEGER NOT NULL DEFAULT 0,
  definition TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_saved_views_project ON saved_views(project_id);

CREATE TABLE IF NOT EXISTS item_comments (
  id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  author_id TEXT NOT NULL,
  body TEXT NOT NULL,
  mentions TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  edited_at TEXT,
  deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_item_comments_item ON item_comments(item_id);

-- M26-I81: full revision history of comment edits (the capability Redmine
-- needs a plugin for and GitLab lacks entirely, #3706) — one row per edit,
-- holding the *previous* body, keyed deterministically by the event id.
CREATE TABLE IF NOT EXISTS comment_revisions (
  id TEXT PRIMARY KEY,
  comment_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  body TEXT NOT NULL,
  edited_by TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_comment_revisions_comment ON comment_revisions(comment_id);

CREATE TABLE IF NOT EXISTS item_participants (
  item_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  source TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (item_id, user_id)
);

CREATE TABLE IF NOT EXISTS item_time_entries (
  id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  minutes INTEGER NOT NULL,
  spent_on TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_item_time_entries_item ON item_time_entries(item_id);
CREATE INDEX IF NOT EXISTS idx_item_time_entries_project ON item_time_entries(project_id);

CREATE TABLE IF NOT EXISTS extracted_tasks (
  id TEXT PRIMARY KEY,
  comment_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  text TEXT NOT NULL,
  item_id TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_extracted_tasks_comment ON extracted_tasks(comment_id);
CREATE INDEX IF NOT EXISTS idx_extracted_tasks_project ON extracted_tasks(project_id);

CREATE TABLE IF NOT EXISTS baselines (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  snapshot TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_baselines_project ON baselines(project_id);

-- M28-I86: per-period timesheet submissions; an approved row freezes the
-- member's entries inside [period_start, period_end] (Redmine plugin semantics,
-- docs/01 §AA.1). status ∈ submitted/approved/rejected.
CREATE TABLE IF NOT EXISTS timesheets (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  total_minutes INTEGER NOT NULL,
  entry_count INTEGER NOT NULL,
  status TEXT NOT NULL,
  decided_by TEXT,
  decided_at TEXT,
  reason TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_timesheets_project ON timesheets(project_id);
CREATE INDEX IF NOT EXISTS idx_timesheets_user ON timesheets(user_id);

-- I99: external intake tokens (projection of intake.token_* events — in
-- drop_projections so rebuild reproduces them; value plaintext like feed_key).
CREATE TABLE IF NOT EXISTS intake_tokens (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  token TEXT NOT NULL UNIQUE,
  concept_id TEXT,
  revoked_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_intake_tokens_project ON intake_tokens(project_id);

-- I104: global non-working days (projection of calendar.holiday_* events —
-- in drop_projections so rebuild reproduces them; date itself is the agg id).
CREATE TABLE IF NOT EXISTS non_working_days (
  date TEXT PRIMARY KEY,
  note TEXT,
  created_at TEXT NOT NULL
);

-- I107: processed mail Message-IDs (projection of imap.message_processed —
-- in drop_projections so rebuild reproduces them; idempotency per Message-ID).
CREATE TABLE IF NOT EXISTS imap_seen (
  message_id TEXT PRIMARY KEY,
  from_email TEXT,
  routed TEXT NOT NULL,
  item_id TEXT,
  project_id TEXT,
  processed_at TEXT NOT NULL
);

-- I108: per-user canned responses (runtime state like notification_prefs —
-- deliberately absent from drop_projections so rebuilds keep the user's
-- library; GitHub Saved Replies semantics).
CREATE TABLE IF NOT EXISTS saved_replies (
  user_id TEXT NOT NULL,
  id TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (user_id, id)
);

-- I111: personal time-off stretches (projection of user.time_off_* events —
-- in drop_projections so rebuild reproduces them; workload/schedule consume).
CREATE TABLE IF NOT EXISTS user_time_off (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  delegate TEXT,
  reason TEXT,
  cancelled_at TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_time_off_user ON user_time_off(user_id);

-- I119: iteration time boxes (projection of cycle.* events — in
-- drop_projections so rebuild reproduces them; orthogonal to milestones,
-- which are release points, not date-sliced containers).
CREATE TABLE IF NOT EXISTS project_cycles (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  name TEXT NOT NULL,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  cancelled_at TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cycles_project ON project_cycles(project_id);

-- I123: item attachment metadata (projection of item.attachment_* events —
-- in drop_projections so rebuild reproduces the rows; the binaries live on
-- disk under data_dir/attachments/{project_id}/, outside the event stream,
-- same split as the artifacts git repo).
CREATE TABLE IF NOT EXISTS attachments (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  item_id TEXT NOT NULL,
  filename TEXT NOT NULL,
  size INTEGER NOT NULL,
  mime TEXT,
  stored_path TEXT NOT NULL,
  uploader TEXT,
  created_at TEXT NOT NULL,
  removed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_attachments_item ON attachments(item_id);

-- I131: risk register (projection of risk.* events — in drop_projections so
-- rebuild reproduces them; PMBOK probability×impact scoring sorts the page).
CREATE TABLE IF NOT EXISTS risks (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  title TEXT NOT NULL,
  probability INTEGER NOT NULL,
  impact INTEGER NOT NULL,
  response TEXT,
  owner TEXT,
  review_date TEXT,
  related_item_id TEXT,
  status TEXT NOT NULL DEFAULT 'open',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_risks_project ON risks(project_id);
"""

FTS_DDL = """
-- Asset full-text index; Chinese indexed as character bigrams (docs/09 §5).
CREATE VIRTUAL TABLE IF NOT EXISTS assets_fts USING fts5(asset_id UNINDEXED, text);
-- Global search (M22-I68): same bigram scheme over items and comments.
CREATE VIRTUAL TABLE IF NOT EXISTS items_search USING fts5(item_id UNINDEXED, text);
CREATE VIRTUAL TABLE IF NOT EXISTS comments_search USING fts5(comment_id UNINDEXED, text);
"""


def create_all(conn: sqlite3.Connection) -> None:
    conn.executescript(EVENTS_DDL)
    conn.executescript(PROJECTIONS_DDL)
    conn.executescript(FTS_DDL)


def drop_projections(conn: sqlite3.Connection) -> None:
    """Used by rebuild-projections: wipe caches, replay events through projectors."""
    for table in (
        "notifications",
        "webhooks",
        "automation_rules",
        "milestones",
        "saved_views",
        "item_comments",
        "comment_revisions",
        "item_participants",
        "item_time_entries",
        "timesheets",
        "intake_tokens",
        "non_working_days",
        "imap_seen",
        "user_time_off",
        "project_cycles",
        "attachments",
        "risks",
        "extracted_tasks",
        "baselines",
        "project_members",
        "users",
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
