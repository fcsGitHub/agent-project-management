"""M28-I86 (docs/01 §AA.1): timesheet submission & approval — Redmine plugin
semantics native: submit a period, owner approves (→ dates frozen, further
writes 409) or rejects (→ editable again, resubmission reuses the row)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from apm import config
from apm.core import projections


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def ctx(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "工时审批", "ontology": "software-dev", "requirement": "I86"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    item = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "记时任务"}).json()
    today = date.today()

    def log(minutes=60, offset=0):
        r = client.post(f"/api/items/{item['id']}/time_entries",
                        json={"minutes": minutes,
                              "spent_on": (today + timedelta(days=offset)).isoformat()})
        assert r.status_code == 200, r.text
        return r.json()

    return {"pid": pid, "item": item, "log": log, "today": today}


def test_submit_reject_and_resubmit(client, ctx):
    pid, log, today = ctx["pid"], ctx["log"], ctx["today"]
    log(60, -1)
    log(120, 0)
    start = (today - timedelta(days=1)).isoformat()
    end = today.isoformat()

    # an empty period is refused
    r = client.post("/api/me/timesheets/submit",
                    json={"project_id": pid, "period_start": "2026-01-01",
                          "period_end": "2026-01-07"})
    assert r.status_code == 422, r.text

    ts = client.post("/api/me/timesheets/submit",
                     json={"project_id": pid, "period_start": start,
                           "period_end": end}).json()
    assert ts["status"] == "submitted"
    assert ts["total_minutes"] == 180 and ts["entry_count"] == 2

    # duplicate submission of the same pending period → 409
    r = client.post("/api/me/timesheets/submit",
                    json={"project_id": pid, "period_start": start, "period_end": end})
    assert r.status_code == 409

    # owner (local admin) rejects → editable again, resubmit reuses the row
    r = client.post(f"/api/timesheets/{ts['id']}/reject",
                    json={"reason": "备注缺失，请补充说明"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "rejected" and "备注缺失" in r.json()["reason"]
    assert client.post(f"/api/items/{ctx['item']['id']}/time_entries",
                       json={"minutes": 30,
                             "spent_on": start}).status_code == 200
    ts2 = client.post("/api/me/timesheets/submit",
                      json={"project_id": pid, "period_start": start, "period_end": end}).json()
    assert ts2["id"] == ts["id"] and ts2["status"] == "submitted"
    assert ts2["total_minutes"] == 210 and ts2["entry_count"] == 3


def test_approve_locks_period_writes(client, ctx):
    pid, log, today = ctx["pid"], ctx["log"], ctx["today"]
    e1 = log(60, -1)
    start = (today - timedelta(days=1)).isoformat()
    end = today.isoformat()
    ts = client.post("/api/me/timesheets/submit",
                     json={"project_id": pid, "period_start": start, "period_end": end}).json()

    apr = client.post(f"/api/timesheets/{ts['id']}/approve")
    assert apr.status_code == 200, apr.text
    assert apr.json()["status"] == "approved" and apr.json()["decided_by"]

    # logging inside the frozen window → 409; outside → fine
    r = client.post(f"/api/items/{ctx['item']['id']}/time_entries",
                    json={"minutes": 30, "spent_on": start})
    assert r.status_code == 409 and "timesheet locked" in r.json()["detail"]
    assert client.post(f"/api/items/{ctx['item']['id']}/time_entries",
                       json={"minutes": 30,
                             "spent_on": (today + timedelta(days=5)).isoformat()},
                      ).status_code == 200

    # editing an entry inside the window is refused wholesale — a frozen period
    # is an immutable payroll fact (fix the note via reject → resubmit instead)
    assert client.patch(f"/api/time_entries/{e1['id']}",
                        json={"note": "补备注"}).status_code == 409
    r = client.patch(f"/api/time_entries/{e1['id']}",
                     json={"spent_on": end})  # both dates frozen
    assert r.status_code == 409

    # deleting a frozen entry → 409
    assert client.delete(f"/api/time_entries/{e1['id']}").status_code == 409

    # a submission overlapping the approved window → 409 (exact-match branch
    # fires first here: "already approved"; overlapping-but-not-equal periods
    # hit the overlap branch, also 409 "locked")
    r = client.post("/api/me/timesheets/submit",
                    json={"project_id": pid, "period_start": start, "period_end": end})
    assert r.status_code == 409


def test_approve_then_rebuild_replays_lock(client, ctx):
    pid, log, today = ctx["pid"], ctx["log"], ctx["today"]
    log(45, -2)
    start = (today - timedelta(days=2)).isoformat()
    end = start
    ts = client.post("/api/me/timesheets/submit",
                     json={"project_id": pid, "period_start": start, "period_end": end}).json()
    assert client.post(f"/api/timesheets/{ts['id']}/approve").status_code == 200
    before = client.get(f"/api/projects/{pid}/timesheets").json()

    projections.rebuild()
    after = client.get(f"/api/projects/{pid}/timesheets").json()
    assert after == before
    # the lock survives replay: the frozen date still refuses writes
    assert client.post(f"/api/items/{ctx['item']['id']}/time_entries",
                       json={"minutes": 10, "spent_on": start}).status_code == 409
