"""Smoke 8 (M4-I14): ontology learning flywheel — scan → candidates (provenance)
→ apply → version+1 + ontology.updated event → validation unlocks new relation
→ re-learn is idempotent."""
import pytest

from apm.core import events
from tests.conftest import wait_for


@pytest.mark.smoke
def test_smoke_08_ontology_learn_apply(client, tmp_data, isolated_ontologies):
    p = client.post(
        "/api/projects",
        json={"name": "本体学习项目", "ontology": "software-dev", "requirement": "驱动归纳信号"},
    ).json()
    pid = p["id"]

    # Signal L1: bug work items carry priority while the concept lacks the field.
    for title, pri in (("登录崩溃", "P1"), ("接口超时", "P0")):
        r = client.post(f"/api/projects/{pid}/items",
                        json={"concept_id": "bug", "title": title, "priority": pri})
        assert r.status_code == 200
    items = client.get(f"/api/projects/{pid}/items").json()["items"]
    bug_id = items[0]["id"]

    # Signal L2: a legacy relation type that the ontology never registered.
    events.emit(event_type="item.related", agg_type="relation", agg_id="rel_smoke8",
                project_id=pid,
                payload={"from_item": bug_id, "to_item": bug_id, "relation_type": "blocks"})

    # Before learning, creating such a relation is rejected (fail-closed).
    r = client.post(f"/api/items/{bug_id}/relations",
                    json={"to_item": bug_id, "relation_type": "blocks"})
    assert r.status_code == 422

    # Scan: both rules fire with provenance attached.
    scan = client.post("/api/ontologies/software-dev/learn").json()
    assert scan["scanned"]["projects"] == 1
    by_id = {c["id"]: c for c in scan["candidates"]}
    assert "add-field:bug:priority" in by_id
    assert by_id["add-field:bug:priority"]["provenance"]["support"] == 2
    assert "register-relation:blocks" in by_id

    # Observations list concepts with zero usage (requirement/milestone unused here).
    assert "requirement" in scan["observations"]["unused_concepts"]

    # Apply: version bump, audit event, hot reload.
    chosen = [c for c in scan["candidates"] if c["kind"] in ("add_field", "add_relation")]
    r = client.post("/api/ontologies/software-dev/apply",
                    json={"candidate_ids": [c["id"] for c in chosen]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["version"] == 2 and not out["errors"]

    upd = wait_for(lambda: [e for e in client.get(
        "/api/events", params={"agg_type": "ontology"}).json()["events"]
        if e["event_type"] == "ontology.updated"])
    assert upd[0]["payload"]["previous_version"] == 1
    assert {a["kind"] for a in upd[0]["payload"]["applied"]} == {"add_field", "add_relation"}

    # The learned relation type now passes item validation (data unlocked).
    r = client.post(f"/api/items/{bug_id}/relations",
                    json={"to_item": bug_id, "relation_type": "blocks"})
    assert r.status_code == 200, r.text

    # Idempotence: applied candidates never re-proposed.
    scan2 = client.post("/api/ontologies/software-dev/learn").json()
    assert not any(c["id"] in {x["id"] for x in chosen} for c in scan2["candidates"])

    # Stale/unknown candidate ids are rejected fail-closed.
    r = client.post("/api/ontologies/software-dev/apply",
                    json={"candidate_ids": ["add-field:bug:priority"]})
    assert r.status_code == 422

    # --- I15: versioning — second apply → v3, then history + semantic diff ---
    client.post(f"/api/projects/{pid}/items",
                json={"concept_id": "task", "title": "实现接口", "priority": "P2"})
    scan3 = client.post("/api/ontologies/software-dev/learn").json()
    chosen3 = [c for c in scan3["candidates"] if c["id"] == "add-field:task:priority"]
    assert chosen3, scan3["candidates"]
    out3 = client.post("/api/ontologies/software-dev/apply",
                       json={"candidate_ids": [chosen3[0]["id"]]}).json()
    assert out3["version"] == 3

    hist = client.get("/api/ontologies/software-dev/history").json()
    assert hist["current_version"] == 3
    assert [h["version"] for h in hist["history"]] == [2, 3]
    assert hist["snapshots"] == [1, 2, 3]

    d = client.get("/api/ontologies/software-dev/diff",
                   params={"from_version": 1, "to_version": 3}).json()
    assert "blocks" in [x["id"] for x in d["diff"]["relations"]["added"]]
    by_cid = {c["id"]: c for c in d["diff"]["concepts"]["modified"]}
    assert "field-added:priority" in [f"{c['type']}:{c['detail']}" for c in by_cid["task"]["changes"]]
    assert not d["impact"]["blocking"] and d["to_validation_errors"] == []

    # Impact analysis on a hand-edit: drop the in-use bug concept and the
    # `blocks` relation directly on disk, then diff snapshot v3 → current.
    import yaml as _yaml
    onto_file = isolated_ontologies / "software-dev.yaml"
    raw = _yaml.safe_load(onto_file.read_text(encoding="utf-8"))
    raw["concepts"] = [c for c in raw["concepts"] if c["id"] not in ("bug", "milestone")]
    raw["relations"] = [x for x in raw["relations"] if x["id"] not in ("verifies", "blocks")]
    onto_file.write_text(_yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    d2 = client.get("/api/ontologies/software-dev/diff", params={"from_version": 3}).json()
    blocking = {(b["kind"], b.get("concept") or b.get("relation")) for b in d2["impact"]["blocking"]}
    assert ("concept-removed-in-use", "bug") in blocking
    assert ("relation-removed-in-use", "blocks") in blocking
    assert any(w["kind"] == "concept-removed-unused" and w["concept"] == "milestone"
               for w in d2["impact"]["warnings"])
    assert d2["to_validation_errors"] == []

    # --- I16: CQ answerability — software-dev fully answerable with evidence ---
    events.emit(event_type="approval.requested", agg_type="approval", agg_id="apr_smoke8",
                project_id=pid, payload={"kind": "gate",
                                         "snapshot": {"gate": "prd_review", "title": "PRD 评审"}})
    events.emit(event_type="approval.granted", agg_type="approval", agg_id="apr_smoke8",
                payload={"comment": "通过"})
    events.emit(event_type="asset.drafted", agg_type="asset", agg_id="asset_smoke8", project_id=pid,
                payload={"library": "test", "kind": "test-suite", "title": "冒烟套件",
                         "tags": [], "commit": "c0ffee", "status": "draft"})
    cq = client.get("/api/ontologies/software-dev/cq-check").json()
    assert cq["checked"] == 4 and all(q["status"] == "answerable" for q in cq["questions"])
    ev = {e["source"]: e for q in cq["questions"] for e in q["evidence"]}
    assert ev["approvals"]["count"] == 1 and ev["assets"]["count"] == 1
    assert ev["relations"]["count"] >= 1 and ev["items"]["count"] >= 3

    # generic keeps deliberate gaps: mapped-but-empty (no_data) and no mapping (unmapped).
    client.post("/api/projects", json={"name": "轻项目CQ", "ontology": "generic"})
    cq2 = client.get("/api/ontologies/generic/cq-check").json()
    statuses = {q["question"]: q["status"] for q in cq2["questions"]}
    assert "no_data" in statuses.values() and "unmapped" in statuses.values()
