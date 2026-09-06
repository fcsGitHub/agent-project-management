"""Smoke 33 (M27): the scheduling-depth trio end-to-end — a lag propagation
chain, the cross-project roadmap reconciled against per-project milestones,
and the burndown replay hand-checked then proven identical after a rebuild."""
from datetime import datetime, timedelta, timezone

import pytest

from apm.core import projections


def _day(offset: int) -> str:
    # M34-I104: auto-scheduled landings skip non-working days — anchor the
    # fixture grid to a Monday so propagation landings stay on workdays.
    base = (datetime.now(timezone.utc) + timedelta(days=7)).date()
    while base.weekday() != 0:
        base -= timedelta(days=1)
    return (base + timedelta(days=offset)).isoformat()


@pytest.mark.smoke
def test_smoke_33_m27_scheduling_depth(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "冒烟排期深化", "ontology": "software-dev", "requirement": "s33"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    # --- 1) lag propagation chain (auto item + depends_on lag=2) -------------
    pred = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "前序",
                             "start_date": _day(0), "due_date": _day(4)}).json()
    succ = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "后继",
                             "start_date": _day(1), "due_date": _day(5)}).json()
    assert client.patch(f"/api/items/{succ['id']}", json={"auto_scheduled": True}).status_code == 200
    rel = client.post(f"/api/items/{succ['id']}/relations",
                      json={"to_item": pred["id"], "relation_type": "depends_on", "lag_days": 2})
    assert rel.status_code == 200, rel.text
    s = client.get(f"/api/items/{succ['id']}").json()
    assert s["start_date"] == _day(7) and s["due_date"] == _day(11)  # 4+1+2, span kept
    # predecessor +3 → relative shift preserves the lag gap
    assert client.patch(f"/api/items/{pred['id']}", json={"due_date": _day(7)}).status_code == 200
    s2 = client.get(f"/api/items/{succ['id']}").json()
    assert s2["start_date"] == _day(10) and s2["due_date"] == _day(14)

    # --- 2) roadmap aggregation reconciles with per-project milestones -------
    ms = client.post(f"/api/projects/{pid}/milestones",
                     json={"title": "冒烟里程碑", "due_date": _day(20)}).json()
    # 5 linked items → 3 done, 2 open (hand-checked burndown below)
    for i in range(3):
        it = client.post(f"/api/projects/{pid}/items",
                         json={"concept_id": "task", "title": f"燃尽项{i}", "milestone_id": ms["id"]}).json()
        assert client.patch(f"/api/items/{it['id']}", json={"status": "done"}).status_code == 200
    for i in range(2):
        client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "未完项", "milestone_id": ms["id"]})

    # a second project with an achieved (past-due, never-overdue) milestone
    r2 = client.post("/api/projects", json={"name": "冒烟排期乙", "ontology": "generic", "requirement": "s33"})
    assert r2.status_code == 200, r2.text
    pid2 = r2.json()["id"]
    ms2 = client.post(f"/api/projects/{pid2}/milestones",
                      json={"title": "已达成", "due_date": _day(-3)}).json()
    assert client.patch(f"/api/milestones/{ms2['id']}", json={"status": "achieved"}).status_code == 200

    rm = client.get("/api/portfolio/roadmap").json()
    rows = {p["project_id"]: p for p in rm["projects"]}
    assert set(rows) >= {pid, pid2}  # both visible projects have milestones
    mine = {m["id"]: m for m in rows[pid]["milestones"]}
    assert mine[ms["id"]]["progress"]["items_total"] == 5
    assert mine[ms["id"]]["progress"]["items_done"] == 3
    assert mine[ms["id"]]["overdue"] is False  # due in the future
    assert rows[pid2]["milestones"][0]["overdue"] is False  # achieved ⇒ never overdue
    # reconcile with the per-project milestone endpoint (same progress caliber)
    proj_ms = client.get(f"/api/projects/{pid}/milestones").json()["milestones"]
    assert next(m for m in proj_ms if m["id"] == ms["id"])["progress"] == mine[ms["id"]]["progress"]

    # --- 3) burndown: hand-computed replay, then rebuild equality ------------
    bd = client.get(f"/api/milestones/{ms['id']}/burndown").json()
    assert bd["total"] == 5 and bd["remaining"] == 2
    assert bd["velocity"]["days"] == 7 and bd["velocity"]["done"] == 3  # all dones today
    assert bd["series"][-1]["remaining"] == 2  # end-of-today tail, hand-checked
    assert bd["ideal"][0]["remaining"] == 5 and bd["ideal"][-1]["remaining"] == 0
    assert len(bd["ideal"]) > len(bd["series"])  # ideal spans the full window

    projections.rebuild()
    bd2 = client.get(f"/api/milestones/{ms['id']}/burndown").json()
    assert bd2 == bd  # replay == live, byte-identical response
    rm2 = client.get("/api/portfolio/roadmap").json()
    mine2 = {m["id"]: m for p in rm2["projects"] if p["project_id"] == pid for m in p["milestones"]}
    assert mine2[ms["id"]]["progress"] == mine[ms["id"]]["progress"]
