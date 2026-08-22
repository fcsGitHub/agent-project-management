"""Smoke 5: release-notes artifact + audit page query + generic second project."""
import pytest
from tests.conftest import wait_for


@pytest.mark.smoke
def test_smoke_05_release_audit_generic(client, tmp_data):
    p = client.post(
        "/api/projects", json={"name": "周报工具", "ontology": "software-dev", "requirement": "r"}
    ).json()
    conv_id = p["bootstrap"]["conversation_id"]
    run = client.post("/api/runs", json={"conversation_id": conv_id, "agent_role": "pm-agent"}).json()
    wait_for(lambda: client.get(f"/api/runs/{run['id']}").json()["status"] == "interrupted")
    apr = client.get("/api/approvals", params={"status": "pending", "project_id": p["id"]}).json()["approvals"][0]
    client.post(f"/api/approvals/{apr['id']}/decision", json={"decision": "approved"})

    # deliver → release-notes exists after gate + dangerous-tool approvals
    d = client.post(f"/api/projects/{p['id']}/deliver").json()
    wait_for(lambda: client.get(f"/api/runs/{d['run_id']}").json()["status"] == "interrupted")
    apr = client.get("/api/approvals", params={"status": "pending", "project_id": p["id"]}).json()["approvals"][0]
    client.post(f"/api/approvals/{apr['id']}/decision", json={"decision": "approved"})
    tool_apr = wait_for(lambda: next(
        (a for a in client.get("/api/approvals", params={"status": "pending", "project_id": p["id"]}).json()["approvals"]
         if a["kind"] == "tool"), None))
    client.post(f"/api/approvals/{tool_apr['id']}/decision", json={"decision": "approved"})
    wait_for(lambda: client.get(f"/api/runs/{d['run_id']}").json()["status"] == "succeeded")
    arts = client.get(f"/api/projects/{p['id']}/artifacts").json()["artifacts"]
    assert any(a["path"] == "artifacts/release/release-notes.md" for a in arts)

    # audit page can query the whole event stream with filters
    evs = client.get("/api/events", params={"project_id": p["id"], "event_type": "run.succeeded"}).json()
    assert evs["total"] >= 2
    approvals = client.get("/api/events", params={"project_id": p["id"], "actor_type": "human"}).json()
    assert approvals["total"] >= 3

    # second project on the generic ontology walks the light 3-phase flow
    g = client.post("/api/projects", json={"name": "轻项目", "ontology": "generic", "requirement": "做个调研"}).json()
    gconv = g["bootstrap"]["conversation_id"]
    grun = client.post("/api/runs", json={"conversation_id": gconv, "agent_role": "pm-agent"}).json()
    wait_for(lambda: client.get(f"/api/runs/{grun['id']}").json()["status"] == "interrupted")
    gapr = client.get("/api/approvals", params={"status": "pending", "project_id": g["id"]}).json()["approvals"][0]
    assert gapr["payload_snapshot"]["gate"] == "work_review"  # remapped gate
    client.post(f"/api/approvals/{gapr['id']}/decision", json={"decision": "approved"})
    wait_for(lambda: client.get(f"/api/runs/{grun['id']}").json()["status"] == "succeeded")
    phases = client.get(f"/api/projects/{g['id']}/phases").json()["phases"]
    assert [x["id"] for x in phases] == ["intake", "execute", "deliver"]
    assert phases[1]["status"] == "passed"
