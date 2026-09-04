"""Smoke 25 (M19-I60): time logging end-to-end — CRUD with soft delete,
fail-closed validation, spent totals on item reads and the board, rebuild
consistency of entries and totals."""
import pytest

from apm.core import projections


@pytest.mark.smoke
def test_smoke_25_time_tracking(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "冒烟工时", "ontology": "software-dev", "requirement": "s25"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    assert client.post("/api/users", json={"id": "u_qa", "name": "QA 王"}).status_code == 200
    r = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "工时冒烟目标", "estimate_hours": 4})
    assert r.status_code == 200, r.text
    item_id = r.json()["id"]

    def switch(uid):
        assert client.post("/api/session/identity", json={"user_id": uid}).status_code == 200

    saved = client.get("/api/users").json()["current"]

    # two identities log time; entries carry the real actor
    e1 = client.post(f"/api/items/{item_id}/time_entries",
                     json={"minutes": 90, "spent_on": "2026-09-04", "note": "设计走查"}).json()
    switch("u_qa")
    e2 = client.post(f"/api/items/{item_id}/time_entries",
                     json={"minutes": 45, "spent_on": "2026-09-05", "note": "用例评审"}).json()
    switch(saved)
    assert e1["user_id"] == "u_admin" and e2["user_id"] == "u_qa"

    # totals + item reads
    listing = client.get(f"/api/items/{item_id}/time_entries").json()
    assert listing["total_minutes"] == 135 and len(listing["entries"]) == 2
    detail = client.get(f"/api/items/{item_id}").json()
    assert detail["spent_minutes"] == 135
    listed = client.get(f"/api/projects/{pid}/items").json()["items"]
    assert next(i for i in listed if i["id"] == item_id)["spent_minutes"] == 135

    # validation gate: zero/negative/oversized minutes and bad dates all 422
    for body in ({"minutes": 0, "spent_on": "2026-09-04"},
                 {"minutes": 2000, "spent_on": "2026-09-04"},
                 {"minutes": 30, "spent_on": "not-a-date"}):
        assert client.post(f"/api/items/{item_id}/time_entries", json=body).status_code == 422

    # soft delete shrinks totals; rebuild reproduces entries and totals exactly
    assert client.delete(f"/api/time_entries/{e2['id']}").status_code == 200
    before = client.get(f"/api/items/{item_id}/time_entries").json()
    assert before["total_minutes"] == 90
    board_before = next(i for b in client.get(f"/api/projects/{pid}/board").json()["buckets"]
                        for i in b["items"] if i["id"] == item_id)["spent_minutes"]
    projections.rebuild()
    after = client.get(f"/api/items/{item_id}/time_entries").json()
    assert [(x["id"], x["minutes"], x["user_id"]) for x in after["entries"]] == \
           [(x["id"], x["minutes"], x["user_id"]) for x in before["entries"]]
    assert after["total_minutes"] == 90
    board_after = next(i for b in client.get(f"/api/projects/{pid}/board").json()["buckets"]
                       for i in b["items"] if i["id"] == item_id)["spent_minutes"]
    assert board_after == board_before == 90
