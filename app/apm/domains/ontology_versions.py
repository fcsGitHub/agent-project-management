"""Ontology versioning: snapshots, semantic diff, impact analysis, history (M4-I15).

semantica VersionManager 轻量版（docs/08 §8.1）：apply 时落两份快照（旧版+新版）到
`data/ontology_history/<name>/v<N>.yaml`；diff 在结构层（concepts/relations/phases/
asset_kinds 的增删改）而非文本层；影响分析扫描投影数据——被删概念的引用 = 阻塞级
（数据与本体会失配），其余为警告。版本真源 = YAML version + ontology.updated 事件。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException

from apm import config
from apm.core import db

router = APIRouter(tags=["ontology-versions"])


def _check_name(name: str) -> None:
    if "/" in name or "\\" in name or name in ("", "."):
        raise HTTPException(status_code=422, detail=f"invalid ontology name '{name}'")


def _ontology_file(name: str) -> Path:
    _check_name(name)
    return config.settings.ontology_dir / f"{name}.yaml"


def _history_dir(name: str) -> Path:
    _check_name(name)
    return config.settings.data_dir / "ontology_history" / name


def snapshot_version(name: str, version: int, raw: dict) -> Path:
    """Archive one ontology version (apply stores both old and new)."""
    d = _history_dir(name)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"v{version}.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _load_live(name: str) -> dict:
    path = _ontology_file(name)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"ontology '{name}' not found")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def current_version(name: str) -> int:
    return int(_load_live(name).get("version") or 1)


def list_snapshots(name: str) -> list[int]:
    d = _history_dir(name)
    if not d.exists():
        return []
    out = []
    for f in d.glob("v*.yaml"):
        try:
            out.append(int(f.stem[1:]))
        except ValueError:
            continue
    return sorted(out)


def load_from_state(name: str, version: int) -> dict:
    """Left side of a diff: the archived snapshot is canonical for that version."""
    path = _history_dir(name) / f"v{version}.yaml"
    if path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if version == current_version(name):
        return _load_live(name)
    raise HTTPException(
        status_code=404,
        detail=f"no snapshot for {name} v{version} (snapshots exist for {list_snapshots(name)};"
               f" pre-M4 versions were never archived)",
    )


def load_to_state(name: str, version: int) -> dict:
    """Right side of a diff: the current version is always the live file, so
    hand-edits on disk can be impact-checked before they are ever loaded."""
    if version == current_version(name):
        return _load_live(name)
    path = _history_dir(name) / f"v{version}.yaml"
    if path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raise HTTPException(
        status_code=404,
        detail=f"no snapshot for {name} v{version} (snapshots exist for {list_snapshots(name)})",
    )


# ------------------------------------------------------------ semantic diff
def _by_id(rows: list) -> dict[str, dict]:
    return {r.get("id"): r for r in rows if isinstance(r, dict)}


def _pair_diff(a: list, b: list) -> dict:
    ia, ib = _by_id(a), _by_id(b)
    pick = lambda idx, wanted: (  # noqa: E731
        [{k: idx[cid][k] for k in keys if k in idx[cid]} for cid in sorted(wanted)]
    )
    keys = ("id", "name")
    return {"added": pick(ib, ib.keys() - ia.keys()),
            "removed": pick(ia, ia.keys() - ib.keys())}


def _concept_changes(ca: dict, cb: dict) -> list[dict]:
    changes: list[dict] = []
    if ca.get("name") != cb.get("name"):
        changes.append({"type": "renamed", "detail": f"{ca.get('name')} → {cb.get('name')}"})
    if ca.get("icon") != cb.get("icon"):
        changes.append({"type": "icon-changed", "detail": f"{ca.get('icon')} → {cb.get('icon')}"})
    if ca.get("default_phase") != cb.get("default_phase"):
        changes.append({"type": "phase-changed",
                        "detail": f"{ca.get('default_phase')} → {cb.get('default_phase')}"})
    fa, fb = _by_id(ca.get("fields", [])), _by_id(cb.get("fields", []))
    for k in fb.keys() - fa.keys():
        changes.append({"type": "field-added", "detail": k})
    for k in fa.keys() - fb.keys():
        changes.append({"type": "field-removed", "detail": k})
    for k in fa.keys() & fb.keys():
        if {x: fa[k].get(x) for x in ("type", "values", "name")} != {x: fb[k].get(x) for x in ("type", "values", "name")}:
            changes.append({"type": "field-changed", "detail": k})
    sa, sb = _by_id(ca.get("states", [])), _by_id(cb.get("states", []))
    for k in sb.keys() - sa.keys():
        changes.append({"type": "state-added", "detail": k})
    for k in sa.keys() - sb.keys():
        changes.append({"type": "state-removed", "detail": k})
    ra, rb = set(ca.get("agent_roles", [])), set(cb.get("agent_roles", []))
    for k in sorted(rb - ra):
        changes.append({"type": "role-added", "detail": k})
    for k in sorted(ra - rb):
        changes.append({"type": "role-removed", "detail": k})
    aka, akb = _by_id(ca.get("artifact_kinds", [])), _by_id(cb.get("artifact_kinds", []))
    for k in akb.keys() - aka.keys():
        changes.append({"type": "artifact-kind-added", "detail": k})
    for k in aka.keys() - akb.keys():
        changes.append({"type": "artifact-kind-removed", "detail": k})
    return changes


def semantic_diff(a: dict, b: dict) -> dict:
    """Structured diff between two ontology dicts (docs/08 §8.1, I15)."""
    ca, cb = _by_id(a.get("concepts", [])), _by_id(b.get("concepts", []))
    modified = []
    for k in ca.keys() & cb.keys():
        changes = _concept_changes(ca[k], cb[k])
        if changes:
            modified.append({"id": k, "name": cb[k].get("name", k), "changes": changes})
    concepts = _pair_diff(a.get("concepts", []), b.get("concepts", []))
    concepts["modified"] = modified
    return {
        "concepts": concepts,
        "relations": _pair_diff(a.get("relations", []), b.get("relations", [])),
        "phases": _pair_diff(a.get("phases", []), b.get("phases", [])),
        "asset_kinds": _pair_diff(a.get("asset_kinds", []), b.get("asset_kinds", [])),
        "libraries": _pair_diff(a.get("libraries", []), b.get("libraries", [])),
    }


# ------------------------------------------------------------ impact analysis
def _projects_using(name: str, conn) -> list[str]:
    return [r["id"] for r in conn.execute(
        "SELECT id FROM projects WHERE ontology = ?", (name,)).fetchall()]


def impact_analysis(name: str, from_raw: dict, to_raw: dict) -> dict:
    """References from live data to things the change removes → blocking (docs/08 §8)."""
    conn = db.get_conn()
    pids = _projects_using(name, conn)
    ph = ",".join("?" for _ in pids) or "''"
    items = conn.execute(
        f"SELECT id, title, concept_id, project_id FROM items"
        f" WHERE project_id IN ({ph})", pids).fetchall() if pids else []
    rels = conn.execute(
        f"SELECT id, relation_type FROM item_relations WHERE project_id IN ({ph})",
        pids).fetchall() if pids else []
    assets = conn.execute("SELECT id, kind FROM assets").fetchall()

    diff = semantic_diff(from_raw, to_raw)
    removed_concepts = {c["id"] for c in diff["concepts"]["removed"]}
    removed_relations = {r["id"] for r in diff["relations"]["removed"]}
    removed_phases = {p["id"] for p in diff["phases"]["removed"]}
    removed_asset_kinds = {k["id"] for k in diff["asset_kinds"]["removed"]}

    blocking: list[dict] = []
    warnings: list[dict] = []
    for cid in sorted(removed_concepts):
        refs = [it for it in items if it["concept_id"] == cid]
        if refs:
            blocking.append({
                "kind": "concept-removed-in-use", "concept": cid,
                "detail": f"概念「{cid}」仍被 {len(refs)} 个工作项引用，删除将破坏类型系统",
                "item_count": len(refs),
                "sample_items": [{"id": it["id"], "title": it["title"]} for it in refs[:5]],
            })
        else:
            warnings.append({"kind": "concept-removed-unused", "concept": cid,
                             "detail": f"概念「{cid}」无任何工作项引用，删除安全"})
    for rid in sorted(removed_relations):
        rows = [r for r in rels if r["relation_type"] == rid]
        if rows:
            blocking.append({
                "kind": "relation-removed-in-use", "relation": rid,
                "detail": f"关系「{rid}」仍有 {len(rows)} 条数据引用（L2 会重新提议注册）",
                "reference_count": len(rows),
            })
        else:
            warnings.append({"kind": "relation-removed-unused", "relation": rid,
                             "detail": f"关系「{rid}」无数据引用，删除安全"})
    live_concepts = to_raw.get("concepts", [])
    for p in sorted(removed_phases):
        if any(c.get("default_phase") == p for c in live_concepts):
            warnings.append({"kind": "phase-still-referenced", "phase": p,
                             "detail": f"阶段「{p}」仍被保留概念的 default_phase 引用"})
    for k in sorted(removed_asset_kinds):
        n = len([a for a in assets if a["kind"] == k])
        if n:
            warnings.append({"kind": "asset-kind-still-used", "asset_kind": k,
                             "detail": f"资产类型「{k}」仍有 {n} 个资产在使用"})
    return {"blocking": blocking, "warnings": warnings}


# ------------------------------------------------------------ API
def _fmt_pair_diff(label: str, d: dict) -> list[str]:
    parts = []
    if d["added"]:
        parts.append(f"+{len(d['added'])} {label}")
    if d["removed"]:
        parts.append(f"-{len(d['removed'])} {label}")
    return parts


@router.get("/ontologies/{name}/history")
def history(name: str) -> dict:
    """ontology.updated event timeline + available snapshots (I15)."""
    _check_name(name)
    rows = db.get_conn().execute(
        "SELECT id, ts, actor_id, payload FROM events"
        " WHERE event_type = 'ontology.updated' AND agg_type = 'ontology' AND agg_id = ?"
        " ORDER BY id ASC", (name,)).fetchall()
    hist = []
    for r in rows:
        p = json.loads(r["payload"])
        hist.append({
            "event_id": r["id"], "ts": r["ts"], "actor_id": r["actor_id"],
            "previous_version": p.get("previous_version"), "version": p.get("version"),
            "applied_count": len(p.get("applied", [])), "applied": p.get("applied", []),
            "summary": p.get("summary"),
        })
    return {"name": name, "current_version": current_version(name),
            "snapshots": list_snapshots(name), "history": hist}


@router.get("/ontologies/{name}/diff")
def diff(name: str, from_version: int | None = None, to_version: int | None = None) -> dict:
    """Semantic diff between two ontology versions + data impact analysis (I15).

    `to_version` defaults to the current (live) file, so hand-edits on disk can be
    impact-checked before they are ever loaded; missing snapshots are a 404.
    """
    cur = current_version(name)
    fv = cur - 1 if from_version is None else from_version
    tv = cur if to_version is None else to_version
    if fv < 1 or tv < 1:
        raise HTTPException(status_code=422, detail="versions start at 1")
    from_raw = load_from_state(name, fv)
    to_raw = load_to_state(name, tv)

    from apm.domains.ontology import validate_ontology_dict

    to_errors = validate_ontology_dict(to_raw)
    d = semantic_diff(from_raw, to_raw)
    impact = impact_analysis(name, from_raw, to_raw)

    parts = []
    for label, key in (("概念", "concepts"), ("关系", "relations"),
                       ("阶段", "phases"), ("资产类型", "asset_kinds"), ("库", "libraries")):
        parts.extend(_fmt_pair_diff(label, d[key]))
    if d["concepts"]["modified"]:
        parts.append(f"~{len(d['concepts']['modified'])} 概念修改")
    parts.sort(key=lambda s: not s.startswith("~"))  # additions/removals first, modifications last
    summary = " · ".join(parts) if parts else "无结构差异"

    return {
        "name": name, "from_version": fv, "to_version": tv,
        "diff": d, "impact": impact, "summary": summary,
        "to_validation_errors": to_errors,
    }
