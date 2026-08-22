#!/usr/bin/env python
"""Cumulative smoke baseline runner (development plan military rule #4).

Runs the pytest cases marked `smoke` under app/tests/smoke in order and writes
a Markdown report to tools/smoke/reports/. The baseline only ever grows: new
iterations append cases here, and no iteration may leave the baseline red.

Usage: python tools/smoke/run_smoke.py
"""
from __future__ import annotations

import datetime as _dt
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "app"
REPORTS = Path(__file__).resolve().parents[1] / "smoke" / "reports"


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/smoke", "-m", "smoke", "-v", "--tb=short"],
        cwd=APP,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = proc.stdout + "\n" + proc.stderr
    m = re.search(r"(\d+) passed", out)
    passed = int(m.group(1)) if m else 0
    m = re.search(r"(\d+) failed", out)
    failed = int(m.group(1)) if m else 0
    m = re.search(r"(\d+) error", out)
    errors = int(m.group(1)) if m else 0
    m = re.search(r"(\d+) skipped", out)
    skipped = int(m.group(1)) if m else 0
    m = re.search(r"(\d+) deselected", out)
    deselected = int(m.group(1)) if m else 0

    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    status = "GREEN" if proc.returncode == 0 else "RED"
    report = [
        f"# Smoke Baseline Report — {stamp}",
        "",
        f"**Status: {status}** · passed {passed} · failed {failed} · error {errors}"
        f" · skipped {skipped} · deselected {deselected}",
        "",
        "```",
        out.strip(),
        "```",
    ]
    (REPORTS / f"smoke-{stamp}.md").write_text("\n".join(report), encoding="utf-8")
    (REPORTS / "latest.md").write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report[:4]))
    print(f"report: {REPORTS / 'latest.md'}")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
