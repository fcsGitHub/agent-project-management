"""Expense line items (M47-I142, docs/01 §AR.2, OpenProject Budget dual-track
semantics): project cost has two tracks — labor (logged minutes × hourly rate,
I122) and material/unit costs (first-class expense rows: what, when, how much,
which work item). Amounts carry an ISO currency and convert to the base
currency via the I139 manual FX table; the budget stays hour-denominated and
the expense track is shown alongside it, never mixed into it. Pure projection
(expense_entries in drop_projections), soft delete via expense.deleted."""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on

router = APIRouter(tags=["expenses"])

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_CURRENCY = re.compile(r"^[A-Z]{3}$")


# ---------------------------------------------------------------- projectors
@on("expense.recorded")
def _proj_expense_recorded(conn, e):
    p = e.payload
    conn.execute(
        "INSERT INTO expense_entries (id, project_id, description, qty, unit_price,"
        " currency, spent_on, vendor, item_id, deleted_at, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?, NULL, ?, ?)",
        (e.agg_id, e.project_id, p["description"], p["qty"], p["unit_price"],
         p["currency"], p["spent_on"], p.get("vendor"), p.get("item_id"), e.ts, e.ts),
    )


@on("expense.deleted")
def _proj_expense_deleted(conn, e):
    conn.execute(
        "UPDATE expense_entries SET deleted_at = ?, updated_at = ? WHERE id = ?",
        (e.ts, e.ts, e.agg_id))


# ---------------------------------------------------------------- helpers
def _validate(body: "ExpenseIn") -> None:
    if body.qty <= 0:
        raise HTTPException(status_code=422, detail="qty must be positive")
    if body.unit_price < 0:
        raise HTTPException(status_code=422, detail="unit_price must not be negative")
    if not _ISO_CURRENCY.match(body.currency):
        raise HTTPException(status_code=422, detail="currency must be a 3-letter ISO code")
    if not _ISO_DATE.match(body.spent_on or ""):
        raise HTTPException(status_code=422, detail="spent_on must be an ISO date (YYYY-MM-DD)")
    if body.item_id:
        from apm.domains.items import require_item

        require_item(body.item_id)


class ExpenseIn(BaseModel):
    description: str
    qty: float
    unit_price: float
    currency: str
    spent_on: str
    vendor: str | None = None
    item_id: str | None = None


# ---------------------------------------------------------------- CRUD API
@router.post("/projects/{project_id}/expenses")
def record_expense(project_id: str, body: ExpenseIn) -> dict:
    from apm.domains.projects import require_project

    require_project(project_id)
    _validate(body)
    eid = new_id("exp")
    events.emit(
        event_type="expense.recorded", agg_type="expense", agg_id=eid,
        project_id=project_id, actor_type="human", actor_id=events.effective_actor(),
        payload={"description": body.description, "qty": body.qty,
                 "unit_price": body.unit_price, "currency": body.currency.upper(),
                 "spent_on": body.spent_on, "vendor": body.vendor,
                 "item_id": body.item_id,
                 "summary": f"费用行：{body.description}（{body.qty}×{body.unit_price} {body.currency.upper()}）"},
    )
    return {"id": eid, **body.model_dump(), "currency": body.currency.upper()}


@router.get("/projects/{project_id}/expenses")
def list_expenses(project_id: str, item_id: str | None = None) -> dict:
    from apm.domains.projects import require_project

    require_project(project_id)
    sql = ("SELECT * FROM expense_entries WHERE project_id = ? AND deleted_at IS NULL")
    params: list = [project_id]
    if item_id:
        sql += " AND item_id = ?"
        params.append(item_id)
    sql += " ORDER BY spent_on DESC, id"
    rows = db.get_conn().execute(sql, params).fetchall()
    return {"expenses": [dict(r) for r in rows]}


@router.delete("/projects/{project_id}/expenses/{expense_id}")
def delete_expense(project_id: str, expense_id: str) -> dict:
    row = db.get_conn().execute(
        "SELECT * FROM expense_entries WHERE id = ? AND project_id = ? AND deleted_at IS NULL",
        (expense_id, project_id)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"unknown expense '{expense_id}'")
    events.emit(
        event_type="expense.deleted", agg_type="expense", agg_id=expense_id,
        project_id=project_id, actor_type="human", actor_id=events.effective_actor(),
        payload={"description": row["description"]},
    )
    return {"deleted": expense_id}
