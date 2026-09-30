"""Smoke 82 (M77): delivery-surface freshness — ① the env-doc drift check
script passes (and genuinely fails when a var is undocumented: the red path
is self-proven inline); ② .env.example documents every env the code names
(the M13/M26/M67 entry points are discoverable again); ③ docker-compose
passes the same set through; ④ the README carries no stale metric numbers
(freshness is anchored to docs/10 §7, the single progress source)."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _env_names(text: str) -> set[str]:
    return set(re.findall(r"APM_[A-Z_]+", text))


@pytest.mark.smoke
def test_smoke_82_m77_delivery_surface():
    code: set[str] = set()
    for f in (ROOT / "app" / "apm").rglob("*.py"):
        if "__pycache__" in str(f):
            continue
        code |= _env_names(f.read_text(encoding="utf-8", errors="replace"))
    assert code, "no APM_* env found — glob broken?"

    # ① drift check script: green as-is, red when a var is stripped from the doc
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "check_env_doc.py")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stdout + r.stderr

    example_path = ROOT / ".env.example"
    original = example_path.read_text(encoding="utf-8")
    try:
        example_path.write_text(
            original.replace("APM_METRICS_ENABLED", "APM_METRICS_REDACTED"), encoding="utf-8", newline="\n")
        r2 = subprocess.run([sys.executable, str(ROOT / "tools" / "check_env_doc.py")],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert r2.returncode == 1, "drift check must fail when a var is undocumented"
        assert "APM_METRICS_ENABLED" in r2.stdout
    finally:
        example_path.write_text(original, encoding="utf-8", newline="\n")

    # ②③ the four previously-invisible entry points are documented + passed through
    example = example_path.read_text(encoding="utf-8")
    for var in ("APM_SMTP_HOST", "APM_SMTP_FROM", "APM_OIDC_ALLOWED_GROUPS", "APM_METRICS_ENABLED"):
        assert var in example, var
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    for var in ("APM_SMTP_HOST", "APM_OIDC_ALLOWED_GROUPS", "APM_METRICS_ENABLED"):
        assert f"${{{var}:-" in compose, var

    # ④ README carries no stale metric numbers (the M4-era rot is gone)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "冒烟基线 7 条" not in readme
    assert "I15 语义 diff" not in readme and "I16 CQ 检查进行中" not in readme
    assert "docs/10-development-plan.md" in readme  # progress source link intact
