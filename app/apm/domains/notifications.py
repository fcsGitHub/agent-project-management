"""In-app notification center (M10-I34): notifications are a pure projection of
existing events — human assignees get notified on `item.assigned`, project
owners on `approval.requested`, and the automation engine's `notify` action
emits `notification.sent` for a targeted user. Read-state is event-sourced
(`notification.read`), so rebuilds reproduce unread counts exactly."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on

router = APIRouter(tags=["notifications"])


# ---------------------------------------------------------------- projectors
NOTIFY_EVENTS = ("item.assigned", "approval.requested", "notification.sent")


def plan_notifications(conn, e) -> list[tuple[str, str, str]]:
    """Pure decision: who should be notified for this event, with what kind and
    summary. Shared by the projection fold and the email channel (M11-I35) so
    both channels never disagree on recipients."""
    out: list[tuple[str, str, str]] = []
    if e.event_type == "item.assigned":
        if e.payload.get("assignee_type") != "human" or not e.payload.get("assignee_id"):
            return out
        row = conn.execute("SELECT title FROM items WHERE id = ?", (e.agg_id,)).fetchone()
        title = row["title"] if row else e.agg_id
        out.append((e.payload["assignee_id"], "assigned", f"被指派工作项「{title}」"))
    elif e.event_type == "approval.requested":
        owners = conn.execute(
            "SELECT user_id FROM project_members WHERE project_id = ? AND role = 'owner'",
            (e.project_id,),
        ).fetchall()
        for o in owners:
            out.append((o["user_id"], "approval", f"审批请求：{e.payload.get('kind', 'gate')}"))
    elif e.event_type == "notification.sent":
        p = e.payload
        if p.get("user_id"):
            out.append((p["user_id"], p.get("kind", "notify"), p.get("summary", "")))
    return out


def _notify(conn, e, user_id: str, kind: str, summary: str) -> None:
    if not user_id:
        return
    # Deterministic id (source event seq + user): rebuild reproduces the exact
    # same ids, so notification.read payload ids keep matching after replay.
    conn.execute(
        "INSERT INTO notifications (id, project_id, user_id, kind, summary, ref_event_id,"
        " read, created_at) VALUES (?,?,?,?,?,?,0,?)",
        (f"n_{e.id}_{user_id}", e.project_id, user_id, kind, summary[:200], e.id, e.ts),
    )


@on("item.assigned")
def _proj_notify_assigned(conn, e):
    for user_id, kind, summary in plan_notifications(conn, e):
        _notify(conn, e, user_id, kind, summary)


@on("approval.requested")
def _proj_notify_approval(conn, e):
    for user_id, kind, summary in plan_notifications(conn, e):
        _notify(conn, e, user_id, kind, summary)


@on("notification.sent")
def _proj_notify_sent(conn, e):
    p = e.payload
    _notify(conn, e, p.get("user_id"), p.get("kind", "notify"), p.get("summary", ""))


@on("notification.read")
def _proj_notification_read(conn, e):
    p = e.payload
    if p.get("all"):
        conn.execute(
            "UPDATE notifications SET read = 1 WHERE user_id = ? AND read = 0",
            (e.actor_id,),
        )
    elif p.get("ids"):
        marks = [(e.actor_id, nid) for nid in p["ids"]]
        conn.executemany(
            "UPDATE notifications SET read = 1 WHERE user_id = ? AND id = ?", marks)


# ---------------------------------------------------------------- API
@router.get("/notifications")
def get_notifications() -> dict:
    user_id = events.effective_actor()
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC, id DESC"
        " LIMIT 30",
        (user_id,),
    ).fetchall()
    unread = conn.execute(
        "SELECT COUNT(*) c FROM notifications WHERE user_id = ? AND read = 0",
        (user_id,),
    ).fetchone()["c"]
    pref = conn.execute(
        "SELECT email_notify FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    email_enabled = bool(pref["email_notify"]) if pref else True
    return {
        "notifications": [dict(r) for r in rows],
        "unread": unread,
        "user_id": user_id,
        "email_enabled": email_enabled,
    }


class ReadIn(BaseModel):
    ids: list[str] | None = None
    all: bool = False


class PrefsIn(BaseModel):
    email_enabled: bool


@router.post("/notifications/prefs")
def set_prefs(body: PrefsIn) -> dict:
    """User-level runtime preference (M11-I37): like feed_key/password it lives
    in the projection table, not the event stream."""
    user_id = events.effective_actor()
    conn = db.get_conn()
    conn.execute(
        "UPDATE users SET email_notify = ?, updated_at = ? WHERE id = ?",
        (1 if body.email_enabled else 0, events.utcnow(), user_id),
    )
    conn.commit()
    return {"user_id": user_id, "email_enabled": body.email_enabled}


@router.post("/notifications/read")
def mark_read(body: ReadIn) -> dict:
    if not body.all and not body.ids:
        raise HTTPException(status_code=422, detail="provide ids or all=true")
    conn = db.get_conn()
    if body.ids:
        known = {r["id"] for r in conn.execute(
            "SELECT id FROM notifications WHERE user_id = ?",
            (events.effective_actor(),)).fetchall()}
        unknown = [i for i in body.ids if i not in known]
        if unknown:
            raise HTTPException(status_code=404, detail=f"unknown notifications: {unknown[:5]}")
    events.emit(
        event_type="notification.read", agg_type="notification",
        agg_id=new_id("nread"), project_id="",
        payload={"ids": body.ids, "all": body.all},
    )
    return {"ok": True}
