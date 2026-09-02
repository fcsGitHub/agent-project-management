"""Ontology template packs: export / import (M5-I18, docs/08 §6).

一张模板包 = ontology.yaml + 概念引用的角色 YAML + 角色提示词模板（L4），
单 JSON 交付、跨项目/跨仓复用。导入 = 改名防冲突 + 校验器把关 + 落盘 +
角色文件「存在即复用、缺失才创建」（不覆盖既有角色）+ ontology.imported 事件。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException

from apm import config
from apm.core import events
from apm.domains.ontology import OntologyError, load_ontology, reload_all, validate_ontology_dict
from apm.domains.ontology_versions import _load_live
from apm.runtime import roles as roles_mod

router = APIRouter(tags=["ontology-pack"])

PACK_FORMAT = "agentpm-ontology-pack"
PACK_VERSION = 1


def _check_name(name: str) -> None:
    if "/" in name or "\\" in name or name in ("", "."):
        raise HTTPException(status_code=422, detail=f"invalid ontology name '{name}'")


def _read_role_asset(rid: str) -> tuple[dict, str | None]:
    base = config.settings.agents_dir
    cfg = yaml.safe_load((base / "roles" / f"{rid}.yaml").read_text(encoding="utf-8")) or {}
    prompt_file = cfg.get("system_prompt_file")
    prompt = None
    if prompt_file:
        p = base / prompt_file
        if p.exists():
            prompt = p.read_text(encoding="utf-8")
    return cfg, prompt


@router.get("/ontologies/{name}/export")
def export(name: str) -> dict:
    """Template pack: ontology + referenced role YAMLs + their prompt templates."""
    _check_name(name)
    try:
        onto = load_ontology(name)
    except OntologyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if onto.errors:
        raise HTTPException(status_code=422, detail=f"ontology '{name}' has validation errors")

    role_ids = sorted({r for c in onto.concepts.values() for r in c.agent_roles})
    roles: list[dict[str, Any]] = []
    missing: list[str] = []
    for rid in role_ids:
        path = config.settings.agents_dir / "roles" / f"{rid}.yaml"
        if not path.exists():
            missing.append(rid)
            continue
        cfg, prompt = _read_role_asset(rid)
        roles.append({"id": rid, "config": cfg, "prompt": prompt})
    return {
        "format": PACK_FORMAT,
        "pack_version": PACK_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ontology": _load_live(name),
        "roles": roles,
        "missing_roles": missing,
    }


@router.post("/ontologies/import")
def import_pack(body: dict) -> dict:
    pack = body.get("pack")
    as_name = body.get("as_name")
    if not isinstance(pack, dict) or pack.get("format") != PACK_FORMAT:
        raise HTTPException(status_code=422, detail=f"pack format must be '{PACK_FORMAT}'")
    _check_name(as_name or "")
    raw = pack.get("ontology")
    if not isinstance(raw, dict):
        raise HTTPException(status_code=422, detail="pack.ontology is missing or empty")
    target = config.settings.ontology_dir / f"{as_name}.yaml"
    if target.exists():
        raise HTTPException(status_code=409, detail=f"ontology '{as_name}' already exists")

    raw["name"] = as_name
    errors = validate_ontology_dict(raw)
    if errors:
        raise HTTPException(status_code=422, detail={"invalid_pack": errors})

    roles_out: list[dict[str, str]] = []
    base = config.settings.agents_dir
    for r in pack.get("roles", []):
        cfg = r.get("config") or {}
        rid = cfg.get("id") or r.get("id")
        if not rid:
            continue
        role_path = base / "roles" / f"{rid}.yaml"
        action = "reused"
        if not role_path.exists():  # 存在即复用，绝不覆盖既有角色
            role_path.parent.mkdir(parents=True, exist_ok=True)
            role_path.write_text(
                yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
            prompt = r.get("prompt")
            pf = cfg.get("system_prompt_file")
            if pf and prompt is not None:
                ppath = base / pf
                ppath.parent.mkdir(parents=True, exist_ok=True)
                if not ppath.exists():
                    ppath.write_text(prompt, encoding="utf-8")
            action = "created"
        roles_out.append({"id": rid, "action": action})

    version = int(raw.get("version") or 1)
    raw["version"] = version
    target.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    events.emit(
        event_type="ontology.imported",
        agg_type="ontology",
        agg_id=as_name,
        actor_type="human",
        actor_id=config.settings.user_id,
        payload={"version": version, "source_format": pack.get("format"),
                 "roles": roles_out,
                 "summary": f"导入本体模板包 → {as_name}（v{version}）"},
    )
    reload_all()
    roles_mod.reset_roles()
    return {"name": as_name, "version": version, "roles": roles_out,
            "missing_roles": pack.get("missing_roles") or [], "errors": []}
