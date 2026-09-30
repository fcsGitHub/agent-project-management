#!/usr/bin/env python
"""M77-I231: env documentation drift check (envsync check-mode, zero-dep).

Greps every APM_* name referenced in app/apm source and compares against
.env.example (and docker-compose.yml passthrough). A variable that exists in
code but is documented nowhere is a config entry users cannot discover —
exit 1 so the smoke chain (or a human, at closure time) notices.

Usage: python tools/check_env_doc.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def env_names_in(text: str) -> set[str]:
    return set(re.findall(r"APM_[A-Z_]+", text))


def main() -> int:
    code: set[str] = set()
    for f in (ROOT / "app" / "apm").rglob("*.py"):
        if "__pycache__" in str(f):
            continue
        code |= env_names_in(f.read_text(encoding="utf-8", errors="replace"))

    example = env_names_in((ROOT / ".env.example").read_text(encoding="utf-8"))
    compose = env_names_in((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    # compose passthroughs listed via ${VAR:-default} interpolations count too
    compose |= set(re.findall(r"\$\{(APM_[A-Z_]+)", (ROOT / "docker-compose.yml").read_text(encoding="utf-8")))

    undocumented = sorted(code - example)
    not_passed = sorted(code - example - compose)

    print(f"env names in code: {len(code)} · in .env.example: {len(example)} · composed: {len(compose)}")
    if undocumented:
        print("MISSING in .env.example:", ", ".join(undocumented))
    if not_passed:
        print("MISSING in docker-compose passthrough:", ", ".join(not_passed))
    if undocumented or not_passed:
        return 1
    print("env docs in sync ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
