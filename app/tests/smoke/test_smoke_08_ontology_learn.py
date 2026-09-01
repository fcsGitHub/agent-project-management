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
