"""I99 external intake (docs/01 §AE.2, Trello board-email semantics over HTTP):
the token is the credential — no login, whitelisted fields, first-class item
through create_item's full validation chain, owner-only token management, and
tokens survive rebuild (they are projections of intake.token_* events)."""
from __future__ import annotations

import pytest

from apm.core import db, projections


@pytest.fixture(autouse=True)
def _restore_identity():
    from apm import config

    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "收件箱演示", "ontology": "software-dev", "requirement": "I99"})
    assert r.status_code == 200
    return r.json()


def _issue(client, pid: str) -> str:
    r = client.post(f"/api/projects/{pid}/intake-token", json={})
    assert r.status_code == 200
    return r.json()["token"]


def test_token_roundtrip_and_attribution(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    assert client.get(f"/api/projects/{pid}/intake-token").json()["issued"] is False

    token = _issue(client, pid)

    # unauthenticated submission lands a first-class item
    r = client.post(f"/api/intake/{token}",
                    json={"title": "来自外部的报告", "priority": "high"})
    assert r.status_code == 200, r.text
    item_id = r.json()["item_id"]
    items = client.get(f"/api/projects/{pid}/items").json()["items"]
    mine = next(i for i in items if i["id"] == item_id)
    assert mine["title"] == "来自外部的报告" and mine["priority"] == "high"
    assert mine["status_group"] not in ("done", "cancelled")

    # whitelisted fields only: bad priority and blank title are refused
    assert client.post(f"/api/intake/{token}",
                       json={"title": "x", "priority": "urgent"}).status_code == 422
    assert client.post(f"/api/intake/{token}", json={"title": "  "}).status_code == 422
    # unknown token → 401 (the credential is wrong, not forbidden)
    assert client.post("/api/intake/itk_nope", json={"title": "x"}).status_code == 401


def test_revoke_and_reissue_rotates_credential(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    token = _issue(client, pid)
    assert client.delete(f"/api/projects/{pid}/intake-token").status_code == 200
    assert client.post(f"/api/intake/{token}", json={"title": "吊销后"}).status_code == 401

    token2 = _issue(client, pid)  # re-issue mints a fresh credential
    assert token2 != token
    assert client.post(f"/api/intake/{token2}", json={"title": "新令牌可用"}).status_code == 200
    assert client.post(f"/api/intake/{token}", json={"title": "旧令牌仍死"}).status_code == 401


def test_tokens_survive_rebuild(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    token = _issue(client, pid)
    projections.rebuild()
    r = client.post(f"/api/intake/{token}", json={"title": "重建后依然可收"})
    assert r.status_code == 200
    assert "重建后依然可收" in [i["title"] for i in
                           client.get(f"/api/projects/{pid}/items").json()["items"]]
