"""M22-I69: project archive/reopen — archived projects are read-only via the
pre-emit guard (409 on writes, audit + reopen still allowed, rebuild replays
history untouched) — and clone — skeleton copy through the normal emit paths
with members/assignees deliberately not copied."""
import pytest

from apm.core import projections


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "归档演示", "ontology": "software-dev", "requirement": "I69"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _mk_item(client, pid, title, **kw):
    r = client.post(f"/api/projects/{pid}/items", json={"concept_id": "task", "title": title, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_archive_readonly_gate_and_reopen(client, pid):
    _mk_item(client, pid, "归档前任务")
    assert [p["id"] for p in client.get("/api/projects").json()["projects"]] == [pid]

    assert client.post(f"/api/projects/{pid}/archive").status_code == 200

    # hidden from the default list, visible with include_archived
    assert client.get("/api/projects").json()["projects"] == []
    lst = client.get("/api/projects", params={"include_archived": "true"}).json()["projects"]
    assert [p["status"] for p in lst if p["id"] == pid] == ["archived"]

    # writes are vetoed with 409; reads stay open
    assert client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "x"}).status_code == 409
    assert client.get(f"/api/projects/{pid}/items").status_code == 200
    assert client.get(f"/api/projects/{pid}/report").status_code == 200

    # reopen flips back to active and writes work again
    assert client.post(f"/api/projects/{pid}/reopen").status_code == 200
    assert client.get("/api/projects").json()["projects"][0]["id"] == pid
    assert client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "恢复后任务"}).status_code == 200

    # rebuild replays the archived→active history identically
    projections.rebuild()
    lst = client.get("/api/projects").json()["projects"]
    assert [p["id"] for p in lst] == [pid]
    assert len(client.get(f"/api/projects/{pid}/items").json()["items"]) == 2


def test_clone_copies_skeleton_not_members(client, pid):
    f = client.post(f"/api/projects/{pid}/features", json={"title": "核心功能"}).json()
    m = client.post(f"/api/projects/{pid}/milestones",
                    json={"title": "发布", "due_date": "2026-09-30"}).json()
    i1 = _mk_item(client, pid, "任务甲", priority="high", feature_id=f["id"], milestone_id=m["id"])
    i2 = _mk_item(client, pid, "任务乙", due_date="2026-09-28")
    assert client.post(f"/api/items/{i2['id']}/relations",
                       json={"to_item": i1["id"], "relation_type": "depends_on"}).status_code == 200

    r = client.post(f"/api/projects/{pid}/clone", json={"name": "归档演示·克隆"})
    assert r.status_code == 200, r.text
    body = r.json()
    new_pid = body["project"]["id"]
    # software-dev instantiation seeds one feature ("MVP"), copied alongside ours
    assert body["counts"] == {"features": 2, "milestones": 1, "items": 2, "relations": 1}

    items = client.get(f"/api/projects/{new_pid}/items").json()["items"]
    assert {i["title"] for i in items} == {"任务甲", "任务乙"}
    # assignees/members are NOT copied — cloning must not widen grants
    assert all(not i["assignee_id"] for i in items)
    members = client.get(f"/api/projects/{new_pid}/members").json()["members"]
    assert len(members) == 1  # only the cloning actor as owner

    ms = client.get(f"/api/projects/{new_pid}/milestones").json()["milestones"]
    assert [x["title"] for x in ms] == ["发布"]
    i2n = next(i for i in items if i["title"] == "任务乙")
    rels = client.get(f"/api/items/{i2n['id']}").json()["relations"]
    assert any(x["relation_type"] == "depends_on" for x in rels)

    # source untouched; the clone survives rebuild
    projections.rebuild()
    lst = client.get("/api/projects", params={"include_archived": "true"}).json()["projects"]
    assert {p["name"] for p in lst} >= {"归档演示", "归档演示·克隆"}
    assert len(client.get(f"/api/projects/{new_pid}/items").json()["items"]) == 2
