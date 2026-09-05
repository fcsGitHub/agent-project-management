"""Smoke 30 (M24-I76): the structure & data-management trio end-to-end —
subtask hierarchy with cycle rejection, CSV import with per-line error
isolation, and multi-baseline history. Closes with a rebuild pass."""
import pytest

from apm.core import projections


@pytest.mark.smoke
def test_smoke_30_m24_structure(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "冒烟结构", "ontology": "software-dev", "requirement": "s30"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    # --- 1) hierarchy: parent → children → cycle rejected --------------------
    root = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "根任务", "due_date": "2026-09-15"})
    assert root.status_code == 200, root.text
    root_id = root.json()["id"]
    child = client.post(f"/api/projects/{pid}/items",
                        json={"concept_id": "task", "title": "子任务", "parent_id": root_id})
    assert child.status_code == 200, child.text
    child_id = child.json()["id"]
    assert client.patch(f"/api/items/{root_id}", json={"parent_id": child_id}).status_code == 422
    direct = client.get(f"/api/projects/{pid}/items", params={"parent": root_id}).json()["items"]
    assert [i["id"] for i in direct] == [child_id]

    # --- 2) CSV import: per-line isolation, parent by title ------------------
    csv_text = (
        "title,concept_id,status,priority,start_date,due_date,estimate_hours,parent_title\n"
        "导入功能,task,,high,2026-09-10,2026-09-12,3,\n"
        "导入子步骤,task,,,,,,导入功能\n"
        "坏数据,task,,,2026-99-01,,,\n"
    )
    imp = client.post(f"/api/projects/{pid}/items/import", json={"csv": csv_text})
    assert imp.status_code == 200, imp.text
    body = imp.json()
    assert body["created"] == 2 and body["failed"] == 1
    imported = {i["title"]: i for i in client.get(f"/api/projects/{pid}/items").json()["items"]}
    assert imported["导入子步骤"]["parent_id"] == imported["导入功能"]["id"]

    # --- 3) multi-baseline history -------------------------------------------
    assert client.post(f"/api/projects/{pid}/baseline").status_code == 200
    client.patch(f"/api/items/{root_id}", json={"due_date": "2026-09-20"})
    assert client.post(f"/api/projects/{pid}/baseline").status_code == 200
    lst = client.get(f"/api/projects/{pid}/baselines").json()["baselines"]
    assert len(lst) == 2
    due0 = lst[0]["snapshot"]["items"][root_id][1]
    due1 = lst[1]["snapshot"]["items"][root_id][1]
    assert due0 != due1 and due1 == "2026-09-20"  # old snapshot untouched
    newest = client.get(f"/api/projects/{pid}/baseline").json()
    assert newest["baseline_id"] == lst[-1]["id"]

    # --- 4) rebuild: hierarchy, import results and baselines all replay ------
    projections.rebuild()
    assert client.get(f"/api/items/{root_id}").json()["parent_id"] is None
    assert client.get(f"/api/items/{child_id}").json()["parent_id"] == root_id
    assert imported["导入子步骤"]["parent_id"] == imported["导入功能"]["id"]
    lst2 = client.get(f"/api/projects/{pid}/baselines").json()["baselines"]
    assert len(lst2) == 2 and lst2[1]["snapshot"]["items"][root_id][1] == "2026-09-20"
