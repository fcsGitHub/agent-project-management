"""Smoke 47 (M41): the rhythm-governance trio end-to-end — the cycle
burndown computes remaining plus the burnup scope stair from the event
replay, the approval reminder nudges owners once per day for stale gates,
the audit CSV export hands an admin the full window, and a rebuild replays
everything."""
import csv
import io
from datetime import datetime, timedelta, timezone

import pytest

from apm import config
from apm.core import db, projections
from apm.domains import automations


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.mark.smoke
def test_smoke_47_m41_rhythm_governance(client, tmp_data, isolated_ontologies, monkeypatch):
    pid = client.post("/api/projects",
                      json={"name": "冒烟节奏治理", "ontology": "software-dev",
                            "requirement": "s47"}).json()["id"]
    today = datetime.now(timezone.utc)

    # --- ① cycle burndown: scope stair + remaining ------------------------------
    c = client.post(f"/api/projects/{pid}/cycles",
                    json={"name": "Sprint 1", "start_date": (today.date() - timedelta(days=6)).isoformat(),
                          "end_date": (today.date() + timedelta(days=6)).isoformat()}).json()
    ids = []
    for i in range(3):
        it = client.post(f"/api/projects/{pid}/items",
                         json={"concept_id": "task", "title": f"燃尽任务{i}"}).json()
        assert client.patch(f"/api/items/{it['id']}",
                            json={"cycle_id": c["id"]}).status_code == 200
        ids.append(it["id"])
    assert client.patch(f"/api/items/{ids[0]}", json={"status": "done"}).status_code == 200
    bd = client.get(f"/api/cycles/{c['id']}/burndown").json()
    assert bd["series"][-1]["total"] == 3 and bd["series"][-1]["remaining"] == 2
    assert bd["ideal"][0]["remaining"] == 3

    # --- ② approval reminder: stale gate nudged once per day --------------------
    apr = client.get(f"/api/projects/{pid}/approvals",
                     params={"limit": 1}).json()
    conn = db.get_conn()
    apr_id = "apr_s47_old"
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM events").fetchone()["m"]
    conn.execute(
        "INSERT INTO events (ts, actor_type, actor_id, project_id, agg_type, agg_id,"
        " event_type, payload, prev_event_id) VALUES (?,?,?,?,?,?,?,?,?)",
        ((today - timedelta(days=5)).isoformat(), "system", "system", pid, "approval",
         apr_id, "approval.requested",
         '{"kind": "code_review", "snapshot": {"summary": "s47"}}', row))
    conn.commit()
    projections.rebuild()                      # replay → approvals row with old ts
    # is_admin is a runtime column (never evented) — rebuild drops it until the
    # next boot re-applies it; do the in-process equivalent before admin calls
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    assert automations._remind_pending_approvals(conn, today.date().isoformat()) == 1
    n = conn.execute(
        "SELECT COUNT(*) AS c FROM notifications WHERE kind = 'approval_reminder'"
    ).fetchone()["c"]
    assert n >= 1
    assert automations._remind_pending_approvals(conn, today.date().isoformat()) == 0

    # --- ③ audit CSV: admin window export ----------------------------------------
    r = client.get(f"/api/projects/{pid}/audit.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    types = {row["event_type"] for row in rows}
    assert {"item.created", "item.updated", "item.status_changed",
            "cycle.created"} <= types

    # --- rebuild: burndown and audit window replay -------------------------------
    projections.rebuild()
    ensure_default_user()
    bd2 = client.get(f"/api/cycles/{c['id']}/burndown").json()
    bd2.pop("generated_at")
    bd.pop("generated_at")
    assert bd2 == bd
    r2 = client.get(f"/api/projects/{pid}/audit.csv")
    assert len(list(csv.DictReader(io.StringIO(r2.text)))) == len(rows)
