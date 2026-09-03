"""M10-I34 notification center: notifications as a pure projection of existing
events (item.assigned → assignee, approval.requested → owners, the automation
`notify` action → targeted user), event-sourced read state, rebuild survival."""
from __future__ import annotations

import pytest

from apm.core import projections, events
from apm.core.ids import new_id


@pytest.fixture(autouse=True)
def _restore_identity():
    """/api/session/identity mutates settings.user_id globally (local-mode
    identity); restore it so leakage doesn't cross test boundaries."""
    from apm import config

    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "通知演示", "ontology": "software-dev", "requirement": "I34"})
    assert r.status_code == 200
    return r.json()


def test_assigned_notification_and_read_flow(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    bug = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "bug", "title": "指派通知"}).json()
    assert client.patch(f"/api/items/{bug['id']}",
                        json={"assignee_type": "human", "assignee_id": "qa-wang"}).status_code == 200

    # Switch identity so the assignee has their own notification stream.
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    out = client.get("/api/notifications").json()
    assert out["user_id"] == "qa-wang" and out["unread"] == 1
    assert out["notifications"][0]["kind"] == "assigned"
    assert "指派通知" in out["notifications"][0]["summary"]

    # Mark the single notification read.
    nid = out["notifications"][0]["id"]
    assert client.post("/api/notifications/read", json={"ids": [nid]}).status_code == 200
    assert client.get("/api/notifications").json()["unread"] == 0

    # Read-state survives rebuild (event-sourced).
    projections.rebuild()
    assert client.get("/api/notifications").json()["unread"] == 0


def test_read_all_and_validation(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    client.post("/api/users", json={"id": "dev-zhang", "name": "Dev 张"})
    items = []
    for t in ("a", "b", "c"):
        it = client.post(f"/api/projects/{pid}/items",
                         json={"concept_id": "task", "title": t}).json()
        items.append(it["id"])
        client.patch(f"/api/items/{it['id']}",
                     json={"assignee_type": "human", "assignee_id": "qa-wang"})
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert client.get("/api/notifications").json()["unread"] == 3

    # Only rows belonging to the caller can be marked; unknown ids 404.
    assert client.post("/api/notifications/read",
                       json={"ids": ["n_nope"]}).status_code == 404
    assert client.post("/api/notifications/read", json={"all": True}).status_code == 200
    assert client.get("/api/notifications").json()["unread"] == 0

    # Empty body refused.
    assert client.post("/api/notifications/read", json={}).status_code == 422


def test_approval_requested_notifies_project_owners(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    events.emit(
        event_type="approval.requested", agg_type="approval", agg_id=new_id("apr"),
        project_id=pid, actor_type="system", actor_id="system",
        payload={"kind": "prd_review", "snapshot": {"summary": "PRD 审批"}},
    )
    owners = client.get("/api/notifications").json()
    assert owners["user_id"] == "u_admin" and owners["unread"] == 1
    assert owners["notifications"][0]["kind"] == "approval"
    assert "prd_review" in owners["notifications"][0]["summary"]


def test_automation_notify_action(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})

    # Validation: unknown user / over-long message refused at rule creation.
    assert client.post(f"/api/projects/{pid}/automations", json={
        "name": "坏用户", "trigger_event": "item.created", "condition": {"concept_id": "bug"},
        "action": {"type": "notify", "user_id": "ghost"}}).status_code == 422
    assert client.post(f"/api/projects/{pid}/automations", json={
        "name": "超长", "trigger_event": "item.created", "condition": {"concept_id": "bug"},
        "action": {"type": "notify", "user_id": "qa-wang", "message": "x" * 201}}).status_code == 422

    assert client.post(f"/api/projects/{pid}/automations", json={
        "name": "建缺陷通知 QA", "trigger_event": "item.created",
        "condition": {"concept_id": "bug"},
        "action": {"type": "notify", "user_id": "qa-wang", "message": "有新缺陷请关注"}}).status_code == 200

    # Switch the stream to the target user before triggering.
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    before = client.get("/api/notifications").json()["unread"]
    client.post(f"/api/projects/{pid}/items", json={"concept_id": "bug", "title": "通知触发"})

    out = client.get("/api/notifications").json()
    assert out["unread"] == before + 1
    note = out["notifications"][0]
    assert note["kind"] == "rule_notify" and "有新缺陷请关注" in note["summary"]

    fired = client.get("/api/events", params={"event_type": "automation.rule_fired"}).json()["events"]
    assert fired and fired[0]["payload"]["result"]["detail"].startswith("已通知 qa-wang")
    assert fired[0]["actor_type"] == "automation"
