"""Ontology learning: infer candidate ontology changes from project data (docs/08 §8).

semantica 融合（M4-I14）：OntologyGenerator 的"从数据推断类型"轻量版——确定性规则
扫描该本体下全部项目的投影数据 → 候选提案（candidates，带 provenance）+ 观察项
（observations，只读统计）→ 人审勾选 → apply 合并 patch 写回本体 YAML（version+1）
并发 `ontology.updated` 事件。全程无 LLM、可重放、可测。

幂等契约：apply 后重跑 learn 不再产出已应用的候选（数据已被本体覆盖）。
"""
from __future__ import annotations

import copy
import json
from collections import Counter

import yaml
from fastapi import APIRouter, HTTPException

from apm import config
from apm.core import db, events
from apm.domains.ontology import (
    KERNEL_RELATIONS,
    OntologyError,
    load_ontology,
    reload_all,
    validate_ontology_dict,
)

router = APIRouter(tags=["ontology-learn"])

FIELD_DEFS = {
    "priority": {"id": "priority", "name": "优先级", "type": "enum",
                 "values": ["P0", "P1", "P2", "P3"]},
    "estimate_hours": {"id": "estimate_hours", "name": "预估工时", "type": "number"},
}


def _ontology_path(name: str):
    if "/" in name or "\\" in name or name in ("", "."):
        raise OntologyError(f"invalid ontology name '{name}'")
    return config.settings.ontology_dir / f"{name}.yaml"


def _projects_using(name: str, conn) -> list[str]:
    return [r["id"] for r in conn.execute(
        "SELECT id FROM projects WHERE ontology = ?", (name,)).fetchall()]


def _samples(rows: list, key: str, limit: int = 3) -> list[str]:
    return [r[key] for r in rows[:limit]]


