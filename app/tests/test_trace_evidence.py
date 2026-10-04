"""M108-I326: requirements-to-evidence traceability — link CRUD with
validation (dup 409 / unknown relation or node 422 / cross-project 422),
impact BFS with direction-aware grouping (depth-2 transitive test evidence,
reverse lookup from a task to its requirement), per-round coverage gaps
(no tests / no implementation / no evidence / orphans / stale links /
changed-after-evidence), and event-sourced rebuild reproducing the graph."""
import time

import pytest

from apm.core import projections


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "追溯演示", "ontology": "software-dev",
                                           "requirement": "I326"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _item(client, pid, concept, title, **kw):
    r = client.post(f"/api/projects/{pid}/items", json={"concept_id": concept, "title": title, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def _link(client, pid, **kw):
    return client.post(f"/api/projects/{pid}/trace/links", json=kw)


def test_trace_link_validation_and_impact(client, pid):
    req = _item(client, pid, "requirement", "登录鉴权")
    task = _item(client, pid, "task", "实现登录模块")
    bug = _item(client, pid, "bug", "登录回归测试")
    adr = "artifacts/adr-001-auth.md"
    r = client.put(f"/api/projects/{pid}/artifacts/{adr}", json={"content": "# ADR 001 采用 JWT"})
    assert r.status_code == 200, r.text

    # canonical direction: evidence → requirement
    assert _link(client, pid, source_type="artifact", source_ref=adr, relation="decides",
                 target_type="item", target_ref=req["id"]).status_code == 200
    assert _link(client, pid, source_type="item", source_ref=task["id"], relation="implements",
                 target_type="item", target_ref=req["id"]).status_code == 200
    # transitive evidence: the bug verifies the task that implements the requirement
    assert _link(client, pid, source_type="item", source_ref=bug["id"], relation="verifies",
                 target_type="item", target_ref=task["id"]).status_code == 200

    # duplicate edge → 409; bad relation / self loop / unknown ref → 422/404
    assert _link(client, pid, source_type="item", source_ref=task["id"], relation="implements",
                 target_type="item", target_ref=req["id"]).status_code == 409
    assert _link(client, pid, source_type="item", source_ref=task["id"], relation="marries",
                 target_type="item", target_ref=req["id"]).status_code == 422
    assert _link(client, pid, source_type="item", source_ref=task["id"], relation="relates_to",
                 target_type="item", target_ref=task["id"]).status_code == 422
    assert _link(client, pid, source_type="item", source_ref="i_nope", relation="implements",
                 target_type="item", target_ref=req["id"]).status_code == 404
    assert _link(client, pid, source_type="artifact", source_ref="artifacts/ghost.md",
                 relation="documents", target_type="item", target_ref=req["id"]).status_code == 404

    # cross-project item refused
    pid2 = client.post("/api/projects", json={"name": "别的项目", "ontology": "software-dev",
                                              "requirement": "x"}).json()["id"]
    other = _item(client, pid2, "task", "别家任务")
    assert _link(client, pid, source_type="item", source_ref=other["id"], relation="implements",
                 target_type="item", target_ref=req["id"]).status_code == 422

    # impact from the requirement side: grouped, transitive test at depth 2
    impact = client.get(f"/api/projects/{pid}/trace/impact",
                        params={"node_ref": req["id"]}).json()
    assert impact["node"]["requirement_like"] is True
    assert [e["ref"] for e in impact["groups"]["decisions"]] == [adr]
    assert [e["ref"] for e in impact["groups"]["implementation"]] == [task["id"]]
    assert [e["ref"] for e in impact["groups"]["tests"]] == [bug["id"]]
    assert impact["groups"]["tests"][0]["depth"] == 2
    assert impact["summary"]["needs_review"] == 0

    # reverse lookup from the task: the requirement lands in the 需求 bucket
    back = client.get(f"/api/projects/{pid}/trace/impact",
                      params={"node_ref": task["id"]}).json()
    assert back["node"]["requirement_like"] is False
    assert [e["ref"] for e in back["groups"]["requirements"]] == [req["id"]]

    # unlink removes the edge everywhere
    links = client.get(f"/api/projects/{pid}/trace/links").json()["links"]
    assert len(links) == 3
    victim = next(ln for ln in links if ln["relation"] == "verifies")
    assert client.delete(f"/api/trace/links/{victim['id']}").status_code == 200
    impact2 = client.get(f"/api/projects/{pid}/trace/impact",
                         params={"node_ref": req["id"]}).json()
    assert impact2["groups"]["tests"] == []
    assert client.get("/api/trace/links/tl_nope").status_code == 405  # only DELETE exists


def test_trace_coverage_gaps(client, pid):
    req = _item(client, pid, "requirement", "导出报表")
    orphan = _item(client, pid, "task", "无主任务")
    linked_task = _item(client, pid, "task", "实现导出")
    test = _item(client, pid, "bug", "导出冒烟")

    cov = client.get(f"/api/projects/{pid}/trace/coverage").json()
    assert cov["summary"]["requirements"] == 1
    assert req["id"] in [r["id"] for r in cov["gaps"]["requirements_without_evidence"]]
    assert cov["gaps"]["requirements_without_tests"][0]["id"] == req["id"]
    assert cov["gaps"]["requirements_without_implementation"][0]["id"] == req["id"]
    assert set(o["id"] for o in cov["gaps"]["orphan_items"]) == \
        {orphan["id"], linked_task["id"], test["id"]}

    assert _link(client, pid, source_type="item", source_ref=linked_task["id"], relation="implements",
                 target_type="item", target_ref=req["id"]).status_code == 200
    assert _link(client, pid, source_type="item", source_ref=test["id"], relation="verifies",
                 target_type="item", target_ref=req["id"]).status_code == 200
    cov = client.get(f"/api/projects/{pid}/trace/coverage").json()
    assert cov["summary"]["closed"] == 1 and cov["summary"]["closed_rate"] == 1.0
    assert cov["gaps"]["requirements_without_tests"] == []
    assert [o["id"] for o in cov["gaps"]["orphan_items"]] == [orphan["id"]]
    assert cov["requirements"][0]["closed"] is True

    # transitive closure: a test hanging off the implementing task counts too
    req2 = _item(client, pid, "requirement", "审计日志")
    task2 = _item(client, pid, "task", "实现审计写入")
    test2 = _item(client, pid, "bug", "审计冒烟")
    assert _link(client, pid, source_type="item", source_ref=task2["id"], relation="implements",
                 target_type="item", target_ref=req2["id"]).status_code == 200
    assert _link(client, pid, source_type="item", source_ref=test2["id"], relation="verifies",
                 target_type="item", target_ref=task2["id"]).status_code == 200
    cov = client.get(f"/api/projects/{pid}/trace/coverage").json()
    by_id = {r["id"]: r for r in cov["requirements"]}
    assert by_id[req2["id"]]["has_test"] is True and by_id[req2["id"]]["closed"] is True
    assert cov["summary"]["closed"] == 2

    # requirement changed after its evidence was registered → 待复核
    time.sleep(0.005)  # event ts is ms-precision; ensure the patch lands later
    assert client.patch(f"/api/items/{req['id']}", json={"title": "导出报表 v2"}).status_code == 200
    cov = client.get(f"/api/projects/{pid}/trace/coverage").json()
    assert cov["summary"]["needs_review"] == 1
    assert cov["gaps"]["changed_after_evidence"][0]["id"] == req["id"]

    # milestone slice keeps the global report untouched
    assert client.post(f"/api/projects/{pid}/milestones",
                       json={"title": "M1", "due_date": "2026-10-30"}).status_code == 200
    mid = client.get(f"/api/projects/{pid}/milestones").json()["milestones"][0]["id"]
    cov = client.get(f"/api/projects/{pid}/trace/coverage", params={"milestone_id": mid}).json()
    assert cov["summary"]["requirements"] == 0


def test_trace_stale_links_and_rebuild(client, pid):
    req = _item(client, pid, "requirement", "性能达标")
    adr = "artifacts/adr-002-perf.md"
    assert client.put(f"/api/projects/{pid}/artifacts/{adr}",
                      json={"content": "# ADR 002 缓存策略"}).status_code == 200
    assert _link(client, pid, source_type="artifact", source_ref=adr, relation="decides",
                 target_type="item", target_ref=req["id"]).status_code == 200

    # deleting the artifact leaves a dangling endpoint → stale link
    assert client.delete(f"/api/projects/{pid}/artifacts/{adr}").status_code == 200
    cov = client.get(f"/api/projects/{pid}/trace/coverage").json()
    assert cov["summary"]["stale_links"] == 1
    assert cov["gaps"]["stale_links"][0]["missing"] == [f"artifact:{adr}"]

    # the graph is a projection: rebuild replays trace.linked/unlinked exactly
    assert _link(client, pid, source_type="item", source_ref=req["id"], relation="documents",
                 target_type="item", target_ref=req["id"]).status_code == 422  # no self loop
    task = _item(client, pid, "task", "压测脚本")
    assert _link(client, pid, source_type="item", source_ref=task["id"], relation="verifies",
                 target_type="item", target_ref=req["id"]).status_code == 200
    before = client.get(f"/api/projects/{pid}/trace/links").json()["links"]
    projections.rebuild()
    after = client.get(f"/api/projects/{pid}/trace/links").json()["links"]
    assert [{k: v for k, v in ln.items() if k in ("source_type", "source_ref", "relation",
                                                  "target_type", "target_ref")} for ln in after] == \
           [{k: v for k, v in ln.items() if k in ("source_type", "source_ref", "relation",
                                                  "target_type", "target_ref")} for ln in before]


def test_trace_generic_ontology_objective(client, tmp_data, isolated_ontologies):
    """需求类概念随本体：generic 本体里 intake 概念是 objective，不是 requirement。"""
    pid = client.post("/api/projects", json={"name": "通用项目", "ontology": "generic",
                                             "requirement": "I326"}).json()["id"]
    obj = _item(client, pid, "objective", "品牌升级")
    act = _item(client, pid, "activity", "设计新视觉")
    cov = client.get(f"/api/projects/{pid}/trace/coverage").json()
    assert cov["summary"]["requirements"] == 1
    assert cov["gaps"]["requirements_without_tests"][0]["id"] == obj["id"]
    assert _link(client, pid, source_type="item", source_ref=act["id"], relation="implements",
                 target_type="item", target_ref=obj["id"]).status_code == 200
    cov = client.get(f"/api/projects/{pid}/trace/coverage").json()
    assert cov["summary"]["with_implementation"] == 1
    impact = client.get(f"/api/projects/{pid}/trace/impact",
                        params={"node_ref": obj["id"]}).json()
    assert impact["node"]["requirement_like"] is True
    assert [e["ref"] for e in impact["groups"]["implementation"]] == [act["id"]]
