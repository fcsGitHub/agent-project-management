"""Smoke 29 (M23-I73): the planning & overview trio end-to-end — a Gantt
baseline snapshot that stays fixed while dates drift, the portfolio report
reconciling with per-project numbers, and a markdown-toolbar-authored comment
stored byte-identically. Closes with a rebuild pass."""
import pytest

from apm.core import projections


@pytest.mark.smoke
def test_smoke_29_m23_planning_overview(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "冒烟计划对照", "ontology": "software-dev", "requirement": "s29"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    p2 = client.post("/api/projects", json={"name": "冒烟组合乙", "ontology": "software-dev", "requirement": "s29b"}).json()

    a = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "架构设计", "start_date": "2026-09-01", "due_date": "2026-09-05"})
    assert a.status_code == 200, a.text
    item_a = a.json()
    client.post(f"/api/projects/{p2['id']}/items", json={"concept_id": "task", "title": "独立任务"})

    # --- 1) baseline: snapshot fixed, later drift visible --------------------
    assert client.post(f"/api/projects/{pid}/baseline").status_code == 200
    snap = client.get(f"/api/projects/{pid}/baseline").json()["baseline"]
    assert snap["items"][item_a["id"]] == ["2026-09-01", "2026-09-05"]
    # dates drift +3 — the snapshot must not move
    assert client.patch(f"/api/items/{item_a['id']}",
                        json={"start_date": "2026-09-04", "due_date": "2026-09-08"}).status_code == 200
    snap2 = client.get(f"/api/projects/{pid}/baseline").json()["baseline"]
    assert snap2["items"][item_a["id"]] == ["2026-09-01", "2026-09-05"]

    # --- 2) portfolio report reconciles with per-project numbers -------------
    client.post(f"/api/items/{item_a['id']}/time_entries", json={"minutes": 90, "spent_on": "2026-09-05"})
    rep = client.get("/api/portfolio/report").json()
    by_id = {p["project_id"]: p for p in rep["projects"]}
    assert by_id[pid]["timelog_minutes"] == 90 and by_id[p2["id"]]["timelog_minutes"] == 0
    assert by_id[pid]["items_active"] == 1 and by_id[p2["id"]]["items_active"] == 1
    assert rep["totals"]["timelog_minutes"] == sum(p["timelog_minutes"] for p in rep["projects"])
    assert rep["totals"]["items_active"] == sum(p["items_active"] for p in rep["projects"])

    # --- 3) toolbar-authored comment: tool-inserted markdown stays raw -------
    body = "**加粗结论** 与待办：\n- [ ] 落地基线\n> 引用上下文"
    cm = client.post(f"/api/items/{item_a['id']}/comments", json={"body": body})
    assert cm.status_code == 200, cm.text
    assert cm.json()["body"] == body  # plain text, byte-identical

    # --- 4) rebuild: baseline, portfolio and comment all replay --------------
    projections.rebuild()
    snap3 = client.get(f"/api/projects/{pid}/baseline").json()["baseline"]
    assert snap3["items"][item_a["id"]] == ["2026-09-01", "2026-09-05"]
    rep2 = client.get("/api/portfolio/report").json()
    assert rep2["totals"]["timelog_minutes"] == 90
    comments = client.get(f"/api/items/{item_a['id']}/comments").json()["comments"]
    assert comments[0]["body"] == body
