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
        " status_group, priority, assignee_type, assignee_id, estimate_hours, custom_fields, created_at,"
        " updated_at, version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
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
            json.dumps(p["custom_fields"], ensure_ascii=False) if p.get("custom_fields") else None,
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
    if "custom_fields" in p:
        sets.append("custom_fields = ?")
        params.append(
            json.dumps(p["custom_fields"], ensure_ascii=False) if p["custom_fields"] else None)
    if sets:
        sets.append("updated_at = ?")
        sets.append("version = version + 1")
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
        "UPDATE items SET assignee_type = ?, assignee_id = ?,"
        " custom_fields = COALESCE(?, custom_fields), updated_at = ?, version = version + 1"
        " WHERE id = ?",
        (p.get("assignee_type"), p.get("assignee_id"),
         json.dumps(p["custom_fields"], ensure_ascii=False) if p.get("custom_fields") else None,
         e.ts, e.agg_id),
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
    return _parse_cf(dict(row)) if row else None


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
    custom_fields: dict | None = None,
    actor_type: str = "human",
    actor_id: str | None = None,
) -> dict:
    onto = project_ontology(project_id)
    _validate_custom_fields(onto, concept_id, custom_fields)
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
            "custom_fields": custom_fields,
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
    return [_parse_cf(_with_assignee_name(dict(r))) for r in rows]


BUCKET_NAMES = {
    "backlog": "待办池",
    "todo": "就绪",
    "in_progress": "进行中",
    "done": "已完成",
    "cancelled": "已取消",
}


def _find_field(onto, field_id: str) -> dict | None:
    """Locate a custom-field declaration across all concepts (first match wins)."""
    for concept in onto.concepts.values():
        for f in concept.fields:
            if f.get("id") == field_id:
                return f
    return None


def _group_key(value) -> str:
    """Canonical column key for one scalar field value (bool → filter literals)."""
    if isinstance(value, bool):
        return "true" if value else "false"  # matches the cf=true/false filter literals
    return str(value)


@router.get("/projects/{project_id}/board")
def get_board(
    project_id: str, feature_id: str | None = None, group_by: str | None = None
) -> dict:
    """Board projection: five lifecycle buckets, optionally re-grouped by a custom
    field (M6-I21: `group_by=field:<id>`, default from board_defaults.group_by)."""
    onto = project_ontology(project_id)
    effective = group_by or onto.board_defaults.get("group_by", "lifecycle")
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
    resp = {
        "project_id": project_id,
        "feature_id": feature_id,
        "buckets": [
            {"id": b, "name": BUCKET_NAMES[b], "items": buckets.get(b, [])} for b in BUCKET_NAMES
        ],
        "columns": columns,
        "group_by": effective,
        "field": None,
        "groups": None,
    }
    if effective == "lifecycle":
        return resp
    if not effective.startswith("field:"):
        raise HTTPException(status_code=422, detail=f"unknown group_by '{effective}' (lifecycle | field:<id>)")
    fid = effective[len("field:") :]
    field = _find_field(onto, fid)
    if not field:
        raise HTTPException(status_code=422, detail=f"field '{fid}' is not declared in ontology")
    # Declared values keep their ontology order (stable columns, even when empty);
    # undeclared keys follow first-seen item order; 未设置 always last. Multiselect
    # values fan out — an item appears once per tag (label-board semantics).
    ordered = [str(v) for v in field.get("values") or []]
    grouped: dict[str, list[dict]] = {}
    none_items: list[dict] = []
    for item in items:
        val = (item.get("custom_fields") or {}).get(fid)
        if val is None or val == []:
            none_items.append(item)
            continue
        for v in val if isinstance(val, list) else [val]:
            key = _group_key(v)
            grouped.setdefault(key, []).append(item)
            if key not in ordered:
                ordered.append(key)
    column_keys = ordered + (["_none"] if none_items else [])
    resp["field"] = {"id": fid, "name": field.get("name", fid), "type": field.get("type", "string")}
    resp["groups"] = [
        {
            "id": k,
            "name": "未设置" if k == "_none" else k,
            "items": (none_items if k == "_none" else grouped.get(k, [])),
        }
        for k in column_keys
    ]
    return resp


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
    custom_fields: dict | None = None


