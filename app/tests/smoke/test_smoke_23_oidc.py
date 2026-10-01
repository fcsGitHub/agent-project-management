"""Smoke 23 (M17-I55): OIDC SSO end-to-end — the feature stays fully dormant
when unconfigured (zero behaviour change), the whole protocol path works
against the local RSA JWT stub, and JIT provisioning is idempotent with the
M8 gate still applied to provisioned users."""
import base64
import json
import time

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from apm import config
from apm.core import oidc
from apm.core.security import SESSION_COOKIE

ISSUER = "https://idp.smoke.test"
CLIENT_ID = "agentpm-smoke"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@pytest.mark.smoke
def test_smoke_23_oidc_sso(client, tmp_data, isolated_ontologies, monkeypatch):
    # --- 1. unconfigured: everything dormant, login/me behave exactly as pre-M17
    assert oidc.enabled() is False
    assert client.get("/api/auth/oidc/login").status_code == 404
    assert client.get("/api/auth/oidc/status").json()["enabled"] is False
    me = client.get("/api/auth/me").json()  # local mode: configured identity
    assert me["source"] == "local"

    # --- 2. configured: full protocol path via the local RSA stub
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nums = key.public_key().public_numbers()
    jwk = {"kid": "smoke", "kty": "RSA", "alg": "RS256", "use": "sig",
           "n": _b64url(nums.n.to_bytes((nums.n.bit_length() + 7) // 8, "big")),
           "e": _b64url(nums.e.to_bytes(3, "big"))}

    def fake_get(url, **kw):
        class R:
            status_code = 200

            def json(self):
                if url.endswith("openid-configuration"):
                    return {"issuer": ISSUER,
                            "authorization_endpoint": f"{ISSUER}/authorize",
                            "token_endpoint": f"{ISSUER}/token",
                            "jwks_uri": f"{ISSUER}/jwks"}
                return {"keys": [jwk]}

        return R()

    holder: dict = {"id_token": "", "verifier": ""}

    def fake_post(url, **kw):
        class R:
            status_code = 200

            def json(self):
                assert kw["data"]["code_verifier"] == holder["verifier"]
                return {"id_token": holder["id_token"]}

        return R()

    monkeypatch.setattr(oidc.httpx2, "get", fake_get)
    monkeypatch.setattr(oidc.httpx2, "post", fake_post)
    monkeypatch.setattr(config.settings, "oidc_issuer", ISSUER)
    monkeypatch.setattr(config.settings, "oidc_client_id", CLIENT_ID)
    monkeypatch.setattr(config.settings, "oidc_client_secret", "s")
    monkeypatch.setattr(config.settings, "oidc_redirect_uri", "http://x/cb")
    monkeypatch.setattr(config.settings, "oidc_allowed_groups", "")
    oidc._discovery_cache.clear()
    assert oidc.enabled() is True

    r = client.get("/api/auth/oidc/login", follow_redirects=False)
    assert r.status_code == 302 and "code_challenge" in r.headers["location"]
    state, nonce, verifier = r.cookies.get("apm_oidc_handshake").split("|")
    holder["verifier"] = verifier

    def mint(nonce=nonce):
        head = _b64url(json.dumps({"alg": "RS256", "typ": "JWT", "kid": "smoke"}).encode())
        payload = _b64url(json.dumps({
            "iss": ISSUER, "aud": CLIENT_ID, "exp": int(time.time()) + 300,
            "nonce": nonce, "email": "smoke@corp.test", "email_verified": True,
            "groups": ["smoke"], }).encode())
        sig = key.sign(f"{head}.{payload}".encode(), padding.PKCS1v15(), hashes.SHA256())
        holder["id_token"] = f"{head}.{payload}.{_b64url(sig)}"

    mint()
    r = client.get(f"/api/auth/oidc/callback?code=c&state={state}", follow_redirects=False)
    assert r.status_code == 302, r.text
    me = client.get("/api/auth/me").json()
    assert me["name"] == "smoke" and me["source"] == "session"

    # --- 3. JIT idempotence: second login, same single account
    r = client.get("/api/auth/oidc/login", follow_redirects=False)
    state, nonce, verifier = r.cookies.get("apm_oidc_handshake").split("|")
    holder["verifier"] = verifier
    mint(nonce)
    assert client.get(f"/api/auth/oidc/callback?code=c&state={state}", follow_redirects=False).status_code == 302
    users = client.get("/api/users").json()["users"]
    assert sum(1 for u in users if u.get("email") == "smoke@corp.test") == 1

    # --- 4. M8 gate still applies: provisioned user is no member anywhere
    assert client.post("/api/users", json={"id": "u_owner", "name": "拥有者"}).status_code == 200
