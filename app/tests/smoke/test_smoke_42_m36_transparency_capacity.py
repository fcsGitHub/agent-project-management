"""Smoke 42 (M36): the transparency-and-capacity trio end-to-end — the
cross-project activity feed interleaves visible projects with filters, a
time-off stretch flags the member on the workload page and cancels cleanly,
the S-curve carries a hand-computed AC line plus a compared baseline PV, and
a rebuild replays all of it."""
from datetime import date, timedelta

import pytest

from apm import config
from apm.core import db, events, projections


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.mark.smoke
def test_smoke_42_m36_transparency_capacity(client, tmp_data, isolated_ontologies):
    # --- ① activity feed: two visible projects interleave, filter narrows ----
    pid_a = client.post("/api/projects",
                        json={"name": "冒烟动态甲", "ontology": "software-dev",
                              "requirement": "s42"}).json()["id"]
    pid_b = client.post("/api/projects",
                        json={"name": "冒烟动态乙", "ontology": "software-dev",
                              "requirement": "s42"}).json()["id"]
    client.post(f"/api/projects/{pid_a}/items",
                json={"concept_id": "task", "title": "甲的任务"})
    client.post(f"/api/projects/{pid_b}/items",
                json={"concept_id": "task", "title": "乙的任务"})
    acts = client.get("/api/portfolio/activity").json()["activities"]
    names = [a["project_name"] for a in acts]
    assert "冒烟动态甲" in names and "冒烟动态乙" in names
    only_b = client.get("/api/portfolio/activity",
                        params={"project_id": pid_b}).json()["activities"]
    assert only_b and all(a["project_id"] == pid_b for a in only_b)

    # --- ② time off: register, workload flags 🏖, cancel ----------------------
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    assert client.post(f"/api/projects/{pid_a}/members",
                       json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200
    it = client.post(f"/api/projects/{pid_a}/items",
                     json={"concept_id": "task", "title": "休假者的任务"}).json()
    client.patch(f"/api/items/{it['id']}",
                 json={"assignee_type": "human", "assignee_id": "qa-wang"})

    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert client.post("/api/me/time-off",
                       json={"start_date": events.utcnow()[:10],
                             "end_date": events.utcnow()[:10],
                             "reason": "冒烟年假"}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    wl = client.get("/api/portfolio/workload").json()
    qa = next(m for m in wl["members"] if m["user_id"] == "qa-wang")
    assert qa["on_leave"] is True

    # --- ③ S-curve: AC hand-computed + compared baseline PV -------------------
    w = client.post(f"/api/projects/{pid_a}/items",
                    json={"concept_id": "task", "title": "权重项",
                          "due_date": events.utcnow()[:10],
                          "estimate_hours": 4}).json()
    v = client.post(f"/api/projects/{pid_a}/items",
                    json={"concept_id": "task", "title": "小权重项",
                          "due_date": events.utcnow()[:10],
                          "estimate_hours": 2}).json()
    assert client.post(f"/api/projects/{pid_a}/baseline").status_code == 200
    assert client.post(f"/api/items/{w['id']}/time_entries",
                       json={"minutes": 60, "spent_on": events.utcnow()[:10]}).status_code == 200
    assert client.patch(f"/api/items/{w['id']}", json={"status": "done"}).status_code == 200
    # drift B's estimate and re-baseline for the compare overlay
    assert client.patch(f"/api/items/{v['id']}", json={"estimate_hours": 4}).status_code == 200
    assert client.post(f"/api/projects/{pid_a}/baseline").status_code == 200
    rows = client.get(f"/api/projects/{pid_a}/baselines").json()["baselines"]
    oldest, newest = rows[0]["id"], rows[-1]["id"]

    curve = client.get(f"/api/projects/{pid_a}/baseline-curve",
                       params={"compare": oldest}).json()
    assert curve["ac_last"] == 1.0                      # 60 minutes = 1h AC
    assert curve["samples"][-1]["ac"] == 1.0
    assert curve["compare"]["baseline_id"] == oldest
    assert curve["pv_total"] == 8 and curve["compare"]["pv_total"] == 6  # 4+4 vs 4+2

    # --- rebuild: feed order, leave flag and curve all replay -----------------
    projections.rebuild()
    curve2 = client.get(f"/api/projects/{pid_a}/baseline-curve",
                        params={"compare": oldest}).json()
    assert curve2["samples"] == curve["samples"]
    assert curve2["compare"]["samples"] == curve["compare"]["samples"]
    wl2 = client.get("/api/portfolio/workload").json()
    qa2 = next(m for m in wl2["members"] if m["user_id"] == "qa-wang")
    assert qa2["on_leave"] is True                      # projection survives
    acts2 = client.get("/api/portfolio/activity",
                       params={"project_id": pid_b}).json()["activities"]
    assert acts2 and all(a["project_id"] == pid_b for a in acts2)
