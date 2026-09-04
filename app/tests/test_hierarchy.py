"""M24-I74: work-item hierarchy — parent must exist and stay in-project,
re-parenting cannot create a cycle, direct-children and recursive-descendant
scopes work, and the tree survives rebuild."""
import pytest

from apm.core import projections


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "层级演示", "ontology": "software-dev", "requirement": "I74"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _mk(client, pid, title, **kw):
    r = client.post(f"/api/projects/{pid}/items", json={"concept_id": "task", "title": title, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_parent_validation_matrix(client, pid):
    parent = _mk(client, pid, "父任务")
    other = client.post("/api/projects",
                        json={"name": "别的项目", "ontology": "software-dev", "requirement": "x"}).json()

    # create: unknown parent / cross-project parent
    assert client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "x", "parent_id": "i_nope"}).status_code == 422
    foreign = client.post(f"/api/projects/{other['id']}/items",
                          json={"concept_id": "task", "title": "外项目任务"}).json()
    assert client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "x", "parent_id": foreign["id"]}).status_code == 422

    # valid create → child of parent
    child = _mk(client, pid, "子任务", parent_id=parent["id"])
    assert child["parent_id"] == parent["id"]

    # re-parent: unknown / cross-project / self / cycle via child
    assert client.patch(f"/api/items/{child['id']}",
                        json={"parent_id": "i_nope"}).status_code == 422
    assert client.patch(f"/api/items/{child['id']}",
                        json={"parent_id": foreign["id"]}).status_code == 422
    assert client.patch(f"/api/items/{child['id']}",
                        json={"parent_id": child["id"]}).status_code == 422
    # making the ancestor a descendant of its own child would loop — rejected
    assert client.patch(f"/api/items/{parent['id']}",
                        json={"parent_id": child["id"]}).status_code == 422

    # legal re-parent applies and survives rebuild
    grand = _mk(client, pid, "孙任务", parent_id=child["id"])
    assert client.patch(f"/api/items/{grand['id']}",
                        json={"parent_id": parent["id"]}).status_code == 200
    projections.rebuild()
    assert client.get(f"/api/items/{grand['id']}").json()["parent_id"] == parent["id"]


def test_children_and_descendant_scopes(client, pid):
    root = _mk(client, pid, "根")
    mid = _mk(client, pid, "中层", parent_id=root["id"])
    leaf = _mk(client, pid, "叶子", parent_id=mid["id"])
    stray = _mk(client, pid, "旁系")

    direct = client.get(f"/api/projects/{pid}/items", params={"parent": root["id"]}).json()["items"]
    assert [i["id"] for i in direct] == [mid["id"]]

    desc = client.get(f"/api/projects/{pid}/items", params={"descendants": root["id"]}).json()["items"]
    assert {i["id"] for i in desc} == {mid["id"], leaf["id"]}
    assert all(i["id"] != root["id"] and i["id"] != stray["id"] for i in desc)

    # deep descendants from the middle node
    desc2 = client.get(f"/api/projects/{pid}/items", params={"descendants": mid["id"]}).json()["items"]
    assert {i["id"] for i in desc2} == {leaf["id"]}
