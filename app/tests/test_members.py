"""M8-I27 project membership & roles: creator-as-owner, member management API,
and network-mode write gating (viewer / non-member → 403 with audit)."""
from __future__ import annotations

import pytest

from apm import config


@pytest.fixture()
def project(client):
    r = client.post("/api/projects",
                    json={"name": "成员演示", "ontology": "software-dev", "requirement": "I27"})
    assert r.status_code == 200
    return r.json()


def test_creator_becomes_owner_and_management_roundtrip(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    members = client.get(f"/api/projects/{pid}/members").json()["members"]
    assert [(m["user_id"], m["role"]) for m in members] == [("u_admin", "owner")]

    client.post("/api/users", json={"id": "qa-li", "name": "QA 李"})
    r = client.post(f"/api/projects/{pid}/members",
                    json={"user_id": "qa-li", "role": "viewer"})
    assert r.status_code == 200
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "qa-li", "role": "viewer"}).status_code == 409

    r = client.patch(f"/api/projects/{pid}/members",
                     json={"user_id": "qa-li", "role": "contributor"})
    assert r.status_code == 200
    roles = {m["user_id"]: m["role"] for m in client.get(f"/api/projects/{pid}/members").json()["members"]}
    assert roles["qa-li"] == "contributor"

    # Last owner is protected.
    assert client.delete(f"/api/projects/{pid}/members/u_admin").status_code == 422
    assert client.patch(f"/api/projects/{pid}/members",
                        json={"user_id": "u_admin", "role": "viewer"}).status_code == 422

    assert client.delete(f"/api/projects/{pid}/members/qa-li").status_code == 200
    roles = {m["user_id"]: m["role"] for m in client.get(f"/api/projects/{pid}/members").json()["members"]}
    assert "qa-li" not in roles

    # Unknown users can't join; unknown member can't be patched.
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "ghost", "role": "viewer"}).status_code == 422
    assert client.patch(f"/api/projects/{pid}/members",
                        json={"user_id": "ghost", "role": "viewer"}).status_code == 404


def test_network_mode_role_gate(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    # Give the default identity a password so it can log in under network mode.
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user

    ensure_default_user()
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "password": "qa-pass"})
    client.post("/api/users", json={"id": "dev-zhang", "name": "Dev 张", "password": "dev-pass"})
    client.post(f"/api/projects/{pid}/members", json={"user_id": "qa-wang", "role": "viewer"})
    client.post(f"/api/projects/{pid}/members", json={"user_id": "dev-zhang", "role": "contributor"})

    config.settings.auth_mode = "network"
    try:
        item = {"concept_id": "task", "title": "写操作"}

        # Viewer: read ok, write forbidden + audited.
        assert client.post("/api/auth/login",
                           json={"user_id": "qa-wang", "password": "qa-pass"}).status_code == 200
        assert client.get(f"/api/projects/{pid}/board").status_code == 200
        r = client.post(f"/api/projects/{pid}/items", json=item)
        assert r.status_code == 403
        denied = client.get("/api/events", params={"event_type": "access.denied"}).json()["events"]
        assert any(e["payload"]["user_id"] == "qa-wang" and e["project_id"] == pid for e in denied)

        # Contributor: writes pass.
        assert client.post("/api/auth/login",
                           json={"user_id": "dev-zhang", "password": "dev-pass"}).status_code == 200
        assert client.post(f"/api/projects/{pid}/items", json=item).status_code == 200

        # Non-member: forbidden on pid.（安全收紧：network 模式下带密码账号
        # 只能由管理员创建——先切回管理员建号，再以外人身份登录。）
        assert client.post("/api/auth/login",
                           json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
        assert client.post("/api/users",
                           json={"id": "outsider", "name": "外人", "password": "out-pass"}).status_code == 200
        assert client.post("/api/auth/login",
                           json={"user_id": "outsider", "password": "out-pass"}).status_code == 200
        r = client.post(f"/api/projects/{pid}/items", json=item)
        assert r.status_code == 403
        # (Session→actor attribution lands in I28; project creation itself stays
        # open to any logged-in identity.)
    finally:
        config.settings.auth_mode = "local"
        config.settings.admin_password = ""

def test_membership_survives_rebuild(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    client.post("/api/users", json={"id": "qa-li", "name": "QA 李"})
    client.post(f"/api/projects/{pid}/members", json={"user_id": "qa-li", "role": "viewer"})
    assert client.post("/api/system/rebuild-projections").status_code == 200
    roles = {m["user_id"]: m["role"] for m in client.get(f"/api/projects/{pid}/members").json()["members"]}
    assert roles == {"u_admin": "owner", "qa-li": "viewer"}
