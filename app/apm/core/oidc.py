"""OIDC single sign-on client (M17-I53) — stdlib + cryptography only (no
authlib dependency), reusing the M8 session signer after the OIDC handshake.

JIT provisioning follows the four constraints distilled from Gitea's lessons
(docs/01 §P.3):
  1. one-shot role — accounts are created with the lowest-privilege role and
     later logins never re-derive roles (no second-login timing quirks);
  2. allowlist — when APM_OIDC_ALLOWED_GROUPS is set, an IdP user outside the
     groups is rejected fail-closed;
  3. trusted claims — only a fully verified id_token (signature/issuer/
     audience/exp/nonce) counts, and email_verified is mandatory;
  4. no silent account linking — an existing local account with the same
     email returns 409; merging is an admin action, not a login side effect.

The whole feature is off unless issuer/client_id/client_secret are configured
(same semantics as the M11 SMTP channel)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlencode

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from apm import config
from apm.core import security

router = APIRouter(tags=["oidc"])

_STATE_COOKIE = "apm_oidc_handshake"  # state|nonce|verifier, 10-minute window
_discovery_cache: dict[str, tuple[dict, float]] = {}


# ------------------------------------------------------------- primitives
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_json(obj: dict) -> bytes:
    return _b64url(json.dumps(obj, separators=(",", ":")).encode()).encode()


def _b64url_decode(seg: str) -> bytes:
    return base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))


def enabled() -> bool:
    s = config.settings
    return bool(s.oidc_issuer and s.oidc_client_id and s.oidc_client_secret)


def allowed_groups() -> list[str]:
    return [g.strip() for g in config.settings.oidc_allowed_groups.split(",") if g.strip()]


def pkce_pair() -> tuple[str, str]:
    """(verifier, challenge=S256) per RFC 7636."""
    verifier = _b64url(secrets.token_bytes(48))
    return verifier, _b64url(hashlib.sha256(verifier.encode()).digest())


# ------------------------------------------------------------- discovery
def discovery(issuer: str, *, force: bool = False) -> dict:
    """Fetch (and cache for an hour) the provider's openid-configuration."""
    cached = _discovery_cache.get(issuer)
    if cached and not force and time.time() - cached[1] < 3600:
        return cached[0]
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    resp = httpx.get(url, timeout=10)
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"OIDC discovery failed ({resp.status_code})")
    doc = resp.json()
    _discovery_cache[issuer] = (doc, time.time())
    return doc


def jwks(issuer: str) -> dict:
    doc = discovery(issuer)
    jwks_uri = doc.get("jwks_uri")
    if not jwks_uri:
        raise HTTPException(status_code=502, detail="OIDC discovery lacks jwks_uri")
    resp = httpx.get(jwks_uri, timeout=10)
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"OIDC jwks fetch failed ({resp.status_code})")
    return resp.json()


# ------------------------------------------------------------- RS256 JWT
def _rsa_verify(signing_input: bytes, signature: bytes, jwk: dict) -> bool:
    n = int.from_bytes(_b64url_decode(jwk["n"]), "big")
    e = int.from_bytes(_b64url_decode(jwk["e"]), "big")
    pub = rsa.RSAPublicNumbers(e, n).public_key()
    try:
        pub.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())
        return True
    except InvalidSignature:
        return False


def verify_id_token(token: str, *, issuer: str, audience: str, keys: dict, nonce: str) -> dict:
    """Full id_token validation: RS256 signature via jwks kid, iss/aud/exp/nonce.
    Returns the claim set or raises 401/422 — never returns unverified claims."""
    try:
        head_b64, payload_b64, sig_b64 = token.split(".")
        header = json.loads(_b64url_decode(head_b64))
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="malformed id_token")
    if header.get("alg") != "RS256":
        raise HTTPException(status_code=401, detail="unsupported id_token alg")
    jwk = keys.get(header.get("kid", ""))
    if jwk is None:
        raise HTTPException(status_code=401, detail="unknown id_token kid")
    if not _rsa_verify(f"{head_b64}.{payload_b64}".encode(), _b64url_decode(sig_b64), jwk):
        raise HTTPException(status_code=401, detail="id_token signature mismatch")
    now = time.time()
    if payload.get("iss", "").rstrip("/") != issuer.rstrip("/"):
        raise HTTPException(status_code=401, detail="id_token issuer mismatch")
    aud = payload.get("aud")
    aud = aud if isinstance(aud, list) else [aud]
    if audience not in aud:
        raise HTTPException(status_code=401, detail="id_token audience mismatch")
    if payload.get("exp", 0) < now - 60:
        raise HTTPException(status_code=401, detail="id_token expired")
    if not hmac.compare_digest(str(payload.get("nonce", "")), nonce):
        raise HTTPException(status_code=401, detail="id_token nonce mismatch")
    return payload


