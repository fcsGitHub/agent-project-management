"""I6 tests: auto-chaining, readiness scheduling, batch start, phases."""
from tests.conftest import wait_for


def _mk_project(client, ontology="software-dev"):
    return client.post(
        "/api/projects",
        json={"name": "周报工具", "ontology": ontology, "requirement": "自动生成周报"},
    ).json()


def _full_flow_to_planned(client, p) -> dict:
    """PM run → approve PRD → planner auto-chains → approve plan → 12 items."""
    conv_id = p["bootstrap"]["conversation_id"]
    pm_run = client.post(
        "/api/runs", json={"conversation_id": conv_id, "agent_role": "pm-agent"}
    ).json()
    wait_for(lambda: client.get(f"/api/runs/{pm_run['id']}").json()["status"] == "interrupted")
    apr = client.get(
        "/api/approvals", params={"status": "pending", "project_id": p["id"]}
    ).json()["approvals"][0]
    assert apr["payload_snapshot"]["gate"] == "prd_review"
    client.post(f"/api/approvals/{apr['id']}/decision", json={"decision": "approved"})
    wait_for(lambda: client.get(f"/api/runs/{pm_run['id']}").json()["status"] == "succeeded")

    # planner auto-chains (flow 0 step 7)
    convs = wait_for(lambda: next(
        (c for c in client.get(
            "/api/conversations", params={"project_id": p["id"]}).json()["conversations"]
         if c["title"] == "计划确认"), None))
    plan_runs = wait_for(lambda: client.get(
        "/api/runs", params={"conversation_id": convs["id"]}).json()["runs"] or None)
    plan_run = plan_runs[0]
    wait_for(lambda: client.get(f"/api/runs/{plan_run['id']}").json()["status"] == "interrupted")
    apr = client.get(
        "/api/approvals", params={"status": "pending", "project_id": p["id"]}
    ).json()["approvals"][0]
    assert apr["payload_snapshot"]["gate"] == "plan_review"
    client.post(f"/api/approvals/{apr['id']}/decision", json={"decision": "approved"})
    wait_for(lambda: client.get(f"/api/runs/{plan_run['id']}").json()["status"] == "succeeded")
    wait_for(lambda: len(client.get(f"/api/projects/{p['id']}/items").json()["items"]) == 12)
    return {"pm_run": pm_run, "plan_run": plan_run, "plan_conversation": convs}


def test_prd_approval_auto_chains_planner(client, tmp_data):
    p = _mk_project(client)
    refs = _full_flow_to_planned(client, p)
    assert refs["plan_conversation"]["kind"] == "drafting"
    # the chain is visible in the audit stream
    evs = client.get("/api/events", params={"event_type": "run.requested"}).json()["events"]
    assert any(e["payload"].get("agent_role") == "planner-agent" for e in evs)
    items = client.get(f"/api/projects/{p['id']}/items").json()["items"]
    assert len(items) == 12


def test_batch_start_respects_dependencies(client, tmp_data):
    p = _mk_project(client)
    _full_flow_to_planned(client, p)
    items = client.get(f"/api/projects/{p['id']}/items").json()["items"]
    by_title = {i["title"].split(" ")[0]: i for i in items}

    # unassigned items are skipped with a reason
    r = client.post("/api/orchestrator/batch-start", json={"item_ids": [by_title["T1"]["id"]]})
    assert r.status_code == 200
    body = r.json()
    assert body["started"] == []
    assert body["skipped"][0]["reason"] == "未指派 Agent 角色"

    # assign agents; T2 depends on T1 → starting [T2, T1] starts only T1
    for item in items:
        client.patch(
            f"/api/items/{item['id']}",
            json={"assignee_type": "agent", "assignee_id": "dev-agent"},
        )
    r = client.post(
        "/api/orchestrator/batch-start",
        json={"item_ids": [by_title["T2"]["id"], by_title["T1"]["id"]]},
    )
    body = r.json()
    started_ids = {s["item_id"] for s in body["started"]}
    assert started_ids == {by_title["T1"]["id"]}
    assert body["skipped"][0]["item_id"] == by_title["T2"]["id"]
    assert "阻塞" in body["skipped"][0]["reason"]

    started = body["started"][0]
    conv = client.get(f"/api/conversations/{started['conversation_id']}").json()
    assert conv["kind"] == "executing" and conv["item_id"] == by_title["T1"]["id"]
    run = wait_for(lambda: client.get(f"/api/runs/{started['run_id']}").json())
    assert run["item_id"] == by_title["T1"]["id"]
    assert client.get(f"/api/items/{by_title['T1']['id']}").json()["status"] == "in_progress"


