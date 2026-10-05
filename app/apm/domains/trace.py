"""Requirements-to-evidence traceability (M108-I326, docs/01 §DA.1): a
first-class link store between 需求 (requirement-class work items) and their
evidence — design decisions, implementation, tests, deliverables, documents.

Why a dedicated store when item_relations / asset_links already exist: those
are typed to one node kind each (item→item, asset→target). Here both ends can
be any of item / artifact (git path) / asset / conversation / feature, and the
relation vocabulary carries the evidence role (implements/verifies/decides/
delivers/documents/relates_to). Consumers: GET .../trace/impact answers
「改这条需求影响哪些模块/文档/测试」(undirected BFS, default depth 2), and
GET .../trace/coverage is the per-round gap report (requirements without
tests/implementation, orphan items, stale links, requirements changed after
their evidence was registered).

Pure projection (trace_links in drop_projections) — rebuild reproduces the
graph from trace.linked/unlinked events."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on

router = APIRouter(tags=["trace"])

RELATIONS = {
    "implements": "实现",
    "verifies": "验证",
    "decides": "决策",
    "delivers": "交付",
    "documents": "记录",
    "relates_to": "关联",
}
NODE_TYPES = ("item", "artifact", "asset", "conversation", "feature")
# impact 分组：正则方向 = 证据 → 需求（implements/verifies/... 的 source 是
# 证据）。发现节点是边 source → 按关系分桶；是边 target（根是证据、目标是它
# 支撑的需求）→ 落「需求」桶。语义随方向，与登记时的书写方向无关。
GROUP_BY_RELATION = {
    "implements": "implementation",
    "verifies": "tests",
    "decides": "decisions",
    "delivers": "deliverables",
    "documents": "documents",
    "relates_to": "related",
}
GROUPS = ("requirements", "decisions", "implementation", "tests", "deliverables", "documents", "related")


# ---------------------------------------------------------------- projectors
@on("trace.linked")
def _proj_trace_linked(conn, e):
    p = e.payload
    conn.execute(
        "INSERT INTO trace_links (id, project_id, source_type, source_ref,"
        " relation, target_type, target_ref, note, created_by, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (e.agg_id, e.project_id, p["source_type"], p["source_ref"], p["relation"],
         p["target_type"], p["target_ref"], p.get("note"), p.get("created_by"), e.ts),
    )


@on("trace.unlinked")
def _proj_trace_unlinked(conn, e):
    conn.execute("DELETE FROM trace_links WHERE id = ?", (e.agg_id,))


# ---------------------------------------------------------------- helpers
def _node_key(node_type: str, ref: str) -> str:
    return f"{node_type}:{ref}"


def _group_for(ln: dict, discovered_is_source: bool) -> str:
    if ln["relation"] == "relates_to":
        return "related"
    return GROUP_BY_RELATION[ln["relation"]] if discovered_is_source else "requirements"


def resolve_node(project_id: str, node_type: str, ref: str) -> dict:
    """Resolve a node ref into display info; missing=True marks dangling
    endpoints (deleted item, artifact path gone) instead of failing reads —
    coverage surfaces them as stale links."""
    out = {"type": node_type, "ref": ref, "missing": False}
    conn = db.get_conn()
    if node_type == "item":
        row = conn.execute(
            "SELECT title, status, concept_id, archived_at FROM items WHERE id = ?",
            (ref,)).fetchone()
        if row:
            out |= {"title": row["title"], "status": row["status"],
                    "concept_id": row["concept_id"], "archived": bool(row["archived_at"])}
        else:
            out["missing"] = True
    elif node_type == "artifact":
        out["title"] = ref
        from apm.content.artifacts import list_artifacts

        if ref not in {a["path"] for a in list_artifacts(project_id)}:
            out["missing"] = True
    elif node_type == "asset":
        row = conn.execute("SELECT title, status FROM assets WHERE id = ?", (ref,)).fetchone()
        if row:
            out |= {"title": row["title"], "status": row["status"]}
        else:
            out["missing"] = True
    elif node_type == "feature":
        row = conn.execute("SELECT title, status FROM features WHERE id = ?", (ref,)).fetchone()
        if row:
            out |= {"title": row["title"], "status": row["status"]}
        else:
            out["missing"] = True
    elif node_type == "conversation":
        row = conn.execute("SELECT title, status FROM conversations WHERE id = ?", (ref,)).fetchone()
        if row:
            out |= {"title": row["title"], "status": row["status"]}
        else:
            out["missing"] = True
    else:  # pragma: no cover — NODE_TYPES validated at the write path
        out["missing"] = True
    return out


def require_node(project_id: str, node_type: str, ref: str) -> dict:
    """Endpoint validation (write path + impact read root): endpoint must exist
    AND belong to this project. asset 是例外——资产库本就是 org 级共享
    （docs/10 M80-I240 分门语义），不做项目归属校验。验收考官 Round 1：
    conversation/feature 同为项目级表，归属门此前只对 item 生效（跨项目节点
    可挂进本项目图+标题经 resolve 泄露）；Round 2：impact 读侧根节点同门——
    否则 A 项目成员拿 B 项目节点 id 当根，resolve_node 按全局 id 泄露标题/状态。"""
    if node_type == "item":
        from apm.domains.items import require_item

        item = require_item(ref)
        if item["project_id"] != project_id:
            raise HTTPException(status_code=422, detail=f"item '{ref}' belongs to another project")
        return resolve_node(project_id, node_type, ref)
    node = resolve_node(project_id, node_type, ref)
    if node["missing"]:
        raise HTTPException(status_code=404, detail=f"unknown {node_type} '{ref}' in project")
    if node_type in ("conversation", "feature"):
        table = "conversations" if node_type == "conversation" else "features"
        row = db.get_conn().execute(
            f"SELECT project_id FROM {table} WHERE id = ?", (ref,)).fetchone()
        if row and row["project_id"] != project_id:
            raise HTTPException(status_code=422,
                                detail=f"{node_type} '{ref}' belongs to another project")
    return node


def requirement_concepts(project_id: str) -> set[str]:
    """需求类概念 = 本体里 default_phase 为 intake 的概念（software-dev 的
    requirement、generic 的 objective）——词汇随本体，不硬编码。"""
    from apm.domains.items import project_ontology

    onto = project_ontology(project_id)
    return {cid for cid, c in onto.concepts.items() if c.default_phase == "intake"}


def _project_links(project_id: str) -> list[dict]:
    rows = db.get_conn().execute(
        "SELECT * FROM trace_links WHERE project_id = ? ORDER BY created_at, id",
        (project_id,)).fetchall()
    return [dict(r) for r in rows]


def _requirement_evidence(links: list[dict], req_key: str) -> dict:
    """Undirected incident-edge classification for one requirement node.
    测试证据传递：实现链上的测试也算（需求 R ←实现— T ←验证— V → R 的
    has_test=True）——与 impact 两跳语义一致，测试不必逐条直挂需求。"""
    classes: dict[str, set[str]] = {}
    count, first_created = 0, None
    for ln in links:
        skey = _node_key(ln["source_type"], ln["source_ref"])
        tkey = _node_key(ln["target_type"], ln["target_ref"])
        g = GROUP_BY_RELATION.get(ln["relation"], "related")
        classes.setdefault(skey, set()).add(g)
        classes.setdefault(tkey, set()).add(g)
        if req_key in (skey, tkey):
            count += 1
            first_created = ln["created_at"] if first_created is None else min(first_created, ln["created_at"])
    if "tests" not in classes.get(req_key, set()):
        # 需求的实现邻居（经 implements 边·无向）自己挂着 verifies → 传递闭环
        req_classes = classes.get(req_key, set())
        for ln in links:
            if GROUP_BY_RELATION.get(ln["relation"]) != "implementation":
                continue
            skey = _node_key(ln["source_type"], ln["source_ref"])
            tkey = _node_key(ln["target_type"], ln["target_ref"])
            other = skey if req_key == tkey else (tkey if req_key == skey else None)
            if other and "tests" in classes.get(other, set()):
                req_classes.add("tests")
                break
    flags = {"has_decision": "decisions" in classes.get(req_key, set()),
             "has_implementation": "implementation" in classes.get(req_key, set()),
             "has_test": "tests" in classes.get(req_key, set()),
             "has_deliverable": "deliverables" in classes.get(req_key, set()),
             "has_document": "documents" in classes.get(req_key, set())}
    return {"flags": flags, "links": count, "first_evidence_at": first_created}


def _stale_reasons(project_id: str, links: list[dict]) -> list[dict]:
    """Dangling endpoints: refs that no longer resolve (deleted item / removed
    artifact / dropped asset...). Artifact existence is checked once per call."""
    reasons = []
    artifact_paths: set[str] | None = None
    for ln in links:
        missing = []
        for side in ("source", "target"):
            ntype, nref = ln[f"{side}_type"], ln[f"{side}_ref"]
            if ntype == "artifact":
                if artifact_paths is None:
                    from apm.content.artifacts import list_artifacts

                    artifact_paths = {a["path"] for a in list_artifacts(project_id)}
                if nref not in artifact_paths:
                    missing.append(f"{ntype}:{nref}")
            elif resolve_node(project_id, ntype, nref)["missing"]:
                missing.append(f"{ntype}:{nref}")
        if missing:
            reasons.append({"link_id": ln["id"], "relation": ln["relation"], "missing": missing})
    return reasons


class TraceLinkIn(BaseModel):
    source_type: str
    source_ref: str
    relation: str
    target_type: str
    target_ref: str
    note: str | None = None


# ---------------------------------------------------------------- endpoints
@router.get("/projects/{project_id}/trace/links")
def list_trace_links(project_id: str, source_type: str | None = None,
                     source_ref: str | None = None) -> dict:
    links = _project_links(project_id)
    if source_type and source_ref:
        links = [ln for ln in links
                 if ln["source_type"] == source_type and ln["source_ref"] == source_ref]
    cache: dict[str, dict] = {}

    def _resolved(ntype: str, nref: str) -> dict:
        key = _node_key(ntype, nref)
        if key not in cache:
            cache[key] = resolve_node(project_id, ntype, nref)
        return cache[key]

    return {"links": [ln | {
        "source": _resolved(ln["source_type"], ln["source_ref"]),
        "target": _resolved(ln["target_type"], ln["target_ref"]),
    } for ln in links]}


@router.post("/projects/{project_id}/trace/links")
def create_trace_link(project_id: str, body: TraceLinkIn) -> dict:
    from apm.domains.projects import require_project

    require_project(project_id)
    if body.relation not in RELATIONS:
        raise HTTPException(status_code=422,
                            detail=f"unknown relation '{body.relation}' (one of {sorted(RELATIONS)})")
    if body.source_type not in NODE_TYPES or body.target_type not in NODE_TYPES:
        raise HTTPException(status_code=422,
                            detail=f"node types must be one of {list(NODE_TYPES)}")
    if (body.source_type, body.source_ref) == (body.target_type, body.target_ref):
        raise HTTPException(status_code=422, detail="cannot link a node to itself")
    require_node(project_id, body.source_type, body.source_ref)
    require_node(project_id, body.target_type, body.target_ref)
    for ln in _project_links(project_id):
        if ((ln["source_type"], ln["source_ref"], ln["relation"], ln["target_type"], ln["target_ref"])
                == (body.source_type, body.source_ref, body.relation, body.target_type, body.target_ref)):
            raise HTTPException(status_code=409, detail="link already exists")
    lid = new_id("tl")
    events.emit(
        event_type="trace.linked", agg_type="trace_link", agg_id=lid,
        project_id=project_id, actor_type="human", actor_id=events.effective_actor(),
        payload={"source_type": body.source_type, "source_ref": body.source_ref,
                 "relation": body.relation, "target_type": body.target_type,
                 "target_ref": body.target_ref, "note": body.note,
                 "created_by": events.effective_actor()},
    )
    return {"id": lid, **body.model_dump()}


@router.delete("/trace/links/{link_id}")
def delete_trace_link(link_id: str) -> dict:
    row = db.get_conn().execute("SELECT * FROM trace_links WHERE id = ?", (link_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"unknown trace link '{link_id}'")
    from apm.domains.members import require_project_write

    require_project_write(row["project_id"])  # M80-I240（M108-I326 登记 check_write_gates）
    events.emit(
        event_type="trace.unlinked", agg_type="trace_link", agg_id=link_id,
        project_id=row["project_id"], actor_type="human", actor_id=events.effective_actor(),
        payload={"relation": row["relation"]},
    )
    return {"unlinked": link_id}


@router.get("/projects/{project_id}/trace/impact")
def trace_impact(project_id: str, node_type: str = "item", node_ref: str = "",
                 depth: int = 2) -> dict:
    """影响分析：从任一节点出发的无向 BFS（默认 2 跳）——改一条需求，直接看
    到受波及的设计决定/实现/测试/交付物/文档；从任务侧进入则反查波及的需求。
    证据登记早于根节点（需求/工作项）末次变更的边标 needs_review（根后来改了、
    证据未复核——coverage 的变更未复核缺口同口径）。根节点过 require_node 归属门
    （考官 Round 2：读侧与写侧同门，跨项目根 422，标题不经 resolve 泄露）。"""
    if node_type not in NODE_TYPES:
        raise HTTPException(status_code=422, detail=f"node types must be one of {list(NODE_TYPES)}")
    if not node_ref:
        raise HTTPException(status_code=422, detail="node_ref is required")
    depth = max(1, min(depth, 3))
    node = require_node(project_id, node_type, node_ref)
    node["requirement_like"] = False
    if node_type == "item" and node.get("concept_id") in requirement_concepts(project_id):
        node["requirement_like"] = True

    links = _project_links(project_id)
    root_row = None
    if node_type == "item":
        root_row = db.get_conn().execute(
            "SELECT updated_at FROM items WHERE id = ?", (node_ref,)).fetchone()

    adjacency: dict[str, list[tuple[dict, str, str]]] = {}
    for ln in links:
        skey = _node_key(ln["source_type"], ln["source_ref"])
        tkey = _node_key(ln["target_type"], ln["target_ref"])
        adjacency.setdefault(skey, []).append((ln, skey, tkey))
        adjacency.setdefault(tkey, []).append((ln, skey, tkey))

    rkey = _node_key(node_type, node_ref)
    groups: dict[str, list[dict]] = {g: [] for g in GROUPS}
    seen: dict[str, dict] = {}

    def _visit(key: str, via: list[dict], group: str, level: int, needs_review: bool) -> None:
        if key in seen and seen[key]["depth"] <= level:
            return
        ntype, nref = key.split(":", 1)
        info = resolve_node(project_id, ntype, nref)
        entry = {"key": key, "type": ntype, "ref": nref, "title": info.get("title", nref),
                 "status": info.get("status"), "missing": info["missing"],
                 "concept_id": info.get("concept_id"), "depth": level,
                 "via": via, "needs_review": needs_review}
        seen[key] = entry
        groups[group].append(entry)
        if level >= depth:
            return
        for ln, skey, tkey in adjacency.get(key, []):
            other = tkey if skey == key else skey
            if other == rkey:
                continue
            review = needs_review or (
                root_row is not None and root_row["updated_at"] is not None
                and ln["created_at"] < root_row["updated_at"])
            edge_info = {"relation": ln["relation"], "link_id": ln["id"],
                         "from": skey, "to": tkey}
            _visit(other, via + [edge_info], _group_for(ln, skey == other),
                   level + 1, review)

    for ln, skey, tkey in adjacency.get(rkey, []):
        other = tkey if skey == rkey else skey
        review = (root_row is not None and root_row["updated_at"] is not None
                  and ln["created_at"] < root_row["updated_at"])
        edge_info = {"relation": ln["relation"], "link_id": ln["id"], "from": skey, "to": tkey}
        _visit(other, [edge_info], _group_for(ln, skey == other), 1, review)

    return {"node": node, "depth": depth, "groups": groups,
            "summary": {g: len(v) for g, v in groups.items()} | {
                "needs_review": sum(1 for v in groups.values() for e in v if e["needs_review"])}}


@router.get("/projects/{project_id}/trace/coverage")
def trace_coverage(project_id: str, milestone_id: str | None = None,
                   cycle_id: str | None = None) -> dict:
    """每轮缺口报告：需求侧（缺测试/缺实现/零证据/变更未复核）+ 任务侧
    （未挂进任何追溯链接的孤儿项——挂了任意一条边即不算）+ 图健康（失效链接）。
    支持按里程碑/迭代切片，对应「每轮收口前跑一遍」。closed = 有实现且有测试
    （决策/交付物为加分项）。"""
    conn = db.get_conn()
    req_concepts = requirement_concepts(project_id)
    where, params = "project_id = ?", [project_id]
    if milestone_id:
        where += " AND milestone_id = ?"
        params.append(milestone_id)
    if cycle_id:
        where += " AND cycle_id = ?"
        params.append(cycle_id)
    items = conn.execute(
        f"SELECT id, title, status, concept_id, updated_at, archived_at FROM items WHERE {where}",
        params).fetchall()
    links = _project_links(project_id)
    linked_keys = {_node_key(ln["source_type"], ln["source_ref"]) for ln in links} | \
                  {_node_key(ln["target_type"], ln["target_ref"]) for ln in links}

    requirements, orphans = [], []
    for it in items:
        key = _node_key("item", it["id"])
        if it["concept_id"] in req_concepts:
            if it["archived_at"]:
                continue
            ev = _requirement_evidence(links, key)
            requirements.append({
                "id": it["id"], "title": it["title"], "status": it["status"],
                "updated_at": it["updated_at"], **ev["flags"],
                "links": ev["links"], "first_evidence_at": ev["first_evidence_at"],
                "needs_review": bool(ev["first_evidence_at"] and it["updated_at"]
                                     and ev["first_evidence_at"] < it["updated_at"]),
                "closed": ev["flags"]["has_implementation"] and ev["flags"]["has_test"],
            })
        elif not it["archived_at"] and key not in linked_keys:
            orphans.append({"id": it["id"], "title": it["title"],
                            "concept_id": it["concept_id"], "status": it["status"]})

    reqs_no_evidence = [r["id"] for r in requirements if r["links"] == 0]
    reqs_no_tests = [r["id"] for r in requirements if not r["has_test"]]
    reqs_no_impl = [r["id"] for r in requirements if not r["has_implementation"]]
    needs_review = [r for r in requirements if r["needs_review"]]
    total = len(requirements)
    closed = sum(1 for r in requirements if r["closed"])
    by_id = {r["id"]: r for r in requirements}
    stale = _stale_reasons(project_id, links)
    return {
        "requirements": requirements,
        "gaps": {
            "requirements_without_evidence": [by_id[i] for i in reqs_no_evidence],
            "requirements_without_tests": [by_id[i] for i in reqs_no_tests],
            "requirements_without_implementation": [by_id[i] for i in reqs_no_impl],
            "orphan_items": orphans,
            "stale_links": stale,
            "changed_after_evidence": needs_review,
        },
        "summary": {
            "requirements": total,
            "with_implementation": total - len(reqs_no_impl),
            "with_tests": total - len(reqs_no_tests),
            "closed": closed,
            "closed_rate": round(closed / total, 2) if total else None,
            "orphan_items": len(orphans),
            "stale_links": len(stale),
            "needs_review": len(needs_review),
        },
    }
