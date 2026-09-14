"""M41-I126 approval overdue reminder (docs/01 §AN.2, ServiceNow
timer→reminder semantics): the daily sweep nudges owners about gate approvals
pending longer than approval_reminder_days — one approval.pending_reminded
per approval per day (event-stream idempotent), decided approvals are out of
scope, and the reminder rides the existing dual notification channels."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from apm import config
from apm.core import db, projections
from apm.core.ids import new_id
from apm.domains import automations


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


def _backdate_request(pid: str, agg_id: str, when: datetime):
    """Append an approval.requested event dated `when`, then rebuild so the
    approvals projection replays it with the backdated requested_at."""
    conn = db.get_conn()
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM events").fetchone()["m"]
    conn.execute(
        "INSERT INTO events (ts, actor_type, actor_id, project_id, agg_type, agg_id,"
        " event_type, payload, prev_event_id) VALUES (?,?,?,?,?,?,?,?,?)",
        (when.isoformat(), "system", "system", pid, "approval", agg_id,
         "approval.requested",
         '{"kind": "code_review", "snapshot": {"summary": " overdue"}}', row))
    conn.commit()
    projections.rebuild()


def test_reminder_window_and_idempotent(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "超时审批", "ontology": "software-dev",
                            "requirement": "I126"}).json()["id"]
    today = datetime.now(timezone.utc).date()
    old_id = new_id("apr")
    # requested 5 days ago (default window is 3) and one fresh today
    _backdate_request(pid, old_id,
                      datetime.now(timezone.utc) - timedelta(days=5))
    fresh_id = new_id("apr")
    _backdate_request(pid, fresh_id, datetime.now(timezone.utc))

    conn = db.get_conn()
    row = conn.execute(
        "SELECT requested_at FROM approvals WHERE id = ?", (old_id,)).fetchone()
    assert row is not None and row["requested_at"][:10] <= (
        date.today() - timedelta(days=5)).isoformat()

    reminded = automations._remind_pending_approvals(
        conn, datetime.now(timezone.utc).date().isoformat())
    assert reminded == 1                              # only the stale one
    n = conn.execute(
        "SELECT COUNT(*) AS c FROM notifications WHERE kind = 'approval_reminder'"
        " AND user_id = 'u_admin'").fetchone()["c"]
    assert n == 1
    # same-day re-run (UTC date, the sweep's anchor): the reminder fact is
    # already in the stream
    assert automations._remind_pending_approvals(
        conn, datetime.now(timezone.utc).date().isoformat()) == 0


def test_decided_approvals_are_skipped(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "已决审批", "ontology": "software-dev",
                            "requirement": "I126"}).json()["id"]
    old_id = new_id("apr")
    _backdate_request(pid, old_id,
                      datetime.now(timezone.utc) - timedelta(days=6))
    conn = db.get_conn()
    assert client.post(f"/api/approvals/{old_id}/decision",
                       json={"decision": "approved", "comment": "放行"}).status_code == 200
    assert automations._remind_pending_approvals(conn, date.today().isoformat()) == 0
    n = conn.execute(
        "SELECT COUNT(*) AS c FROM notifications WHERE kind = 'approval_reminder'"
    ).fetchone()["c"]
    assert n == 0


def test_no_project_rows_are_skipped(client, tmp_data, isolated_ontologies):
    conn = db.get_conn()
    old_id = new_id("apr")
    _backdate_request(pid="", agg_id=old_id,
                      when=datetime.now(timezone.utc) - timedelta(days=6))
    # events with empty project_id exist (system-level); the reminder query
    # excludes them and must not crash on the missing owner list
    assert automations._remind_pending_approvals(conn, date.today().isoformat()) == 0
