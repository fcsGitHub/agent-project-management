"""Smoke 3 (I10 DoD): 12 tasks generated → NL filter applies + ui_command event."""
import pytest
from tests.conftest import wait_for


@pytest.mark.smoke
def test_smoke_03_nl_filter(client, tmp_data):
    p = client.post(
        "/api/projects", json={"name": "周报工具", "ontology": "software-dev", "requirement": "r"}
    ).json()
    conv_id = p["bootstrap"]["conversation_id"]
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
    items = wait_for(lambda: (lambda l: len(l) == 12 and l or None)(
        client.get(f"/api/projects/{p['id']}/items").json()["items"]))
    assert len(items) == 12

    # NL: "只看高优先级任务" → parsed as a priority filter + ui_command event
    r = client.post("/api/ui_commands", json={
        "utterance": "只看高优先级任务",
        "page_state": {"route": f"/p/{p['id']}/board", "project_id": p["id"]},
    })
    assert r.status_code == 200
    action = r.json()["actions"][0]
    assert action["action"] == "set_filter" and action["params"]["priority"] == "high"
    assert action["read_only"] is True

    # The filter actually narrows the item set the board would render
    highs = [i for i in items if i["priority"] == "high"]
    assert 0 < len(highs) < len(items)
    filtered = client.get(
        f"/api/projects/{p['id']}/items", params={"priority": "high"}
    ).json()["items"]
    assert {i["id"] for i in filtered} == {i["id"] for i in highs}

    evs = client.get("/api/events", params={"event_type": "ui_command.executed"}).json()["events"]
    assert any(e["payload"]["utterance"] == "只看高优先级任务" for e in evs)
    assert evs[0]["actor_type"] == "ui_agent"
