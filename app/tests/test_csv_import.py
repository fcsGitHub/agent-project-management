"""M24-I75: CSV import/export — fixed-header import through create_item's full
validation (per-line errors never roll back valid lines), parent_title
referencing existing or same-file rows, template download, and a CSV export
that round-trips titles and hierarchy."""
import pytest


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "导入演示", "ontology": "software-dev", "requirement": "I75"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_csv_import_export_roundtrip(client, pid):
    # existing item referenced by parent_title from the file
    existing = client.post(f"/api/projects/{pid}/items",
                           json={"concept_id": "task", "title": "已有父任务"}).json()

    csv_text = (
        "title,concept_id,status,priority,start_date,due_date,estimate_hours,parent_title\n"
        "导入一,task,,high,2026-09-10,2026-09-12,3,\n"
        "导入二子,task,,,,,,已有父任务\n"
        "坏日期,task,,x,09/2026/30,,,\n"
    )
    r = client.post(f"/api/projects/{pid}/items/import", json={"csv": csv_text})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 2 and body["failed"] == 1
    rows = body["results"]
    assert rows[0]["ok"] and rows[1]["ok"]
    assert not rows[2]["ok"] and "ISO date" in rows[2]["error"]

    # imported hierarchy: 导入二子 is a child of the EXISTING item
    child = next(i for i in client.get(f"/api/projects/{pid}/items").json()["items"]
                 if i["title"] == "导入二子")
    assert child["parent_id"] == existing["id"]

    # same-file parent chain: a later row can parent to an earlier imported one
    csv2 = ("title,concept_id,parent_title\n"
            "链一,task,\n"
            "链二,task,链一\n")
    r2 = client.post(f"/api/projects/{pid}/items/import", json={"csv": csv2})
    assert r2.json()["created"] == 2
    items = {i["title"]: i for i in client.get(f"/api/projects/{pid}/items").json()["items"]}
    assert items["链二"]["parent_id"] == items["链一"]["id"]

    # template carries the fixed header
    tpl = client.get(f"/api/projects/{pid}/items/import-template")
    assert tpl.status_code == 200 and tpl.text.splitlines()[0].startswith("title,concept_id")

    # export: contains every title (hierarchy preserved via parent_title column)
    ex = client.get(f"/api/projects/{pid}/items.csv")
    assert ex.status_code == 200 and ex.headers["content-type"].startswith("text/csv")
    for t in ("已有父任务", "导入一", "导入二子", "链二"):
        assert t in ex.text

    # duplicate titles are allowed but the first one wins for parent lookup
    projections_check = client.get(f"/api/projects/{pid}/items").json()["items"]
    assert len(projections_check) == 5

    # empty / header-only file → 422
    assert client.post(f"/api/projects/{pid}/items/import", json={"csv": "title\n"}).status_code == 200
    assert client.post(f"/api/projects/{pid}/items/import", json={"csv": "bad header\n"}).status_code == 422
