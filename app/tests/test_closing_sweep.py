"""M42-I130 closing sweep (docs/01 §AO.3): three leftover small items from
past reviews — the intake panel is hidden from non-owners (server stays
owner-only), the attachment extension allowlist rejects other types with 415,
and an approval pending past 2× the reminder window escalates to instance
admins alongside the project owner."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

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


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "收尾打包", "ontology": "software-dev", "requirement": "I130"})
    assert r.status_code == 200
    return r.json()["id"]


def test_attachment_extension_allowlist(client, pid, tmp_data, isolated_ontologies, monkeypatch):
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "带白名单"}).json()["id"]
    monkeypatch.setattr(config.settings, "attachment_allowed_ext", "pdf,png")
    ok = client.post(f"/api/items/{it}/attachments",
                     files={"file": ("a.PDF", b"%PDF", "application/pdf")})
    assert ok.status_code == 200                                  # case-insensitive
    bad = client.post(f"/api/items/{it}/attachments",
                      files={"file": ("virus.exe", b"MZ", "application/x-exe")})
    assert bad.status_code == 415
    noext = client.post(f"/api/items/{it}/attachments",
                        files={"file": ("README", b"hi", "text/plain")})
    assert noext.status_code == 415
    # empty config = everything allowed (I123 default)
    monkeypatch.setattr(config.settings, "attachment_allowed_ext", "")
    assert client.post(f"/api/items/{it}/attachments",
                       files={"file": ("README", b"hi", "text/plain")}).status_code == 200


def test_escalation_past_double_window(client, pid, tmp_data, isolated_ontologies):
    """pending 5 days (window 3) → owner only; pending 7 days (≥2×3) →
    owner + admins via the escalated flag."""
    from datetime import datetime as dt
    conn = db.get_conn()

    def backdate(agg_id, when: dt):
        row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM events").fetchone()["m"]
        conn.execute(
            "INSERT INTO events (ts, actor_type, actor_id, project_id, agg_type, agg_id,"
            " event_type, payload, prev_event_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (when.isoformat(), "system", "system", pid, "approval", agg_id,
             "approval.requested",
             '{"kind": "code_review", "snapshot": {"summary": "I130"}}', row))
        conn.commit()
        projections.rebuild()
        from apm.domains.users import ensure_default_user
        ensure_default_user()                          # rebuild drops is_admin

    today = dt.now(timezone.utc).date()
    automations._remind_pending_approvals(conn, (dt.now(timezone.utc).date()).isoformat())
    # fresh project: nothing pending yet
    backdate("apr_130a", dt.now(timezone.utc) - timedelta(days=5))
    assert automations._remind_pending_approvals(
        conn, datetime.now(timezone.utc).date().isoformat()) == 1
    rows = db.get_conn().execute(
        "SELECT payload FROM events WHERE event_type = 'approval.pending_reminded'"
        " AND agg_id = 'apr_130a'").fetchall()
    import json
    assert json.loads(rows[-1]["payload"])["escalated"] is False   # 5 < 2×3

    # 7-day-old approval escalates to admins too
    backdate("apr_130b", dt.now(timezone.utc) - timedelta(days=7))
    assert automations._remind_pending_approvals(
        conn, datetime.now(timezone.utc).date().isoformat()) == 1
    ev = db.get_conn().execute(
        "SELECT payload FROM events WHERE event_type = 'approval.pending_reminded'"
        " AND agg_id = 'apr_130b'").fetchone()
    assert json.loads(ev["payload"])["escalated"] is True
    n = db.get_conn().execute(
        "SELECT COUNT(*) AS c FROM notifications WHERE kind = 'approval_reminder'"
        " AND user_id = 'u_admin'").fetchone()["c"]
    assert n >= 1                                   # admin received the escalation


def test_intake_panel_hidden_for_non_owner(client, pid, tmp_data, isolated_ontologies):
    """Server contract stays owner-only (M38 C-level): the token query 403s
    for contributors, so the UI renders the card only for owners/admins."""
    client.post("/api/users", json={"id": "u_viewer", "name": "路人"})
    client.post("/api/session/identity", json={"user_id": "u_viewer"})
    assert client.get(f"/api/projects/{pid}/intake-token").status_code == 403
