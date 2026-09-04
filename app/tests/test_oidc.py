"""M17-I53: OIDC SSO client — full protocol path against a local RSA JWT stub
(no IdP container needed), plus the JIT four-constraint rejection matrix.

The stub monkeypatches httpx.get/post so discovery/jwks/token endpoints are
served from in-memory dicts; id_tokens are signed with a test RSA key whose
public part is published as the stub jwks."""
import base64
import hashlib
import json
import time

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from apm import config
from apm.core import oidc
from apm.core.security import SESSION_COOKIE, session_user

ISSUER = "https://idp.example.test"
CLIENT_ID = "agentpm-test"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@pytest.fixture()
def idp(monkeypatch):
    """Local IdP stub: RSA key + discovery/jwks/token endpoints in memory."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nums = key.public_key().public_numbers()
    jwk = {
        "kid": "stub-key",
        "kty": "RSA",
        "alg": "RS256",
        "use": "sig",
        "n": _b64url(nums.n.to_bytes((nums.n.bit_length() + 7) // 8, "big")),
        "e": _b64url(nums.e.to_bytes(3, "big")),
    }
    discovery_doc = {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/authorize",
        "token_endpoint": f"{ISSUER}/token",
        "jwks_uri": f"{ISSUER}/jwks",
    }

    def fake_get(url, **kw):
        class R:
            status_code = 200

            def json(self):
                if url.endswith("openid-configuration"):
                    return discovery_doc
                if url.endswith("/jwks"):
                    return {"keys": [jwk]}
                raise AssertionError(url)

        return R()

    def fake_post(url, **kw):
        class R:
            status_code = 200

            def json(self):
                assert url == f"{ISSUER}/token"
                assert kw["data"]["code"] == "good-code"
                assert kw["data"]["code_verifier"] == fake_post.verifier
                return {"id_token": fake_post.id_token}

        return R()

    fake_post.id_token = ""
    fake_post.verifier = ""
    monkeypatch.setattr(oidc.httpx, "get", fake_get)
    monkeypatch.setattr(oidc.httpx, "post", fake_post)
    return {"key": key, "id_token": fake_post}


def _mint(key, claims, *, nonce="n-1", kid="stub-key", alg="RS256", iss=ISSUER, aud=CLIENT_ID,
          exp=None, bad_key=None):
    head = {"alg": alg, "typ": "JWT"}
    if kid:
        head["kid"] = kid
    payload = {"iss": iss, "aud": aud, "exp": exp or int(time.time()) + 300,
               "nonce": nonce, "email": "zhang@corp.test", "email_verified": True,
               "groups": ["corp-dev"], **claims}
    signing = f"{_b64url(json.dumps(head).encode())}.{_b64url(json.dumps(payload).encode())}"
    signer = bad_key or key
    sig = signer.sign(signing.encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing}.{_b64url(sig)}"


def _setup(monkeypatch, allow=""):
    monkeypatch.setattr(config.settings, "oidc_issuer", ISSUER)
    monkeypatch.setattr(config.settings, "oidc_client_id", CLIENT_ID)
    monkeypatch.setattr(config.settings, "oidc_client_secret", "secret-x")
    monkeypatch.setattr(config.settings, "oidc_redirect_uri", "http://localhost:8000/api/auth/oidc/callback")
    monkeypatch.setattr(config.settings, "oidc_allowed_groups", allow)
    oidc._discovery_cache.clear()


def test_feature_off_without_config(client, tmp_data, isolated_ontologies):
    assert oidc.enabled() is False
    assert client.get("/api/auth/oidc/login").status_code == 404
    assert client.get("/api/auth/oidc/callback").status_code == 404


def test_login_discovery_and_callback_provision(client, tmp_data, isolated_ontologies, idp, monkeypatch):
    _setup(monkeypatch)
    r = client.get("/api/auth/oidc/login", follow_redirects=False)
    assert r.status_code == 302
    assert ISSUER in r.headers["location"] and "code_challenge" in r.headers["location"]
    cookie = r.cookies.get("apm_oidc_handshake") or ""
    assert cookie.count("|") == 2
    state, nonce, verifier = cookie.split("|")

    idp["id_token"].id_token = _mint(idp["key"], {}, nonce=nonce)
    idp["id_token"].verifier = verifier
    r = client.get(f"/api/auth/oidc/callback?code=good-code&state={state}", follow_redirects=False)
    assert r.status_code == 302, r.text
    assert SESSION_COOKIE in r.headers.get("set-cookie", "")
    who = client.get("/api/auth/me").json()
    assert who["name"] == "zhang" and who["source"] == "session"  # OIDC -> session identity


def test_jit_relogin_is_idempotent(client, tmp_data, isolated_ontologies, idp, monkeypatch):
    _setup(monkeypatch)
    for _ in range(2):  # two logins → still one account, name untouched
        r = client.get("/api/auth/oidc/login", follow_redirects=False)
        state, nonce, verifier = r.cookies.get("apm_oidc_handshake").split("|")
        idp["id_token"].id_token = _mint(idp["key"], {}, nonce=nonce)
        idp["id_token"].verifier = verifier
        _r = client.get(f"/api/auth/oidc/callback?code=good-code&state={state}", follow_redirects=False)
        assert _r.status_code == 302, (_r.status_code, _r.text[:120])
    users = client.get("/api/users").json()["users"]
    assert sum(1 for u in users if u.get("email") == "zhang@corp.test") == 1


def test_rejection_matrix(client, tmp_data, isolated_ontologies, idp, monkeypatch):
    _setup(monkeypatch, allow="corp-dev")

    def handshake():
        r = client.get("/api/auth/oidc/login", follow_redirects=False)
        state, nonce, verifier = r.cookies.get("apm_oidc_handshake").split("|")
        idp["id_token"].verifier = verifier
        return state, nonce

    # tampered signature (signed by a different key)
    state, nonce = handshake()
    rogue = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    idp["id_token"].id_token = _mint(idp["key"], {}, nonce=nonce, bad_key=rogue)
    assert client.get(f"/api/auth/oidc/callback?code=good-code&state={state}").status_code == 401

    # forged issuer
    state, nonce = handshake()
    idp["id_token"].id_token = _mint(idp["key"], {}, nonce=nonce, iss="https://evil.test")
    assert client.get(f"/api/auth/oidc/callback?code=good-code&state={state}").status_code == 401

    # expired token
    state, nonce = handshake()
    idp["id_token"].id_token = _mint(idp["key"], {}, nonce=nonce, exp=int(time.time()) - 999)
    assert client.get(f"/api/auth/oidc/callback?code=good-code&state={state}").status_code == 401

    # stale handshake cookie → nonce mismatch (replay)
    state, nonce = handshake()
    idp["id_token"].id_token = _mint(idp["key"], {}, nonce="stale-nonce")
    assert client.get(f"/api/auth/oidc/callback?code=good-code&state={state}").status_code == 401

    # state mismatch
    state, nonce = handshake()
    idp["id_token"].id_token = _mint(idp["key"], {}, nonce=nonce)
    assert client.get(f"/api/auth/oidc/callback?code=good-code&state=other-state").status_code == 401

    # unverified email
    state, nonce = handshake()
    idp["id_token"].id_token = _mint(idp["key"], {"email_verified": False}, nonce=nonce)
    assert client.get(f"/api/auth/oidc/callback?code=good-code&state={state}").status_code == 422

    # group outside the allowlist
    state, nonce = handshake()
    idp["id_token"].id_token = _mint(idp["key"], {"groups": ["other-org"]}, nonce=nonce)
    assert client.get(f"/api/auth/oidc/callback?code=good-code&state={state}").status_code == 403

    # no accounts were provisioned by any rejected path
    users = client.get("/api/users").json()["users"]
    assert not [u for u in users if u.get("email") == "zhang@corp.test"]


def test_local_account_conflict_is_409_not_merged(client, tmp_data, isolated_ontologies, idp, monkeypatch):
    _setup(monkeypatch)
    client.post("/api/users", json={"id": "u_local", "name": "zhang"})  # local account, same name
    r = client.get("/api/auth/oidc/login", follow_redirects=False)
    state, nonce, verifier = r.cookies.get("apm_oidc_handshake").split("|")
    idp["id_token"].id_token = _mint(idp["key"], {}, nonce=nonce)
    idp["id_token"].verifier = verifier
    r = client.get(f"/api/auth/oidc/callback?code=good-code&state={state}", follow_redirects=False)
    assert r.status_code == 409
    users = client.get("/api/users").json()["users"]
    assert [u for u in users if u["name"] == "zhang"][0]["id"] == "u_local"
