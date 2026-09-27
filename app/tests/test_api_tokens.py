"""M66-I199 PAT 机器接入（docs/01 §BK.2，GitHub PAT 语义的单实例裁剪）：
display-once（库存 SHA-256）、可选过期档位、per-token last_used 遥测、
立即吊销；Bearer 以创建者身份行动，token 管理端点本身不走 Bearer。
api_token.created/revoked 事件入流 rebuild 存活；last_used 在投影外的
side 表（遥测不进事件流——M46/I186 同轨）。"""
from __future__ import annotations

import pytest

from apm import config
from apm.core import db, events


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


def _mk_token(client, name="CI 令牌", **kw):
    r = client.post("/api/auth/tokens", json={"name": name, **kw})
    assert r.status_code == 200
    return r.json()


def test_create_shows_raw_once_and_list_hides_it(client, tmp_data):
    tok = _mk_token(client, expires_in_days=30)
    assert tok["token"].startswith("apm_") and len(tok["token"]) > 20
    assert tok["expires_at"]

    toks = client.get("/api/auth/tokens").json()["tokens"]
    assert len(toks) == 1
    row = toks[0]
    assert row["id"] == tok["id"]
    assert row["prefix"] == tok["token"][:10]
    assert "token" not in row and "hash" not in row  # raw never echoed again
    assert row["revoked_at"] is None and row["last_used_at"] is None

    r = client.post("/api/auth/tokens", json={"name": "坏档位", "expires_in_days": 13})
    assert r.status_code == 422
    r = client.post("/api/auth/tokens", json={"name": ""})
    assert r.status_code == 422


def test_bearer_acts_as_creator_in_network_mode(client, monkeypatch):
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    client.post("/api/users", json={"id": "ci-bot", "name": "CI", "password": "ci-pass"})
    monkeypatch.setattr(config.settings, "auth_mode", "network")
    try:
        assert client.post("/api/auth/login",
                           json={"user_id": "ci-bot", "password": "ci-pass"}).status_code == 200
        tok = _mk_token(client, name="外部 agent")
        client.post("/api/auth/logout")

        # no credentials → write 401; garbage Bearer → 401
        assert client.post("/api/projects", json={"name": "x"}).status_code == 401
        assert client.post("/api/projects", json={"name": "x"},
                           headers={"Authorization": "Bearer apm_deadbeef"}).status_code == 401
        # valid Bearer acts as its creator
        r = client.post("/api/projects", json={"name": "令牌项目", "ontology": "software-dev"},
                        headers={"Authorization": f"Bearer {tok['token']}"})
        assert r.status_code == 200
        # usage telemetry recorded on the token card (management needs a
        # session — Bearer is excluded from /api/auth/* by design)
        assert client.post("/api/auth/login",
                           json={"user_id": "ci-bot", "password": "ci-pass"}).status_code == 200
        row = client.get("/api/auth/tokens").json()["tokens"][0]
        assert row["last_used_at"]
    finally:
        config.settings.admin_password = ""


def test_revoke_and_expiry_kill_access_and_rebuild_survives(client, monkeypatch):
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    client.post("/api/users", json={"id": "ci-bot", "name": "CI", "password": "ci-pass"})
    monkeypatch.setattr(config.settings, "auth_mode", "network")
    try:
        assert client.post("/api/auth/login",
                           json={"user_id": "ci-bot", "password": "ci-pass"}).status_code == 200
        tok = _mk_token(client, name="会被吊销")
        h = {"Authorization": f"Bearer {tok['token']}"}

        # expired token (emitted directly with a past expiry) is dead on arrival
        events.emit(event_type="api_token.created", agg_type="api_token", agg_id="tok_old",
                    actor_type="human", actor_id="ci-bot",
                    payload={"user_id": "ci-bot", "name": "过期", "prefix": "apm_old",
                             "hash": "stale-hash", "expires_at": "2020-01-01T00:00:00+00:00",
                             "summary": "创建 API 令牌：过期"})

        # logout so the session cookie can't shadow the Bearer assertions
        # (session wins in the gate)
        client.post("/api/auth/logout")
        assert client.post("/api/projects", json={"name": "x"},
                           headers={"Authorization": "Bearer apm_stale"}).status_code == 401
        assert client.post("/api/projects", json={"name": "令牌项目", "ontology": "software-dev"},
                           headers=h).status_code == 200

        # revoke + foreign-404 need a session (management excludes Bearer by
        # design); logout again before trusting Bearer-only 401s
        assert client.post("/api/auth/login",
                           json={"user_id": "ci-bot", "password": "ci-pass"}).status_code == 200
        assert client.delete(f"/api/auth/tokens/{tok['id']}").status_code == 200
        # someone else's token id is 404, not a revocation
        assert client.delete("/api/auth/tokens/tok_nope").status_code == 404
        client.post("/api/auth/logout")
        assert client.post("/api/projects", json={"name": "x"}, headers=h).status_code == 401

        # rebuild needs an instance admin
        assert client.post("/api/auth/login",
                           json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
        assert client.post("/api/system/rebuild-projections").status_code == 200
        client.post("/api/auth/logout")
        # both api_token.created events replay (hash is in the payload) but the
        # revocation revokes — token stays dead across rebuild
        assert client.post("/api/projects", json={"name": "x"}, headers=h).status_code == 401
        assert client.post("/api/projects", json={"name": "x"},
                           headers={"Authorization": "Bearer apm_stale"}).status_code == 401
        rows = db.get_conn().execute("SELECT id, revoked_at FROM api_tokens").fetchall()
        by_id = {r["id"]: r["revoked_at"] for r in rows}
        assert by_id[tok["id"]] and by_id["tok_old"] is None
    finally:
        config.settings.admin_password = ""


def test_last_used_survives_rebuild(client, tmp_data):
    tok = _mk_token(client, name="遥测存活")
    conn = db.get_conn()
    conn.execute("INSERT INTO api_token_usage (token_id, last_used_at) VALUES (?,?)",
                 (tok["id"], "2026-09-28T00:00:00+00:00"))
    conn.commit()
    assert client.post("/api/system/rebuild-projections").status_code == 200
    row = client.get("/api/auth/tokens").json()["tokens"][0]
    assert row["last_used_at"] == "2026-09-28T00:00:00+00:00"
