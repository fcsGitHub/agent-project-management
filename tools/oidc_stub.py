"""Minimal local OIDC IdP stub for browser demos (M17-I54).

Serves discovery/jwks/authorize/token on :9001 and signs id_tokens with a
hard-coded test RSA key (keep demo-only — never use in production).
authorize() immediately redirects back to the client's redirect_uri with a
fresh code, so one browser round-trip completes the SSO handshake.

Usage:
  python tools/oidc_stub.py                 # issuer http://localhost:9001
Start AgentPM with:
  APM_OIDC_ISSUER=http://localhost:9001 \
  APM_OIDC_CLIENT_ID=agentpm-demo \
  APM_OIDC_CLIENT_SECRET=demo-secret \
  APM_OIDC_REDIRECT_URI=http://localhost:8000/api/auth/oidc/callback
"""
import base64
import hashlib
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ISSUER = "http://localhost:9001"
CLIENT_ID = "agentpm-demo"
CLIENT_SECRET = "demo-secret"

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
NUMS = KEY.public_key().public_numbers()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


JWK = {
    "kid": "stub-key", "kty": "RSA", "alg": "RS256", "use": "sig",
    "n": _b64url(NUMS.n.to_bytes((NUMS.n.bit_length() + 7) // 8, "big")),
    "e": _b64url(NUMS.e.to_bytes(3, "big")),
}

# code -> {nonce, verifier}; authorize stores, token consumes
CODES: dict[str, dict] = {}


def mint_id_token(nonce: str) -> str:
    now = int(time.time())
    head = _b64url(json.dumps({"alg": "RS256", "typ": "JWT", "kid": "stub-key"}).encode())
    payload = _b64url(json.dumps({
        "iss": ISSUER, "aud": CLIENT_ID, "sub": "stub-user-1",
        "exp": now + 600, "iat": now, "nonce": nonce,
        "email": "zhang.demo@corp.test", "email_verified": True,
        "preferred_username": "zhang.demo", "groups": ["corp-dev"],
    }).encode())
    signing = f"{head}.{payload}".encode()
    sig = KEY.sign(signing, padding.PKCS1v15(), hashes.SHA256())
    return f"{head}.{payload}.{_b64url(sig)}"


class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/.well-known/openid-configuration":
            self._json({
                "issuer": ISSUER,
                "authorization_endpoint": f"{ISSUER}/authorize",
                "token_endpoint": f"{ISSUER}/token",
                "jwks_uri": f"{ISSUER}/jwks",
            })
        elif u.path == "/jwks":
            self._json({"keys": [JWK]})
        elif u.path == "/authorize":
            code = secrets.token_urlsafe(24)
            CODES[code] = {"nonce": (q.get("nonce") or [""])[0],
                           "verifier": ""}  # verifier arrives at /token
            loc = f"{(q.get('redirect_uri') or [''])[0]}?code={code}&state={(q.get('state') or [''])[0]}"
            self.send_response(302)
            self.send_header("Location", loc)
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self._json({"error": "not_found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/token":
            self._json({"error": "not_found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            form = parse_qs(self.rfile.read(length).decode())
            auth = (self.headers.get("Authorization") or "")
            assert auth == f"Basic { _b64url(f'{CLIENT_ID}:{CLIENT_SECRET}'.encode()) }", f"bad auth {auth!r}"
            code = (form.get("code") or [""])[0]
            rec = CODES.pop(code, None)
            assert rec, "unknown or consumed code"
            rec["verifier"] = (form.get("code_verifier") or [""])[0]
            assert rec["verifier"], "PKCE verifier required"
            self._json({
                "access_token": "stub-access",
                "id_token": mint_id_token(rec["nonce"]),
                "token_type": "Bearer",
            })
        except AssertionError as e:
            self._json({"error": str(e)}, 400)

    def log_message(self, fmt, *args):  # quieter demos
        print("[oidc-stub]", self.path)


if __name__ == "__main__":
    print(f"OIDC stub IdP on {ISSUER} (client_id={CLIENT_ID})")
    # Threading: one stalled connection must not freeze every other endpoint.
    ThreadingHTTPServer(("127.0.0.1", 9001), Handler).serve_forever()
