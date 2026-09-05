"""M25-I78 (docs/01 §X.2): blocks closure — completing a blocked item is
refused while the blocker is unfinished; relations carry lag_days; the guard
and the data both survive rebuild."""
import pytest

from apm.core import projections


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "闭锁演示", "ontology": "software-dev", "requirement": "I78"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _mk(client, pid, title):
    r = client.post(f"/api/projects/{pid}/items", json={"concept_id": "task", "title": title})
    assert r.status_code == 200, r.text
    return r.json()


def test_blocks_closure_matrix(client, pid):
    blocker = _mk(client, pid, "阻塞者")
    blocked = _mk(client, pid, "被阻塞")
    r = client.post(f"/api/items/{blocker['id']}/relations",
                    json={"to_item": blocked["id"], "relation_type": "blocks"})
    assert r.status_code == 200, r.text

    # unfinished blocker → completing the blocked item is refused, by name
    r = client.patch(f"/api/items/{blocked['id']}", json={"status": "done"})
    assert r.status_code == 422, r.text
    assert "blocked by 阻塞者" in r.json()["detail"]

    # cancelling the blocked item itself stays allowed (giving up ≠ finishing)
    assert client.patch(f"/api/items/{blocked['id']}",
                        json={"status": "cancelled"}).status_code == 200

    # once the blocker completes, closure goes through
    blocker2 = _mk(client, pid, "完成阻塞者")
    blocked2 = _mk(client, pid, "解锁项")
    client.post(f"/api/items/{blocker2['id']}/relations",
                json={"to_item": blocked2["id"], "relation_type": "blocks"})
    assert client.patch(f"/api/items/{blocker2['id']}", json={"status": "done"}).status_code == 200
    assert client.patch(f"/api/items/{blocked2['id']}", json={"status": "done"}).status_code == 200


def test_relation_lag_days_roundtrip(client, pid):
    a = _mk(client, pid, "前序")
    b = _mk(client, pid, "后继")
    r = client.post(f"/api/items/{a['id']}/relations",
                    json={"to_item": b["id"], "relation_type": "precedes", "lag_days": 3})
    assert r.status_code == 200, r.text
    rel = next(x for x in r.json()["relations"]
               if x["relation_type"] == "precedes" and x["to_item"] == b["id"])
    assert rel["lag_days"] == 3

    # omitted lag is stored as NULL, not 0 (OpenProject: lag is optional)
    c = _mk(client, pid, "无间隔")
    r = client.post(f"/api/items/{a['id']}/relations",
                    json={"to_item": c["id"], "relation_type": "precedes"})
    rel = next(x for x in r.json()["relations"]
               if x["relation_type"] == "precedes" and x["to_item"] == c["id"])
    assert rel["lag_days"] is None


def test_relations_survive_rebuild_and_still_guard(client, pid):
    blocker = _mk(client, pid, "重建阻塞者")
    blocked = _mk(client, pid, "重建被阻塞")
    client.post(f"/api/items/{blocker['id']}/relations",
                json={"to_item": blocked["id"], "relation_type": "blocks", "lag_days": 1})
    projections.rebuild()

    detail = client.get(f"/api/items/{blocker['id']}").json()
    rel = next(x for x in detail["relations"] if x["to_item"] == blocked["id"])
    assert rel["relation_type"] == "blocks" and rel["lag_days"] == 1

    r = client.patch(f"/api/items/{blocked['id']}", json={"status": "done"})
    assert r.status_code == 422
