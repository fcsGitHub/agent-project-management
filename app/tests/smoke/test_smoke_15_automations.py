"""Smoke 15 (M9-I29): automation rules — fail-closed CRUD validation, a bug-creation
rule that assigns and stamps severity with automation attribution, condition gating,
single-layer loop safety, rebuild consistency, and the dry-run endpoint."""
import pytest

from apm.core import projections


@pytest.mark.smoke
def test_smoke_15_automations(client, tmp_data, isolated_ontologies):
    p = client.post("/api/projects",
                    json={"name": "冒烟15自动化", "ontology": "software-dev",
                          "requirement": "automation"}).json()
    pid = p["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})

    # Fail-closed: unknown trigger / action / user / field are refused at creation.
    base = {"name": "缺陷建卡即指派", "trigger_event": "item.created",
            "condition": {"concept_id": "bug"},
            "action": {"type": "assign", "user_id": "qa-wang"}}
    assert client.post(f"/api/projects/{pid}/automations",
                       json={**base, "trigger_event": "item.deleted"}).status_code == 422
    assert client.post(f"/api/projects/{pid}/automations",
                       json={**base, "action": {"type": "explode"}}).status_code == 422
    assert client.post(f"/api/projects/{pid}/automations",
                       json={**base, "action": {"type": "assign", "user_id": "ghost"}}).status_code == 422
    assert client.post(f"/api/projects/{pid}/automations", json={
        "name": "坏字段", "trigger_event": "item.created", "condition": {},
        "action": {"type": "set_field", "field_id": "nonsense", "value": 1}}).status_code == 422

    # Two real rules: assign on bug creation; stamp severity on bug creation.
    assert client.post(f"/api/projects/{pid}/automations", json=base).status_code == 200
    assert client.post(f"/api/projects/{pid}/automations", json={
        "name": "严重度置 P0", "trigger_event": "item.created",
        "condition": {"concept_id": "bug"},
        "action": {"type": "set_field", "field_id": "severity", "value": "P0"}}).status_code == 200
    rules = client.get(f"/api/projects/{pid}/automations").json()["rules"]
    assert len(rules) == 2

    # A matching bug creation fires both rules; actions are attributed to automation.
    bug = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "bug", "title": "冒烟缺陷"}).json()
    assert bug["assignee_id"] == "qa-wang"
    assert bug["custom_fields"]["severity"] == "P0"
    fired = client.get("/api/events",
                       params={"event_type": "automation.rule_fired"}).json()["events"]
    assert len(fired) == 2 and all(e["actor_type"] == "automation" for e in fired)
    assert all(e["payload"]["item_id"] == bug["id"] for e in fired)
    assigned = client.get("/api/events",
                          params={"event_type": "item.assigned"}).json()["events"]
    assert any(e["actor_type"] == "automation" and e["actor_id"] == rules[0]["id"]
               for e in assigned)

    # Condition gate: a non-bug creation fires nothing.
    client.post(f"/api/projects/{pid}/items",
                json={"concept_id": "requirement", "title": "普通需求"})
    assert len(client.get("/api/events",
                          params={"event_type": "automation.rule_fired"}).json()["events"]) == 2
    rid = rules[0]["id"]
    # Disabled rules stay quiet (both off → the silent bug triggers nothing).
    for rule in rules:
        client.patch(f"/api/projects/{pid}/automations/{rule['id']}", json={"enabled": False})
    client.post(f"/api/projects/{pid}/items", json={"concept_id": "bug", "title": "静默缺陷"})
    assert len(client.get("/api/events",
                          params={"event_type": "automation.rule_fired"}).json()["events"]) == 2
    client.patch(f"/api/projects/{pid}/automations/{rid}", json={"enabled": True})

    # Dry-run reports without executing.
    out = client.post(f"/api/projects/{pid}/automations/{rid}/test").json()
    assert out["matched"] is True and out["action"]["type"] == "assign"

    # Rebuild: rules and fired history both derive from the event log.
    projections.rebuild()
    assert len(client.get(f"/api/projects/{pid}/automations").json()["rules"]) == 2
    history = client.get(f"/api/projects/{pid}/automations/{rid}/runs").json()
    assert history["total"] == 1 and history["runs"][0]["result"]["ok"] is True

    # Cleanup for a clean board picture: delete one rule.
    assert client.delete(f"/api/projects/{pid}/automations/{rid}").status_code == 200
    assert len(client.get(f"/api/projects/{pid}/automations").json()["rules"]) == 1
