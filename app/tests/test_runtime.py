"""I5 tests: role runs on LangGraph (replay), gate approvals, interrupt-inject-resume."""
from tests.conftest import wait_for


def _mk_project(client, **kw):
    return client.post(
        "/api/projects", json={"name": "周报工具", "ontology": "software-dev",
                               "requirement": "自动生成周报", **kw}
    ).json()


def _start_run(client, conversation_id, role, **kw):
    r = client.post(
        "/api/runs", json={"conversation_id": conversation_id, "agent_role": role, **kw}
    )
    assert r.status_code == 200, r.text
    return r.json()


def _wait_status(client, run_id, statuses):
    def check():
        run = client.get(f"/api/runs/{run_id}").json()
        return run if run["status"] in statuses else None

    return wait_for(check)


def _pending_approvals(client, project_id):
    return client.get(
        "/api/approvals", params={"status": "pending", "project_id": project_id}
    ).json()["approvals"]


def test_pm_agent_run_to_gate_approval(client, tmp_data):
    p = _mk_project(client)
    conv_id = p["bootstrap"]["conversation_id"]
    run = _start_run(client, conv_id, "pm-agent")
    run = _wait_status(client, run["id"], ("interrupted",))
    assert run["status"] == "interrupted"

    # conversation awaits review; PRD artifact committed; approval pending
    conv = client.get(f"/api/conversations/{conv_id}").json()
    assert conv["status"] == "awaiting_review"
    arts = client.get(f"/api/projects/{p['id']}/artifacts").json()["artifacts"]
    prd = next(a for a in arts if a["path"] == "artifacts/prd.md")
    assert prd["commit"]

    approvals = _pending_approvals(client, p["id"])
    assert len(approvals) == 1
    apr = approvals[0]
    assert apr["kind"] == "gate"
    assert apr["payload_snapshot"]["gate"] == "prd_review"
    assert apr["payload_snapshot"]["artifact"]["path"] == "artifacts/prd.md"
    assert apr["payload_snapshot"]["artifact"]["commit"] == prd["commit"]

    # spans carry OTel + apm anchors (docs/10 I5 DoD)
    spans = client.get(f"/api/runs/{run['id']}/spans").json()["spans"]
    kinds = {s["span_kind"] for s in spans}
    assert {"agent", "generation", "tool", "gate"} <= kinds
    gen = next(s for s in spans if s["span_kind"] == "generation")
    assert gen["attributes"]["gen_ai.request.model"]
    assert "apm.conversation_id" in gen["attributes"]
    tool = next(s for s in spans if s["name"] == "tool.write_artifact")
    assert tool["attributes"]["apm.diff_ref"].startswith("artifacts/prd.md@")

    # assistant message with step row landed in the conversation
    msgs = client.get(f"/api/conversations/{conv_id}/messages").json()["messages"]
    assert any("已起草 artifacts/prd.md" in m["content"] for m in msgs)

    # approve → run succeeds, conversation back to active
    r = client.post(f"/api/approvals/{apr['id']}/decision",
                    json={"decision": "approved", "comment": "OK"})
    assert r.status_code == 200
    run = _wait_status(client, run["id"], ("succeeded", "failed"))
    assert run["status"] == "succeeded", run
    assert client.get(f"/api/conversations/{conv_id}").json()["status"] == "active"


def test_interrupt_inject_resume_pru_contains_constraint(client, tmp_data):
    p = _mk_project(client)
    conv_id = p["bootstrap"]["conversation_id"]
    run = _start_run(client, conv_id, "pm-agent")
    _wait_status(client, run["id"], ("interrupted",))
    apr = _pending_approvals(client, p["id"])[0]

    # interrupt: send a constraint message while awaiting review
    r = client.post(f"/api/conversations/{conv_id}/messages",
                    json={"content": "必须兼容 Python 3.9，不要用 3.10+ 语法"})
    assert r.status_code == 200
    # resume the conversation with the new instruction → revise path
    r = client.post(f"/api/conversations/{conv_id}/resume",
                    json={"instruction": "按补充约束重拟 PRD"})
    assert r.status_code == 200
    _wait_status(client, run["id"], ("interrupted",))  # back at gate with new draft

    # approval snapshot refreshed to the new commit
    apr2 = client.get("/api/approvals", params={"status": "pending"}).json()["approvals"][0]
    assert apr2["id"] == apr["id"]
    arts = client.get(f"/api/projects/{p['id']}/artifacts").json()["artifacts"]
    prd = next(a for a in arts if a["path"] == "artifacts/prd.md")
    assert apr2["payload_snapshot"]["artifact"]["commit"] == prd["commit"]
    assert prd["versions"] >= 2  # redrafted

    # approve → PRD contains the injected constraint
    client.post(f"/api/approvals/{apr['id']}/decision", json={"decision": "approved"})
    _wait_status(client, run["id"], ("succeeded",))
    detail = client.get(f"/api/projects/{p['id']}/artifacts/artifacts/prd.md").json()
    assert "Python 3.9" in detail["content"]


