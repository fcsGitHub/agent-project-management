"""Auth endpoints (M8-I26): login/logout/me with signed HttpOnly cookies.
Login attempts (success and failure) land in the audit stream as session.*
events; credentials themselves never do."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from apm import config
from apm.core import db, events
from apm.core.ids import new_id
from apm.core.security import SESSION_COOKIE, issue_session, session_user, verify_password

router = APIRouter(tags=["auth"])


class LoginIn(BaseModel):
    user_id: str
    password: str


@router.post("/auth/login")
def login(body: LoginIn, response: Response) -> dict:
    row = db.get_conn().execute(
        "SELECT id, name, password_hash FROM users WHERE id = ?", (body.user_id,)
    ).fetchone()
    if not row or not verify_password(body.password, row["password_hash"]):
        events.emit(
            event_type="session.login_failed",
            agg_type="session",
            agg_id=new_id("sess"),
            actor_type="human",
            actor_id=body.user_id,
            payload={"user_id": body.user_id, "summary": f"登录失败：{body.user_id}"},
        )
        raise HTTPException(status_code=401, detail="invalid credentials")
    response.set_cookie(
        SESSION_COOKIE,
        issue_session(row["id"]),
        httponly=True,
        samesite="lax",
        max_age=config.settings.session_ttl_hours * 3600,
    )
    events.emit(
        event_type="session.logged_in",
        agg_type="session",
        agg_id=new_id("sess"),
        actor_type="human",
        actor_id=row["id"],
        payload={"user_id": row["id"], "summary": f"登录：{row['name']}（{row['id']}）"},
    )
    return {"user_id": row["id"], "name": row["name"]}


@router.post("/auth/logout")
def logout(request: Request, response: Response) -> dict:
    user_id = session_user(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE)
    if user_id:
        events.emit(
            event_type="session.logged_out",
            agg_type="session",
            agg_id=new_id("sess"),
            actor_type="human",
            actor_id=user_id,
            payload={"user_id": user_id, "summary": f"登出：{user_id}"},
        )
    return {"ok": True}


@router.get("/auth/me")
def me(request: Request) -> dict:
    """Effective identity: a valid session cookie wins; local mode falls back to
    the configured single-user identity."""
    user_id = session_user(request.cookies.get(SESSION_COOKIE))
    source = "session"
    if not user_id:
        if config.settings.auth_mode != "local":
            raise HTTPException(status_code=401, detail="login required")
        user_id = config.settings.user_id
        source = "local"
    row = db.get_conn().execute(
        "SELECT id, name, is_admin FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="unknown user")
    return {
        "user_id": row["id"],
        "name": row["name"],
        "is_admin": bool(row["is_admin"]),
        "source": source,
    }
