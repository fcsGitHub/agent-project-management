"""I10 tests: NL command parsing, read-only direct exec, write confirmation."""
from tests.conftest import wait_for


def _mk_project(client):
    return client.post(
        "/api/projects", json={"name": "P", "ontology": "software-dev", "requirement": "r"}
    ).json()


def test_nl_navigation_and_filter(client, tmp_data):
    p = _mk_project(client)
    r = client.post("/api/ui_commands", json={
        "utterance": "打开看板", "page_state": {"project_id": p["id"]},
    })
    assert r.status_code == 200
    body = r.json()
    assert body["actions"][0]["action"] == "navigate"
    assert body["actions"][0]["params"]["path"].endswith("/board")
    assert body["requires_confirmation"] is False

    r = client.post("/api/ui_commands", json={
        "utterance": "打开审计页", "page_state": {"project_id": p["id"]},
    })
    assert r.json()["actions"][0]["params"]["path"].endswith("/audit")


def test_nl_priority_filter_and_event(client, tmp_data):
    p = _mk_project(client)
    r = client.post("/api/ui_commands", json={
        "utterance": "只看高优先级任务", "page_state": {"route": f"/p/{p['id']}/board", "project_id": p["id"]},
    })
    assert r.status_code == 200
    action = r.json()["actions"][0]
    assert action["action"] == "set_filter"
    assert action["params"]["priority"] == "high"
    assert action["read_only"] is True

    # the executed command lands in the audit stream with on_behalf_of actor
    evs = client.get("/api/events", params={"event_type": "ui_command.executed"}).json()["events"]
    assert len(evs) == 1
    assert evs[0]["actor_type"] == "ui_agent"
    assert f"on_behalf_of=" in evs[0]["actor_id"]
    assert evs[0]["payload"]["utterance"] == "只看高优先级任务"


def test_nl_unparsable_returns_candidates(client, tmp_data):
    r = client.post("/api/ui_commands", json={
        "utterance": "帮我把火箭发射了", "page_state": {},
    })
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["candidates"]


def test_nl_bulk_approve_requires_confirmation(client, tmp_data):
    p = _mk_project(client)
    conv_id = p["bootstrap"]["conversation_id"]
    run = client.post("/api/runs", json={"conversation_id": conv_id, "agent_role": "pm-agent"}).json()
    wait_for(lambda: client.get(f"/api/runs/{run['id']}").json()["status"] == "interrupted")

    r = client.post("/api/ui_commands", json={
        "utterance": "批量批准全部待审批", "page_state": {"project_id": p["id"]},
    })
    body = r.json()
    assert body["requires_confirmation"] is True
    write_action = next(a for a in body["actions"] if not a["read_only"])
    assert write_action["action"] == "bulk_approve"

    # not executed yet: no decision events
    assert not client.get("/api/events", params={"event_type": "approval.granted"}).json()["events"]

    r = client.post(f"/api/ui_commands/{body['id']}/confirm")
    assert r.status_code == 200
    assert r.json()["results"][0]["approved"] == 1
    wait_for(lambda: client.get(f"/api/runs/{run['id']}").json()["status"] == "succeeded")

    evs = client.get("/api/events", params={"event_type": "ui_command.executed"}).json()["events"]
    assert any(e["payload"].get("results") for e in evs)
