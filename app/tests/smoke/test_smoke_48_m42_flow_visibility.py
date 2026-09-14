"""Smoke 48 (M42): the flow-visibility trio end-to-end — the board payload
derives a blocked flag from unfinished blockers, the velocity endpoint
aggregates committed vs completed per completed cycle with an average, the
escalation path pulls instance admins in past 2× the reminder window, and a
rebuild replays everything."""
from datetime import datetime, timedelta, timezone
import json

import pytest

from apm import config
from apm.core import db, projections


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.mark.smoke
def test_smoke_48_m42_flow_visibility(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "冒烟流量可见", "ontology": "software-dev",
                            "requirement": "s48"}).json()["id"]
    today = datetime.now(timezone.utc)

    # --- ① blocked flag on the board payload ------------------------------------
    blocker = client.post(f"/api/projects/{pid}/items",
                          json={"concept_id": "task", "title": "阻塞者"}).json()["id"]
    blocked = client.post(f"/api/projects/{pid}/items",
                          json={"concept_id": "task", "title": "被阻塞者"}).json()["id"]
    assert client.post(f"/api/items/{blocker}/relations",
                       json={"to_item": blocked, "relation_type": "blocks"}).status_code == 200
    items = {i["title"]: i for i in client.get(f"/api/projects/{pid}/items").json()["items"]}
    assert items["被阻塞者"]["blocked"] is True
    assert items["阻塞者"]["blocked"] is False

    # --- ② velocity: two completed cycles with known scope ----------------------
    c1 = client.post(f"/api/projects/{pid}/cycles",
                     json={"name": "V-Sprint 1", "start_date": (today.date() - timedelta(days=12)).isoformat(),
                           "end_date": (today.date() - timedelta(days=6)).isoformat()}).json()
    c2 = client.post(f"/api/projects/{pid}/cycles",
                     json={"name": "V-Sprint 2", "start_date": (today.date() - timedelta(days=5)).isoformat(),
                           "end_date": (today.date() - timedelta(days=1)).isoformat()}).json()

    def backdate(ts: datetime, iid: str, event: str, payload: str):
        conn = db.get_conn()
        row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM events").fetchone()["m"]
        conn.execute(
            "INSERT INTO events (ts, actor_type, actor_id, project_id, agg_type, agg_id,"
            " event_type, payload, prev_event_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (ts.isoformat(), "human", "u_admin", pid, "item", iid, event, payload, row))
        conn.commit()

    for i, c in ((0, c1), (1, c1), (2, c2)):
        it = client.post(f"/api/projects/{pid}/items",
                         json={"concept_id": "task", "title": f"周期项{i}"}).json()["id"]
        backdate(today - timedelta(days=11 - i * 5), it, "item.updated",
                 json.dumps({"cycle_id": c["id"]}))
        client.patch(f"/api/items/{it}", json={"cycle_id": c["id"]})
    backdate(today - timedelta(days=8), blocker, "item.updated",
             json.dumps({"cycle_id": c1["id"]}))
    client.patch(f"/api/items/{blocker}", json={"cycle_id": c1["id"]})

    v = client.get(f"/api/projects/{pid}/velocity").json()
    by_name = {c["name"]: c for c in v["cycles"]}
    # committed is the scope count ON the commitment day (first in-scope day):
    # V-Sprint 1 had only 周期项0 mounted on its day -11 → committed 1
    assert by_name["V-Sprint 1"]["committed"] == 1
    assert by_name["V-Sprint 2"]["committed"] == 1 and by_name["V-Sprint 2"]["completed"] == 0
    assert v["average_completed"] == 0.0

    # --- ③ escalation: stale approval past 2× window reaches admins -------------
    conn = db.get_conn()
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM events").fetchone()["m"]
    conn.execute(
        "INSERT INTO events (ts, actor_type, actor_id, project_id, agg_type, agg_id,"
        " event_type, payload, prev_event_id) VALUES (?,?,?,?,?,?,?,?,?)",
        ((today - timedelta(days=7)).isoformat(), "system", "system", pid, "approval",
         "apr_s48_old", "approval.requested",
         '{"kind": "plan_review", "snapshot": {"summary": "s48"}}', row))
    conn.commit()
    projections.rebuild()
    from apm.domains.users import ensure_default_user
    ensure_default_user()                            # rebuild drops runtime is_admin
    from apm.domains import automations
    assert automations._remind_pending_approvals(conn, today.date().isoformat()) == 1
    n = conn.execute(
        "SELECT COUNT(*) AS c FROM notifications WHERE kind = 'approval_reminder'"
        " AND user_id = 'u_admin'").fetchone()["c"]
    assert n >= 1

    # --- rebuild: flags, velocity, audit trail replay ----------------------------
    projections.rebuild()
    ensure_default_user()
    items2 = {i["title"]: i for i in client.get(f"/api/projects/{pid}/items").json()["items"]}
    assert items2["被阻塞者"]["blocked"] is True
    v2 = client.get(f"/api/projects/{pid}/velocity").json()
    v2.pop("generated_at")
    v.pop("generated_at")
    assert v2 == v
    r = client.get(f"/api/projects/{pid}/audit.csv")
    assert "approval.pending_reminded" in r.text
