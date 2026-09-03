"""M8-I26 auth foundation: pbkdf2 credentials, signed session cookie, auth_mode
gate with audited login events."""
from __future__ import annotations

from apm import config
from apm.core.security import hash_password, verify_password


def test_password_hash_roundtrip():
    h = hash_password("s3cret")
    assert h != "s3cret" and h.startswith("pbkdf2$")
    assert verify_password("s3cret", h)
    assert not verify_password("wrong", h)
    assert not verify_password("s3cret", None)
    assert not verify_password("s3cret", "garbage")


def _enable_network(admin_password="admin-pass") -> None:
    config.settings.auth_mode = "network"
    config.settings.admin_password = admin_password
    from apm.domains.users import ensure_default_user

    ensure_default_user()


def _disable_network() -> None:
    config.settings.auth_mode = "local"
    config.settings.admin_password = ""


def test_network_mode_requires_login_for_writes(client, tmp_data):
    _enable_network()
    try:
        # Reads stay open; writes are refused without a session.
        assert client.get("/api/projects").status_code == 200
        assert client.post("/api/projects", json={"name": "x"}).status_code == 401

        # Failed logins are audited.
        assert client.post("/api/auth/login",
                           json={"user_id": "u_admin", "password": "nope"}).status_code == 401
        evs = client.get("/api/events",
                         params={"event_type": "session.login_failed"}).json()["events"]
        assert any(e["payload"]["user_id"] == "u_admin" for e in evs)

        # Successful login → cookie → writes pass → me reports session identity.
        r = client.post("/api/auth/login",
                        json={"user_id": "u_admin", "password": "admin-pass"})
        assert r.status_code == 200 and "apm_session" in r.cookies
        assert client.post("/api/projects",
                           json={"name": "网络项目", "ontology": "software-dev"}).status_code == 200
        me = client.get("/api/auth/me").json()
        assert me["user_id"] == "u_admin" and me["source"] == "session" and me["is_admin"] is True
        evs = client.get("/api/events",
                         params={"event_type": "session.logged_in"}).json()["events"]
        assert evs

        # Logout clears the session → gated again.
        assert client.post("/api/auth/logout").status_code == 200
        assert client.post("/api/projects", json={"name": "y"}).status_code == 401
    finally:
        _disable_network()


def test_local_mode_stays_open(client, tmp_data):
    assert client.post("/api/projects",
                       json={"name": "本地项目", "ontology": "software-dev"}).status_code == 200
    me = client.get("/api/auth/me").json()
    assert me["source"] == "local" and me["user_id"] == "u_admin"


def test_passwordless_user_cannot_login(client, tmp_data):
    client.post("/api/users", json={"id": "qa-li", "name": "qa-li"})
    _enable_network()
    try:
        assert client.post("/api/auth/login",
                           json={"user_id": "qa-li", "password": "whatever"}).status_code == 401
    finally:
        _disable_network()
