"""Smoke 7: rebuild-projections consistency + service-restart conversation recovery."""
import pytest
from tests.conftest import wait_for


@pytest.mark.smoke
def test_smoke_07_rebuild_and_restart(client, tmp_data):
    p = client.post(
        "/api/projects", json={"name": "周报工具", "ontology": "software-dev", "requirement": "r"}
    ).json()
    conv_id = p["bootstrap"]["conversation_id"]
    run = client.post("/api/runs", json={"conversation_id": conv_id, "agent_role": "pm-agent"}).json()
    wait_for(lambda: client.get(f"/api/runs/{run['id']}").json()["status"] == "interrupted")
    client.post(f"/api/conversations/{conv_id}/messages", json={"content": "必须兼容 Python 3.9"})
    client.post(f"/api/conversations/{conv_id}/resume", json={"instruction": "按约束重拟"})
    wait_for(lambda: client.get(f"/api/runs/{run['id']}").json()["status"] == "interrupted")

    # Snapshot all read models before the rebuild
    def snapshot():
        return {
            "projects": client.get("/api/projects").json(),
            "convs": client.get("/api/conversations", params={"project_id": p["id"]}).json(),
            "conv": client.get(f"/api/conversations/{conv_id}").json(),
            "runs": client.get("/api/runs", params={"project_id": p["id"]}).json(),
            "spans": client.get(f"/api/runs/{run['id']}/spans").json(),
            "approvals": client.get("/api/approvals", params={"project_id": p["id"]}).json(),
        }

    before = snapshot()

    r = client.post("/api/system/rebuild-projections")
    assert r.status_code == 200
    after = snapshot()
    for key in before:
        assert before[key] == after[key], f"projection drift after rebuild: {key}"

    # Service restart: a fresh app instance over the same storage keeps every
    # conversation message and state losslessly (03 §3.3 promise 1).
    from fastapi.testclient import TestClient

    from apm.main import create_app

    with TestClient(create_app()) as restarted:
        conv = restarted.get(f"/api/conversations/{conv_id}").json()
        assert conv["status"] == "awaiting_review"
        contents = [m["content"] for m in conv["messages"]]
        assert any("Python 3.9" in c for c in contents)
        assert len(conv["messages"]) == len(before["conv"]["messages"])
        # crash compensation did not disturb the settled run state
        run_after = restarted.get(f"/api/runs/{run['id']}").json()
        assert run_after["status"] == "interrupted"
