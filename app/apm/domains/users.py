"""Users domain: identity registry + session identity switching (M5-I19).

事件溯源一致：users 表是 `user.registered`/`user.updated` 事件的投影；切换身份
落 `session.identity_switched` 事件（审计可见"谁在哪一刻换成了谁"）。单机 MVP
的"登录"= 身份选择：切换后 `settings.user_id` 即当前身份，后续所有 emit 默认
actor 归到该身份（on_behalf_of 链路在 NL 命令层已有，此处打通 UI 操作）。
"""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm import config
from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on
from apm.core import security

router = APIRouter(tags=["users"])

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


# ------------------------------------------------------------ projections
@on("user.registered")
def _proj_user_register(conn, e):
    p = e.payload
    conn.execute(
        "INSERT OR IGNORE INTO users (id, name, email, created_at, updated_at)"
        " VALUES (?,?,?,?,?)",
        (e.agg_id, p.get("name", ""), p.get("email"), e.ts, e.ts),
    )


@on("user.updated")
def _proj_user_update(conn, e):
    p = e.payload
    conn.execute(
        "UPDATE users SET name = ?, email = ?, updated_at = ? WHERE id = ?",
        (p.get("name"), p.get("email"), e.ts, e.agg_id),
    )


def _require_user(uid: str) -> dict:
    row = db.get_conn().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if not row:
        raise HTTPException(status_code=422, detail=f"unknown user '{uid}'")
    return dict(row)


def _safe_user(row) -> dict:
    """Projection row without credential material (M8-I26)."""
    d = dict(row)
    d.pop("password_hash", None)
    if "is_admin" in d:
        d["is_admin"] = bool(d["is_admin"])
    return d


def ensure_default_user() -> None:
    """Bootstrap: register the configured single-user identity on first boot.

    Events, not rows — rebuild-projections reproduces the registry from history.
    Security state is the exception (M8-I26): is_admin and password_hash are
    direct runtime columns, never evented (credentials must not enter the audit
    log). APM_ADMIN_PASSWORD re-applies the admin password on every boot, which
    is also the recovery path after a projection rebuild.
    """
    conn = db.get_conn()
    n = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    if n == 0:
        events.emit(
            event_type="user.registered",
            agg_type="user",
            agg_id=config.settings.user_id,
            payload={"name": config.settings.user_name, "email": None},
        )
    conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (config.settings.user_id,))
    if config.settings.admin_password:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (security.hash_password(config.settings.admin_password), config.settings.user_id),
        )
    conn.commit()


# ------------------------------------------------------------ API
@router.get("/users")
def list_users() -> dict:
    rows = db.get_conn().execute(
        "SELECT * FROM users ORDER BY created_at, id").fetchall()
    current = config.settings.user_id
    return {
        "users": [_safe_user(r) for r in rows],
        "current": current,
        "current_name": next((r["name"] for r in rows if r["id"] == current), current),
    }


class UserIn(BaseModel):
    id: str | None = None
    name: str
    email: str | None = None
    password: str | None = None  # admin-style account creation (M8-I27); hashed, never evented


@router.post("/users")
def register_user(body: UserIn) -> dict:
    uid = (body.id or "").strip() or _derive_id(body.name)
    if not _ID_RE.match(uid):
        raise HTTPException(status_code=422, detail="user id must match ^[a-z0-9][a-z0-9_-]{0,63}$")
    if db.get_conn().execute("SELECT 1 FROM users WHERE id = ?", (uid,)).fetchone():
        raise HTTPException(status_code=409, detail=f"user '{uid}' already exists")
    events.emit(
        event_type="user.registered",
        agg_type="user",
        agg_id=uid,
        payload={"name": body.name, "email": body.email},
    )
    if body.password:
        db.get_conn().execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (security.hash_password(body.password), uid),
        )
        db.get_conn().commit()
    return _safe_user(_require_user(uid))


class IdentityIn(BaseModel):
    user_id: str


@router.post("/session/identity")
def switch_identity(body: IdentityIn) -> dict:
    if config.settings.auth_mode == "network":
        # 网络模式下身份由登录会话决定（M8-I28），切换 = 登出再登录。
        raise HTTPException(status_code=422, detail="identity switching is local-mode only; use login/logout")
    user = _require_user(body.user_id)
    previous = config.settings.user_id
    config.settings.user_id = user["id"]
    events.emit(
        event_type="session.identity_switched",
        agg_type="session",
        agg_id=new_id("sess"),
        payload={"from": previous, "to": user["id"],
                 "summary": f"身份切换：{previous} → {user['id']}（{user['name']}）"},
    )
    return {"current": user["id"], "name": user["name"], "previous": previous}


def _derive_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:  # 纯非 ASCII 名（如中文）：退化为 u+短随机，避免碰撞
        return f"u-{new_id('u').split('_', 1)[1][:6]}"
    return slug[:60]
