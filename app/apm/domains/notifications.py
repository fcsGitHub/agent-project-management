"""In-app notification center (M10-I34): notifications are a pure projection of
existing events — human assignees get notified on `item.assigned`, project
owners on `approval.requested`, and the automation engine's `notify` action
emits `notification.sent` for a targeted user. Since M18-I58 participants
(author/assignee/mentioned/watchers, see `item_participants`) are notified on
follow-up item events — minimal face: status changes and new comments. Read
state is event-sourced (`notification.read`), so rebuilds reproduce unread
counts exactly."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on

router = APIRouter(tags=["notifications"])


# ---------------------------------------------------------------- projectors
NOTIFY_EVENTS = (
    "item.assigned", "approval.requested", "notification.sent",
    "comment.created", "item.status_changed", "item.due_soon_notified",
    "approval.pending_reminded",
)

# I96 (docs/01 §AD.2, GitLab Custom level): per-kind delivery gates. mention is
# always deliverable — every other kind defaults to on when no pref row exists.
NOTIFY_KINDS: dict[str, str] = {
    "assigned": "指派给我",
    "approval": "审批请求",
    "comment": "参与项新评论",
    "item": "参与项状态变更",
    "mention": "@提及",
    "due_soon": "临近截止提醒",
    "approval_reminder": "审批超时提醒",
}


def pref_allows(conn, user_id: str, kind: str, channel: str) -> bool:
    """Single delivery gate both channels call (GitLab #410008 lesson: gate at
    the delivery path, once per channel, never ad hoc). mention is unfailable."""
    if kind == "mention":
        return True
    row = conn.execute(
        f"SELECT {channel} FROM notification_prefs WHERE user_id = ? AND kind = ?",
        (user_id, kind),
    ).fetchone()
    return bool(row[channel]) if row else True


def _item_title(conn, item_id: str) -> str:
    row = conn.execute("SELECT title FROM items WHERE id = ?", (item_id,)).fetchone()
    return row["title"] if row else item_id


def plan_notifications(conn, e) -> list[tuple[str, str, str]]:
    """Pure decision: who should be notified for this event, with what kind and
    summary. Shared by the projection fold and the email channel (M11-I35) so
    both channels never disagree on recipients."""
    out: list[tuple[str, str, str]] = []
    if e.event_type == "item.assigned":
        if e.payload.get("assignee_type") != "human" or not e.payload.get("assignee_id"):
            return out
        title = _item_title(conn, e.agg_id)
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
    elif e.event_type == "comment.created":
        # M18-I58: participants hear about new comments; the author and the
        # mentioned users are skipped (mentioned users already got the
        # targeted mention notification via notification.sent). agg_id is the
        # comment id — the item comes from the payload.
        p = e.payload
        item_id = p.get("item_id") or e.agg_id
        skip = {p.get("author_id")} | set(json.loads(p.get("mentions_json", "[]")))
        title = _item_title(conn, item_id)
        preview = (p.get("body") or "")[:60]
        for r in conn.execute(
                "SELECT user_id FROM item_participants WHERE item_id = ?", (item_id,)):
            if r["user_id"] not in skip:
                out.append((r["user_id"], "comment",
                            f"参与的工作项「{title}」有新评论：{preview}"))
    elif e.event_type == "item.status_changed":
        # M18-I58: watchers/participants follow the item's lifecycle; the actor
        # who made the change is never notified
        title = _item_title(conn, e.agg_id)
        for r in conn.execute(
                "SELECT user_id FROM item_participants WHERE item_id = ?", (e.agg_id,)):
            if r["user_id"] != e.actor_id:
                out.append((r["user_id"], "item",
                            f"参与的工作项「{title}」状态变更为 {e.payload.get('status', '?')}"))
    elif e.event_type == "item.due_soon_notified":
        # I105: the daily sweep's built-in due-date reminder — recipient is
        # the human assignee recorded in the payload (Plane automations
        # semantics); both channels gate it as kind "due_soon".
        p = e.payload
        if p.get("assignee_id"):
            out.append((p["assignee_id"], "due_soon",
                        f"工作项「{p.get('title', '')}」将于 {p.get('due_date', '?')} 到期"))
    elif e.event_type == "approval.pending_reminded":
        # I126: the daily sweep nudges owners about gate approvals that have
        # been pending past the reminder window (ServiceNow timer→reminder).
        kind = e.payload.get("kind", "gate")
        days = e.payload.get("days_pending", "?")
        for o in conn.execute(
                "SELECT user_id FROM project_members WHERE project_id = ? AND role = 'owner'",
                (e.project_id,)).fetchall():
            out.append((o["user_id"], "approval_reminder",
                        f"审批已挂起 {days} 天：{kind}（{e.agg_id}）"))
    return out


def _notify(conn, e, user_id: str, kind: str, summary: str) -> None:
    if not user_id:
        return
    if not pref_allows(conn, user_id, kind, "inapp"):
        return  # I96: per-kind in-app gate
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


@on("comment.created")
def _proj_notify_comment(conn, e):
    # runs after comments.py's participant-join (same event, earlier import)
    for user_id, kind, summary in plan_notifications(conn, e):
        _notify(conn, e, user_id, kind, summary)


@on("item.status_changed")
def _proj_notify_status(conn, e):
    for user_id, kind, summary in plan_notifications(conn, e):
        _notify(conn, e, user_id, kind, summary)


@on("item.due_soon_notified")
def _proj_notify_due_soon(conn, e):
    for user_id, kind, summary in plan_notifications(conn, e):
        _notify(conn, e, user_id, kind, summary)


@on("approval.pending_reminded")
def _proj_notify_approval_reminder(conn, e):
    for user_id, kind, summary in plan_notifications(conn, e):
        _notify(conn, e, user_id, kind, summary)


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
    out = []
    for r in rows:
        d = dict(r)
        # mention 通知跳转工作项：ref_event_id → 事件 agg_id 即 item_id（M18-I57）
        if d.get("ref_event_id"):
            ev = conn.execute(
                "SELECT agg_id FROM events WHERE id = ?", (d["ref_event_id"],)).fetchone()
            if ev:
                d["item_id"] = ev["agg_id"]
        out.append(d)
    return {
        "notifications": out,
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


class KindPrefIn(BaseModel):
    kind: str
    inapp: bool
    email: bool


class KindPrefsIn(BaseModel):
    prefs: list[KindPrefIn]


@router.get("/me/notification-prefs")
def get_kind_prefs() -> dict:
    """I96: per-kind × channel matrix; missing rows are fully-on defaults."""
    user_id = events.effective_actor()
    conn = db.get_conn()
    rows = {r["kind"]: r for r in conn.execute(
        "SELECT kind, inapp, email FROM notification_prefs WHERE user_id = ?", (user_id,))}
    pref = conn.execute(
        "SELECT email_notify FROM users WHERE id = ?", (user_id,)).fetchone()
    return {
        "email_enabled": bool(pref["email_notify"]) if pref else True,
        "kinds": [
            {"kind": k, "label": label,
             "inapp": bool(rows[k]["inapp"]) if k in rows else True,
             "email": bool(rows[k]["email"]) if k in rows else True}
            for k, label in NOTIFY_KINDS.items()
        ],
    }


@router.put("/me/notification-prefs")
def put_kind_prefs(body: KindPrefsIn) -> dict:
    user_id = events.effective_actor()
    bad = [p.kind for p in body.prefs if p.kind not in NOTIFY_KINDS]
    if bad:
        raise HTTPException(status_code=422, detail=f"unknown kinds: {bad}")
    if any(p.kind == "mention" and not (p.inapp and p.email) for p in body.prefs):
        raise HTTPException(status_code=422, detail="mention notifications cannot be turned off")
    conn = db.get_conn()
    now = events.utcnow()
    for p in body.prefs:
        conn.execute(
            "INSERT INTO notification_prefs (user_id, kind, inapp, email, updated_at)"
            " VALUES (?,?,?,?,?) ON CONFLICT(user_id, kind) DO UPDATE SET"
            " inapp=excluded.inapp, email=excluded.email, updated_at=excluded.updated_at",
            (user_id, p.kind, 1 if p.inapp else 0, 1 if p.email else 0, now),
        )
    conn.commit()
    return {"ok": True, "user_id": user_id}


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
