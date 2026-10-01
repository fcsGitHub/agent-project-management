"""Auth endpoints (M8-I26): login/logout/me with signed HttpOnly cookies.
Login attempts (success and failure) land in the audit stream as session.*
events; credentials themselves never do."""
from __future__ import annotations

import threading
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from apm import config
from apm.core import db, events
from apm.core.ids import new_id
from apm.core.security import (
    SESSION_COOKIE,
    hash_password,
    issue_session,
    session_user,
    verify_password,
)

router = APIRouter(tags=["auth"])

# ---- 登录防爆破（M82-I247，OWASP API2:2023 认证端点反暴力破解义务）----
# 失败滑窗：per-user 内存时间戳队列，窗口内失败达阈值即临时锁定（429+Retry-After），
# 窗口滑出自动解除、成功登录清零。锁定状态属运行态安全状态（webhook secret 同构）：
# 不入事件流、rebuild 不复现是特性而非缺陷。不设 env 旋钮——少写少腐（M77 教训）。
LOCKOUT_MAX_FAILURES = 5
LOCKOUT_WINDOW_SECONDS = 600.0
_login_failures: dict[str, list[float]] = {}
_login_lock = threading.Lock()
# 模块级哑哈希：未知用户也跑一次同价 pbkdf2 校验，计时不可用于枚举用户名。
_DUMMY_HASH = hash_password("apm-dummy-password-for-timing-equalization")


def _locked_retry_after(user_id: str) -> int | None:
    """锁定中返回剩余秒数（窗口滑出即自动解除）；未锁定返回 None。"""
    now = time.monotonic()
    with _login_lock:
        fails = [t for t in _login_failures.get(user_id, []) if now - t < LOCKOUT_WINDOW_SECONDS]
        _login_failures[user_id] = fails
        if len(fails) >= LOCKOUT_MAX_FAILURES:
            return max(1, round(LOCKOUT_WINDOW_SECONDS - (now - fails[0])))
        return None


def _record_failure(user_id: str) -> bool:
    """记一次失败；恰好达到阈值（锁定生效的转折点）时返回 True——调用方此时发一次
    session.login_locked 审计事件（转折点语义：后续 429 不再逐次发事件防攻击者灌水）。"""
    now = time.monotonic()
    with _login_lock:
        fails = [t for t in _login_failures.get(user_id, []) if now - t < LOCKOUT_WINDOW_SECONDS]
        fails.append(now)
        _login_failures[user_id] = fails
        return len(fails) == LOCKOUT_MAX_FAILURES


def _clear_failures(user_id: str) -> None:
    with _login_lock:
        _login_failures.pop(user_id, None)


class LoginIn(BaseModel):
    user_id: str
    password: str


def _login_failed(body: LoginIn, *, locked_event: bool = False) -> None:
    if locked_event:
        events.emit(
            event_type="session.login_locked",
            agg_type="session",
            agg_id=new_id("sess"),
            actor_type="human",
            actor_id=body.user_id,
            payload={"user_id": body.user_id, "summary": f"登录临时锁定：{body.user_id}（失败过多）"},
        )
    events.emit(
        event_type="session.login_failed",
        agg_type="session",
        agg_id=new_id("sess"),
        actor_type="human",
        actor_id=body.user_id,
        payload={"user_id": body.user_id, "summary": f"登录失败：{body.user_id}"},
    )


@router.post("/auth/login")
def login(body: LoginIn, response: Response) -> dict:
    retry_after = _locked_retry_after(body.user_id)
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="账户已临时锁定（登录失败过多），请稍后重试",
            headers={"Retry-After": str(retry_after)},
        )
    row = db.get_conn().execute(
        "SELECT id, name, password_hash FROM users WHERE id = ?", (body.user_id,)
    ).fetchone()
    if row is None:
        # 未知用户：跑同价哈希校验再拒（计时均衡防用户枚举）。
        verify_password(body.password, _DUMMY_HASH)
        if _record_failure(body.user_id):
            _login_failed(body, locked_event=True)
        else:
            _login_failed(body)
        raise HTTPException(status_code=401, detail="invalid credentials")
    if not verify_password(body.password, row["password_hash"]):
        if _record_failure(body.user_id):
            _login_failed(body, locked_event=True)
        else:
            _login_failed(body)
        raise HTTPException(status_code=401, detail="invalid credentials")
    _clear_failures(body.user_id)
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
