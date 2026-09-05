"""Smoke 31 (M25): the planning-governance trio end-to-end — baseline
variance table reconciliation (+3/-1 rows and summary), blocks closure
matrix with a named refusal, and list pagination (unbounded default,
total + limit/offset). Closes with a rebuild pass."""
import pytest

from apm.core import projections


@pytest.mark.smoke
def test_smoke_31_m25_planning_governance(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "冒烟计划治理", "ontology": "software-dev", "requirement": "s31"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    # --- 1) baseline variance reconciliation ---------------------------------
    # three scheduled items, one baseline, then move two of them
    ids = {}
    for title, due in (("甲任务", "2026-09-10"), ("乙任务", "2026-09-12"), ("丙任务", "2026-09-15")):
        it = client.post(f"/api/projects/{pid}/items",
                         json={"concept_id": "task", "title": title, "due_date": due})
        assert it.status_code == 200, it.text
        ids[title] = it.json()["id"]
    assert client.post(f"/api/projects/{pid}/baseline").status_code == 200
    client.patch(f"/api/items/{ids['甲任务']}", json={"due_date": "2026-09-13"})  # +3 days
    client.patch(f"/api/items/{ids['乙任务']}", json={"due_date": "2026-09-11"})  # -1 day

    var = client.get(f"/api/projects/{pid}/baseline-variance").json()
    rows = {v["item_id"]: v for v in var["variances"]}
    assert set(rows) == {ids["甲任务"], ids["乙任务"]}  # 丙未动 → omitted
    assert rows[ids["甲任务"]]["due_deviation"] == 3
    assert rows[ids["乙任务"]]["due_deviation"] == -1
    assert var["summary"] == {"count": 2, "max_due_delay": 3}
    # include_same flips on: all three listed, summary counts them
    full = client.get(f"/api/projects/{pid}/baseline-variance",
                      params={"include_same": "1"}).json()
    assert len(full["variances"]) == 3 and full["summary"]["count"] == 3

    # --- 2) blocks closure matrix ---------------------------------------------
    blocker = client.post(f"/api/projects/{pid}/items",
                          json={"concept_id": "task", "title": "阻塞项"}).json()
    blocked = client.post(f"/api/projects/{pid}/items",
                          json={"concept_id": "task", "title": "被阻塞项"}).json()
    assert client.post(f"/api/items/{blocker['id']}/relations",
                       json={"to_item": blocked["id"], "relation_type": "blocks", "lag_days": 2}
                       ).status_code == 200

    # unfinished blocker → completion refused, by name
    ref = client.patch(f"/api/items/{blocked['id']}", json={"status": "done"})
    assert ref.status_code == 422 and "blocked by 阻塞项" in ref.json()["detail"]
    # cancelling the blocked item itself is fine (giving up ≠ finishing)
    assert client.patch(f"/api/items/{blocked['id']}", json={"status": "cancelled"}).status_code == 200
    # blocker completes → next blocked item may complete
    blocker2 = client.post(f"/api/projects/{pid}/items",
                           json={"concept_id": "task", "title": "解锁项"}).json()
    blocked2 = client.post(f"/api/projects/{pid}/items",
                           json={"concept_id": "task", "title": "待完成项"}).json()
    client.post(f"/api/items/{blocker2['id']}/relations",
                json={"to_item": blocked2["id"], "relation_type": "blocks"})
    assert client.patch(f"/api/items/{blocker2['id']}", json={"status": "done"}).status_code == 200
    assert client.patch(f"/api/items/{blocked2['id']}", json={"status": "done"}).status_code == 200
    # lag rides on the detail payload
    rels = client.get(f"/api/items/{blocker['id']}").json()["relations"]
    assert any(x["to_item"] == blocked["id"] and x["relation_type"] == "blocks"
               and x["lag_days"] == 2 for x in rels)

    # --- 3) pagination: unbounded default, total + limit/offset ---------------
    lst = client.get(f"/api/projects/{pid}/items").json()
    assert lst["total"] == 7 and len(lst["items"]) == 7  # default stays all
    p1 = client.get(f"/api/projects/{pid}/items", params={"limit": 5, "offset": 0}).json()
    p2 = client.get(f"/api/projects/{pid}/items", params={"limit": 5, "offset": 5}).json()
    assert p1["total"] == 7 and len(p1["items"]) == 5
    assert p2["total"] == 7 and len(p2["items"]) == 2
    assert [i["id"] for i in p1["items"]] + [i["id"] for i in p2["items"]] == \
        [i["id"] for i in lst["items"]]  # no overlap, no gap
    # limit clamped to 1-200; offset beyond the end is empty
    assert len(client.get(f"/api/projects/{pid}/items", params={"limit": 999}).json()["items"]) == 7
    assert len(client.get(f"/api/projects/{pid}/items", params={"limit": 0}).json()["items"]) == 1
    assert client.get(f"/api/projects/{pid}/items",
                      params={"limit": 5, "offset": 100}).json()["items"] == []

    # --- 4) rebuild: variance compares, guard and pagination all replay -------
    projections.rebuild()
    var2 = client.get(f"/api/projects/{pid}/baseline-variance").json()
    assert {v["item_id"]: v["due_deviation"] for v in var2["variances"]} == \
        {ids["甲任务"]: 3, ids["乙任务"]: -1}
    b2 = client.get(f"/api/items/{blocker['id']}").json()
    assert any(x["relation_type"] == "blocks" and x["lag_days"] == 2 for x in b2["relations"])
    fresh = client.post(f"/api/projects/{pid}/items",
                        json={"concept_id": "task", "title": "重建后再造"}).json()
    ref2 = client.post(f"/api/items/{fresh['id']}/relations",
                       json={"to_item": fresh["id"], "relation_type": "blocked_by"})
    assert ref2.status_code == 422  # blocked_by stays unregistered after rebuild
    assert client.get(f"/api/projects/{pid}/items",
                      params={"limit": 3, "offset": 3}).json()["total"] == 8
