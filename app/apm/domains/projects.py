"""Project domain: CRUD with ontology template instantiation + phase graph."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm import config
from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on
from apm.domains.ontology import OntologyError, load_ontology, require_valid

router = APIRouter(tags=["projects"])

# Archived projects are read-only (M22-I69, OpenProject semantics): every live
# emit targeting them is vetoed except the audit/reopen/clone bookkeeping
# events. Historical events replay untouched (rebuild bypasses emit).
_ARCHIVED_WRITABLE = {"project.reopened", "project.cloned", "access.denied"}


def _archive_guard(event_type: str, project_id: str) -> None:
    if not project_id or event_type in _ARCHIVED_WRITABLE:
        return
    row = db.get_conn().execute(
        "SELECT status FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row and row["status"] == "archived":
        raise HTTPException(status_code=409, detail="project is archived (read-only)")
    if row and row["status"] == "completed":
        # I132: a delivered project is frozen the same way — /reopen revives it
        raise HTTPException(status_code=409, detail="project is completed (reopen to continue)")


events.add_emit_guard(_archive_guard)


# ------------------------------------------------------------ projections
@on("project.created")
def _proj_project_created(conn, e):
    p = e.payload
    conn.execute(
        "INSERT INTO projects (id, name, description, ontology, template, status, charter,"
        " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            e.agg_id,
            p.get("name", ""),
            p.get("description"),
            p.get("ontology", ""),
            p.get("template", p.get("ontology", "")),
            "active",
            p.get("charter"),
            e.ts,
            e.ts,
        ),
    )


@on("project.field_disabled")
def _proj_field_disabled(conn, e):
    _set_field_state(conn, e.agg_id, e.payload["field_id"], active=False)


@on("project.field_enabled")
def _proj_field_enabled(conn, e):
    _set_field_state(conn, e.agg_id, e.payload["field_id"], active=True)


def _set_field_state(conn, project_id: str, field_id: str, *, active: bool) -> None:
    """field_overrides = JSON list of deactivated field ids (M7-I25)."""
    row = conn.execute("SELECT field_overrides FROM projects WHERE id = ?", (project_id,)).fetchone()
    cur = set(json.loads(row[0])) if row and row[0] else set()
    if active:
        cur.discard(field_id)
    else:
        cur.add(field_id)
    conn.execute("UPDATE projects SET field_overrides = ? WHERE id = ?",
                 (json.dumps(sorted(cur)) if cur else None, project_id))


@on("project.updated")
def _proj_project_updated(conn, e):
    p = e.payload
    sets, params = [], []
    for key in ("name", "description", "status", "charter", "budget_hours"):
        if key in p:
            sets.append(f"{key} = ?")
            params.append(p[key])
    if sets:
        sets.append("updated_at = ?")
        params.append(e.ts)
        params.append(e.agg_id)
        conn.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id = ?", params)


@on("project.reopened")
def _proj_project_reopened(conn, e):
    conn.execute("UPDATE projects SET status = 'active', updated_at = ? WHERE id = ?",
                 (e.ts, e.agg_id))


@on("project.completed")
def _proj_project_completed(conn, e):
    conn.execute("UPDATE projects SET status = 'completed', updated_at = ? WHERE id = ?",
                 (e.ts, e.agg_id))


# ---------------------------------------------------------------- helpers
def get_project(project_id: str) -> dict | None:
    row = db.get_conn().execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        return None
    p = dict(row)
    p["disabled_fields"] = json.loads(p.pop("field_overrides") or "[]")
    return p


def disabled_fields(project_id: str) -> set[str]:
    """Project-deactivated custom fields (OpenProject-style per-project activation,
    M7-I25). Absent override = every declared ontology field is active."""
    p = get_project(project_id)
    return set(p["disabled_fields"]) if p else set()


def require_project(project_id: str) -> dict:
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail=f"project {project_id} not found")
    return p


def initial_charter(name: str, requirement: str, ontology_name: str) -> str:
    onto = load_ontology(ontology_name)
    concepts = "\n".join(
        f"- {c.icon} {c.name}（{cid}）：状态 {' → '.join(s['id'] for s in c.states)}"
        for cid, c in onto.concepts.items()
    )
    return (
        f"# 项目宪章：{name}\n\n"
        f"## 目标\n{requirement or '（待补充）'}\n\n"
        f"## 边界与约束\n- 单人开发，Agent 执行、人审批\n\n"
        f"## 本体概念表（{onto.display_name}）\n{concepts}\n"
    )


def apply_project_template(project_id: str, ontology_name: str, requirement: str) -> dict:
    """Instantiate ontology defaults: first feature + drafting conversation +
    content repo. Extended per-iteration; returns created refs."""
    from apm.domains.features import create_feature

    feature = create_feature(
        project_id=project_id, title="MVP", brief=requirement or None, sort_order=0
    )
    created = {"feature_id": feature["id"]}

    # Conversation bootstrap lands with the conversation domain (I3).
    try:
        from apm.domains.conversations import create_conversation

        conv = create_conversation(
            project_id=project_id,
            feature_id=feature["id"],
            kind="drafting",
            title="PRD 起草",
            instruction=f"基于以下需求起草 PRD：{requirement_text(requirement)}",
            actor_type="system",
        )
        created["conversation_id"] = conv["id"]
    except ImportError:
        pass

    # Content repo bootstrap lands with the content domain (I4).
    try:
        from apm.content.gitrepo import init_project_repo

        init_project_repo(project_id, charter=initial_charter(name_of(project_id), requirement, ontology_name), ontology_name=ontology_name)
        from apm.content.prompts import seed_role_prompts

        seed_role_prompts(project_id)
        created["content_repo"] = True
    except ImportError:
        pass
    return created


def requirement_text(requirement: str | None) -> str:
    return (requirement or "（待补充一句话需求）").strip()


def name_of(project_id: str) -> str:
    p = get_project(project_id)
    return p["name"] if p else project_id


# ------------------------------------------------------------------ models
class ProjectIn(BaseModel):
    name: str
    description: str | None = None
    ontology: str = "software-dev"
    requirement: str | None = None


class ProjectPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    charter: str | None = None
    budget_hours: float | None = None  # I122: labor budget in hours


@router.post("/projects")
def post_project(body: ProjectIn) -> dict:
    try:
        onto = require_valid(body.ontology)
    except OntologyError as e:
        raise HTTPException(status_code=422, detail=str(e))
    pid = new_id("p")
    charter = initial_charter(body.name, body.requirement or "", body.ontology)
    events.emit(
        event_type="project.created",
        agg_type="project",
        agg_id=pid,
        project_id=pid,
        actor_id=events.effective_actor(),
        payload={
            "name": body.name,
            "description": body.description,
            "ontology": body.ontology,
            "template": body.ontology,
            "charter": charter,
            "requirement": body.requirement,
        },
    )
    # Creator becomes owner (M8-I27, Gitea-style bootstrap).
    events.emit(
        event_type="project.member_added",
        agg_type="project",
        agg_id=pid,
        project_id=pid,
        actor_id=events.effective_actor(),
        payload={"user_id": events.effective_actor(), "role": "owner"},
    )
    created = apply_project_template(pid, body.ontology, body.requirement or "")
    events.emit(
        event_type="project.template_applied",
        agg_type="project",
        agg_id=pid,
        project_id=pid,
        actor_type="system",
        payload={"ontology": onto.name, "created": created, "phases": [p["id"] for p in onto.phases]},
    )
    project = get_project(pid)
    project["bootstrap"] = created
    return project


@router.get("/projects")
def list_projects(include_archived: bool = False) -> dict:
    conn = db.get_conn()
    if include_archived:
        rows = conn.execute("SELECT * FROM projects ORDER BY created_at").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM projects WHERE status != 'archived' ORDER BY created_at"
        ).fetchall()
    groups: dict[str, dict] = {}
    for r in conn.execute(
        "SELECT project_id, status_group, COUNT(*) c FROM items GROUP BY project_id, status_group"
    ).fetchall():
        groups.setdefault(r["project_id"], {})[r["status_group"]] = r["c"]
    gates = {
        r["project_id"]: r["c"]
        for r in conn.execute(
            "SELECT project_id, COUNT(*) c FROM approvals WHERE status = 'pending' GROUP BY project_id"
        ).fetchall()
    }
    projects = []
    for r in rows:
        p = dict(r)
        p["item_counts"] = {**{b: 0 for b in ("backlog", "todo", "in_progress", "done", "cancelled")},
                            **groups.get(p["id"], {})}
        p["gates_pending"] = gates.get(p["id"], 0)
        projects.append(p)
    return {"projects": projects}


@router.get("/projects/{project_id}")
def get_project_detail(project_id: str) -> dict:
    project = require_project(project_id)
    rows = db.get_conn().execute(
        "SELECT * FROM features WHERE project_id = ? AND status != 'archived'"
        " ORDER BY sort_order, created_at",
        (project_id,),
    ).fetchall()
    project["features"] = [dict(r) for r in rows]
    counts = {"backlog": 0, "todo": 0, "in_progress": 0, "done": 0, "cancelled": 0}
    for r in db.get_conn().execute(
        "SELECT status_group, COUNT(*) c FROM items WHERE project_id = ? GROUP BY status_group",
        (project_id,),
    ).fetchall():
        counts[r["status_group"]] = r["c"]
    project["item_counts"] = counts
    return project


@router.patch("/projects/{project_id}")
def patch_project(project_id: str, body: ProjectPatch) -> dict:
    project = require_project(project_id)
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    if not changes:
        return project
    events.emit(
        event_type="project.updated",
        agg_type="project",
        agg_id=project_id,
        project_id=project_id,
        payload=changes,
    )
    return get_project(project_id)  # type: ignore[return-value]


@router.post("/projects/{project_id}/archive")
def archive_project(project_id: str) -> dict:
    require_project(project_id)
    events.emit(
        event_type="project.updated",
        agg_type="project",
        agg_id=project_id,
        project_id=project_id,
        payload={"status": "archived"},
    )
    return get_project(project_id)  # type: ignore[return-value]


@router.post("/projects/{project_id}/reopen")
def reopen_project(project_id: str) -> dict:
    """Unarchive (M22-I69): back to active — the write guard whitelist allows
    the dedicated project.reopened event even while still archived."""
    require_project(project_id)
    events.emit(
        event_type="project.reopened",
        agg_type="project",
        agg_id=project_id,
        project_id=project_id,
        payload={},
    )
    return get_project(project_id)  # type: ignore[return-value]


# ---------------------------------------------------- closure (I132)
@router.get("/projects/{project_id}/closure-checklist")
def closure_checklist(project_id: str) -> dict:
    """M43-I132 (docs/01 §AP.2, PMBOK Closing Process Group): closure is a
    checkable list, not a shrug — five projections must all be green before
    the project may be marked completed. Pure projection, zero new tables."""
    conn = db.get_conn()
    require_project(project_id)

    def count(sql: str) -> int:
        return conn.execute(sql, (project_id,)).fetchone()["c"]

    checks = [
        {"key": "active_items", "label": "无未完成工作项",
         "ok": count("SELECT COUNT(*) AS c FROM items WHERE project_id = ?"
                     " AND status_group NOT IN ('done','cancelled') AND archived_at IS NULL") == 0},
        {"key": "pending_approvals", "label": "无待决审批",
         "ok": count("SELECT COUNT(*) AS c FROM approvals WHERE project_id = ?"
                     " AND status = 'pending'") == 0},
        {"key": "unapproved_timesheets", "label": "无待审工时单",
         "ok": count("SELECT COUNT(*) AS c FROM timesheets WHERE project_id = ?"
                     " AND status = 'submitted'") == 0},
        {"key": "open_risks", "label": "无未缓解风险",
         "ok": count("SELECT COUNT(*) AS c FROM risks WHERE project_id = ?"
                     " AND status = 'open'") == 0},
        {"key": "pending_milestones", "label": "无未达成里程碑",
         "ok": count("SELECT COUNT(*) AS c FROM milestones WHERE project_id = ?"
                     " AND status IN ('planned','in_progress')") == 0},
    ]
    all_green = all(c["ok"] for c in checks)
    return {"project_id": project_id, "checks": checks, "all_green": all_green}


@router.post("/projects/{project_id}/complete")
def complete_project(project_id: str) -> dict:
    """Mark the project delivered — allowed only when the closure checklist is
    fully green (409 with the failing items otherwise). completed is a distinct
    terminal-ish status (frozen like archived, /reopen revives)."""
    checklist = closure_checklist(project_id)
    failing = [c for c in checklist["checks"] if not c["ok"]]
    if failing:
        raise HTTPException(status_code=409, detail={
            "message": "closure checklist has failing items",
            "items": [{"key": c["key"], "label": c["label"]} for c in failing]})
    events.emit(
        event_type="project.completed",
        agg_type="project",
        agg_id=project_id,
        project_id=project_id,
        actor_type="human",
        actor_id=events.effective_actor(),
        payload={"completed_at": events.utcnow()},
    )
    return get_project(project_id)  # type: ignore[return-value]


class FieldActivationIn(BaseModel):
    field_id: str
    active: bool


@router.patch("/projects/{project_id}/fields")
def patch_project_fields(project_id: str, body: FieldActivationIn) -> dict:
    """Per-project custom-field activation (M7-I25, OpenProject-style: ontology
    declares, the project activates/deactivates)."""
    p = require_project(project_id)
    onto = load_ontology(p["ontology"])
    declared = {f["id"] for c in onto.concepts.values() for f in c.fields}
    if body.field_id not in declared:
        raise HTTPException(status_code=422,
                            detail=f"field '{body.field_id}' is not declared in ontology '{onto.name}'")
    events.emit(
        event_type="project.field_enabled" if body.active else "project.field_disabled",
        agg_type="project",
        agg_id=project_id,
        project_id=project_id,
        payload={"field_id": body.field_id},
    )
    return get_project(project_id)  # type: ignore[return-value]


@router.get("/projects/{project_id}/ontology")
def get_project_ontology(project_id: str) -> dict:
    project = require_project(project_id)
    onto = load_ontology(project["ontology"])
    d = onto.to_dict()
    d["project_id"] = project_id
    d["git_path"] = "ontology/ontology.yaml"
    return d


@router.get("/projects/{project_id}/graph")
def get_project_graph(project_id: str) -> dict:
    """Phase graph (from ontology) + task nodes (items) + relation edges."""
    project = require_project(project_id)
    onto = load_ontology(project["ontology"])
    nodes: list[dict] = []
    edges: list[dict] = []
    prev_phase = None
    for p in onto.phases:
        nodes.append(
            {
                "id": f"phase:{p['id']}",
                "kind": "phase",
                "label": p.get("name", p["id"]),
                "gate": p.get("gate"),
            }
        )
        if p.get("gate"):
            nodes.append(
                {
                    "id": f"gate:{p['gate']}",
                    "kind": "gate",
                    "label": onto.gate_label(p["gate"]),
                    "phase": p["id"],
                }
            )
            edges.append({"source": f"phase:{p['id']}", "target": f"gate:{p['gate']}", "kind": "sequence"})
        if prev_phase:
            prev_gate = onto.gate_of_phase(prev_phase)
            src = f"gate:{prev_gate}" if prev_gate else f"phase:{prev_phase}"
            edges.append({"source": src, "target": f"phase:{p['id']}", "kind": "sequence"})
        prev_phase = p["id"]

    for item in db.get_conn().execute(
        "SELECT * FROM items WHERE project_id = ?", (project_id,)
    ).fetchall():
        concept = onto.concepts.get(item["concept_id"])
        phase = concept.default_phase if concept else None
        nodes.append(
            {
                "id": item["id"],
                "kind": "task",
                "label": item["title"],
                "concept_id": item["concept_id"],
                "status": item["status"],
                "status_group": item["status_group"],
                "assignee_type": item["assignee_type"],
                "assignee_id": item["assignee_id"],
                "phase": phase,
            }
        )
        if phase:
            edges.append(
                {"source": f"phase:{phase}", "target": item["id"], "kind": "contains"}
            )
    for rel in db.get_conn().execute(
        "SELECT * FROM item_relations WHERE project_id = ?", (project_id,)
    ).fetchall():
        edges.append(
            {
                "source": rel["from_item"],
                "target": rel["to_item"],
                "kind": rel["relation_type"],
            }
        )
    # M47-I143: 跨项目 to_item 不在本项目节点集——补「外部依赖」占位节点。
    # 对当前用户不可读的项目只给 🔒 占位（不泄露对方标题）；可读则显示真实
    # 标题与来源项目名。
    from apm.core.events import effective_actor as _actor
    from apm.domains.members import is_instance_admin, member_role

    known = {n["id"] for n in nodes}
    me = _actor()
    admin = is_instance_admin(me)
    for rel in db.get_conn().execute(
        "SELECT to_item AS iid FROM item_relations WHERE project_id = ?",
        (project_id,)).fetchall():
        ext = rel["iid"]
        if ext in known:
            continue
        row = db.get_conn().execute(
            "SELECT title, project_id FROM items WHERE id = ?", (ext,)).fetchone()
        if row is None:
            continue
        readable = admin or member_role(row["project_id"], me)
        proj = db.get_conn().execute(
            "SELECT name FROM projects WHERE id = ?", (row["project_id"],)).fetchone()
        nodes.append({
            "id": ext, "kind": "task",
            "label": row["title"] if readable else "🔒 外部依赖",
            "concept_id": "external",
            "status": "external", "status_group": "external",
            "external": True,
            "external_project_id": row["project_id"] if readable else None,
            "external_project_name": (proj["name"] if proj else None) if readable else None,
        })
        known.add(ext)
    return {"project_id": project_id, "nodes": nodes, "edges": edges}


# ------------------------------------------------------------------ clone (I69)
class CloneIn(BaseModel):
    name: str
    structure: bool = True
    items: bool = True
    milestones: bool = True


@router.post("/projects/{project_id}/clone")
def clone_project(project_id: str, body: CloneIn) -> dict:
    """Copy a project's skeleton into a new one (M22-I69, Redmine
    copy-at-creation semantics). Members/assignees are deliberately NOT
    copied — membership is a grant, cloning must not widen it. Every entity
    is created through its normal emit path, so the clone is fully
    event-sourced and the write guard's whitelist admits project.cloned."""
    src = require_project(project_id)
    new = post_project(ProjectIn(
        name=body.name,
        description=f"克隆自 {src['name']}",
        ontology=src["ontology"],
    ))
    conn = db.get_conn()
    counts = {"features": 0, "milestones": 0, "items": 0, "relations": 0}
    feat_map: dict[str, str] = {}
    ms_map: dict[str, str] = {}
    item_map: dict[str, str] = {}

    if body.structure:
        from apm.domains.features import create_feature
        for f in conn.execute(
            "SELECT * FROM features WHERE project_id = ? AND status != 'archived'"
            " ORDER BY sort_order, created_at", (project_id,),
        ).fetchall():
            nf = create_feature(project_id=new["id"], title=f["title"],
                                brief=f["brief"], sort_order=f["sort_order"] or 0)
            feat_map[f["id"]] = nf["id"]
            counts["features"] += 1

    if body.milestones:
        from apm.domains.milestones import MilestoneIn, post_milestone
        for m in conn.execute(
            "SELECT * FROM milestones WHERE project_id = ? ORDER BY due_date, created_at",
            (project_id,),
        ).fetchall():
            nm = post_milestone(new["id"], MilestoneIn(
                title=m["title"], due_date=m["due_date"], description=m["description"]))
            ms_map[m["id"]] = nm["id"]
            counts["milestones"] += 1

    if body.items:
        from apm.domains.items import create_item
        for it in conn.execute(
            "SELECT * FROM items WHERE project_id = ? ORDER BY created_at", (project_id,),
        ).fetchall():
            ni = create_item(
                project_id=new["id"],
                concept_id=it["concept_id"] or "task",
                title=it["title"],
                status=it["status"],
                priority=it["priority"],
                estimate_hours=it["estimate_hours"],
                start_date=it["start_date"],
                due_date=it["due_date"],
                custom_fields=json.loads(it["custom_fields"]) if it["custom_fields"] else None,
                feature_id=feat_map.get(it["feature_id"]),
                milestone_id=ms_map.get(it["milestone_id"]),
            )
            item_map[it["id"]] = ni["id"]
            counts["items"] += 1
        # relations between two copied items (depends_on keeps M14 scheduling usable)
        for rel in conn.execute(
            "SELECT * FROM item_relations WHERE project_id = ?", (project_id,),
        ).fetchall():
            if rel["from_item"] in item_map and rel["to_item"] in item_map:
                events.emit(
                    event_type="item.related",
                    agg_type="item",
                    agg_id=item_map[rel["from_item"]],
                    project_id=new["id"],
                    payload={"from_item": item_map[rel["from_item"]],
                             "to_item": item_map[rel["to_item"]],
                             "relation_type": rel["relation_type"]},
                )
                counts["relations"] += 1

    events.emit(
        event_type="project.cloned",
        agg_type="project",
        agg_id=new["id"],
        project_id=new["id"],
        payload={"source_project_id": project_id, "source_name": src["name"], "counts": counts},
    )
    return {"project": get_project(new["id"]), "counts": counts}