def test_planner_run_creates_items_after_approval(client, tmp_data):
    p = _mk_project(client)
    conv_id = p["bootstrap"]["conversation_id"]
    run = _start_run(client, conv_id, "planner-agent")
    _wait_status(client, run["id"], ("interrupted",))
    apr = _pending_approvals(client, p["id"])[0]
    assert apr["payload_snapshot"]["gate"] == "plan_review"

    items_before = client.get(f"/api/projects/{p['id']}/items").json()["items"]
    assert items_before == []
    client.post(f"/api/approvals/{apr['id']}/decision", json={"decision": "approved"})
    _wait_status(client, run["id"], ("succeeded",))

    items = client.get(f"/api/projects/{p['id']}/items").json()["items"]
    assert len(items) == 12  # WBS replay fixture creates the 12-task tree
    assert all(i["concept_id"] == "task" for i in items)
    assert all(i["feature_id"] == p["bootstrap"]["feature_id"] for i in items)
    highs = [i for i in items if i["priority"] == "high"]
    assert highs  # for the NL filter smoke later
    # depends_on relations were created (T1 has no outgoing deps, T2 depends on T1)
    t1_id = items[0]["id"]
    rels1 = client.get(f"/api/items/{t1_id}").json()["relations"]
    from_rels1 = [r for r in rels1 if r["from_item"] == t1_id]
    assert from_rels1 == []
    t2 = next(i for i in items if i["title"].startswith("T2"))
    rels2 = client.get(f"/api/items/{t2['id']}").json()["relations"]
    from_rels2 = [r for r in rels2 if r["from_item"] == t2["id"]]
    assert any(r["relation_type"] == "depends_on" for r in from_rels2)


def test_reject_path_fails_run(client, tmp_data):
    p = _mk_project(client)
    conv_id = p["bootstrap"]["conversation_id"]
    run = _start_run(client, conv_id, "pm-agent")
    _wait_status(client, run["id"], ("interrupted",))
    apr = _pending_approvals(client, p["id"])[0]
    # rejection requires a comment (fail-closed)
    r = client.post(f"/api/approvals/{apr['id']}/decision", json={"decision": "rejected"})
    assert r.status_code == 422
    r = client.post(f"/api/approvals/{apr['id']}/decision",
                    json={"decision": "rejected", "comment": "范围不对"})
    assert r.status_code == 200
    run = _wait_status(client, run["id"], ("failed",))
    assert "rejected" in (run["error"] or "")


def test_release_run_dangerous_tool_approval(client, tmp_data):
    p = _mk_project(client)
    conv_id = p["bootstrap"]["conversation_id"]
    run = _start_run(client, conv_id, "release-agent")
    _wait_status(client, run["id"], ("interrupted",))
    apr = _pending_approvals(client, p["id"])[0]
    assert apr["payload_snapshot"]["gate"] == "release_approval"
    client.post(f"/api/approvals/{apr['id']}/decision", json={"decision": "approved"})

    # gate approval passes → dangerous create_git_tag interrupts again
    tool_apr = wait_for(lambda: next(
        (a for a in _pending_approvals(client, p["id"]) if a["kind"] == "tool"), None
    ))
    assert tool_apr["payload_snapshot"]["tool"] == "create_git_tag"
    # release-notes artifact exists (smoke 5 precondition)
    arts = client.get(f"/api/projects/{p['id']}/artifacts").json()["artifacts"]
    assert any(a["path"] == "artifacts/release/release-notes.md" for a in arts)

    client.post(f"/api/approvals/{tool_apr['id']}/decision", json={"decision": "approved"})
    run = _wait_status(client, run["id"], ("succeeded", "failed"))
    assert run["status"] == "succeeded", run


def test_dev_run_moves_item_status(client, tmp_data):
    p = _mk_project(client)
    feature_id = p["bootstrap"]["feature_id"]
    item = client.post(
        f"/api/projects/{p['id']}/items",
        json={"concept_id": "task", "title": "T7 导入解析", "feature_id": feature_id},
    ).json()
    conv = client.post(
        "/api/conversations",
        json={"project_id": p["id"], "feature_id": feature_id, "kind": "executing",
              "title": "T7 执行", "instruction": "实现导入解析并自测", "item_id": item["id"]},
    ).json()
    run = _start_run(client, conv["id"], "dev-agent", item_id=item["id"])
    assert client.get(f"/api/items/{item['id']}").json()["status"] == "in_progress"
    _wait_status(client, run["id"], ("interrupted",))
    apr = _pending_approvals(client, p["id"])[0]
    assert apr["payload_snapshot"]["gate"] == "code_review"
    client.post(f"/api/approvals/{apr['id']}/decision", json={"decision": "approved"})
    _wait_status(client, run["id"], ("succeeded",))
    assert client.get(f"/api/items/{item['id']}").json()["status"] == "done"
