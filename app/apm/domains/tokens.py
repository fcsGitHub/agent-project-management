"""Personal access tokens (M66-I199, docs/01 §BK.2): machine access with
GitHub PAT semantics — display-once raw token, SHA-256 at rest, optional
expiry, per-token last_used_at, immediate revocation. Tokens are user-scoped:
a Bearer token acts as its creator (no fine-grained scopes — single-instance
product). api_token.created/revoked are events (rebuild-survivable);
last_used_at is telemetry in a side table (perf/recents 同理, survives rebuild)."""
from __future__ import annotations

import hashlib
import secrets

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from apm import config
from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on
from apm.core.security import SESSION_COOKIE, session_user

router = APIRouter(tags=["tokens"])

TOKEN_PREFIX = "apm_"
_EXPIRY_CHOICES = (7, 30, 60, 90)  # GitHub's standard menu; None = never


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


@on("api_token.created")
def _proj_token_created(conn, e):
    p = e.payload
    conn.execute(
        "INSERT INTO api_tokens (id, user_id, name, prefix, hash, expires_at, revoked_at, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (
            e.agg_id,
            p.get("user_id"),
            p.get("name"),
            p.get("prefix"),
            p.get("hash"),
            p.get("expires_at"),
            None,
            e.ts,
        ),
    )


@on("api_token.revoked")
def _proj_token_revoked(conn, e):
    conn.execute("UPDATE api_tokens SET revoked_at = ? WHERE id = ?", (e.ts, e.agg_id))


def current_user(request: Request) -> str:
    """Session cookie first, then local-mode fallback (same rule as /auth/me).
    Bearer tokens are resolved by the auth gate before routes run."""
    user_id = session_user(request.cookies.get(SESSION_COOKIE))
    if user_id:
        return user_id
    if config.settings.auth_mode != "local":
        raise HTTPException(status_code=401, detail="login required")
    return config.settings.user_id


def api_token_user(raw: str) -> str | None:
    """The user_id behind a valid Bearer token — else None. Records usage."""
    if not raw:
        return None
    conn = db.get_conn()
    row = conn.execute(
        "SELECT id, user_id, expires_at, revoked_at FROM api_tokens WHERE hash = ?",
        (_hash_token(raw),),
    ).fetchone()
    if not row or row["revoked_at"]:
        return None
    if row["expires_at"] and row["expires_at"] <= events.utcnow():
        return None
    conn.execute(
        "INSERT INTO api_token_usage (token_id, last_used_at) VALUES (?,?)"
        " ON CONFLICT(token_id) DO UPDATE SET last_used_at = excluded.last_used_at",
        (row["id"], events.utcnow()),
    )
    conn.commit()
    return row["user_id"]


class TokenIn(BaseModel):
    name: str
    expires_in_days: int | None = None


@router.post("/auth/tokens")
def create_token(body: TokenIn, request: Request) -> dict:
    user_id = current_user(request)
    name = (body.name or "").strip()
    if not name or len(name) > 100:
        raise HTTPException(status_code=422, detail="name must be 1-100 chars")
    if body.expires_in_days is not None and body.expires_in_days not in _EXPIRY_CHOICES:
        raise HTTPException(status_code=422, detail=f"expires_in_days must be one of {_EXPIRY_CHOICES}")
    raw = TOKEN_PREFIX + secrets.token_hex(16)
    expires_at = None
    if body.expires_in_days:
        from datetime import datetime, timedelta, timezone

        expires_at = (datetime.now(timezone.utc) + timedelta(days=body.expires_in_days)).isoformat(
            timespec="seconds"
        )
    tid = new_id("tok")
    events.emit(
        event_type="api_token.created",
        agg_type="api_token",
        agg_id=tid,
        actor_type="human",
        actor_id=user_id,
        payload={
            "user_id": user_id,
            "name": name,
            "prefix": raw[:10],
            "hash": _hash_token(raw),
            "expires_at": expires_at,
            "summary": f"创建 API 令牌：{name}",
        },
    )
    return {"id": tid, "token": raw, "prefix": raw[:10], "expires_at": expires_at}


@router.get("/auth/tokens")
def list_tokens(request: Request) -> dict:
    user_id = current_user(request)
    rows = db.get_conn().execute(
        "SELECT t.id, t.name, t.prefix, t.expires_at, t.revoked_at, t.created_at,"
        " u.last_used_at FROM api_tokens t"
        " LEFT JOIN api_token_usage u ON u.token_id = t.id"
        " WHERE t.user_id = ? ORDER BY t.created_at DESC",
        (user_id,),
    ).fetchall()
    return {"tokens": [dict(r) for r in rows]}


@router.delete("/auth/tokens/{token_id}")
def revoke_token(token_id: str, request: Request) -> dict:
    user_id = current_user(request)
    row = db.get_conn().execute(
        "SELECT id, user_id, revoked_at FROM api_tokens WHERE id = ?", (token_id,)
    ).fetchone()
    if not row or row["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="token not found")
    if row["revoked_at"]:
        return {"ok": True, "already_revoked": True}
    events.emit(
        event_type="api_token.revoked",
        agg_type="api_token",
        agg_id=token_id,
        actor_type="human",
        actor_id=user_id,
        payload={"user_id": user_id, "summary": f"吊销 API 令牌：{token_id}"},
    )
    return {"ok": True}
