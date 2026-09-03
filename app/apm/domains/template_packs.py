"""Template pack registry: browse / preview / one-click instantiate (M7-I23,
docs/01 §F.2). 注册表 = 本体目录活扫描（单一真源：I18 导入即落盘，不另建表以免
双真源）+ 事件合成 provenance：`pack.registered`（启动时对无导入记录的本体补
登记，幂等）与 `ontology.imported`（I18 既有契约，复用为导入登记）。instantiate
复用建项目共链路（projects.post_project）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm.core import events
from apm.domains.ontology import OntologyError, list_ontologies, load_ontology
from apm.domains.projects import ProjectIn, post_project

router = APIRouter(tags=["template-packs"])

_PROVENANCE_LIMIT = 10_000  # registry provenance reads the whole (small) log tail


def register_builtin_packs() -> int:
    """Startup registration: every library pack enters the registry exactly once —
    imported packs are already recorded by `ontology.imported`, the rest get
    `pack.registered` (idempotent across restarts)."""
    seen = {e.agg_id for e in events.query_events(event_type="pack.registered", limit=_PROVENANCE_LIMIT)[0]}
    n = 0
    for onto in list_ontologies():
        if onto.name in seen:
            continue
        if events.query_events(event_type="ontology.imported", agg_id=onto.name, limit=1)[0]:
            continue
        events.emit(
            event_type="pack.registered",
            agg_type="ontology_pack",
            agg_id=onto.name,
            actor_type="system",
            actor_id="runtime",
            payload={"source": "builtin", "version": onto.version},
        )
        n += 1
    return n


def _provenance() -> dict[str, dict]:
    """name → source/at/by, synthesized from the append-only log (replay-safe)."""
    prov: dict[str, dict] = {}
    for e in events.query_events(event_type="pack.registered", limit=_PROVENANCE_LIMIT)[0]:
        prov[e.agg_id] = {"source": "builtin", "registered_at": e.ts}
    for e in events.query_events(event_type="ontology.imported", limit=_PROVENANCE_LIMIT)[0]:
        prov[e.agg_id] = {
            "source": "imported",
            "imported_at": e.ts,
            "imported_by": e.actor_id,
        }
    return prov


def _summary(onto) -> dict:
    concepts = onto.concepts.values()
    return {
        "concepts": len(onto.concepts),
        "states": sum(len(c.states) for c in concepts),
        "fields": sum(len(c.fields) for c in concepts),
        "phases": len(onto.phases),
        "relations": len(onto.relations),
        "competency_questions": len(onto.competency_questions),
    }


@router.get("/template-packs")
def list_packs() -> dict:
    prov = _provenance()
    packs = []
    for onto in list_ontologies():
        p = prov.get(onto.name, {})
        packs.append(
            {
                "name": onto.name,
                "display_name": onto.display_name,
                "version": onto.version,
                "source": p.get("source", "builtin"),
                "valid": not onto.errors,
                **_summary(onto),
                "registered_at": p.get("registered_at"),
                "imported_at": p.get("imported_at"),
                "imported_by": p.get("imported_by"),
            }
        )
    return {"packs": packs}


@router.get("/template-packs/{name}")
def preview_pack(name: str) -> dict:
    try:
        onto = load_ontology(name)
    except OntologyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    p = _provenance().get(name, {})
    return {
        "name": onto.name,
        "display_name": onto.display_name,
        "version": onto.version,
        "source": p.get("source", "builtin"),
        "summary": _summary(onto),
        "competency_questions": onto.competency_questions,
        "concepts": [c.to_dict() for c in onto.concepts.values()],
        "phases": onto.phases,
        "relations": onto.relations,
        "board_defaults": onto.board_defaults,
        "asset_kinds": onto.asset_kinds,
        "libraries": onto.libraries,
        "errors": onto.errors,
    }


class InstantiateIn(BaseModel):
    project_name: str
    requirement: str | None = None


@router.post("/template-packs/{name}/instantiate")
def instantiate(name: str, body: InstantiateIn) -> dict:
    try:
        onto = load_ontology(name)
    except OntologyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if onto.errors:
        raise HTTPException(status_code=422, detail=f"ontology '{name}' has validation errors")
    if not body.project_name.strip():
        raise HTTPException(status_code=422, detail="project_name is required")
    # 建项目共链路：与 POST /projects 完全一致（宪章/首特性/起草对话/内容仓 bootstrap）。
    return post_project(
        ProjectIn(name=body.project_name, ontology=name, requirement=body.requirement)
    )
