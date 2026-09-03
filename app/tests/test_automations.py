"""M9-I29 automation rules: event-sourced CRUD with fail-closed validation, the
post-emit executor (trigger/condition/action), automation attribution, and the
single-layer loop guard."""
from __future__ import annotations

import pytest

from apm.core import db, projections


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "自动化演示", "ontology": "software-dev", "requirement": "I29"})
    assert r.status_code == 200
    return r.json()


def _rule(client, pid, **over):
    body = {"name": "缺陷建卡即指派", "trigger_event": "item.created",
            "condition": {"concept_id": "bug"},
            "action": {"type": "assign", "user_id": "qa-wang"}, **over}
    return client.post(f"/api/projects/{pid}/automations", json=body)


def test_rule_crud_roundtrip_and_rebuild(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    r = _rule(client, pid)
    assert r.status_code == 200
    rule = r.json()
    assert rule["enabled"] is True and rule["condition"]["concept_id"] == "bug"

    rules = client.get(f"/api/projects/{pid}/automations").json()["rules"]
    assert len(rules) == 1 and rules[0]["id"] == rule["id"]

    # Rebuild: the rules table is a projection — replay must reproduce it.
    projections.rebuild()
    rules = client.get(f"/api/projects/{pid}/automations").json()["rules"]
    assert len(rules) == 1 and rules[0]["action"]["type"] == "assign"

    r = client.patch(f"/api/projects/{pid}/automations/{rule['id']}", json={"enabled": False})
    assert r.status_code == 200 and r.json()["enabled"] is False
    r = client.patch(f"/api/projects/{pid}/automations/{rule['id']}",
                     json={"action": {"type": "set_priority", "value": "urgent"}})
    assert r.status_code == 422  # merged action must still validate (fail-closed)

    assert client.delete(f"/api/projects/{pid}/automations/{rule['id']}").status_code == 200
    assert client.get(f"/api/projects/{pid}/automations").json()["rules"] == []
    assert client.delete(f"/api/projects/{pid}/automations/{rule['id']}").status_code == 404
    assert client.patch(f"/api/projects/{pid}/automations/{rule['id']}",
                        json={"enabled": True}).status_code == 404


def test_rule_fires_with_automation_attribution(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    assert _rule(client, pid).status_code == 200
    assert client.post(f"/api/projects/{pid}/automations", json={
        "name": "严重度置 P0", "trigger_event": "item.created",
        "condition": {"concept_id": "bug"},
        "action": {"type": "set_field", "field_id": "severity", "value": "P0"},
    }).status_code == 200

    item = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "bug", "title": "登录崩溃"}).json()
    assert item["assignee_id"] == "qa-wang" and item["assignee_type"] == "human"
    assert item["custom_fields"]["severity"] == "P0"

    fired = client.get("/api/events", params={"event_type": "automation.rule_fired"}).json()["events"]
    assert len(fired) == 2
    assert all(e["actor_type"] == "automation" for e in fired)
    assert all(e["payload"]["item_id"] == item["id"] for e in fired)
    assigned = client.get("/api/events", params={"event_type": "item.assigned"}).json()["events"]
    assert any(e["actor_type"] == "automation" and e["payload"].get("assignee_id") == "qa-wang"
               for e in assigned)

    history = client.get(
        f"/api/projects/{pid}/automations/{fired[0]['agg_id']}/runs").json()
    assert history["total"] == 1 and history["runs"][0]["result"]["ok"] is True


