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

        # Failed logins are audited (M114-I339: the raw event stream demands a
        # session, so the audit read happens after the successful login — the
        # login_failed row itself predates it and is still on the stream).
        assert client.post("/api/auth/login",
                           json={"user_id": "u_admin", "password": "nope"}).status_code == 401

        # Successful login → cookie → writes pass → me reports session identity.
        r = client.post("/api/auth/login",
                        json={"user_id": "u_admin", "password": "admin-pass"})
        assert r.status_code == 200 and "apm_session" in r.cookies
        evs = client.get("/api/events",
                         params={"event_type": "session.login_failed"}).json()["events"]
        assert any(e["payload"]["user_id"] == "u_admin" for e in evs)
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


# ---- 登录防爆破（M82-I247）----

import time

from apm.domains import auth_api


def _clear_login_guard() -> None:
    auth_api._login_failures.clear()


def test_login_lockout_window(client, tmp_data):
    """窗口内失败达阈值→临时锁定（正确密码也 429）→窗口滑出自动解除。"""
    _enable_network()
    try:
        _clear_login_guard()
        for _ in range(auth_api.LOCKOUT_MAX_FAILURES - 1):
            assert client.post("/api/auth/login",
                               json={"user_id": "u_admin", "password": "nope"}).status_code == 401
        # 第 5 次失败（达阈值的那次本身）仍是 401——锁定从下一次尝试起生效。
        assert client.post("/api/auth/login",
                           json={"user_id": "u_admin", "password": "nope"}).status_code == 401
        # 锁定生效：正确密码也 429 + Retry-After。
        r = client.post("/api/auth/login",
                        json={"user_id": "u_admin", "password": "admin-pass"})
        assert r.status_code == 429
        assert 0 < int(r.headers["Retry-After"]) <= auth_api.LOCKOUT_WINDOW_SECONDS

        # 窗口滑出 → 自动解除，正确密码恢复登录。
        auth_api._login_failures["u_admin"] = [time.monotonic() - auth_api.LOCKOUT_WINDOW_SECONDS - 1]
        assert client.post("/api/auth/login",
                           json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
        # 锁定转折点只发一次 session.login_locked（防攻击者逐次 429 灌水审计流）。
        # M114-I339: 审计读在恢复登录之后（事件流不再对匿名开放），断言强度不变。
        evs = client.get("/api/events",
                         params={"event_type": "session.login_locked"}).json()["events"]
        assert len(evs) == 1 and evs[0]["payload"]["user_id"] == "u_admin"
    finally:
        _clear_login_guard()
        _disable_network()


def test_login_success_clears_failure_count(client, tmp_data):
    """成功登录清零计数：3 败→成功→再 4 败仍是 401 而非 429。"""
    _enable_network()
    try:
        _clear_login_guard()
        for _ in range(3):
            assert client.post("/api/auth/login",
                               json={"user_id": "u_admin", "password": "nope"}).status_code == 401
        assert client.post("/api/auth/login",
                           json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
        for _ in range(4):
            assert client.post("/api/auth/login",
                               json={"user_id": "u_admin", "password": "nope"}).status_code == 401
        assert client.post("/api/auth/login",
                           json={"user_id": "u_admin", "password": "nope"}).status_code == 401
    finally:
        _clear_login_guard()
        _disable_network()


def test_lockout_is_per_user_and_covers_unknown(client, tmp_data):
    """锁定按用户隔离：未知用户名同样计入锁定，且不殃及他人。"""
    _enable_network()
    try:
        _clear_login_guard()
        for _ in range(auth_api.LOCKOUT_MAX_FAILURES):
            assert client.post("/api/auth/login",
                               json={"user_id": "u_ghost", "password": "x"}).status_code == 401
        assert client.post("/api/auth/login",
                           json={"user_id": "u_ghost", "password": "x"}).status_code == 429
        # 其他用户不受影响。
        assert client.post("/api/auth/login",
                           json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
    finally:
        _clear_login_guard()
        _disable_network()
