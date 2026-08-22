"""Project domain: CRUD with ontology template instantiation + phase graph."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on
from apm.domains.ontology import OntologyError, load_ontology, require_valid

router = APIRouter(tags=["projects"])


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


@on("project.updated")
def _proj_project_updated(conn, e):
    p = e.payload
    sets, params = [], []
    for key in ("name", "description", "status", "charter"):
        if key in p:
            sets.append(f"{key} = ?")
            params.append(p[key])
    if sets:
        sets.append("updated_at = ?")
        params.append(e.ts)
        params.append(e.agg_id)
        conn.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id = ?", params)


# ---------------------------------------------------------------- helpers
def get_project(project_id: str) -> dict | None:
    row = db.get_conn().execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return dict(row) if row else None


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
        payload={
            "name": body.name,
            "description": body.description,
            "ontology": body.ontology,
            "template": body.ontology,
            "charter": charter,
            "requirement": body.requirement,
        },
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
def list_projects() -> dict:
    rows = db.get_conn().execute("SELECT * FROM projects ORDER BY created_at").fetchall()
    return {"projects": [dict(r) for r in rows]}


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
    return {"project_id": project_id, "nodes": nodes, "edges": edges}
