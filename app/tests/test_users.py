"""M5-I19 users & identity: registry projection, switching, assignee validation,
per-person audit filters."""
from __future__ import annotations

import pytest

from apm import config


@pytest.fixture(autouse=True)
def restore_identity():
    """Identity switching mutates process-global settings — always restore."""
    yield
    config.settings.user_id = "u_admin"


def test_default_user_bootstrapped(client, tmp_data):
    out = client.get("/api/users").json()
    assert out["current"] == "u_admin" and out["current_name"] == "李雷"
    assert any(u["id"] == "u_admin" for u in out["users"])


def test_register_switch_and_per_person_audit(client, tmp_data):
    u = client.post("/api/users", json={"name": "王工"}).json()
    assert u["name"] == "王工" and u["id"].startswith("u-")  # 中文姓名 → 短随机 id

    # Duplicate name → derived id differs, but registering is idempotent-ish; fine.
    r2 = client.post("/api/users", json={"id": "qa-wang", "name": "王工"})
    assert r2.status_code == 200 and r2.json()["id"] == "qa-wang"

    # Explicit id, charset enforced.
    assert client.post("/api/users", json={"id": "Bad Id", "name": "X"}).status_code == 422

    r = client.post("/api/session/identity", json={"user_id": "qa-wang"}).json()
    assert r["current"] == "qa-wang" and r["previous"] == "u_admin"

    # Actions under the new identity are attributed to it.
    p = client.post("/api/projects", json={"name": "协作项目", "ontology": "software-dev"}).json()
    evs = client.get("/api/events", params={"actor_id": "qa-wang"}).json()["events"]
    assert evs and all(e["actor_id"] == "qa-wang" for e in evs)
    assert any(e["event_type"] == "project.created" for e in evs)

    # The switch itself is auditable.
    sw = client.get("/api/events", params={"event_type": "session.identity_switched"}).json()["events"]
    assert sw and sw[0]["payload"]["from"] == "u_admin" and sw[0]["payload"]["to"] == "qa-wang"

    # Unknown identity rejected.
    assert client.post("/api/session/identity", json={"user_id": "ghost"}).status_code == 422


def test_human_assignee_requires_registered_user(client, tmp_data):
    client.post("/api/users", json={"id": "qa1", "name": "测试员"})
    p = client.post("/api/projects", json={"name": "指派项目", "ontology": "software-dev"}).json()
    pid = p["id"]

    ok = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "bug", "title": "崩溃", "priority": "P1"})
    assert ok.status_code == 200
    item_id = client.get(f"/api/projects/{pid}/items").json()["items"][0]["id"]

    # Unregistered human assignee fails closed; registered passes with name echoed.
    r = client.patch(f"/api/items/{item_id}", json={"assignee_type": "human", "assignee_id": "ghost"})
    assert r.status_code == 422
    r = client.patch(f"/api/items/{item_id}", json={"assignee_type": "human", "assignee_id": "qa1"})
    assert r.status_code == 200
    detail = client.get(f"/api/items/{item_id}").json()
    assert detail["assignee_id"] == "qa1" and detail["assignee_name"] == "测试员"

    # Creation-time validation too.
    r = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "X", "assignee_type": "human",
                          "assignee_id": "ghost"})
    assert r.status_code == 422

    # Role assignees stay free-form.
    r = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "Y", "assignee_type": "role",
                          "assignee_id": "dev-agent"})
    assert r.status_code == 200

    # Per-assignee item filter (board slice).
    items = client.get(f"/api/projects/{pid}/items", params={"assignee_id": "qa1"}).json()["items"]
    assert len(items) == 1 and items[0]["assignee_name"] == "测试员"


def test_approvals_filter_by_decider(client, tmp_data, isolated_ontologies):
    from apm.core import events

    events.emit(event_type="approval.requested", agg_type="approval", agg_id="apr_u1",
                project_id="", payload={"kind": "gate", "snapshot": {"gate": "prd_review"}})
    events.emit(event_type="approval.granted", agg_type="approval", agg_id="apr_u1",
                actor_id="u_admin", payload={"comment": "通过"})
    events.emit(event_type="approval.requested", agg_type="approval", agg_id="apr_u2",
                project_id="", payload={"kind": "gate", "snapshot": {"gate": "design_review"}})
    events.emit(event_type="approval.granted", agg_type="approval", agg_id="apr_u2",
                actor_id="qa1", payload={"comment": "ok"})

    mine = client.get("/api/approvals", params={"decided_by": "qa1", "status": "approved"}).json()
    assert [a["id"] for a in mine["approvals"]] == ["apr_u2"]
    admins = client.get("/api/approvals", params={"decided_by": "u_admin", "status": "approved"}).json()
    assert [a["id"] for a in admins["approvals"]] == ["apr_u1"]
