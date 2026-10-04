"""Smoke 9 (M108-I326): requirements-to-evidence traceability — links make a
requirement's evidence visible (impact: decision/implementation/test groups,
transitive test at depth 2), coverage closes the loop (closed_rate 1.0 once
implementation+test are attached), and the graph is a pure projection
(rebuild reproduces it)."""
import pytest

from apm.core import projections


def _setup(client):
    p = client.post("/api/projects", json={"name": "追溯冒烟", "ontology": "software-dev",
                                           "requirement": "I326"}).json()
    pid = p["id"]
    req = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "requirement", "title": "登录鉴权"}).json()
    task = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "实现登录模块"}).json()
    test = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "bug", "title": "登录回归测试"}).json()
    adr = "artifacts/adr-001-auth.md"
    assert client.put(f"/api/projects/{pid}/artifacts/{adr}",
                      json={"content": "# ADR 001 采用 JWT"}).status_code == 200
    for body in (
        {"source_type": "artifact", "source_ref": adr, "relation": "decides",
         "target_type": "item", "target_ref": req["id"]},
        {"source_type": "item", "source_ref": task["id"], "relation": "implements",
         "target_type": "item", "target_ref": req["id"]},
        {"source_type": "item", "source_ref": test["id"], "relation": "verifies",
         "target_type": "item", "target_ref": task["id"]},
    ):
        r = client.post(f"/api/projects/{pid}/trace/links", json=body)
        assert r.status_code == 200, r.text
    return pid, req["id"], adr


@pytest.mark.smoke
def test_smoke_09_trace_impact(client, tmp_data, isolated_ontologies):
    pid, req_id, adr = _setup(client)

    impact = client.get(f"/api/projects/{pid}/trace/impact", params={"node_ref": req_id}).json()
    assert impact["node"]["requirement_like"] is True
    assert [e["ref"] for e in impact["groups"]["decisions"]] == [adr]
    assert impact["groups"]["implementation"][0]["ref"].startswith("i_")
    # transitive: the test hangs off the task, but counts as the requirement's evidence
    assert impact["groups"]["tests"][0]["depth"] == 2
    assert impact["summary"]["needs_review"] == 0

    # duplicate edge is refused — the graph stays a clean set
    dup = client.post(f"/api/projects/{pid}/trace/links",
                      json={"source_type": "item", "source_ref": impact["groups"]["implementation"][0]["ref"],
                            "relation": "implements", "target_type": "item", "target_ref": req_id})
    assert dup.status_code == 409


@pytest.mark.smoke
def test_smoke_09_trace_coverage_rebuild(client, tmp_data, isolated_ontologies):
    pid, req_id, _ = _setup(client)

    cov = client.get(f"/api/projects/{pid}/trace/coverage").json()
    assert cov["summary"]["requirements"] == 1
    assert cov["summary"]["closed"] == 1 and cov["summary"]["closed_rate"] == 1.0
    assert cov["gaps"]["requirements_without_tests"] == []
    assert cov["gaps"]["orphan_items"] == []
    assert cov["gaps"]["stale_links"] == []

    # the trace graph is event-sourced: wipe + replay reproduces it exactly
    before = client.get(f"/api/projects/{pid}/trace/links").json()["links"]
    assert projections.rebuild() > 0
    after = client.get(f"/api/projects/{pid}/trace/links").json()["links"]
    assert [(ln["source_type"], ln["source_ref"], ln["relation"],
             ln["target_type"], ln["target_ref"]) for ln in after] == \
           [(ln["source_type"], ln["source_ref"], ln["relation"],
             ln["target_type"], ln["target_ref"]) for ln in before]
