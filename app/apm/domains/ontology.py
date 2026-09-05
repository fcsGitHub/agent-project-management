"""Ontology service: load/validate ontology YAML, compile type registry.

The ontology is the project's type system (docs/08): concepts (with lifecycle
states mapped to the five buckets), relations, phase graph, asset kinds and
libraries. Everything downstream (forms, board columns, phase graphs, asset
forms, NL dictionaries) is driven by the compiled registry.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException

from apm import config
from apm.core import events

router = APIRouter(tags=["ontology"])

# I78 (docs/01 §X.2): blocks/precedes/relates join the kernel — OpenProject
# relation semantics. blocked_by is deliberately absent: stored one-way as
# blocks (the reverse view), never a separate type.
KERNEL_RELATIONS = ("contains", "depends_on", "produces", "consumes",
                    "blocks", "precedes", "relates")
BUCKETS = ("backlog", "todo", "in_progress", "done", "cancelled")
# CQ support surfaces (docs/08 §8.1, I16): projections/event types that can answer a CQ.
CQ_SOURCES = ("items", "relations", "approvals", "assets", "runs", "events", "artifacts")

GATE_LABELS = {
    "prd_review": "PRD 评审",
    "design_review": "设计评审",
    "plan_review": "计划确认",
    "code_review": "代码评审",
    "acceptance": "验收（DoD）",
    "release_approval": "发布批准",
    "work_review": "工作评审",
    "delivery_approval": "交付审批",
    "asset_review": "资产入库评审",
}


class OntologyError(Exception):
    pass


class Concept:
    def __init__(self, raw: dict[str, Any]):
        self.id: str = raw["id"]
        self.name: str = raw.get("name", self.id)
        self.icon: str = raw.get("icon", "▪")
        self.default_phase: str | None = raw.get("default_phase")
        self.states: list[dict[str, str]] = raw.get("states", [])
        self.fields: list[dict[str, Any]] = raw.get("fields", [])
        self.artifact_kinds: list[dict[str, Any]] = raw.get("artifact_kinds", [])
        self.agent_roles: list[str] = raw.get("agent_roles", [])
        # M26-I82: optional allowed-transition whitelist ({from, to} pairs).
        # Absent/empty means every transition is legal (backward compatible).
        self.transitions: list[dict[str, Any]] = raw.get("transitions", [])

    def state_group(self, status: str) -> str | None:
        for s in self.states:
            if s["id"] == status:
                return s.get("group")
        return None

    def initial_status(self) -> str:
        return self.states[0]["id"] if self.states else ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "icon": self.icon,
            "default_phase": self.default_phase,
            "states": self.states,
            "transitions": self.transitions,
            "fields": self.fields,
            "artifact_kinds": self.artifact_kinds,
            "agent_roles": self.agent_roles,
        }


class Ontology:
    def __init__(self, raw: dict[str, Any], errors: list[str] | None = None, name: str | None = None):
        self.raw = raw
        self.name: str = name or raw.get("name", "")
        self.errors: list[str] = errors or []
        self.display_name: str = raw.get("display_name", self.name)
        self.version: int = int(raw.get("version", 1))
        self.competency_questions: list[str] = raw.get("competency_questions", [])
        self.concepts: dict[str, Concept] = {c["id"]: Concept(c) for c in raw.get("concepts", [])}
        self.relations: list[dict[str, Any]] = raw.get("relations", [])
        self.phases: list[dict[str, Any]] = raw.get("phases", [])
        self.board_defaults: dict[str, Any] = raw.get("board_defaults", {})
        self.asset_kinds: list[dict[str, Any]] = raw.get("asset_kinds", [])
        self.libraries: list[dict[str, Any]] = raw.get("libraries", [])

    # -- lookups ---------------------------------------------------------
    def concept(self, concept_id: str) -> Concept:
        if concept_id not in self.concepts:
            raise OntologyError(f"unknown concept '{concept_id}' in ontology '{self.name}'")
        return self.concepts[concept_id]

    def gate_of_phase(self, phase_id: str) -> str | None:
        for p in self.phases:
            if p["id"] == phase_id:
                return p.get("gate")
        return None

    def phase_of_gate(self, gate_id: str) -> str | None:
        for p in self.phases:
            if p.get("gate") == gate_id:
                return p["id"]
        return None

    def phase_name(self, phase_id: str) -> str:
        for p in self.phases:
            if p["id"] == phase_id:
                return p.get("name", phase_id)
        return phase_id

    def gate_label(self, gate_id: str) -> str:
        return GATE_LABELS.get(gate_id, gate_id)

    def relation_ids(self) -> list[str]:
        return list(KERNEL_RELATIONS) + [r["id"] for r in self.relations]

    def validate_item_status(self, concept_id: str, status: str) -> str:
        """Return the bucket for a status, raising on unknown concept/status."""
        group = self.concept(concept_id).state_group(status)
        if group is None:
            valid = [s["id"] for s in self.concept(concept_id).states]
            raise OntologyError(
                f"status '{status}' not in concept '{concept_id}' lifecycle {valid}"
            )
        return group

    def validate_transition(self, concept_id: str, from_status: str, to_status: str) -> None:
        """M26-I82: enforce the concept's optional transition whitelist —
        an undeclared/empty list keeps every transition legal (backward
        compatible); a declared one is fail-closed (OpenProject status-flow
        matrix, simplified to concept level)."""
        c = self.concept(concept_id)
        if not c.transitions:
            return
        allowed = {(t.get("from"), t.get("to")) for t in c.transitions}
        if (from_status, to_status) not in allowed:
            legal = [f"{f}→{t}" for f, t in sorted(allowed)]
            raise OntologyError(
                f"transition '{from_status}'→'{to_status}' not allowed for concept "
                f"'{concept_id}' (declared: {legal})"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "version": self.version,
            "competency_questions": self.competency_questions,
            "concepts": [c.to_dict() for c in self.concepts.values()],
            "relations": self.relations,
            "kernel_relations": list(KERNEL_RELATIONS),
            "phases": self.phases,
            "board_defaults": self.board_defaults,
            "asset_kinds": self.asset_kinds,
            "libraries": self.libraries,
            "errors": self.errors,
        }


def validate_ontology_dict(d: dict[str, Any]) -> list[str]:
    """Structural validation (docs/08 §3 constraints). Returns error list."""
    errors: list[str] = []
    if not d.get("name"):
        errors.append("missing 'name'")
    concepts = d.get("concepts", [])
    if not concepts:
        errors.append("at least one concept is required")
    if len(concepts) > 12:
        errors.append(f"{len(concepts)} concepts > 12 (small-ontology rule)")
    seen_concepts: set[str] = set()
    for c in concepts:
        cid = c.get("id")
        if not cid:
            errors.append("concept missing id")
            continue
        if cid in seen_concepts:
            errors.append(f"duplicate concept '{cid}'")
        seen_concepts.add(cid)
        states = c.get("states", [])
        if not states:
            errors.append(f"concept '{cid}' has no states")
        seen_states: set[str] = set()
        for s in states:
            if s.get("id") in seen_states:
                errors.append(f"concept '{cid}': duplicate state '{s.get('id')}'")
            seen_states.add(s.get("id") or "")
            if s.get("group") not in BUCKETS:
                errors.append(f"concept '{cid}' state '{s.get('id')}': group must be one of {BUCKETS}")
        if len(c.get("fields", [])) > 10:
            errors.append(f"concept '{cid}': >10 fields")
        # Field types (docs/01 §D.4): string/enum/number/date/ref + M6 boolean/multiselect.
        for f in c.get("fields", []):
            ftype = f.get("type")
            if ftype not in ("string", "enum", "number", "date", "ref", "boolean", "multiselect"):
                errors.append(f"concept '{cid}' field '{f.get('id')}': unknown type '{ftype}'")
            if ftype in ("enum", "multiselect") and not f.get("values"):
                errors.append(f"concept '{cid}' field '{f.get('id')}': {ftype} requires values")
        known_phases = {p.get("id") for p in d.get("phases", [])}
        if c.get("default_phase") and c["default_phase"] not in known_phases:
            errors.append(f"concept '{cid}': unknown default_phase '{c['default_phase']}'")

    relations = d.get("relations", [])
    if len(relations) > 6:
        errors.append(f"{len(relations)} custom relations > 6")
    known = seen_concepts
    for r in relations:
        if r.get("id") in KERNEL_RELATIONS:
            errors.append(f"custom relation '{r.get('id')}' overlaps kernel relation semantics")
        if r.get("domain") not in known or r.get("range") not in known:
            errors.append(f"relation '{r.get('id')}': domain/range must reference concepts")

    phases = d.get("phases", [])
    phase_ids = [p.get("id") for p in phases]
    if len(phase_ids) != len(set(phase_ids)):
        errors.append("duplicate phase ids")
    if phases:
        gates = [p.get("gate") for p in phases if p.get("gate")]
        if len(gates) != len(set(gates)):
            errors.append("duplicate gate ids in phases")
    # Phases are a linear sequence in the MVP format, hence trivially a DAG;
    # assert ids exist for concept default_phase references (checked above).

    asset_kinds = d.get("asset_kinds", [])
    libraries = d.get("libraries", [])
    if len(asset_kinds) > 10:
        errors.append(f"{len(asset_kinds)} asset kinds > 10")
    if len(libraries) > 6:
        errors.append(f"{len(libraries)} libraries > 6")
    lib_ids = {l.get("id") for l in libraries}
    accepts: dict[str, set[str]] = {l.get("id"): set(l.get("accepts", [])) for l in libraries}
    kind_ids = set()
    for k in asset_kinds:
        kid = k.get("id")
        kind_ids.add(kid)
        lib = k.get("library")
        if lib not in lib_ids:
            errors.append(f"asset kind '{kid}': unknown library '{lib}'")
        elif kid not in accepts.get(lib, set()):
            errors.append(f"asset kind '{kid}' not listed in library '{lib}' accepts")
        dep = k.get("deposits_to")
        if dep and dep not in {a.get("id") for a in asset_kinds}:
            errors.append(f"artifact kind '{dep}' (deposits_to) is not a declared asset kind")
    for c in concepts:
        for ak in c.get("artifact_kinds", []):
            dep = ak.get("deposits_to")
            if dep and dep not in kind_ids:
                errors.append(f"concept '{c.get('id')}' artifact kind '{ak.get('id')}': deposits_to '{dep}' unknown")

    # CQ answerability mappings (I16): each maps one declared question to data surfaces.
    questions = d.get("competency_questions", [])
    seen_cq: set[str] = set()
    for m in d.get("cq_mappings") or []:
        q = m.get("question") if isinstance(m, dict) else None
        if q not in questions:
            errors.append(f"cq_mapping question not in competency_questions: {q}")
        elif q in seen_cq:
            errors.append(f"duplicate cq_mapping for question: {q}")
        seen_cq.add(q or "")
        supports = (m.get("supports") or []) if isinstance(m, dict) else []
        if not supports:
            errors.append(f"cq_mapping for '{q}': supports is required")
        for s in supports:
            if not isinstance(s, dict) or s.get("source") not in CQ_SOURCES:
                errors.append(f"cq_mapping for '{q}': unknown support source {s}")
            elif s.get("source") == "events" and not s.get("event_types"):
                errors.append(f"cq_mapping for '{q}': events source requires event_types")
    return errors


_lock = threading.Lock()
_cache: dict[str, Ontology] = {}


def load_ontology(name: str) -> Ontology:
    if "/" in name or "\\" in name or name in ("", "."):
        raise OntologyError(f"invalid ontology name '{name}'")
    with _lock:
        if name in _cache:
            return _cache[name]
    path = config.settings.ontology_dir / f"{name}.yaml"
    if not path.exists():
        raise OntologyError(f"ontology file not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    errors = validate_ontology_dict(raw)
    onto = Ontology(raw, errors=errors, name=name)
    with _lock:
        _cache[name] = onto
    return onto


def list_ontologies() -> list[Ontology]:
    out: list[Ontology] = []
    d = config.settings.ontology_dir
    if d.exists():
        for f in sorted(d.glob("*.yaml")):
            try:
                out.append(load_ontology(f.stem))
            except OntologyError:
                continue
    return out


def reload_all() -> list[Ontology]:
    with _lock:
        _cache.clear()
    return list_ontologies()


def require_valid(name: str) -> Ontology:
    onto = load_ontology(name)
    if onto.errors:
        raise OntologyError(f"ontology '{name}' invalid: {'; '.join(onto.errors)}")
    return onto


# ---------------------------------------------------------------- routers
@router.get("/ontologies")
def get_ontologies() -> dict:
    return {
        "ontologies": [
            {
                "name": o.name,
                "display_name": o.display_name,
                "version": o.version,
                "valid": not o.errors,
                "errors": o.errors,
                "phases": [p["id"] for p in o.phases],
            }
            for o in list_ontologies()
        ]
    }


@router.get("/ontologies/{name}")
def get_ontology(name: str) -> dict:
    try:
        onto = load_ontology(name)
    except OntologyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return onto.to_dict()


@router.post("/system/reload-ontologies")
def reload_ontologies() -> dict:
    ontos = reload_all()
    events.emit(
        event_type="ontology.changed",
        agg_type="system",
        agg_id="ontologies",
        actor_type="system",
        payload={"reloaded": [o.name for o in ontos]},
    )
    return {
        "status": "ok",
        "ontologies": [
            {"name": o.name, "valid": not o.errors, "errors": o.errors} for o in ontos
        ],
    }
