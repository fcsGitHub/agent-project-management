"""Project membership & roles (M8-I27): owner / contributor / viewer, trimmed
from Plane's two-tier model (docs/01 §G.1) — AgentPM projects are top-level, so
only the project tier exists. Creator becomes owner (Gitea-style). Network mode
gates project mutations on membership; denials are audited (`access.denied`)."""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from apm import config
from apm.core import db, events
from apm.core.projections import on
from apm.core.security import SESSION_COOKIE, session_user
from apm.domains.projects import require_project

router = APIRouter(tags=["members"])

ROLES = ("owner", "contributor", "viewer")
WRITE_ROLES = ("owner", "contributor")

# ---------------------------------------------------------------- projectors
@on("project.member_added")
def _proj_member_added(conn, e):
    conn.execute(
        "INSERT INTO project_members (project_id, user_id, role, created_at, updated_at)"
        " VALUES (?,?,?,?,?) ON CONFLICT(project_id, user_id)"
        " DO UPDATE SET role = excluded.role, updated_at = excluded.updated_at",
        (e.project_id, e.payload["user_id"], e.payload["role"], e.ts, e.ts),
    )


@on("project.member_role_changed")
def _proj_member_role_changed(conn, e):
    conn.execute(
        "UPDATE project_members SET role = ?, updated_at = ? WHERE project_id = ? AND user_id = ?",
        (e.payload["role"], e.ts, e.project_id, e.payload["user_id"]),
    )


@on("project.member_notify_level")
def _proj_member_notify_level(conn, e):
    # M63-I190: per-member notification level (docs/01 §BH.2) — NULL = default
    # "participating" noise, "mentions_only" mutes participant-kind branches.
    conn.execute(
        "UPDATE project_members SET notify_level = ?, updated_at = ?"
        " WHERE project_id = ? AND user_id = ?",
        (e.payload.get("level"), e.ts, e.project_id, e.payload["user_id"]),
    )


@on("project.member_removed")
def _proj_member_removed(conn, e):
    conn.execute(
        "DELETE FROM project_members WHERE project_id = ? AND user_id = ?",
        (e.project_id, e.payload["user_id"]),
    )


