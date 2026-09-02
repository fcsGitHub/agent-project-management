"""M5-I17 LLM-assisted ontology learning: provider channel, confidence floor,
dedup merge with pattern rules, graceful degradation, apply via the same chain."""
from __future__ import annotations

import pytest
import yaml

from apm.core import events


@pytest.fixture()
def project(client):
    r = client.post(
        "/api/projects",
        json={"name": "LLM 归纳演示", "ontology": "software-dev", "requirement": "llm 建议"},
    )
    assert r.status_code == 200
    return r.json()


def test_learn_llm_unique_candidate_applyable(client, tmp_data, isolated_ontologies, project):
    # Replay layer suggests wire-deposit for name-covered artifact kinds
    # (requirement → requirement-pattern); the pattern layer has no such signal
    # (no asset link exists), so this candidate is LLM-only.
    r = client.post("/api/ontologies/software-dev/learn-llm")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["llm"]["provider_mode"] == "replay"
    assert out["llm"]["accepted"] >= 1 and not out["llm"]["error"]

    by_id = {c["id"]: c for c in out["candidates"]}
    cand = by_id["wire-deposit:requirement:requirement:requirement-pattern"]
    assert cand["provenance"]["channels"] == ["llm"]
    assert cand["provenance"]["confidence"] >= 0.65
    assert cand["provenance"]["rule"] == "LLM-curate"

    # Apply through the same governance chain (validate → version+1 → event).
    r = client.post("/api/ontologies/software-dev/apply",
                    json={"candidate_ids": [cand["id"]]})
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 2

    live = yaml.safe_load(
        (isolated_ontologies / "software-dev.yaml").read_text(encoding="utf-8"))
    req_concept = next(c for c in live["concepts"] if c["id"] == "requirement")
    assert req_concept["artifact_kinds"][0]["deposits_to"] == "requirement-pattern"

    # Idempotent: the suggestion disappears once wired.
    out2 = client.post("/api/ontologies/software-dev/learn-llm").json()
    assert "wire-deposit:requirement:requirement:requirement-pattern" not in {
        c["id"] for c in out2["candidates"]}


def test_learn_llm_merges_with_pattern_candidates(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    client.post(f"/api/projects/{pid}/items",
                json={"concept_id": "bug", "title": "崩溃", "priority": "P1"})

    # Simulate a real LLM recording: fixture also proposes the field the pattern
    # layer already found → merged, not duplicated.
    fixtures = tmp_data / "fixtures"
    (fixtures / "recordings.yaml").write_text(
        "ontology-curator/curate: >-\n"
        '  {"candidates": [{"op": "add_field", "concept": "bug", "field_id": "priority",\n'
        '  "confidence": 0.8, "rationale": "缺陷单普遍带优先级"}]}\n',
        encoding="utf-8",
    )
    out = client.post("/api/ontologies/software-dev/learn-llm").json()
    assert out["llm"]["accepted"] == 1 and out["llm"]["merged"] == 1
    ids = [c["id"] for c in out["candidates"]]
    assert ids.count("add-field:bug:priority") == 1
    cand = next(c for c in out["candidates"] if c["id"] == "add-field:bug:priority")
    assert cand["provenance"]["channels"] == ["llm", "pattern"]
    assert cand["provenance"]["llm_rationale"] == "缺陷单普遍带优先级"


def test_learn_llm_drops_low_confidence_and_degrades_on_bad_json(
    client, tmp_data, isolated_ontologies, project
):
    fixtures = tmp_data / "fixtures"
    (fixtures / "recordings.yaml").write_text(
        "ontology-curator/curate: >-\n"
        '  {"candidates": [{"op": "add_field", "concept": "bug", "field_id": "priority",\n'
        '  "confidence": 0.4, "rationale": "不太确定"}]}\n',
        encoding="utf-8",
    )
    out = client.post("/api/ontologies/software-dev/learn-llm").json()
    assert out["llm"]["raw"] == 1 and out["llm"]["dropped_low_confidence"] == 1
    assert out["llm"]["accepted"] == 0

    # Invalid JSON → graceful degradation, pattern layer untouched.
    (fixtures / "recordings.yaml").write_text(
        "ontology-curator/curate: \"这不是{{JSON\"\n", encoding="utf-8")
    out2 = client.post("/api/ontologies/software-dev/learn-llm").json()
    assert out2["llm"]["error"] and out2["llm"]["accepted"] == 0
    assert isinstance(out2["candidates"], list)


def test_cq_events_evidence_scoped_to_ontology_projects(client, tmp_data, isolated_ontologies):
    """B 级修复（M4 审阅）：events 证据只统计该本体项目，不再全局计数。"""
    a = client.post("/api/projects",
                    json={"name": "甲", "ontology": "software-dev"}).json()
    b = client.post("/api/projects", json={"name": "乙", "ontology": "generic"}).json()

    # One gate approval inside project 甲 (software-dev), one inside 乙 (generic).
    events.emit(event_type="approval.requested", agg_type="approval", agg_id="apr_a",
                project_id=a["id"], payload={"kind": "gate", "snapshot": {"gate": "prd_review"}})
    events.emit(event_type="approval.granted", agg_type="approval", agg_id="apr_a",
                project_id=a["id"], payload={"comment": "ok"})
    events.emit(event_type="approval.requested", agg_type="approval", agg_id="apr_b",
                project_id=b["id"], payload={"kind": "gate", "snapshot": {"gate": "review"}})

    cq = client.get("/api/ontologies/software-dev/cq-check").json()
    q1 = next(q for q in cq["questions"] if q["question"].startswith("需求是否"))
    ev = {e["source"]: e for e in q1["evidence"]}
    # Only 甲's requested+granted count; 乙's approval.requested is out of scope.
    assert ev["events"]["count"] == 2
    assert "approval.requested×1" in ev["events"]["summary"]