def _learn(name: str) -> dict:
    onto = load_ontology(name)
    if onto.errors:
        raise HTTPException(status_code=422, detail=f"ontology '{name}' has validation errors")
    conn = db.get_conn()
    pids = _projects_using(name, conn)
    ph = ",".join("?" for _ in pids) or "''"
    items = conn.execute(
        f"SELECT * FROM items WHERE project_id IN ({ph})", pids).fetchall() if pids else []
    rels = conn.execute(
        f"SELECT r.*, a.concept_id AS from_concept, b.concept_id AS to_concept"
        f" FROM item_relations r JOIN items a ON a.id = r.from_item"
        f" JOIN items b ON b.id = r.to_item"
        f" WHERE r.project_id IN ({ph})", pids).fetchall() if pids else []
    links = conn.execute(
        f"SELECT l.asset_id, l.target_ref, a.kind AS asset_kind, a.status AS asset_status"
        f" FROM asset_links l JOIN assets a ON a.id = l.asset_id"
        f" WHERE l.target_type = 'artifact'").fetchall()

    candidates: list[dict] = []

    # L1 add-field（infer_properties）：数据在用、本体未声明的字段 → 显式化。
    concept_by_id: dict = dict(onto.concepts)

    def declares(cid: str | None, field_id: str) -> bool:
        c = concept_by_id.get(cid or "")
        return c is not None and field_id in {f["id"] for f in c.fields}

    for field_id, field_def in FIELD_DEFS.items():
        used = [it for it in items if it["concept_id"] and it[field_id] is not None]
        by_concept: Counter = Counter(
            it["concept_id"] for it in used if not declares(it["concept_id"], field_id))
        for cid, count in by_concept.items():
            candidates.append({
                "id": f"add-field:{cid}:{field_id}",
                "kind": "add_field",
                "summary": f"概念「{concept_by_id[cid].name}」的 {count} 个工作项在用字段"
                           f" {field_id}，但本体未声明",
                "patch": {"op": "add_field", "concept": cid, "field": dict(field_def)},
                "provenance": {"rule": "L1-add-field", "support": count,
                               "sample_item_ids": _samples(used, "id")},
            })

    # L2 register-relation（一致性护栏）：数据中存在未注册的关系类型。
    registered = set(onto.relation_ids()) | set(KERNEL_RELATIONS)
    by_type: dict[str, list] = {}
    for r in rels:
        if r["relation_type"] not in registered:
            by_type.setdefault(r["relation_type"], []).append(r)
    for rtype, rows in by_type.items():
        pairs = Counter((r["from_concept"], r["to_concept"]) for r in rows)
        (dom, rng), _ = pairs.most_common(1)[0]
        candidates.append({
            "id": f"register-relation:{rtype}",
            "kind": "add_relation",
            "summary": f"数据中存在 {len(rows)} 条未注册关系「{rtype}」"
                       f"（{dom} → {rng}）",
            "patch": {"op": "add_relation",
                      "relation": {"id": rtype, "name": rtype, "domain": dom, "range": rng}},
            "provenance": {"rule": "L2-register-relation", "support": len(rows),
                           "sample_item_ids": _samples(rows, "from_item")},
        })

    # L3 wire-deposit（沉淀链接补全）：已链接工件但缺少 deposits_to 映射。
    declared: dict[str, list[str]] = {}  # artifact_kind -> [concept_id]
    for c in onto.concepts.values():
        for ak in c.artifact_kinds:
            ak_id = ak["id"] if isinstance(ak, dict) else ak
            declared.setdefault(ak_id, []).append(c.id)
    deposits_to: dict[str, str] = {}
    for ak in onto.concepts.values():
        for entry in ak.artifact_kinds:
            if isinstance(entry, dict) and entry.get("deposits_to"):
                deposits_to[entry["id"]] = entry["deposits_to"]
    seen_link: dict[tuple, list] = {}
    for l in links:
        try:
            target = json.loads(l["target_ref"]) if isinstance(l["target_ref"], str) else {}
        except (json.JSONDecodeError, TypeError):
            continue
        parts = (target.get("path") or "").split("/")
        if len(parts) < 3 or parts[0] != "artifacts":
            continue
        artifact_kind = parts[1]
        if l["asset_status"] != "published":
            continue
        seen_link.setdefault((artifact_kind, l["asset_kind"]), []).append(l["asset_id"])
    for (artifact_kind, asset_kind), asset_ids in seen_link.items():
        if deposits_to.get(artifact_kind) == asset_kind:
            continue  # 已映射（或指向别处——留给 I15 影响分析）
        for cid in declared.get(artifact_kind, []):
            candidates.append({
                "id": f"wire-deposit:{cid}:{artifact_kind}:{asset_kind}",
                "kind": "wire_deposit",
                "summary": f"已发布资产类型 {asset_kind} 引用工件 {artifact_kind}，"
                           f"但概念「{concept_by_id[cid].name}」未声明 deposits_to",
                "patch": {"op": "wire_deposit", "concept": cid,
                          "artifact_kind": artifact_kind, "deposits_to": asset_kind},
                "provenance": {"rule": "L3-wire-deposit", "support": len(asset_ids),
                               "sample_asset_ids": asset_ids[:3]},
            })

    # L4 add-role（角色覆盖）：Run 实际用过的角色补进概念绑定。
    if pids:
        run_rows = conn.execute(
            f"SELECT r.agent_role, r.id AS run_id, i.concept_id"
            f" FROM runs r JOIN items i ON i.id = r.item_id"
            f" WHERE r.project_id IN ({ph}) AND r.agent_role IS NOT NULL"
            f" AND i.concept_id IS NOT NULL", pids).fetchall()
        by_pair: dict[tuple, list] = {}
        for r in run_rows:
            by_pair.setdefault((r["concept_id"], r["agent_role"]), []).append(r)
        for (cid, role), rows in by_pair.items():
            if cid in concept_by_id and role not in concept_by_id[cid].agent_roles:
                candidates.append({
                    "id": f"add-role:{cid}:{role}",
                    "kind": "add_role",
                    "summary": f"角色 {role} 已在概念「{concept_by_id[cid].name}」的"
                               f" {len(rows)} 个工作项上执行，但未绑定",
                    "patch": {"op": "add_role", "concept": cid, "role": role},
                    "provenance": {"rule": "L4-add-role", "support": len(rows),
                                   "sample_run_ids": _samples(rows, "run_id")},
                })

    # observations：零使用概念（semantica optimize 的"剪枝建议"，只读不进 apply）。
    used_concepts = {it["concept_id"] for it in items if it["concept_id"]}
    unused = [c.id for c in onto.concepts.values() if c.id not in used_concepts]

    return {
        "ontology": name,
        "version": onto.version,
        "scanned": {"projects": len(pids), "items": len(items),
                    "relations": len(rels), "artifact_links": len(links)},
        "candidates": candidates,
        "observations": {"unused_concepts": unused},
    }


