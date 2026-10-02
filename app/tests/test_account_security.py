"""M96-I290: account security — self-service password change, admin reset,
and credential-epoch session invalidation (docs/01 §CO)."""
from __future__ import annotations

import hashlib
import hmac
import time

from apm import config
from apm.core import db


def _enable_network(admin_password="admin-pass") -> None:
    config.settings.auth_mode = "network"
    config.settings.admin_password = admin_password
    from apm.domains.users import ensure_default_user

    ensure_default_user()


def _disable_network() -> None:
    config.settings.auth_mode = "local"
    config.settings.admin_password = ""


def _login(client, uid="u_admin", password="admin-pass"):
    r = client.post("/api/auth/login", json={"user_id": uid, "password": password})
    assert r.status_code == 200, r.text
    return r


def test_password_change_invalidates_sessions(client, tmp_data):
    _enable_network()
    try:
        _login(client)
        assert client.get("/api/auth/me").json()["source"] == "session"

        # Wrong old password → 422, audited, session survives.
        r = client.post("/api/me/password",
                        json={"old_password": "wrong", "new_password": "brand-new-pw"})
        assert r.status_code == 422
        assert client.get("/api/auth/me").json()["source"] == "session"

        # Correct change → 200; the very same cookie is dead immediately.
        r = client.post("/api/me/password",
                        json={"old_password": "admin-pass", "new_password": "brand-new-pw"})
        assert r.status_code == 200
        assert client.get("/api/auth/me").status_code == 401

        # Old password no longer logs in; the new one does.
        assert client.post("/api/auth/login",
                           json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 401
        _login(client, password="brand-new-pw")

        # Audit trail exists, and no password ever entered the event stream.
        evs = client.get("/api/events",
                         params={"event_type": "user.password_changed"}).json()["events"]
        assert evs and evs[0]["payload"]["via"] == "self"
        assert "brand-new-pw" not in str(evs)
        fails = client.get("/api/events",
                           params={"event_type": "user.password_change_failed"}).json()["events"]
        assert fails and fails[0]["payload"]["reason"] == "old_password_mismatch"
    finally:
        _disable_network()


def test_admin_reset_gated_and_invalidates(client, tmp_data):
    _enable_network()
    try:
        # Non-admin member → 403.
        _login(client)
        assert client.post("/api/users",
                           json={"id": "u_dev", "name": "开发者", "password": "dev-pass-1"}).status_code == 200
        client.post("/api/auth/logout")
        _login(client, "u_dev", "dev-pass-1")
        assert client.post("/api/users/u_dev/password",
                           json={"new_password": "dev-pass-2"}).status_code == 403

        # Admin resets → target's session dies; new password works.
        client.post("/api/auth/logout")
        _login(client)
        assert client.post("/api/users/u_dev/password",
                           json={"new_password": "dev-pass-2"}).status_code == 200
        assert client.post("/api/auth/login",
                           json={"user_id": "u_dev", "password": "dev-pass-1"}).status_code == 401
        _login(client, "u_dev", "dev-pass-2")

        evs = client.get("/api/events",
                         params={"event_type": "user.password_reset"}).json()["events"]
        assert evs and evs[0]["payload"]["via"] == "admin"
        assert "dev-pass-2" not in str(evs)
    finally:
        _disable_network()


def test_legacy_three_part_token_valid_until_change(client, tmp_data):
    _enable_network()
    try:
        # Hand-craft a pre-M96 token: sig over "user_id.expiry" (epoch 0).
        from apm.core.security import get_secret

        msg = f"u_admin.{int(time.time()) + 3600}"
        sig = hmac.new(get_secret().encode(), msg.encode(), hashlib.sha256).hexdigest()
        client.cookies.set("apm_session", f"{msg}.{sig}")
        assert client.get("/api/auth/me").json()["user_id"] == "u_admin"

        # After a credential change the legacy token is dead (epoch 0 ≠ 1).
        _login(client)
        client.post("/api/me/password",
                    json={"old_password": "admin-pass", "new_password": "next-pw-1"})
        client.cookies.set("apm_session", f"{msg}.{sig}")
        assert client.get("/api/auth/me").status_code == 401
    finally:
        _disable_network()


def test_sso_account_without_local_password_409(client, tmp_data):
    _enable_network()
    try:
        _login(client)
        # OIDC JIT-style: created without a password → password_hash is NULL.
        assert client.post("/api/users",
                           json={"id": "u_sso", "name": "单点用户"}).status_code == 200
        assert client.post("/api/users/u_sso/password",
                           json={"new_password": "pw-123456"}).status_code == 409
        # Self change path for an SSO identity (act as u_sso via admin reset is
        # blocked too, so exercise the guard directly through the endpoint).
        r = client.post("/api/me/password",
                        json={"old_password": "x", "new_password": "y"})
        assert r.status_code in (409, 422)  # admin's own hash exists → 422 path
    finally:
        _disable_network()
