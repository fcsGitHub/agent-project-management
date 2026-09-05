"""Smoke 35 (M29): the efficiency-and-observability trio end-to-end — the
personal schedule data source reconciled against per-project facts, the
quick-edit guard inheritance proven through the very PATCH the modal issues,
and the run aggregation report checked against the run list, then a rebuild."""
from datetime import datetime, timedelta, timezone

import pytest

from apm import config
from apm.core import events, projections


@pytest.mark.smoke
def test_smoke_35_m29_efficiency_observability(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "冒烟效率可观测", "ontology": "software-dev", "requirement": "s35"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    me = config.settings.user_id
    today = datetime.now(timezone.utc).date()
    day = (today + timedelta(days=3)).isoformat()

    # --- 1) my/schedule: data source for the calendar ------------------------
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "月历任务",
                           "start_date": day, "due_date": day,
                           "assignee_type": "human", "assignee_id": me}).json()
    sch = client.get("/api/my/schedule").json()
    row = next(i for i in sch["items"] if i["id"] == it["id"])
    assert row["title"] == "月历任务" and row["project_name"] == "冒烟效率可观测"
    # the same PATCH the calendar drag issues → schedule reflects it
    day2 = (today + timedelta(days=5)).isoformat()
    assert client.patch(f"/api/items/{it['id']}",
                        json={"start_date": day2, "due_date": day2}).status_code == 200
    sch2 = client.get("/api/my/schedule").json()
    assert next(i for i in sch2["items"] if i["id"] == it["id"])["due_date"] == day2

    # --- 2) quick edit inherits every guard on patch_item --------------------
    # bug whitelist (I82): open→verified refused, legal chain accepted
    bug = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "bug", "title": "快捷缺陷"}).json()
    assert client.patch(f"/api/items/{bug['id']}",
                        json={"status": "verified"}).status_code == 422
    assert client.patch(f"/api/items/{bug['id']}",
                        json={"status": "fixing"}).status_code == 200
    # blocks closure (I78): finishing a blocked task is refused — the relation
    # is issued from the blocker's side (from=blocker blocks to=the task)
    blocker = client.post(f"/api/projects/{pid}/items",
                          json={"concept_id": "task", "title": "阻塞者"}).json()
    client.post(f"/api/items/{blocker['id']}/relations",
                json={"to_item": it["id"], "relation_type": "blocks"})
    r = client.patch(f"/api/items/{it['id']}", json={"status": "done"})
    assert r.status_code == 422 and "blocked by" in r.json()["detail"]

    # --- 3) runs report reconciles with the run list --------------------------
    rid = "run_smoke35"
    events.emit(event_type="run.requested", agg_type="run", agg_id=rid,
                project_id=pid, payload={"conversation_id": "conv-s35",
                                         "agent_role": "pm-agent"})
    events.emit(event_type="run.started", agg_type="run", agg_id=rid,
                project_id=pid, payload={})
    events.emit(event_type="run.succeeded", agg_type="run", agg_id=rid,
                project_id=pid, payload={"output": {}})
    rep = client.get(f"/api/projects/{pid}/runs/report").json()
    listing = client.get("/api/runs", params={"project_id": pid, "limit": 200}).json()["runs"]
    mine = [x for x in listing if x["project_id"] == pid]
    assert rep["total"] == len(mine) == 1
    assert rep["success_rate"] == 1.0 and rep["gate_pending_rate"] == 0.0
    assert rep["by_role"][0]["agent_role"] == "pm-agent"

    # --- 4) rebuild: everything replays identically ---------------------------
    projections.rebuild()
    assert client.get(f"/api/projects/{pid}/runs/report").json() == rep
    sch3 = client.get("/api/my/schedule").json()
    assert next(i for i in sch3["items"] if i["id"] == it["id"])["due_date"] == day2
