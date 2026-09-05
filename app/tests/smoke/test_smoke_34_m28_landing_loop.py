"""Smoke 34 (M28): the landing-loop trio end-to-end — the timesheet
submit→approve lock matrix, the cross-project workload aggregation
reconciled against per-project facts, and a rebuild pass. The print view
(I88) is browser-side (@media print + window.print) and is exercised in the
milestone review's isolated browser replay."""
from datetime import datetime, timedelta, timezone

import pytest

from apm import config
from apm.core import projections


@pytest.mark.smoke
def test_smoke_34_m28_landing_loop(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "冒烟落地闭环", "ontology": "software-dev", "requirement": "s34"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    item = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "记时任务"}).json()
    # assign to the caller so the workload projection picks the member up
    assert client.patch(f"/api/items/{item['id']}",
                        json={"assignee_type": "human",
                              "assignee_id": config.settings.user_id}).status_code == 200
    today = datetime.now(timezone.utc).date()
    start = (today - timedelta(days=1)).isoformat()
    end = today.isoformat()

    # --- 1) timesheet: submit → approve → freeze matrix -----------------------
    assert client.post(f"/api/items/{item['id']}/time_entries",
                       json={"minutes": 60, "spent_on": start}).status_code == 200
    ts = client.post("/api/me/timesheets/submit",
                     json={"project_id": pid, "period_start": start, "period_end": end}).json()
    assert ts["status"] == "submitted" and ts["total_minutes"] == 60 and ts["entry_count"] == 1
    assert client.post(f"/api/timesheets/{ts['id']}/approve").status_code == 200

    # frozen: log/edit/delete touching approved dates → 409; outside → fine
    assert client.post(f"/api/items/{item['id']}/time_entries",
                       json={"minutes": 30, "spent_on": end}).status_code == 409
    assert client.post(f"/api/items/{item['id']}/time_entries",
                       json={"minutes": 30,
                             "spent_on": (today + timedelta(days=3)).isoformat()},
                      ).status_code == 200
    entry = client.get(f"/api/items/{item['id']}/time_entries").json()["entries"][0]
    assert client.patch(f"/api/time_entries/{entry['id']}",
                        json={"note": "尝试改动"}).status_code == 409
    assert client.delete(f"/api/time_entries/{entry['id']}").status_code == 409

    # --- 2) workload: reconcile against per-project facts --------------------
    # u_admin holds one active item (the assigned task); logged time = 60
    # (frozen entry) + 30 (fresh, outside the lock) = 90 minutes in 7 days.
    wl = client.get("/api/portfolio/workload").json()
    me = wl["members"][0]
    assert me["user_id"] == config.settings.user_id
    assert me["active"] == 1 and me["overdue"] == 0 and me["minutes_7d"] == 90
    assert me["projects"] == {"冒烟落地闭环": 1}

    # --- 3) rebuild: approvals and the lock replay byte-identically ----------
    before = client.get(f"/api/projects/{pid}/timesheets").json()
    projections.rebuild()
    assert client.get(f"/api/projects/{pid}/timesheets").json() == before
    assert client.post(f"/api/items/{item['id']}/time_entries",
                       json={"minutes": 15, "spent_on": start}).status_code == 409
