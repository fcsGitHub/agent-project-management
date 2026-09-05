"""M26-I82 (docs/01 §Y.3): optional concept-level transition whitelist —
declared lists are fail-closed (OpenProject status-flow semantics simplified
to concept level); undeclared concepts stay fully open; every entry point
inherits the guard because it lives inside change_status."""
import pytest

from apm.core import projections


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "流转演示", "ontology": "software-dev", "requirement": "I82"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _mk(client, pid, concept, title):
    r = client.post(f"/api/projects/{pid}/items", json={"concept_id": concept, "title": title})
    assert r.status_code == 200, r.text
    return r.json()


def test_transition_whitelist_matrix(client, pid):
    bug = _mk(client, pid, "bug", "白名单缺陷")
    # declared whitelist is fail-closed: no open→verified skip
    r = client.patch(f"/api/items/{bug['id']}", json={"status": "verified"})
    assert r.status_code == 422
    assert "transition" in r.json()["detail"]
    # the declared path works step by step
    assert client.patch(f"/api/items/{bug['id']}", json={"status": "fixing"}).status_code == 200
    assert client.patch(f"/api/items/{bug['id']}", json={"status": "fixed"}).status_code == 200
    assert client.patch(f"/api/items/{bug['id']}", json={"status": "verified"}).status_code == 200

    # undeclared concept (task) keeps every transition legal
    task = _mk(client, pid, "task", "无限制任务")
    assert client.patch(f"/api/items/{task['id']}", json={"status": "done"}).status_code == 200

    # transitions ride the ontology dict (declared vs empty)
    onto = client.get(f"/api/projects/{pid}/ontology").json()
    bug_def = next(c for c in onto["concepts"] if c["id"] == "bug")
    assert {"from": "open", "to": "fixing"} in bug_def["transitions"]
    task_def = next(c for c in onto["concepts"] if c["id"] == "task")
    assert task_def["transitions"] == []


def test_whitelist_via_batch_and_rebuild(client, pid):
    b1 = _mk(client, pid, "bug", "批量一")
    b2 = _mk(client, pid, "bug", "批量二")
    # batch goes through patch_item → change_status, so the guard applies per
    # item and is reported per item (no rollback semantics change)
    body = client.post(f"/api/projects/{pid}/items/batch-patch",
                       json={"ids": [b1["id"], b2["id"]], "patch": {"status": "verified"}}).json()
    assert body["updated"] == 0
    assert all(not x["ok"] for x in body["results"])

    # the guard survives rebuild, and a legal path still completes
    client.patch(f"/api/items/{b1['id']}", json={"status": "fixing"})
    projections.rebuild()
    assert client.patch(f"/api/items/{b1['id']}", json={"status": "verified"}).status_code == 422
    assert client.patch(f"/api/items/{b2['id']}", json={"status": "verified"}).status_code == 422