def test_condition_gate_and_single_layer_no_loop(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    # B fires on item.updated — A's own automation writes must NOT trigger it.
    assert client.post(f"/api/projects/{pid}/automations", json={
        "name": "bug 建卡置严重度", "trigger_event": "item.created",
        "condition": {"concept_id": "bug"},
        "action": {"type": "set_field", "field_id": "severity", "value": "P1"},
    }).status_code == 200
    assert client.post(f"/api/projects/{pid}/automations", json={
        "name": "更新即提优先级", "trigger_event": "item.updated",
        "condition": {"fields": {"priority": "low"}},
        "action": {"type": "set_priority", "value": "high"},
    }).status_code == 200

    # A bug creation matches A (field written); a requirement creation matches nothing.
    client.post(f"/api/projects/{pid}/items", json={"concept_id": "bug", "title": "B1"})
    req = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "requirement", "title": "R1"}).json()
    fired = client.get("/api/events", params={"event_type": "automation.rule_fired"}).json()["events"]
    assert len(fired) == 1  # B never fired off A's item.updated (single-layer)
    assert fired[0]["payload"]["item_title"] == "B1"

    # A human update that matches B's condition fires it exactly once.
    client.patch(f"/api/items/{req['id']}", json={"priority": "low"})
    fired = client.get("/api/events", params={"event_type": "automation.rule_fired"}).json()["events"]
    assert len(fired) == 2
    assert fired[0]["payload"]["result"]["detail"].startswith("优先级")
    item = client.get(f"/api/items/{req['id']}").json()
    assert item["priority"] == "high"

    # Disabled rules don't fire.
    rules = client.get(f"/api/projects/{pid}/automations").json()["rules"]
    for rule in rules:
        client.patch(f"/api/projects/{pid}/automations/{rule['id']}", json={"enabled": False})
    client.post(f"/api/projects/{pid}/items", json={"concept_id": "bug", "title": "B2"})
    fired = client.get("/api/events", params={"event_type": "automation.rule_fired"}).json()["events"]
    assert len(fired) == 2


def test_rule_validation_fail_closed(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    assert _rule(client, pid, trigger_event="item.deleted").status_code == 422
    assert _rule(client, pid, action={"type": "close_ticket"}).status_code == 422
    assert _rule(client, pid, action={"type": "assign", "user_id": "ghost"}).status_code == 422
    assert _rule(client, pid,
                 action={"type": "set_field", "field_id": "nonsense", "value": "x"}).status_code == 422
    # severity is enum-declared: out-of-value is refused through the item write path.
    assert _rule(client, pid,
                 action={"type": "set_field", "field_id": "severity", "value": "urgent"}).status_code == 422
    assert _rule(client, pid, condition={"concept_id": "alien"}).status_code == 422
    assert _rule(client, pid, condition={"fields": {"nonsense": "x"}}).status_code == 422
    assert client.post(f"/api/projects/{pid}/automations", json={
        "name": "s", "trigger_event": "item.created", "condition": {"concept_id": "bug"},
        "action": {"type": "set_status", "status": "nonexistent"}}).status_code == 422
    assert client.get(f"/api/projects/{pid}/automations").json()["rules"] == []


def test_dry_run_reports_without_executing(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    rule = _rule(client, pid).json()
    # No trigger events yet.
    out = client.post(f"/api/projects/{pid}/automations/{rule['id']}/test").json()
    assert out["matched"] is False and "还没有" in out["reason"]

    bug = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "bug", "title": "崩溃"}).json()
    out = client.post(f"/api/projects/{pid}/automations/{rule['id']}/test").json()
    assert out["matched"] is True and out["item_id"] == bug["id"]
    assert out["action"]["type"] == "assign"

    # A strict rule whose condition the latest bug does not satisfy: dry-run reports
    # the miss AND a matching-but-never-fired action must stay unexecuted.
    strict = client.post(f"/api/projects/{pid}/automations", json={
        "name": "P0 才转修复中", "trigger_event": "item.created",
        "condition": {"concept_id": "bug", "fields": {"severity": "P0"}},
        "action": {"type": "set_status", "status": "fixing"},
    }).json()
    out = client.post(f"/api/projects/{pid}/automations/{strict['id']}/test").json()
    assert out["matched"] is False  # severity is unset on the latest bug
    assert client.get(f"/api/items/{bug['id']}").json()["status"] == "open"

    client.patch(f"/api/items/{bug['id']}", json={"custom_fields": {"severity": "P0"}})
    out = client.post(f"/api/projects/{pid}/automations/{strict['id']}/test").json()
    assert out["matched"] is True and out["action"]["type"] == "set_status"
    assert client.get(f"/api/items/{bug['id']}").json()["status"] == "open"  # dry-run 执行不了任何动作
