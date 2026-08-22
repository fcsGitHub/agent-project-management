"""Smoke 4 (API version, I6 DoD): batch start → interrupt → resume → awaiting_review → bulk approve."""
import pytest
from tests.conftest import wait_for


@pytest.mark.smoke
def test_smoke_04_batch_lifecycle(client, tmp_data):
    p = client.post(
        "/api/projects",
        json={"name": "周报工具", "ontology": "software-dev", "requirement": "自动生成周报"},
    ).json()
    conv_id = p["bootstrap"]["conversation_id"]

    # PM → approve PRD → planner chains → approve plan → 12 tasks
    run = client.post("/api/runs", json={"conversation_id": conv_id, "agent_role": "pm-agent"}).json()
    wait_for(lambda: client.get(f"/api/runs/{run['id']}").json()["status"] == "interrupted")
    apr = client.get("/api/approvals", params={"status": "pending", "project_id": p["id"]}).json()["approvals"][0]
    client.post(f"/api/approvals/{apr['id']}/decision", json={"decision": "approved"})
    plan_conv = wait_for(lambda: next(
        (c for c in client.get("/api/conversations", params={"project_id": p["id"]}).json()["conversations"]
         if c["title"] == "计划确认"), None))
    plan_run = wait_for(lambda: client.get(
        "/api/runs", params={"conversation_id": plan_conv["id"]}).json()["runs"] or None)[0]
    wait_for(lambda: client.get(f"/api/runs/{plan_run['id']}").json()["status"] == "interrupted")
    apr = client.get("/api/approvals", params={"status": "pending", "project_id": p["id"]}).json()["approvals"][0]
    client.post(f"/api/approvals/{apr['id']}/decision", json={"decision": "approved"})
    items = wait_for(lambda: (lambda l: l or None)(
        client.get(f"/api/projects/{p['id']}/items").json()["items"]))
    assert len(items) == 12

    # Batch start the dependency-free leaves (T1 only)
    by_tid = {i["title"].split(" ")[0]: i for i in items}
    for i in items:
        client.patch(f"/api/items/{i['id']}", json={"assignee_type": "agent", "assignee_id": "dev-agent"})
    r = client.post("/api/orchestrator/batch-start", json={"item_ids": [by_tid["T1"]["id"]]})
    started = r.json()["started"]
    assert len(started) == 1
    run_id = started[0]["run_id"]
    conv2 = started[0]["conversation_id"]
    wait_for(lambda: client.get(f"/api/runs/{run_id}").json()["status"] == "interrupted")

    # Interrupt the conversation mid-await, then resume → back to awaiting review
    client.post(f"/api/conversations/{conv2}/messages", json={"content": "第 3 步的异常处理不对，改成重试三次"})
    client.post(f"/api/conversations/{conv2}/resume", json={"instruction": "按补充约束重做"})
    wait_for(lambda: client.get(f"/api/runs/{run_id}").json()["status"] == "interrupted")
    conv = client.get(f"/api/conversations/{conv2}").json()
    assert conv["status"] == "awaiting_review"

    # Bulk approve the pending code_review gate
    pendings = client.get("/api/approvals", params={"status": "pending", "project_id": p["id"]}).json()["approvals"]
    assert pendings
    r = client.post("/api/approvals/bulk-decision",
                    json={"ids": [a["id"] for a in pendings], "decision": "approved"})
    assert r.status_code == 200
    wait_for(lambda: client.get(f"/api/runs/{run_id}").json()["status"] == "succeeded")
    assert client.get(f"/api/items/{by_tid['T1']['id']}").json()["status"] == "done"

    # All approval actions are in the audit stream
    granted = client.get("/api/events", params={"event_type": "approval.granted"}).json()["events"]
    assert len(granted) >= 3  # prd, plan, code_review