def _apply(name: str, body: dict) -> dict:
    scan = _learn(name)
    by_id = {c["id"]: c for c in scan["candidates"]}
    chosen_ids = body.get("candidate_ids") or []
    unknown = [cid for cid in chosen_ids if cid not in by_id]
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown or stale candidate ids: {unknown}")
    if not chosen_ids:
        raise HTTPException(status_code=422, detail="candidate_ids is required")

    path = _ontology_path(name)
    if not path.exists():
        raise OntologyError(f"ontology file not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    original = copy.deepcopy(raw)  # pre-apply state, archived as v{old} below
    concepts = {c["id"]: c for c in raw.get("concepts", [])}

    for cid in chosen_ids:
        patch = by_id[cid]["patch"]
        concept = concepts.get(patch.get("concept"))
        if patch["op"] == "add_field" and concept is not None:
            concept.setdefault("fields", []).append(dict(patch["field"]))
        elif patch["op"] == "add_relation":
            raw.setdefault("relations", []).append(dict(patch["relation"]))
        elif patch["op"] == "wire_deposit" and concept is not None:
            for ak in concept.get("artifact_kinds", []):
                if isinstance(ak, dict) and ak["id"] == patch["artifact_kind"]:
                    ak["deposits_to"] = patch["deposits_to"]
                elif isinstance(ak, str) and ak == patch["artifact_kind"]:
                    concept["artifact_kinds"][concept["artifact_kinds"].index(ak)] = {
                        "id": ak, "deposits_to": patch["deposits_to"]}
        elif patch["op"] == "add_role" and concept is not None:
            concept.setdefault("agent_roles", []).append(patch["role"])

    errors = validate_ontology_dict(raw)
    if errors:
        raise HTTPException(status_code=422, detail={"apply_failed_validation": errors})
    old_version = int(raw.get("version") or 1)
    raw["version"] = old_version + 1

    # Version snapshots (I15): keep both sides of this transition diffable.
    from apm.domains.ontology_versions import snapshot_version

    snapshot_version(name, old_version, original)
    snapshot_version(name, raw["version"], raw)

    path.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")

    applied = [by_id[cid] for cid in chosen_ids]
    event = events.emit(
        event_type="ontology.updated",
        agg_type="ontology",
        agg_id=name,
        actor_type="human",
        actor_id=config.settings.user_id,
        payload={
            "version": raw["version"],
            "previous_version": old_version,
            "applied": [{"id": c["id"], "kind": c["kind"], "summary": c["summary"],
                         "provenance_rule": c["provenance"]["rule"]}
                        for c in applied],
            "summary": f"本体学习应用 {len(applied)} 项候选（v{old_version} → v{raw['version']}）",
        },
    )
    reload_all()
    onto = load_ontology(name)
    return {"name": name, "version": onto.version, "event_id": event.id,
            "applied": applied, "errors": onto.errors}


@router.post("/ontologies/{name}/learn")
def learn(name: str) -> dict:
    return _learn(name)


@router.post("/ontologies/{name}/apply")
def apply_candidates(name: str, body: dict) -> dict:
    return _apply(name, body)
