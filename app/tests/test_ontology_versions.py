"""M4-I15 ontology versioning: snapshots, semantic diff, impact analysis, history."""
from __future__ import annotations

import pytest
import yaml

from apm.core import events


@pytest.fixture()
def project(client):
    r = client.post(
        "/api/projects",
        json={"name": "版本化演示", "ontology": "software-dev", "requirement": "diff 演示"},
    )
    assert r.status_code == 200
    return r.json()


def _apply_all_candidates(client, name: str, kinds: set[str]) -> dict:
    scan = client.post(f"/api/ontologies/{name}/learn").json()
    ids = [c["id"] for c in scan["candidates"] if c["kind"] in kinds]
    assert ids, f"expected candidates of kinds {kinds}, got {scan['candidates']}"
    r = client.post(f"/api/ontologies/{name}/apply", json={"candidate_ids": ids})
    assert r.status_code == 200, r.text
    return r.json()


def _emit_legacy_relation(client, pid: str, relation_type: str = "blocked_by") -> str:
    """Seed one relation row of a type the ontology never registered (legacy data).
    I78 moved blocks/precedes/relates into the kernel, so the probe is now
    blocked_by — deliberately absent (stored one-way as blocks)."""
    items = client.get(f"/api/projects/{pid}/items").json()["items"]
    assert items, "need at least one item to attach the relation to"
    events.emit(event_type="item.related", agg_type="relation", agg_id=f"rel_{relation_type}",
                project_id=pid,
                payload={"from_item": items[0]["id"], "to_item": items[0]["id"],
                         "relation_type": relation_type})
    return items[0]["id"]


def test_history_and_diff_after_two_applies(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    client.post(f"/api/projects/{pid}/items",
                json={"concept_id": "bug", "title": "崩溃", "priority": "P1"})
    _emit_legacy_relation(client, pid)  # L2 signal: unregistered relation `blocked_by`
    out1 = _apply_all_candidates(client, "software-dev", {"add_field", "add_relation"})
    assert out1["version"] == 2
    assert {a["kind"] for a in out1["applied"]} == {"add_field", "add_relation"}

    # Second signal: task items using priority → another apply → v3.
    client.post(f"/api/projects/{pid}/items",
                json={"concept_id": "task", "title": "实现", "priority": "P2"})
    out2 = _apply_all_candidates(client, "software-dev", {"add_field"})
    assert out2["version"] == 3

    hist = client.get("/api/ontologies/software-dev/history").json()
    assert hist["current_version"] == 3
    assert [h["version"] for h in hist["history"]] == [2, 3]
    assert hist["history"][0]["previous_version"] == 1
    assert hist["snapshots"] == [1, 2, 3]
    assert all(h["applied_count"] > 0 for h in hist["history"])

    # v1 → v3 semantic diff: relation added in the first hop, fields in both.
    d = client.get("/api/ontologies/software-dev/diff",
                   params={"from_version": 1, "to_version": 3}).json()
    assert d["from_version"] == 1 and d["to_version"] == 3
    assert "blocked_by" in [r["id"] for r in d["diff"]["relations"]["added"]]
    by_cid = {c["id"]: c for c in d["diff"]["concepts"]["modified"]}
    assert "field-added:priority" in [c["type"] + ":" + c["detail"] for c in by_cid["bug"]["changes"]]
    assert "field-added:priority" in [c["type"] + ":" + c["detail"] for c in by_cid["task"]["changes"]]
    assert not d["impact"]["blocking"] and d["to_validation_errors"] == []
    assert "+1 关系" in d["summary"] and "~2 概念修改" in d["summary"]


def test_diff_defaults_to_current_and_flags_removed_concept_usage(
    client, tmp_data, isolated_ontologies, project
):
    pid = project["id"]
    client.post(f"/api/projects/{pid}/items", json={"concept_id": "bug", "title": "崩溃"})
    _emit_legacy_relation(client, pid)
    _apply_all_candidates(client, "software-dev", {"add_relation"})  # registers `blocked_by` (v2)

    # Hand-edit the live file: drop the in-use bug concept, the unused milestone
    # concept and their relations (content change on disk, version stays 2).
    path = isolated_ontologies / "software-dev.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["concepts"] = [c for c in raw["concepts"] if c["id"] not in ("bug", "milestone")]
    raw["relations"] = [r for r in raw["relations"] if r["id"] not in ("verifies", "blocked_by")]
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")

    d = client.get("/api/ontologies/software-dev/diff", params={"from_version": 2}).json()
    assert d["to_version"] == 2  # live file still declares version 2
    blocking = {(b["kind"], b.get("concept") or b.get("relation")): b for b in d["impact"]["blocking"]}
    assert blocking[("concept-removed-in-use", "bug")]["item_count"] == 1
    assert blocking[("relation-removed-in-use", "blocked_by")]["reference_count"] == 1
    warn_kinds = {w["kind"] for w in d["impact"]["warnings"]}
    assert "concept-removed-unused" in warn_kinds  # milestone had no items
    assert d["to_validation_errors"] == []


def test_diff_rejects_pre_history_versions(client, tmp_data, isolated_ontologies):
    # software-dev starts at v1: `from` would be v0, which is not a legal version.
    r = client.get("/api/ontologies/software-dev/diff")
    assert r.status_code == 422
    hist = client.get("/api/ontologies/software-dev/history").json()
    assert hist["history"] == [] and hist["snapshots"] == []
    assert hist["current_version"] == 1