def test_phases_progression_and_deliver(client, tmp_data):
    p = _mk_project(client)
    phases = client.get(f"/api/projects/{p['id']}/phases").json()["phases"]
    assert phases[0]["status"] == "active"  # intake
    assert phases[1]["status"] == "active"  # analysis gate pending

    _full_flow_to_planned(client, p)
    phases = client.get(f"/api/projects/{p['id']}/phases").json()["phases"]
    assert phases[0]["status"] == "passed"  # intake: no gate, flowed through
    assert phases[1]["status"] == "passed"  # analysis gate (prd_review) approved
    assert phases[2]["status"] == "skipped"  # design jumped over (light flow)
    assert phases[3]["status"] == "passed"  # planning gate (plan_review) approved

    # deliver endpoint launches a release run producing release notes
    r = client.post(f"/api/projects/{p['id']}/deliver")
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    wait_for(lambda: client.get(f"/api/runs/{run_id}").json()["status"] == "interrupted")
    apr = client.get(
        "/api/approvals", params={"status": "pending", "project_id": p["id"]}
    ).json()["approvals"][0]
    client.post(f"/api/approvals/{apr['id']}/decision", json={"decision": "approved"})
    wait_for(lambda: next(
        (a for a in client.get(
            "/api/approvals", params={"status": "pending", "project_id": p["id"]}).json()["approvals"]
         if a["kind"] == "tool"), None))
    tool_apr = next(
        a for a in client.get(
            "/api/approvals", params={"status": "pending", "project_id": p["id"]}).json()["approvals"]
        if a["kind"] == "tool")
    client.post(f"/api/approvals/{tool_apr['id']}/decision", json={"decision": "approved"})
    wait_for(lambda: client.get(f"/api/runs/{run_id}").json()["status"] == "succeeded")
    arts = client.get(f"/api/projects/{p['id']}/artifacts").json()["artifacts"]
    assert any(a["path"] == "artifacts/release/release-notes.md" for a in arts)


def test_generic_project_light_flow(client, tmp_data):
    p = _mk_project(client, ontology="generic")
    conv_id = p["bootstrap"]["conversation_id"]
    run = client.post(
        "/api/runs", json={"conversation_id": conv_id, "agent_role": "pm-agent"}
    ).json()
    wait_for(lambda: client.get(f"/api/runs/{run['id']}").json()["status"] == "interrupted")
    apr = client.get(
        "/api/approvals", params={"status": "pending", "project_id": p["id"]}
    ).json()["approvals"][0]
    # role gate prd_review remapped onto the generic ontology's first gate
    assert apr["payload_snapshot"]["gate"] == "work_review"
    client.post(f"/api/approvals/{apr['id']}/decision", json={"decision": "approved"})
    wait_for(lambda: client.get(f"/api/runs/{run['id']}").json()["status"] == "succeeded")

    refs = _full_flow_to_planned_tail(client, p)
    items = refs["items"]
    assert len(items) == 12
    # tasks created under the generic ontology's 'activity' concept lifecycle
    assert all(i["concept_id"] == "activity" for i in items)
    # an activity item started by the scheduler maps to the generic 'doing' state
    client.patch(
        f"/api/items/{items[0]['id']}",
        json={"assignee_type": "agent", "assignee_id": "dev-agent"},
    )
    r = client.post("/api/orchestrator/batch-start", json={"item_ids": [items[0]["id"]]})
    started = r.json()["started"][0]
    wait_for(lambda: client.get(f"/api/runs/{started['run_id']}").json()["status"] == "interrupted")
    item = client.get(f"/api/items/{items[0]['id']}").json()
    assert item["status"] == "doing" and item["status_group"] == "in_progress"


def _full_flow_to_planned_tail(client, p) -> dict:
    """After the PM gate is approved: wait planner chain, approve plan, return items."""
    convs = wait_for(lambda: next(
        (c for c in client.get(
            "/api/conversations", params={"project_id": p["id"]}).json()["conversations"]
         if c["title"] == "计划确认"), None))
    plan_runs = wait_for(lambda: client.get(
        "/api/runs", params={"conversation_id": convs["id"]}).json()["runs"] or None)
    plan_run = plan_runs[0]
    wait_for(lambda: client.get(f"/api/runs/{plan_run['id']}").json()["status"] == "interrupted")
    apr = client.get(
        "/api/approvals", params={"status": "pending", "project_id": p["id"]}
    ).json()["approvals"][0]
    client.post(f"/api/approvals/{apr['id']}/decision", json={"decision": "approved"})
    wait_for(lambda: client.get(f"/api/runs/{plan_run['id']}").json()["status"] == "succeeded")
    items = wait_for(lambda: (lambda l: l or None)(
        client.get(f"/api/projects/{p['id']}/items").json()["items"]))
    return {"items": items, "plan_run": plan_run}