def _ensure_human_assignee(assignee_type: str | None, assignee_id: str | None) -> None:
    """Human assignees must be registered identities (M5-I19). Role assignees are free."""
    if assignee_type == "human" and assignee_id:
        row = db.get_conn().execute(
            "SELECT 1 FROM users WHERE id = ?", (assignee_id,)).fetchone()
        if not row:
            raise HTTPException(
                status_code=422,
                detail=f"unknown user '{assignee_id}' (register via POST /api/users)")


def _parse_cf(item: dict) -> dict:
    if isinstance(item.get("custom_fields"), str):
        try:
            item["custom_fields"] = json.loads(item["custom_fields"])
        except json.JSONDecodeError:
            item["custom_fields"] = {}
    return item


def _with_assignee_name(item: dict) -> dict:
    if item.get("assignee_type") == "human" and item.get("assignee_id"):
        row = db.get_conn().execute(
            "SELECT name FROM users WHERE id = ?", (item["assignee_id"],)).fetchone()
        item["assignee_name"] = row["name"] if row else item["assignee_id"]
    return item


def _validate_custom_fields(onto, concept_id: str, cf: dict) -> None:
    """Custom field values must match the concept's declared fields (M6-I20)."""
    concept = onto.concept(concept_id)
    declared = {f["id"]: f for f in concept.fields}
    for k, v in (cf or {}).items():
        spec = declared.get(k)
        if spec is None:
            raise HTTPException(status_code=422,
                                detail=f"custom field '{k}' not declared on concept '{concept_id}'")
        ftype = spec.get("type")
        ok = {
            "string": lambda v: isinstance(v, str),
            "date": lambda v: isinstance(v, str) and len(v) >= 8,
            "ref": lambda v: isinstance(v, str),
            "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            "boolean": lambda v: isinstance(v, bool),
            "enum": lambda v: v in (spec.get("values") or []),
            "multiselect": lambda v: isinstance(v, list) and bool(v)
            and all(x in (spec.get("values") or []) for x in v),
        }[ftype]
        if not ok(v):
            raise HTTPException(
                status_code=422,
                detail=f"custom field '{k}' (type {ftype}) invalid value: {v!r}")


class ItemPatch(BaseModel):
    title: str | None = None
    priority: str | None = None
    estimate_hours: float | None = None
    status: str | None = None
    assignee_type: str | None = None
    assignee_id: str | None = None
    feature_id: str | None = None
    custom_fields: dict | None = None


class RelationIn(BaseModel):
    to_item: str
    relation_type: str


@router.post("/projects/{project_id}/items")
def post_item(project_id: str, body: ItemIn) -> dict:
    _ensure_human_assignee(body.assignee_type, body.assignee_id)
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
        custom_fields=body.custom_fields,
    )


@router.get("/projects/{project_id}/items")
def get_items(
    project_id: str,
    feature_id: str | None = None,
    concept_id: str | None = None,
    status_group: str | None = None,
    assignee_id: str | None = None,
    priority: str | None = None,
    cf: str | None = None,
) -> dict:
    items = list_items(
        project_id=project_id,
        feature_id=feature_id,
        concept_id=concept_id,
        status_group=status_group,
        assignee_id=assignee_id,
        priority=priority,
    )
    if cf:  # "field:value" — multiselect 值为包含匹配（M6-I20）
        field, _, expected = cf.partition(":")
        def _hit(it):
            got = (it.get("custom_fields") or {}).get(field)
            if isinstance(got, list):
                return expected in got
            return got == expected or (isinstance(got, bool) and expected in ("true", "false")
                                       and got == (expected == "true"))
        items = [it for it in items if _hit(it)]
    return {"items": items}


@router.get("/items/{item_id}")
def get_item_detail(item_id: str) -> dict:
    item = require_item(item_id)
    rels = db.get_conn().execute(
        "SELECT * FROM item_relations WHERE from_item = ? OR to_item = ?",
        (item_id, item_id),
    ).fetchall()
    item["relations"] = [dict(r) for r in rels]
    return _parse_cf(_with_assignee_name(item))


@router.patch("/items/{item_id}")
def patch_item(item_id: str, body: ItemPatch) -> dict:
    item = require_item(item_id)
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    if "custom_fields" in changes:
        onto = project_ontology(item["project_id"])
        _validate_custom_fields(onto, item["concept_id"], changes["custom_fields"])
    if "status" in changes:
        new_status = changes.pop("status")
        item = change_status(item, new_status)
    if "assignee_type" in changes or "assignee_id" in changes:
        _ensure_human_assignee(
            changes.get("assignee_type", item["assignee_type"]),
            changes.get("assignee_id", item["assignee_id"]))
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
