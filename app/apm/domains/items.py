"""Work item domain: ontology-driven types, five-bucket state machine, relations."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on
from apm.domains.ontology import KERNEL_RELATIONS, OntologyError, load_ontology

router = APIRouter(tags=["items"])


# ------------------------------------------------------------ projections
@on("item.created")
def _proj_item_created(conn, e):
    p = e.payload
    conn.execute(
        "INSERT INTO items (id, project_id, feature_id, parent_id, concept_id, title, status,"
        " status_group, priority, assignee_type, assignee_id, estimate_hours, created_at,"
        " updated_at, version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
        (
            e.agg_id,
            e.project_id,
            p.get("feature_id"),
            p.get("parent_id"),
            p.get("concept_id"),
            p.get("title", ""),
            p.get("status", ""),
            p.get("status_group", ""),
            p.get("priority"),
            p.get("assignee_type"),
            p.get("assignee_id"),
            p.get("estimate_hours"),
            e.ts,
            e.ts,
        ),
    )


@on("item.updated")
def _proj_item_updated(conn, e):
    p = e.payload
    sets, params = [], []
    for key in ("title", "priority", "estimate_hours", "milestone_id", "feature_id"):
        if key in p:
            sets.append(f"{key} = ?")
            params.append(p[key])
    if sets:
        sets.append("updated_at = ?", "version = version + 1")
        params.extend([e.ts, e.agg_id])
        conn.execute(f"UPDATE items SET {', '.join(sets)} WHERE id = ?", params)


@on("item.status_changed")
def _proj_item_status(conn, e):
    p = e.payload
    conn.execute(
        "UPDATE items SET status = ?, status_group = ?, updated_at = ?, version = version + 1"
        " WHERE id = ?",
        (p["status"], p["status_group"], e.ts, e.agg_id),
    )


@on("item.assigned")
def _proj_item_assigned(conn, e):
    p = e.payload
    conn.execute(
        "UPDATE items SET assignee_type = ?, assignee_id = ?, updated_at = ?, version = version + 1"
        " WHERE id = ?",
        (p.get("assignee_type"), p.get("assignee_id"), e.ts, e.agg_id),
    )


@on("item.related")
def _proj_item_related(conn, e):
    p = e.payload
    conn.execute(
        "INSERT INTO item_relations (id, project_id, from_item, to_item, relation_type, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (new_id("rel"), e.project_id, p["from_item"], p["to_item"], p["relation_type"], e.ts),
    )


# ---------------------------------------------------------------- helpers
def get_item(item_id: str) -> dict | None:
    row = db.get_conn().execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return dict(row) if row else None


def require_item(item_id: str) -> dict:
    item = get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"item {item_id} not found")
    return item


def project_ontology(project_id: str):
    from apm.domains.projects import require_project

    project = require_project(project_id)
    return load_ontology(project["ontology"])


def create_item(
    *,
    project_id: str,
    concept_id: str,
    title: str,
    feature_id: str | None = None,
    parent_id: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    assignee_type: str | None = None,
    assignee_id: str | None = None,
    estimate_hours: float | None = None,
    actor_type: str = "human",
    actor_id: str = "u_admin",
) -> dict:
    onto = project_ontology(project_id)
    try:
        concept = onto.concept(concept_id)
        status = status or concept.initial_status()
        group = onto.validate_item_status(concept_id, status)
    except OntologyError as e:
        raise HTTPException(status_code=422, detail=str(e))
    iid = new_id("i")
    events.emit(
        event_type="item.created",
        agg_type="item",
        agg_id=iid,
        project_id=project_id,
        actor_type=actor_type,
        actor_id=actor_id,
        payload={
            "concept_id": concept_id,
            "title": title,
            "feature_id": feature_id,
            "parent_id": parent_id,
            "status": status,
            "status_group": group,
            "priority": priority,
            "assignee_type": assignee_type,
            "assignee_id": assignee_id,
            "estimate_hours": estimate_hours,
        },
    )
    return get_item(iid)  # type: ignore[return-value]


def change_status(item: dict, new_status: str, actor_type="human", actor_id="u_admin") -> dict:
    onto = project_ontology(item["project_id"])
    try:
        group = onto.validate_item_status(item["concept_id"], new_status)
    except OntologyError as e:
        raise HTTPException(status_code=422, detail=str(e))
    events.emit(
        event_type="item.status_changed",
        agg_type="item",
        agg_id=item["id"],
        project_id=item["project_id"],
        actor_type=actor_type,
        actor_id=actor_id,
        payload={"from": item["status"], "status": new_status, "status_group": group},
    )
    return get_item(item["id"])  # type: ignore[return-value]


def list_items(
    *,
    project_id: str | None = None,
    feature_id: str | None = None,
    concept_id: str | None = None,
    status_group: str | None = None,
    status: str | None = None,
    assignee_id: str | None = None,
    priority: str | None = None,
) -> list[dict]:
    where, params = ["1=1"], []
    if project_id:
        where.append("project_id = ?")
        params.append(project_id)
    if feature_id:
        where.append("feature_id = ?")
        params.append(feature_id)
    if concept_id:
        where.append("concept_id = ?")
        params.append(concept_id)
    if status_group:
        where.append("status_group = ?")
        params.append(status_group)
    if status:
        where.append("status = ?")
        params.append(status)
    if assignee_id:
        where.append("assignee_id = ?")
        params.append(assignee_id)
    if priority:
        where.append("priority = ?")
        params.append(priority)
    rows = db.get_conn().execute(
        f"SELECT * FROM items WHERE {' AND '.join(where)} ORDER BY created_at", params
    ).fetchall()
    return [dict(r) for r in rows]


BUCKET_NAMES = {
    "backlog": "待办池",
    "todo": "就绪",
    "in_progress": "进行中",
    "done": "已完成",
    "cancelled": "已取消",
}


@router.get("/projects/{project_id}/board")
def get_board(project_id: str, feature_id: str | None = None) -> dict:
    """Board projection: ontology lifecycle states grouped into five buckets."""
    onto = project_ontology(project_id)
    items = list_items(project_id=project_id, feature_id=feature_id)
    buckets: dict[str, list[dict]] = {b: [] for b in BUCKET_NAMES}
    for item in items:
        buckets.setdefault(item["status_group"], []).append(item)
    columns = []
    for concept in onto.concepts.values():
        for s in concept.states:
            columns.append(
                {
                    "id": f"{concept.id}:{s['id']}",
                    "concept_id": concept.id,
                    "concept_name": concept.name,
                    "status": s["id"],
                    "name": s.get("name", s["id"]),
                    "group": s["group"],
                }
            )
    return {
        "project_id": project_id,
        "feature_id": feature_id,
        "buckets": [
            {"id": b, "name": BUCKET_NAMES[b], "items": buckets.get(b, [])} for b in BUCKET_NAMES
        ],
        "columns": columns,
        "group_by": onto.board_defaults.get("group_by", "lifecycle"),
    }


# ------------------------------------------------------------------ models
class ItemIn(BaseModel):
    concept_id: str
    title: str
    feature_id: str | None = None
    parent_id: str | None = None
    status: str | None = None
    priority: str | None = None
    assignee_type: str | None = None
    assignee_id: str | None = None
    estimate_hours: float | None = None


class ItemPatch(BaseModel):
    title: str | None = None
    priority: str | None = None
    estimate_hours: float | None = None
    status: str | None = None
    assignee_type: str | None = None
    assignee_id: str | None = None
    feature_id: str | None = None


class RelationIn(BaseModel):
    to_item: str
    relation_type: str


@router.post("/projects/{project_id}/items")
def post_item(project_id: str, body: ItemIn) -> dict:
    return create_item(
        project_id=project_id,
        concept_id=body.concept_id,
        title=body.title,
        feature_id=body.feature_id,
        parent_id=body.parent_id,
        status=body.status,
        priority=body.priority,
        assignee_type=body.assignee_type,
        assignee_id=body.assignee_id,
        estimate_hours=body.estimate_hours,
    )


@router.get("/projects/{project_id}/items")
def get_items(
    project_id: str,
    feature_id: str | None = None,
    concept_id: str | None = None,
    status_group: str | None = None,
    assignee_id: str | None = None,
    priority: str | None = None,
) -> dict:
    return {
        "items": list_items(
            project_id=project_id,
            feature_id=feature_id,
            concept_id=concept_id,
            status_group=status_group,
            assignee_id=assignee_id,
            priority=priority,
        )
    }


@router.get("/items/{item_id}")
def get_item_detail(item_id: str) -> dict:
    item = require_item(item_id)
    rels = db.get_conn().execute(
        "SELECT * FROM item_relations WHERE from_item = ? OR to_item = ?",
        (item_id, item_id),
    ).fetchall()
    item["relations"] = [dict(r) for r in rels]
    return item


@router.patch("/items/{item_id}")
def patch_item(item_id: str, body: ItemPatch) -> dict:
    item = require_item(item_id)
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    if "status" in changes:
        new_status = changes.pop("status")
        item = change_status(item, new_status)
    if "assignee_type" in changes or "assignee_id" in changes:
        events.emit(
            event_type="item.assigned",
            agg_type="item",
            agg_id=item_id,
            project_id=item["project_id"],
            payload={
                "assignee_type": changes.pop("assignee_type", item["assignee_type"]),
                "assignee_id": changes.pop("assignee_id", item["assignee_id"]),
            },
        )
    if changes:
        events.emit(
            event_type="item.updated",
            agg_type="item",
            agg_id=item_id,
            project_id=item["project_id"],
            payload=changes,
        )
    return get_item(item_id)  # type: ignore[return-value]


@router.post("/items/{item_id}/relations")
def post_relation(item_id: str, body: RelationIn) -> dict:
    item = require_item(item_id)
    target = require_item(body.to_item)
    onto = project_ontology(item["project_id"])
    valid = set(onto.relation_ids())
    if body.relation_type not in valid:
        raise HTTPException(
            status_code=422,
            detail=f"relation '{body.relation_type}' not allowed (kernel: {KERNEL_RELATIONS})",
        )
    if item["project_id"] != target["project_id"]:
        raise HTTPException(status_code=422, detail="cross-project relations not supported")
    events.emit(
        event_type="item.related",
        agg_type="item",
        agg_id=item_id,
        project_id=item["project_id"],
        payload={"from_item": item_id, "to_item": body.to_item, "relation_type": body.relation_type},
    )
    return get_item_detail(item_id)
