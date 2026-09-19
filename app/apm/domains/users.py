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
    """Projection row without credential material (M8-I26).
    feed_key 是持久读凭据（feed/ical 订阅），只允许本人经 /me/feed-key 查看，
    列表/详情一律剔除。"""
    d = dict(row)
    d.pop("password_hash", None)
    d.pop("feed_key", None)
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
    if body.password:
        # 带密码=可登录凭据，仅管理员可发放（OIDC JIT 无密码走此端点不受限）。
        from apm.domains.members import is_instance_admin

        if not is_instance_admin(events.effective_actor()):
            raise HTTPException(
                status_code=403, detail="admin role required to create accounts with passwords")
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


# ---------------------------------------------------- saved replies (I108)
class SavedReplyIn(BaseModel):
    title: str
    body: str


@router.get("/me/saved-replies")
def list_saved_replies() -> dict:
    """GitHub Saved Replies semantics (docs/01 §AH.2): the user's own canned
    responses, runtime state (like notification_prefs — rebuild keeps them)."""
    rows = db.get_conn().execute(
        "SELECT id, title, body, created_at FROM saved_replies WHERE user_id = ?"
        " ORDER BY created_at, id", (events.effective_actor(),)).fetchall()
    return {"replies": [dict(r) for r in rows]}


@router.post("/me/saved-replies")
def add_saved_reply(body: SavedReplyIn) -> dict:
    title = (body.title or "").strip()
    text = (body.body or "").strip()
    if not title or len(title) > 100:
        raise HTTPException(status_code=422, detail="title is required (≤100 chars)")
    if not text or len(text) > 2000:
        raise HTTPException(status_code=422, detail="body is required (≤2000 chars)")
    rid = new_id("sr")
    db.get_conn().execute(
        "INSERT INTO saved_replies (user_id, id, title, body, created_at) VALUES (?,?,?,?,?)",
        (events.effective_actor(), rid, title, text, events.utcnow()),
    )
    db.get_conn().commit()
    return {"id": rid, "title": title, "body": text}


@router.delete("/me/saved-replies/{reply_id}")
def delete_saved_reply(reply_id: str) -> dict:
    conn = db.get_conn()
    cur = conn.execute(
        "DELETE FROM saved_replies WHERE user_id = ? AND id = ?",
        (events.effective_actor(), reply_id))
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="no such saved reply")
    return {"deleted": reply_id}


# ---------------------------------------------------- time off (I111)
@on("user.time_off_started")
def _proj_time_off_started(conn, e):
    p = e.payload
    conn.execute(
        "INSERT INTO user_time_off (id, user_id, start_date, end_date, delegate,"
        " reason, cancelled_at, created_at) VALUES (?,?,?,?,?,?,NULL,?)",
        (e.agg_id, p["user_id"], p["start_date"], p["end_date"],
         p.get("delegate"), p.get("reason"), e.ts),
    )


@on("user.time_off_cancelled")
def _proj_time_off_cancelled(conn, e):
    conn.execute(
        "UPDATE user_time_off SET cancelled_at = ? WHERE id = ?", (e.ts, e.agg_id))


def _overlaps(conn, user_id: str, start: str, end: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM user_time_off WHERE user_id = ? AND cancelled_at IS NULL"
        " AND NOT (end_date < ? OR start_date > ?) LIMIT 1",
        (user_id, start, end)).fetchone() is not None


def is_on_leave(conn, user_id: str, day: str | None = None) -> bool:
    """True when `day` (default today) falls inside one of the user's active
    time-off stretches — the workload page and my-schedule consume this."""
    day = day or events.utcnow()[:10]
    return conn.execute(
        "SELECT 1 FROM user_time_off WHERE user_id = ? AND cancelled_at IS NULL"
        " AND start_date <= ? AND end_date >= ? LIMIT 1",
        (user_id, day, day)).fetchone() is not None


class TimeOffIn(BaseModel):
    start_date: str
    end_date: str
    reason: str | None = None
    delegate: str | None = None  # I117: stands in during the stretch


@router.get("/me/time-off")
def list_time_off() -> dict:
    rows = db.get_conn().execute(
        "SELECT id, start_date, end_date, delegate, reason, cancelled_at, created_at"
        " FROM user_time_off WHERE user_id = ? ORDER BY start_date",
        (events.effective_actor(),)).fetchall()
    return {"time_off": [dict(r) for r in rows]}


@router.post("/me/time-off")
def add_time_off(body: TimeOffIn) -> dict:
    from datetime import date as _date

    user_id = events.effective_actor()
    try:
        start = _date.fromisoformat(body.start_date)
        end = _date.fromisoformat(body.end_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid date")
    if end < start:
        raise HTTPException(status_code=422, detail="end_date must not precede start_date")
    if body.delegate:
        if body.delegate == user_id:
            raise HTTPException(status_code=422, detail="cannot delegate to yourself")
        # I117: the delegate must share at least one project with the vacationer,
        # otherwise the handoff would land work where the stand-in can't see it.
        shared = db.get_conn().execute(
            "SELECT 1 FROM project_members a JOIN project_members b"
            " ON a.project_id = b.project_id"
            " WHERE a.user_id = ? AND b.user_id = ? LIMIT 1",
            (user_id, body.delegate)).fetchone()
        if shared is None:
            raise HTTPException(status_code=422, detail="delegate must share a project with you")
    if _overlaps(db.get_conn(), user_id, body.start_date, body.end_date):
        raise HTTPException(status_code=409, detail="overlaps an existing time-off stretch")
    off_id = new_id("off")
    events.emit(
        event_type="user.time_off_started", agg_type="time_off", agg_id=off_id,
        actor_type="human", actor_id=user_id,
        payload={"user_id": user_id, "start_date": body.start_date,
                 "end_date": body.end_date, "reason": body.reason,
                 "delegate": body.delegate},
    )
    return {"id": off_id, "start_date": body.start_date,
            "end_date": body.end_date, "reason": body.reason,
            "delegate": body.delegate}


# ---------------------------------------------------- hourly rate (I122)
class RateIn(BaseModel):
    rate: float


@router.get("/me/hourly-rate")
def get_hourly_rate() -> dict:
    row = db.get_conn().execute(
        "SELECT hourly_rate FROM users WHERE id = ?", (events.effective_actor(),)).fetchone()
    return {"rate": row["hourly_rate"] if row else None}


@router.post("/me/hourly-rate")
def set_hourly_rate(body: RateIn) -> dict:
    """Own-data runtime preference (same family as email_notify/feed_key):
    the cost report derives labor cost from logged minutes × this rate."""
    if body.rate < 0:
        raise HTTPException(status_code=422, detail="rate must not be negative")
    conn = db.get_conn()
    conn.execute(
        "UPDATE users SET hourly_rate = ?, updated_at = ? WHERE id = ?",
        (body.rate, events.utcnow(), events.effective_actor()))
    conn.commit()
    return {"rate": body.rate}


@router.delete("/me/time-off/{off_id}")
def cancel_time_off(off_id: str) -> dict:
    conn = db.get_conn()
    row = conn.execute(
        "SELECT * FROM user_time_off WHERE id = ? AND user_id = ? AND cancelled_at IS NULL",
        (off_id, events.effective_actor())).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="no such active time-off")
    events.emit(
        event_type="user.time_off_cancelled", agg_type="time_off", agg_id=off_id,
        actor_type="human", actor_id=events.effective_actor(),
        payload={"user_id": row["user_id"]},
    )
    return {"cancelled": off_id}
