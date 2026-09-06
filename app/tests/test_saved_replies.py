"""I108 saved replies (docs/01 §AH.2, GitHub Saved Replies semantics): the
user's own canned responses as runtime state — own-data only, length-capped,
and deliberately outside drop_projections so a rebuild keeps the library."""
from __future__ import annotations

import pytest

from apm import config
from apm.core import db, projections


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "常用回复演示", "ontology": "software-dev", "requirement": "I108"})
    assert r.status_code == 200
    return r.json()


def test_crud_roundtrip_own_data_only(client, tmp_data, isolated_ontologies, project):
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    assert client.get("/api/me/saved-replies").json()["replies"] == []

    r1 = client.post("/api/me/saved-replies",
                     json={"title": "LGTM", "body": "LGTM，注意补测试。"})
    assert r1.status_code == 200, r1.text
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    r2 = client.post("/api/me/saved-replies",
                     json={"title": "需要复现步骤", "body": "请附复现步骤与截图。"})
    assert r2.status_code == 200
    client.post("/api/session/identity", json={"user_id": "u_admin"})

    # each identity sees only its own library
    mine = [x["title"] for x in client.get("/api/me/saved-replies").json()["replies"]]
    theirs = [x["title"] for x in client.post(
        "/api/session/identity", json={"user_id": "qa-wang"})
        and client.get("/api/me/saved-replies").json()["replies"]]
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    assert mine == ["LGTM"] and theirs == ["需要复现步骤"]

    # deleting someone else's reply is a 404 (own-data strictly scoped)
    other_id = client.post("/api/session/identity", json={"user_id": "qa-wang"}) and \
        client.get("/api/me/saved-replies").json()["replies"][0]["id"]
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    assert client.delete(f"/api/me/saved-replies/{other_id}").status_code == 404
    mine_id = client.get("/api/me/saved-replies").json()["replies"][0]["id"]
    assert client.delete(f"/api/me/saved-replies/{mine_id}").status_code == 200
    assert client.get("/api/me/saved-replies").json()["replies"] == []


def test_validation_caps(client, tmp_data, isolated_ontologies, project):
    assert client.post("/api/me/saved-replies",
                       json={"title": "", "body": "x"}).status_code == 422
    assert client.post("/api/me/saved-replies",
                       json={"title": "t", "body": "  "}).status_code == 422
    assert client.post("/api/me/saved-replies",
                       json={"title": "t" * 101, "body": "x"}).status_code == 422
    assert client.post("/api/me/saved-replies",
                       json={"title": "t", "body": "x" * 2001}).status_code == 422
    ok = client.post("/api/me/saved-replies",
                     json={"title": "t" * 100, "body": "x" * 2000})
    assert ok.status_code == 200


def test_rebuild_keeps_the_library(client, tmp_data, isolated_ontologies, project):
    client.post("/api/me/saved-replies", json={"title": "留存", "body": "重建后还在。"})
    projections.rebuild()
    titles = [x["title"] for x in client.get("/api/me/saved-replies").json()["replies"]]
    assert titles == ["留存"]  # runtime state, not in drop_projections
