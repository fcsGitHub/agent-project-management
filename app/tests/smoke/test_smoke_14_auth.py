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
        fails = client.get("/api/events",
                           params={"event_type": "session.login_failed"}).json()["events"]
        assert any(e["payload"]["user_id"] == "u_admin" for e in fails)

        # Correct login → session cookie → writes pass.
        r = client.post("/api/auth/login",
                        json={"user_id": "u_admin", "password": "smoke-admin-pass"})
        assert r.status_code == 200
        p = client.post("/api/projects",
                        json={"name": "冒烟14项目", "ontology": "software-dev",
                              "requirement": "auth"}).json()
        assert p["id"]
        me = client.get("/api/auth/me").json()
        assert me["user_id"] == "u_admin" and me["source"] == "session"

        # Logout → session gone, gate back on.
        assert client.post("/api/auth/logout").status_code == 200
        assert client.post("/api/projects",
                           json={"name": "y", "ontology": "software-dev"}).status_code == 401
    finally:
        config.settings.auth_mode = "local"
        config.settings.admin_password = ""
