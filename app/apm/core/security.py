"""Auth primitives (M8-I26): stdlib-only password hashing and signed session
tokens. Password hashes live only in the users projection table (never in the
event log); sessions are HMAC-signed `user_id.expiry.signature` tokens carried
in an HttpOnly cookie."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from apm import config

_PBKDF2_ITERATIONS = 200_000
SESSION_COOKIE = "apm_session"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), _PBKDF2_ITERATIONS
    ).hex()
    return f"pbkdf2${salt}${digest}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    parts = stored.split("$")
    if len(parts) != 3 or parts[0] != "pbkdf2":
        return False
    calc = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), parts[1].encode(), _PBKDF2_ITERATIONS
    ).hex()
    return hmac.compare_digest(calc, parts[2])


def get_secret() -> str:
    """Instance secret: settings override, else generated once and persisted
    under data_dir so existing sessions survive restarts."""
    secret = config.settings.secret_key
    if secret:
        return secret
    path = config.settings.data_dir / "secret.key"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    secret = secrets.token_hex(32)
    path.write_text(secret, encoding="utf-8")
    return secret


def issue_session(user_id: str) -> str:
    ttl = config.settings.session_ttl_hours * 3600
    msg = f"{user_id}.{int(time.time()) + ttl}"
    sig = hmac.new(get_secret().encode(), msg.encode(), hashlib.sha256).hexdigest()
    return f"{msg}.{sig}"


def session_user(token: str | None) -> str | None:
    """The user_id for a valid, unexpired token — else None."""
    if not token:
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    user_id, exp, sig = parts
    expected = hmac.new(
        get_secret().encode(), f"{user_id}.{exp}".encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        exp_ts = int(exp)
    except ValueError:
        return None
    if exp_ts < time.time():
        return None
    return user_id
