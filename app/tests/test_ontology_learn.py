"""M4-I14 ontology learning: learn → candidates with provenance → apply → version+1."""
from __future__ import annotations

import pytest

from apm.core import events


@pytest.fixture()
def project(client):
    r = client.post(
        "/api/projects",
        json={"name": "本体学习演示", "ontology": "software-dev", "requirement": "演示归纳信号"},
    )
    assert r.status_code == 200
    return r.json()


def _create_item(client, pid, concept_id, title, **kw):
    r = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": concept_id, "title": title, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_learn_detects_all_four_rules(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]

    # L1: bug items carry priority, but the bug concept declares no priority field.
    _create_item(client, pid, "bug", "登录崩溃", priority="P1")
    _create_item(client, pid, "bug", "上传失败", priority="P2")

    # L2: a legacy relation type that the ontology never registered.
    # (I78 promoted blocks/precedes/relates into the kernel, so the unregistered
    # probe is now blocked_by — deliberately absent, stored one-way as blocks.)
    items = client.get(f"/api/projects/{pid}/items").json()["items"]
    bug_id = [i for i in items if i["concept_id"] == "bug"][0]["id"]
    task_id = _create_item(client, pid, "task", "修复登录崩溃")["id"]
    events.emit(event_type="item.related", agg_type="relation", agg_id="rel_legacy1",
                project_id=pid,
                payload={"from_item": bug_id, "to_item": task_id, "relation_type": "blocked_by"})

    # L3: published asset of kind test-suite linked to artifact kind `code`
    # (task declares `code` without deposits_to).
    events.emit(event_type="asset.drafted", agg_type="asset", agg_id="asset_l3", project_id=pid,
                payload={"library": "test", "kind": "test-suite", "title": "冒烟套件",
                         "tags": [], "commit": "c0ffee", "status": "draft"})
    events.emit(event_type="asset.published", agg_type="asset", agg_id="asset_l3",
                payload={"status": "published", "title": "冒烟套件", "library": "test",
                         "kind": "test-suite"})
    events.emit(event_type="asset.linked", agg_type="asset", agg_id="asset_l3", project_id=pid,
                payload={"type": "provenance", "target_type": "artifact",
                         "target": {"project_id": pid, "path": "artifacts/code/app.py",
                                    "commit": "c0ffee", "conversation_id": None}})

    # L4: a run used release-agent on a task item (task binds only planner/dev).
    events.emit(event_type="run.requested", agg_type="run", agg_id="run_l4", project_id=pid,
                payload={"feature_id": None, "item_id": task_id, "conversation_id": "c_x",
                         "agent_role": "release-agent", "graph_node_id": "development",
                         "instruction": "整理发布说明"})

    r = client.post("/api/ontologies/software-dev/learn")
    assert r.status_code == 200, r.text
    scan = r.json()
    assert scan["scanned"]["projects"] == 1 and scan["scanned"]["items"] == 3

    by_id = {c["id"]: c for c in scan["candidates"]}
    assert "add-field:bug:priority" in by_id
    assert by_id["add-field:bug:priority"]["provenance"]["support"] == 2
    assert "register-relation:blocked_by" in by_id
    assert by_id["register-relation:blocked_by"]["patch"]["relation"]["domain"] == "bug"
    assert "wire-deposit:task:code:test-suite" in by_id
    assert "add-role:task:release-agent" in by_id
    for c in scan["candidates"]:
        assert c["provenance"]["rule"].startswith("L")

    # Observations: requirement/milestone got no items in this project.
    assert "requirement" in scan["observations"]["unused_concepts"]


def test_apply_bumps_version_and_unlocks_relation(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    _create_item(client, pid, "bug", "接口超时", priority="P0")
    item = client.get(f"/api/projects/{pid}/items").json()["items"][0]

    # The unregistered relation type is rejected before the ontology learns it
    # (blocks joined the kernel in I78; blocked_by stays unregistered by design).
    r = client.post(f"/api/items/{item['id']}/relations",
                    json={"to_item": item["id"], "relation_type": "blocked_by"})
    assert r.status_code == 422

    events.emit(event_type="item.related", agg_type="relation", agg_id="rel_legacy2",
                project_id=pid,
                payload={"from_item": item["id"], "to_item": item["id"],
                         "relation_type": "blocked_by"})
    scan = client.post("/api/ontologies/software-dev/learn").json()
    ids = [c["id"] for c in scan["candidates"]]

    r = client.post("/api/ontologies/software-dev/apply", json={"candidate_ids": ids})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["version"] == 2 and not out["errors"]
    assert {a["id"] for a in out["applied"]} == set(ids)

    # ontology.updated lands in the audit stream with diff summary.
    evs = client.get("/api/events", params={"agg_type": "ontology"}).json()["events"]
    upd = [e for e in evs if e["event_type"] == "ontology.updated"]
    assert upd and upd[0]["payload"]["version"] == 2
    assert upd[0]["payload"]["previous_version"] == 1
    assert len(upd[0]["payload"]["applied"]) == len(ids)

    # The newly registered relation type now passes validation (data unlocked).
    r = client.post(f"/api/items/{item['id']}/relations",
                    json={"to_item": item["id"], "relation_type": "blocked_by"})
    assert r.status_code == 200, r.text

    # Idempotence: re-learn no longer proposes applied candidates.
    scan2 = client.post("/api/ontologies/software-dev/learn").json()
    assert not any(c["id"] in ids for c in scan2["candidates"])


def test_apply_rejects_unknown_and_stale_candidates(client, tmp_data, isolated_ontologies, project):
    r = client.post("/api/ontologies/software-dev/apply",
                    json={"candidate_ids": ["add-field:bug:priority"]})
    assert r.status_code == 422  # no such candidate in a fresh scan
    r = client.post("/api/ontologies/software-dev/apply", json={"candidate_ids": []})
    assert r.status_code == 422


def test_learn_rejects_invalid_ontology(client, tmp_data, isolated_ontologies):
    (isolated_ontologies / "broken.yaml").write_text(
        "name: broken\nconcepts: []\n", encoding="utf-8")
    r = client.post("/api/ontologies/broken/learn")
    assert r.status_code == 422
