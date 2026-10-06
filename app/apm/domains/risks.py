"""Risk register (M43-I131, docs/01 §AP.1, PMBOK probability×impact matrix +
OpenProject's native risk module): a risk is a first-class register entry —
probability (1-3) × impact (1-3) yields the score that sorts the page, every
risk carries a response plan, an owner and a review date, and the lifecycle
runs open → mitigated → closed. Pure projection (risks in drop_projections),
so rebuild reproduces the register from the event stream."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on

router = APIRouter(tags=["risks"])

LEVELS = {1: "low", 2: "medium", 3: "high"}
LIFECYCLE = {"open": {"mitigated"}, "mitigated": {"closed"}, "closed": set()}


# ---------------------------------------------------------------- projectors
@on("risk.created")
def _proj_risk_created(conn, e):
    p = e.payload
    conn.execute(
        "INSERT INTO risks (id, project_id, title, probability, impact, response,"
        " owner, review_date, related_item_id, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?, 'open', ?, ?)",
        (e.agg_id, e.project_id, p["title"], p["probability"], p["impact"],
         p.get("response"), p.get("owner"), p.get("review_date"),
         p.get("related_item_id"), e.ts, e.ts),
    )


@on("risk.updated")
def _proj_risk_updated(conn, e):
    p = e.payload
    sets, params = [], []
    for key in ("title", "probability", "impact", "response", "owner",
                "review_date", "related_item_id", "status"):
        if key in p:
            sets.append(f"{key} = ?")
            params.append(p[key])
    if sets:
        sets.append("updated_at = ?")
        params.extend([e.ts, e.agg_id])
        conn.execute(f"UPDATE risks SET {', '.join(sets)} WHERE id = ?", params)


@on("risk.closed")
def _proj_risk_closed(conn, e):
    conn.execute(
        "UPDATE risks SET status = 'closed', updated_at = ? WHERE id = ?",
        (e.ts, e.agg_id))


# ---------------------------------------------------------------- helpers
def get_risk(risk_id: str) -> dict | None:
    row = db.get_conn().execute(
        "SELECT * FROM risks WHERE id = ?", (risk_id,)).fetchone()
    return dict(row) if row else None


def require_risk(risk_id: str) -> dict:
    r = get_risk(risk_id)
    if r is None:
        raise HTTPException(status_code=404, detail=f"unknown risk '{risk_id}'")
    return r


def _validate_levels(probability: int, impact: int) -> None:
    if probability not in LEVELS or impact not in LEVELS:
        raise HTTPException(status_code=422, detail="probability/impact must be 1 (low), 2 (medium) or 3 (high)")


def _require_item(item_id: str) -> dict:
    from apm.domains.items import require_item
    return require_item(item_id)


class RiskIn(BaseModel):
    title: str
    probability: int
    impact: int
    response: str | None = None
    owner: str | None = None
    review_date: str | None = None
    related_item_id: str | None = None


class RiskPatch(BaseModel):
    title: str | None = None
    probability: int | None = None
    impact: int | None = None
    response: str | None = None
    owner: str | None = None
    review_date: str | None = None
    related_item_id: str | None = None
    status: str | None = None  # open | mitigated | closed


# ---------------------------------------------------------------- endpoints
@router.get("/projects/{project_id}/risks")
def list_risks(project_id: str) -> dict:
    rows = db.get_conn().execute(
        "SELECT * FROM risks WHERE project_id = ? AND status != 'closed'"
        " ORDER BY probability * impact DESC, created_at", (project_id,)).fetchall()
    return {"risks": [dict(r) | {"score": r["probability"] * r["impact"]} for r in rows]}


@router.post("/projects/{project_id}/risks")
def create_risk(project_id: str, body: RiskIn) -> dict:
    _validate_levels(body.probability, body.impact)
    if body.related_item_id:
        item = _require_item(body.related_item_id)
        # M114-I339: 关联工作项必须同项目（_validate_milestone 同惯例）
        if item["project_id"] != project_id:
            raise HTTPException(
                status_code=422,
                detail=f"item '{body.related_item_id}' belongs to another project")
    rid = new_id("rk")
    events.emit(
        event_type="risk.created", agg_type="risk", agg_id=rid,
        project_id=project_id, actor_type="human", actor_id=events.effective_actor(),
        payload={"title": body.title, "probability": body.probability,
                 "impact": body.impact, "response": body.response,
                 "owner": body.owner, "review_date": body.review_date,
                 "related_item_id": body.related_item_id},
    )
    return {"id": rid, **body.model_dump(), "score": body.probability * body.impact,
            "status": "open"}


@router.patch("/risks/{risk_id}")
def patch_risk(risk_id: str, body: RiskPatch) -> dict:
    r = require_risk(risk_id)
    from apm.domains.members import require_project_write
    require_project_write(r["project_id"])  # M80-I240
    if r["status"] == "closed":
        raise HTTPException(status_code=409, detail="risk is closed")
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    if not changes:
        return r
    if "status" in changes:
        target = changes["status"]
        if target not in ("open", "mitigated", "closed"):
            raise HTTPException(status_code=422, detail="unknown status")
        if target not in LIFECYCLE[r["status"]]:
            raise HTTPException(
                status_code=422, detail=f"cannot move {r['status']} → {target}")
    if ("probability" in changes or "impact" in changes):
        _validate_levels(changes.get("probability", r["probability"]),
                         changes.get("impact", r["impact"]))
    if "related_item_id" in changes and changes["related_item_id"]:
        item = _require_item(changes["related_item_id"])
        # M114-I339: 关联工作项必须同项目（create 同款）
        if item["project_id"] != r["project_id"]:
            raise HTTPException(
                status_code=422,
                detail=f"item '{changes['related_item_id']}' belongs to another project")
    events.emit(
        event_type="risk.updated", agg_type="risk", agg_id=risk_id,
        project_id=r["project_id"], actor_type="human", actor_id=events.effective_actor(),
        payload=changes,
    )
    return {**r, **changes}


@router.post("/risks/{risk_id}/close")
def close_risk(risk_id: str) -> dict:
    r = require_risk(risk_id)
    from apm.domains.members import require_project_write
    require_project_write(r["project_id"])  # M80-I240
    events.emit(
        event_type="risk.closed", agg_type="risk", agg_id=risk_id,
        project_id=r["project_id"], actor_type="human", actor_id=events.effective_actor(),
        payload={"title": r["title"]},
    )
    return {"closed": risk_id}