# ---------------------------------------------------------------- helpers
def member_role(project_id: str, user_id: str) -> str | None:
    row = db.get_conn().execute(
        "SELECT role FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()
    return row["role"] if row else None


def list_members(project_id: str) -> list[dict]:
    rows = db.get_conn().execute(
        "SELECT m.user_id, m.role, m.notify_level, m.created_at, u.name"
        " FROM project_members m LEFT JOIN users u ON u.id = m.user_id"
        " WHERE m.project_id = ? ORDER BY m.created_at, m.user_id",
        (project_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def is_instance_admin(user_id: str) -> bool:
    row = db.get_conn().execute(
        "SELECT is_admin FROM users WHERE id = ?", (user_id,)).fetchone()
    return bool(row["is_admin"]) if row else False


def require_instance_user() -> str:
    """M76-I228: org-level reads (assets / template packs) — local mode is
    trusted; network mode requires a logged-in instance user. 401 (not 403):
    there is no project to be a member of — the gate is authentication, not
    project membership."""
    from apm.core import events as _events

    if config.settings.auth_mode == "local":
        return _events.effective_actor()
    actor = _events.effective_actor()
    if actor in ("", "anonymous"):
        raise HTTPException(status_code=401, detail="login required")
    return actor


def check_project_write(project_id: str, user_id: str) -> tuple[bool, str | None]:
    """May `user_id` mutate `project_id`? Returns (allowed, effective role)."""
    if is_instance_admin(user_id):
        return True, "admin"
    role = member_role(project_id, user_id)
    if role in WRITE_ROLES:
        return True, role
    return False, role  # None = non-member; "viewer" = read-only member


def require_project_write(project_id: str) -> None:
    """M80-I240 (docs/01 §BY.1): domain-level write gate for id-path resources
    the middleware whitelist never covered (cycles/milestones/features/risks,
    conversations/runs entries, asset deposits). check_project_write already
    grants the local-mode trusted user (bootstrap admin), so local behavior
    is unchanged; network-mode non-members/viewers get 403."""
    allowed, role = check_project_write(project_id, events.effective_actor())
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail=f"project write requires a member role (you are {role or 'not a member'} of {project_id})")


def require_project_read(project_id: str) -> None:
    """M114-I339 (docs/01 §DE.1): read-side twin of require_project_write for
    global-id single resources whose write siblings have carried the M80-I240
    gate since the last audit (runs/milestones/cycles/features detail and
    friends) — M76-I228 covered the org/project list faces but left these
    same-class reads open (the "one more gap of the same gate" lesson from
    M110 R2-F1). Local mode trusted; network mode passes for the instance
    admin or any project member (viewer included, matching the `_gate`
    family's any-role read semantics); outsiders get 403 like
    expenses/automations. Unlike require_project_write this grants the admin
    explicitly: admins already read audit.csv, so a read gate must not lock
    them out of project data."""
    if config.settings.auth_mode == "local":
        return
    actor = events.effective_actor()
    if is_instance_admin(actor) or member_role(project_id, actor) is not None:
        return
    raise HTTPException(status_code=403, detail="not a project member")


def visible_project_ids(actor: str) -> set[str] | None:
    """M114-I339: aggregate list faces (runs/conversations/approvals/events)
    filter cross-project rows with the same membership semantics as the
    feed/search `_visible` family. Returns None = unrestricted (local mode or
    instance admin); a (possibly empty) set of visible project ids otherwise —
    anonymous network callers get the empty set, mirroring
    reports._activity_list's `user is None` skip."""
    if config.settings.auth_mode == "local" or is_instance_admin(actor):
        return None
    rows = db.get_conn().execute("SELECT id FROM projects").fetchall()
    return {r["id"] for r in rows if member_role(r["id"], actor) is not None}


def project_id_for_path(path: str) -> str | None:
    """Best-effort project context for a /api path (M8-I27 write gating)."""
    m = re.match(r"^/api/projects/([^/]+)", path)
    if m:
        return m.group(1)
    m = re.match(r"^/api/(items|conversations|runs|approvals|artifacts)/([^/]+)", path)
    if m:
        table, resource_id = m.group(1), m.group(2)  # table from a fixed whitelist
        row = db.get_conn().execute(
            f"SELECT project_id FROM {table} WHERE id = ?", (resource_id,)
        ).fetchone()
        return row["project_id"] if row else None
    return None


def _session_user(request: Request) -> str | None:
    return session_user(request.cookies.get(SESSION_COOKIE))


def _require_member_manager(project_id: str, request: Request) -> str:
    """Who may change membership: instance admin or the project owner (network
    mode); local mode is single-user and always allowed."""
    if config.settings.auth_mode != "network":
        return config.settings.user_id
    user_id = _session_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="login required")
    if is_instance_admin(user_id) or member_role(project_id, user_id) == "owner":
        return user_id
    events.emit(
        event_type="access.denied",
        agg_type="project",
        agg_id=project_id,
        project_id=project_id,
        actor_type="human",
        actor_id=user_id,
        payload={"user_id": user_id, "summary": f"成员管理被拒绝：{user_id} @ {project_id}"},
    )
    raise HTTPException(status_code=403, detail="only the project owner may manage members")


def _reject_last_owner_change(project_id: str, user_id: str, *, removing: bool, new_role: str | None = None) -> None:
    if member_role(project_id, user_id) != "owner":
        return
    would_keep = removing is False and new_role == "owner"
    others = [
        m for m in list_members(project_id)
        if m["role"] == "owner" and m["user_id"] != user_id
    ]
    if not would_keep and not others:
        raise HTTPException(status_code=422, detail="cannot remove or demote the last owner")


# ---------------------------------------------------------------- API
class MemberIn(BaseModel):
    user_id: str
    role: str = "contributor"


class MemberRoleIn(BaseModel):
    user_id: str
    role: str


@router.get("/projects/{project_id}/members")
def get_members(project_id: str) -> dict:
    require_project(project_id)
    return {"members": list_members(project_id)}


@router.post("/projects/{project_id}/members")
def add_member(project_id: str, body: MemberIn, request: Request) -> dict:
    require_project(project_id)
    _require_member_manager(project_id, request)
    if body.role not in ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of {ROLES}")
    if not db.get_conn().execute("SELECT 1 FROM users WHERE id = ?", (body.user_id,)).fetchone():
        raise HTTPException(status_code=422, detail=f"unknown user '{body.user_id}'")
    if member_role(project_id, body.user_id):
        raise HTTPException(status_code=409, detail=f"user '{body.user_id}' is already a member")
    events.emit(
        event_type="project.member_added",
        agg_type="project",
        agg_id=project_id,
        project_id=project_id,
        payload={"user_id": body.user_id, "role": body.role},
    )
    return {"project_id": project_id, "user_id": body.user_id, "role": body.role}


@router.patch("/projects/{project_id}/members")
def change_role(project_id: str, body: MemberRoleIn, request: Request) -> dict:
    require_project(project_id)
    _require_member_manager(project_id, request)
    if body.role not in ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of {ROLES}")
    if not member_role(project_id, body.user_id):
        raise HTTPException(status_code=404, detail=f"user '{body.user_id}' is not a member")
    _reject_last_owner_change(project_id, body.user_id, removing=False, new_role=body.role)
    events.emit(
        event_type="project.member_role_changed",
        agg_type="project",
        agg_id=project_id,
        project_id=project_id,
        payload={"user_id": body.user_id, "role": body.role},
    )
    return {"project_id": project_id, "user_id": body.user_id, "role": body.role}


NOTIFY_LEVELS = (None, "mentions_only")


class MemberNotifyLevelIn(BaseModel):
    # M63-I190: None = 默认（参与即响）；"mentions_only" = 参与类静音。
    level: str | None = None


@router.patch("/projects/{project_id}/members/{user_id}/notify-level")
def set_notify_level(project_id: str, user_id: str, body: MemberNotifyLevelIn, request: Request) -> dict:
    """Per-member notification level (M63-I190, docs/01 §BH.2 — GitHub watch
    三档取两档: Ignore 连提及都吞过于激进, 取 Slack「保留直接提及」语义).
    Owner/admin may set anyone; a member may always downgrade themselves.
    Governance-critical notifications (mention/assignment/approval/due_soon/
    watch rules) bypass this level entirely."""
    require_project(project_id)
    if body.level not in NOTIFY_LEVELS:
        raise HTTPException(status_code=422, detail=f"level must be one of {NOTIFY_LEVELS}")
    if not member_role(project_id, user_id):
        raise HTTPException(status_code=404, detail=f"user '{user_id}' is not a member")
    # 本人可降级自己；否则需 owner/admin（_require_member_manager 语义）
    caller = _session_user(request) if config.settings.auth_mode == "network" else config.settings.user_id
    if caller != user_id:
        _require_member_manager(project_id, request)
    events.emit(
        event_type="project.member_notify_level",
        agg_type="project",
        agg_id=project_id,
        project_id=project_id,
        actor_type="human",
        actor_id=caller,
        payload={"user_id": user_id, "level": body.level},
    )
    return {"project_id": project_id, "user_id": user_id, "level": body.level}


@router.delete("/projects/{project_id}/members/{user_id}")
def remove_member(project_id: str, user_id: str, request: Request) -> dict:
    require_project(project_id)
    _require_member_manager(project_id, request)
    if not member_role(project_id, user_id):
        raise HTTPException(status_code=404, detail=f"user '{user_id}' is not a member")
    _reject_last_owner_change(project_id, user_id, removing=True)
    events.emit(
        event_type="project.member_removed",
        agg_type="project",
        agg_id=project_id,
        project_id=project_id,
        payload={"user_id": user_id},
    )
    return {"project_id": project_id, "user_id": user_id, "removed": True}
