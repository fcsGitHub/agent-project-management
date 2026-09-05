"""External intake (M32-I99, docs/01 §AE.2): Trello's board-level email address
and Jira's mail handler give a container a credential-carrying address that
outsiders can post to without an account — AgentPM's HTTP-minimal version is an
intake token. The owner mints one per project; `POST /intake/{token}` lands a
first-class item through the full create_item validation chain (actor_type=
"intake"), so archived-project guards, concept whitelists and projections all
apply for free. Tokens are projections of intake.token_* events (rebuild
reproduces them); the value itself is stored plaintext like users.feed_key —
the owner UI re-displays it for copying."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on
from apm.domains.items import create_item
from apm.domains.members import is_instance_admin, member_role
from apm.domains.projects import require_project

router = APIRouter(tags=["intake"])

PRIORITIES = ("high", "medium", "low")


def _require_owner(project_id: str) -> None:
    user_id = events.effective_actor()
    if is_instance_admin(user_id) or member_role(project_id, user_id) == "owner":
        return
    raise HTTPException(status_code=403, detail="owner role required for intake tokens")


# ---------------------------------------------------------------- projectors
@on("intake.token_issued")
def _proj_token_issued(conn, e):
    conn.execute(
        "INSERT INTO intake_tokens (id, project_id, token, concept_id, revoked_at,"
        " created_at, updated_at) VALUES (?,?,?,?,NULL,?,?)"
        " ON CONFLICT(id) DO UPDATE SET token=excluded.token,"
        " concept_id=excluded.concept_id, revoked_at=NULL, updated_at=excluded.updated_at",
        (e.agg_id, e.project_id, e.payload["token"], e.payload.get("concept_id"),
         e.ts, e.ts),
    )


@on("intake.token_revoked")
def _proj_token_revoked(conn, e):
    conn.execute(
        "UPDATE intake_tokens SET revoked_at = ?, updated_at = ? WHERE id = ?",
        (e.ts, e.ts, e.agg_id),
    )


# ---------------------------------------------------------------- owner API
class TokenOut(BaseModel):
    token: str
    concept_id: str | None = None
    revoked: bool = False


def _active_token(conn, project_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM intake_tokens WHERE project_id = ? AND revoked_at IS NULL",
        (project_id,)).fetchone()
    return dict(row) if row else None


@router.get("/projects/{project_id}/intake-token")
def get_token(project_id: str) -> dict:
    require_project(project_id)
    _require_owner(project_id)
    row = _active_token(db.get_conn(), project_id)
    if not row:
        return {"issued": False}
    return {"issued": True, "token": row["token"], "concept_id": row["concept_id"]}


@router.post("/projects/{project_id}/intake-token")
def issue_token(project_id: str, body: dict | None = None) -> dict:
    require_project(project_id)
    _require_owner(project_id)
    conn = db.get_conn()
    previous = _active_token(conn, project_id)
    if previous:  # re-issue: revoke the old one first (single active token)
        events.emit(
            event_type="intake.token_revoked", agg_type="intake_token",
            agg_id=previous["id"], project_id=project_id,
            actor_type="human", actor_id=events.effective_actor(),
            payload={},
        )
    token = new_id("itk") + secrets.token_hex(12)
    concept_id = (body or {}).get("concept_id")
    events.emit(
        event_type="intake.token_issued", agg_type="intake_token",
        agg_id=new_id("ittk"), project_id=project_id,
        actor_type="human", actor_id=events.effective_actor(),
        payload={"token": token, "concept_id": concept_id},
    )
    return {"token": token, "concept_id": concept_id}


@router.delete("/projects/{project_id}/intake-token")
def revoke_token(project_id: str) -> dict:
    require_project(project_id)
    _require_owner(project_id)
    conn = db.get_conn()
    row = _active_token(conn, project_id)
    if not row:
        raise HTTPException(status_code=404, detail="no active intake token")
    events.emit(
        event_type="intake.token_revoked", agg_type="intake_token",
        agg_id=row["id"], project_id=project_id,
        actor_type="human", actor_id=events.effective_actor(),
        payload={},
    )
    return {"ok": True}


# ---------------------------------------------------------------- public API
class IntakeIn(BaseModel):
    title: str
    priority: str | None = None


@router.post("/intake/{token}")
def submit_intake(token: str, body: IntakeIn) -> dict:
    """No-login landing: the token IS the credential. Field whitelist — title,
    optional priority; anything else the outside world might send is dropped."""
    title = (body.title or "").strip()
    if not title or len(title) > 200:
        raise HTTPException(status_code=422, detail="title is required (≤200 chars)")
    priority = body.priority
    if priority is not None and priority not in PRIORITIES:
        raise HTTPException(status_code=422, detail=f"priority must be one of {PRIORITIES}")

    conn = db.get_conn()
    row = conn.execute(
        "SELECT * FROM intake_tokens WHERE token = ?", (token,)).fetchone()
    if not row or row["revoked_at"] is not None or not secrets.compare_digest(row["token"], token):
        raise HTTPException(status_code=401, detail="invalid intake token")
    project_id = row["project_id"]
    require_project(project_id)  # 404 for unknown project; archived → 409 via guard

    item = create_item(
        project_id=project_id,
        concept_id=row["concept_id"] or "task",
        title=title,
        priority=priority,
        actor_type="intake",
        actor_id="intake",
    )
    return {"ok": True, "item_id": item["id"], "title": item["title"]}
