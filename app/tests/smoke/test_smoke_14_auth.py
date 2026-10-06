"""Smoke 14 (M8-I26): auth foundation — network mode gates mutations, login/
logout/logout events are audited, passwordless users fail closed, and local
mode keeps the old no-login behavior."""
import pytest

from apm import config


@pytest.mark.smoke
def test_smoke_14_auth_foundation(client, tmp_data):
    try:
        config.settings.auth_mode = "network"
        config.settings.admin_password = "smoke-admin-pass"
        from apm.domains.users import ensure_default_user

        ensure_default_user()

        # Unauthenticated writes are refused; reads stay open.
        assert client.post("/api/projects",
                           json={"name": "x", "ontology": "software-dev"}).status_code == 401
        assert client.get("/api/projects").status_code == 200

        # Wrong password → 401 + audited failure.
        assert client.post("/api/auth/login",
                           json={"user_id": "u_admin", "password": "wrong"}).status_code == 401

        # Correct login → session cookie → writes pass.
        r = client.post("/api/auth/login",
                        json={"user_id": "u_admin", "password": "smoke-admin-pass"})
        assert r.status_code == 200
        # M114-I339: the raw event stream demands a session — the audit read
        # for the failed attempt happens after the successful login.
        fails = client.get("/api/events",
                           params={"event_type": "session.login_failed"}).json()["events"]
        assert any(e["payload"]["user_id"] == "u_admin" for e in fails)
        p = client.post("/api/projects",
                        json={"name": "冒烟14项目", "ontology": "software-dev",
                              "requirement": "auth"}).json()
        assert p["id"]
        me = client.get("/api/auth/me").json()
        assert me["user_id"] == "u_admin" and me["source"] == "session"
        # Admin-style account creation while signed in (M8-I27).
        assert client.post("/api/users",
                           json={"id": "qa-wang", "name": "QA 王", "password": "qa-pass"}).status_code == 200

        # Logout → session gone, gate back on.
        assert client.post("/api/auth/logout").status_code == 200
        assert client.post("/api/projects",
                           json={"name": "y", "ontology": "software-dev"}).status_code == 401

        # Membership & roles (M8-I27): creator owns the project; a viewer member
        # can read but their writes are forbidden and audited.
        assert client.post("/api/auth/login",
                           json={"user_id": "u_admin", "password": "smoke-admin-pass"}).status_code == 200
        p = client.post("/api/projects",
                        json={"name": "冒烟14成员项目", "ontology": "software-dev"}).json()
        members = client.get(f"/api/projects/{p['id']}/members").json()["members"]
        assert members[0]["user_id"] == "u_admin" and members[0]["role"] == "owner"
        assert client.post(f"/api/projects/{p['id']}/members",
                           json={"user_id": "qa-wang", "role": "viewer"}).status_code == 200
        assert client.post("/api/auth/login",
                           json={"user_id": "qa-wang", "password": "qa-pass"}).status_code == 200
        assert client.get(f"/api/projects/{p['id']}/board").status_code == 200
        assert client.post(f"/api/projects/{p['id']}/items",
                           json={"concept_id": "task", "title": "T"}).status_code == 403
        denied = client.get("/api/events", params={"event_type": "access.denied"}).json()["events"]
        assert any(e["payload"]["user_id"] == "qa-wang" and e["project_id"] == p["id"] for e in denied)

        # Session→actor attribution (M8-I28): qa-wang promotes to contributor and
        # their writes are attributed to qa-wang, not the local default identity.
        assert client.post("/api/auth/login",
                           json={"user_id": "u_admin", "password": "smoke-admin-pass"}).status_code == 200
        assert client.patch(f"/api/projects/{p['id']}/members",
                            json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200
        assert client.post("/api/auth/login",
                           json={"user_id": "qa-wang", "password": "qa-pass"}).status_code == 200
        assert client.post(f"/api/projects/{p['id']}/items",
                           json={"concept_id": "task", "title": "QA 的任务"}).status_code == 200
        created = client.get("/api/events", params={"event_type": "item.created"}).json()["events"]
        assert created and created[-1]["actor_id"] == "qa-wang"
        # qa-wang creates their own project → they own it (creator-as-owner).
        own = client.post("/api/projects",
                          json={"name": "QA 自建项目", "ontology": "software-dev"}).json()
        members = {m["user_id"]: m["role"] for m in client.get(f"/api/projects/{own['id']}/members").json()["members"]}
        assert members["qa-wang"] == "owner"
        # Local identity switching is refused under network mode.
        assert client.post("/api/session/identity",
                           json={"user_id": "u_admin"}).status_code == 422
    finally:
        config.settings.auth_mode = "local"
        config.settings.admin_password = ""
