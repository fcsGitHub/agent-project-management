"""I97 responsiveness metrics (docs/01 §AD.3, CHAOSS Time to First Response):
approval latency straight off the approvals projection, comment first-response
from the event stream excluding the author, honest None on empty slices, and
byte-stable numbers across rebuild."""
from __future__ import annotations

import pytest

from apm.core import db, events, projections
from apm.core.ids import new_id


@pytest.fixture(autouse=True)
def _restore_identity():
    from apm import config

    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "响应力演示", "ontology": "software-dev", "requirement": "I97"})
    assert r.status_code == 200
    return r.json()


def _gate(client, pid: str, agg_id: str, decision: str | None) -> None:
    events.emit(
        event_type="approval.requested", agg_type="approval", agg_id=agg_id,
        project_id=pid, actor_type="system", actor_id="system",
        payload={"kind": "gate_review", "snapshot": {}})
    if decision:
        events.emit(
            event_type=f"approval.{decision}", agg_type="approval", agg_id=agg_id,
            project_id=pid, actor_type="human", actor_id="u_admin",
            payload={"kind": "gate_review", "comment": "ok"})


def test_empty_project_honest_none(client, tmp_data, isolated_ontologies, project):
    body = client.get(f"/api/projects/{project['id']}/responsiveness").json()
    assert body["approvals"] is None and body["comments"] is None
    assert body["comments_unanswered"] == 0


def test_approval_pairs_and_pending_excluded(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    _gate(client, pid, new_id("apr"), "granted")
    _gate(client, pid, new_id("apr"), "rejected")
    _gate(client, pid, new_id("apr"), None)  # still pending → no sample

    body = client.get(f"/api/projects/{pid}/responsiveness").json()
    a = body["approvals"]
    assert a is not None and a["count"] == 2
    assert a["avg_h"] < 1 and a["over_48h"] == 0  # decided within the test second


def test_comment_first_response_excludes_author(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    bug = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "bug", "title": "响应对象"}).json()

    # admin asks, qa-wang answers → admin's comment has one first response
    client.post(f"/api/items/{bug['id']}/comments", json={"body": "第一条，求助"})
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    client.post(f"/api/items/{bug['id']}/comments", json={"body": "第二条，回复"})
    # qa-wang's own comment has no reply yet
    body = client.get(f"/api/projects/{pid}/responsiveness").json()
    assert body["comments"]["count"] == 1
    assert body["comments"]["avg_h"] < 1
    assert body["comments_unanswered"] == 1

    # a fresh project where the author replies to himself → nothing counts
    p2 = client.post("/api/projects",
                     json={"name": "自说自话", "ontology": "software-dev", "requirement": "x"}).json()
    b2 = client.post(f"/api/projects/{p2['id']}/items",
                     json={"concept_id": "bug", "title": "自评"}).json()
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    client.post(f"/api/items/{b2['id']}/comments", json={"body": "一"})
    client.post(f"/api/items/{b2['id']}/comments", json={"body": "二"})
    body2 = client.get(f"/api/projects/{p2['id']}/responsiveness").json()
    assert body2["comments"] is None and body2["comments_unanswered"] == 2


def test_rebuild_reproduces_numbers(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    _gate(client, pid, new_id("apr"), "granted")
    bug = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "bug", "title": "重建对账"}).json()
    client.post(f"/api/items/{bug['id']}/comments", json={"body": "问"})
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    client.post(f"/api/items/{bug['id']}/comments", json={"body": "答"})

    before = client.get(f"/api/projects/{pid}/responsiveness").json()
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    projections.rebuild()
    after = client.get(f"/api/projects/{pid}/responsiveness").json()

    assert after["approvals"] == before["approvals"]
    assert after["comments"] == before["comments"]
    assert after["comments_unanswered"] == before["comments_unanswered"]