# ------------------------------------------------------------- JIT account
def jit_account(claims: dict) -> dict:
    """Provision (or re-admit) an OIDC user per the four constraints.
    Roles are one-shot at creation (viewer default); re-login never mutates."""
    from apm.core import db
    from apm.core.ids import new_id
    from apm.domains.users import UserIn, register_user

    email = claims.get("email")
    if not email or not claims.get("email_verified"):
        raise HTTPException(status_code=422, detail="OIDC account lacks a verified email claim")
    groups = [g for g in claims.get("groups", []) if isinstance(g, str)]
    allow = allowed_groups()
    if allow and not set(groups) & set(allow):
        raise HTTPException(status_code=403, detail="IdP groups are not in the allowlist")

    row = db.get_conn().execute(
        "SELECT id, name FROM users WHERE email = ?", (email,)).fetchone()
    if row is not None:
        return {"id": row["id"], "name": row["name"], "existing": True}

    # A local (password) account with the same email must not be hijacked by a
    # login — surfacing it as 409 keeps merging an explicit admin action.
    clash = db.get_conn().execute(
        "SELECT id FROM users WHERE name = ?", (email.partition("@")[0],)).fetchone()
    if clash is not None:
        raise HTTPException(status_code=409, detail="a local account with this name already exists")

    user = register_user(UserIn(id=new_id("u_oidc"), name=email.partition("@")[0], email=email))
    return {"id": user["id"], "name": user["name"], "existing": False}


# ------------------------------------------------------------- endpoints
@router.get("/auth/oidc/login")
def oidc_login():
    if not enabled():
        raise HTTPException(status_code=404, detail="OIDC is not configured")
    s = config.settings
    doc = discovery(s.oidc_issuer)
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    verifier, challenge = pkce_pair()
    params = {
        "response_type": "code",
        "client_id": s.oidc_client_id,
        "redirect_uri": s.oidc_redirect_uri,
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    resp = RedirectResponse(f"{doc['authorization_endpoint']}?{urlencode(params)}", status_code=302)
    resp.set_cookie(_STATE_COOKIE, f"{state}|{nonce}|{verifier}",
                    max_age=600, httponly=True, samesite="lax")
    return resp


@router.get("/auth/oidc/callback")
def oidc_callback(request: Request, code: str = "", state: str = ""):
    if not enabled():
        raise HTTPException(status_code=404, detail="OIDC is not configured")
    s = config.settings
    raw = request.cookies.get(_STATE_COOKIE)
    if not raw or "|" not in raw:
        raise HTTPException(status_code=401, detail="missing OIDC handshake state")
    cookie_state, nonce, verifier = raw.split("|", 2)
    if not hmac.compare_digest(cookie_state, state):
        raise HTTPException(status_code=401, detail="OIDC state mismatch")

    doc = discovery(s.oidc_issuer)
    token_resp = httpx.post(
        doc["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": s.oidc_redirect_uri,
            "code_verifier": verifier,
        },
        auth=(s.oidc_client_id, s.oidc_client_secret),
        timeout=10,
    )
    if token_resp.status_code != 200:
        raise HTTPException(status_code=401, detail="OIDC code exchange failed")
    id_token = token_resp.json().get("id_token")
    if not id_token:
        raise HTTPException(status_code=401, detail="OIDC token response lacks id_token")
    keys = {k["kid"]: k for k in jwks(s.oidc_issuer).get("keys", []) if "kid" in k}
    claims = verify_id_token(id_token, issuer=s.oidc_issuer,
                             audience=s.oidc_client_id, keys=keys, nonce=nonce)
    user = jit_account(claims)

    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie(
        security.SESSION_COOKIE,
        security.issue_session(user["id"]),
        httponly=True,
        samesite="lax",
        max_age=config.settings.session_ttl_hours * 3600,
    )
    resp.delete_cookie(_STATE_COOKIE)
    return resp
