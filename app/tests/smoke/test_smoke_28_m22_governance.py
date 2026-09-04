"""Smoke 28 (M22-I70): the governance & efficiency trio end-to-end — global
search hits (items + comments, Chinese bigrams), the archive read-only gate
with reopen, a project clone roundtrip (members never copied), and bulk edit
where every item emits its own audit events. Closes with a rebuild pass."""
import pytest

from apm.core import projections


@pytest.mark.smoke
def test_smoke_28_m22_governance(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "冒烟治理", "ontology": "software-dev", "requirement": "s28"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    a = client.post(f"/api/projects/{pid}/items", json={"concept_id": "task", "title": "统一登录模块"})
    assert a.status_code == 200, a.text
    item_a = a.json()
    b = client.post(f"/api/projects/{pid}/items", json={"concept_id": "task", "title": "支付对接"})
    assert b.status_code == 200, b.text
    item_b = b.json()
    c = client.post(f"/api/items/{item_a['id']}/comments", json={"body": "登录模块要兼容旧接口"})
    assert c.status_code == 200, c.text

    # --- 1) global search: Chinese hit on title and comment -----------------
    r = client.get("/api/search", params={"q": "登录模块"}).json()
    assert [i["id"] for i in r["items"]] == [item_a["id"]]
    assert len(r["comments"]) == 1

    # --- 2) archive gate: writes 409, reopen restores -----------------------
    assert client.post(f"/api/projects/{pid}/archive").status_code == 200
    assert client.get("/api/projects").json()["projects"] == []  # hidden by default
    assert client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "被拒"}).status_code == 409
    assert client.get(f"/api/projects/{pid}/items").status_code == 200  # reads open
    assert client.post(f"/api/projects/{pid}/reopen").status_code == 200
    assert client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "恢复后新建"}).status_code == 200

    # --- 3) clone roundtrip: skeleton copied, members not -------------------
    cl = client.post(f"/api/projects/{pid}/clone", json={"name": "冒烟治理·克隆"})
    assert cl.status_code == 200, cl.text
    body = cl.json()
    new_pid = body["project"]["id"]
    assert body["counts"]["items"] >= 3
    members = client.get(f"/api/projects/{new_pid}/members").json()["members"]
    assert len(members) == 1  # only the cloning actor
    items_new = client.get(f"/api/projects/{new_pid}/items").json()["items"]
    assert {i["title"] for i in items_new} >= {"统一登录模块", "支付对接"}

    # --- 4) bulk edit: per-item events, one bad id doesn't block the rest ---
    bad_id = "i_does_not_exist"
    bp = client.post(f"/api/projects/{pid}/items/batch-patch",
                     json={"ids": [item_a["id"], item_b["id"], bad_id],
                           "patch": {"priority": "high"}})
    assert bp.status_code == 200, bp.text
    res = bp.json()
    assert res["updated"] == 2 and len(res["results"]) == 3
    failed = next(x for x in res["results"] if not x["ok"])
    assert failed["id"] == bad_id and "not in this project" in failed["error"]
    upd = client.get("/api/events", params={"event_type": "item.updated"}).json()["events"]
    prio = [e for e in upd if e["payload"].get("priority") == "high" and e["project_id"] == pid]
    assert {e["agg_id"] for e in prio} == {item_a["id"], item_b["id"]}

    # --- 5) rebuild: search index, project list and items all replay --------
    projections.rebuild()
    r = client.get("/api/search", params={"q": "登录模块"}).json()
    # the clone's copy shares the title and is legitimately indexed too
    assert item_a["id"] in [i["id"] for i in r["items"]]
    lst = client.get("/api/projects", params={"include_archived": "true"}).json()["projects"]
    assert {p["name"] for p in lst} >= {"冒烟治理", "冒烟治理·克隆"}
    assert client.get(f"/api/items/{item_a['id']}").json()["priority"] == "high"
