"""Role loading: agents/roles/*.yaml → typed role registry (docs/07 §2)."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import yaml

from apm import config


class Role:
    def __init__(self, raw: dict[str, Any], path: Path):
        self.id: str = raw["id"]
        self.display_name: str = raw.get("display_name", self.id)
        self.concepts: list[str] = raw.get("concepts", [])
        self.model: dict[str, Any] = raw.get("model", {})
        self.system_prompt_file: str = raw.get("system_prompt_file", "")
        self.tools: list[str] = raw.get("tools", [])
        self.output: dict[str, Any] = raw.get("output", {})
        self.limits: dict[str, Any] = raw.get("limits", {})
        self.path = path

    def system_prompt(self) -> str:
        p = config.settings.agents_dir / self.system_prompt_file
        if p.exists():
            return p.read_text(encoding="utf-8")
        return f"你是 {self.display_name}。"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "concepts": self.concepts,
            "model": self.model,
            "tools": self.tools,
            "output": self.output,
            "limits": self.limits,
            "system_prompt": self.system_prompt(),
        }


_lock = threading.Lock()
_cache: dict[str, Role] = {}


def load_roles() -> dict[str, Role]:
    with _lock:
        if _cache:
            return _cache
        d = config.settings.agents_dir / "roles"
        if d.exists():
            for f in sorted(d.glob("*.yaml")):
                try:
                    raw = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
                    role = Role(raw, f)
                    _cache[role.id] = role
                except Exception:
                    continue
        return _cache


def get_role(role_id: str) -> Role:
    roles = load_roles()
    if role_id not in roles:
        raise KeyError(f"unknown agent role '{role_id}' (available: {sorted(roles)})")
    return roles[role_id]


def reset_roles() -> None:
    with _lock:
        _cache.clear()
