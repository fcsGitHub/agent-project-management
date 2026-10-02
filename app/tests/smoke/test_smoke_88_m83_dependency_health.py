"""Smoke 88 (M83): dependency health — ① the requirements.txt floors are
satisfied by the installed environment and pip-check-clean within AgentPM's
dependency closure (shared-env neighbours pinning older versions are out of
scope: docker deploys build a fresh env from requirements.txt); ② the
release pin: APP_VERSION carries the current release (smoke 86 locks cross-anchor agreement,
this file pins the current release value); ③ deprecation regression locks:
the starlette testclient stays on httpx2 (no "httpx with" warning at import)
and no per-request cookies= usage remains in the test suite."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import warnings

import pytest

from apm.version import APP_VERSION

from tests.smoke.test_smoke_82_m77_delivery_surface import ROOT


def _req_packages() -> dict[str, str]:
    """requirements.txt → {normalized name: floor version}."""
    out: dict[str, str] = {}
    req = (ROOT / "app" / "requirements.txt").read_text(encoding="utf-8")
    for ln in req.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9_.-]+)>=([0-9][^;\s]*)", ln)
        assert m, f"requirements line not in name>=version form: {ln}"
        out[m.group(1).lower().replace("_", "-")] = m.group(2)
    return out


@pytest.mark.smoke
def test_smoke_88_dependency_closure_consistency():
    reqs = _req_packages()
    # ① 装机版本满足每个声明下限
    for name, floor in reqs.items():
        r = subprocess.run([sys.executable, "-m", "pip", "show", name],
                           capture_output=True, text=True)
        m = re.search(r"^Version: (.+)$", r.stdout, re.M)
        assert m, f"{name} not installed"
        installed, floor_parts = m.group(1).split("."), floor.split(".")
        assert installed >= floor_parts or _vnum(installed) >= _vnum(floor_parts), \
            f"{name}: installed {m.group(1)} < floor {floor}"

    # ② 闭包内 pip check 干净：冲突行的 dependent 不属于 requirements 集
    #   （共享环境的邻居包 pin 旧版属于邻居的事——docker 部署从 requirements 全新构建）
    r = subprocess.run([sys.executable, "-m", "pip", "check"],
                       capture_output=True, text=True)
    lines = [ln for ln in r.stdout.splitlines() if "has requirement" in ln]
    for ln in lines:
        dependent = ln.split(" has requirement", 1)[0].strip().lower().replace("_", "-")
        assert dependent not in reqs, f"closure conflict: {ln}"

    # ③ 弃用回归锁：testclient 走 httpx2——import 不再发「httpx with」弃用警告
    import importlib

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.reload(importlib.import_module("fastapi.testclient"))
    assert not [w for w in caught if "httpx with" in str(w.message)], \
        "starlette testclient httpx deprecation is back"

    # ④ per-request cookies=<...> 用法零残留（testclient 运行时弃用源）
    tests_dir = ROOT / "app" / "tests"
    for py in tests_dir.rglob("*.py"):
        src = py.read_text(encoding="utf-8")
        assert not re.search(r".(get|post|put|patch|delete|request)\(\s*[^)]*cookies=\{", src), \
            f"per-request cookies usage in {py.name}"


def _vnum(parts: list[str]) -> tuple[int, ...]:
    nums = []
    for p in parts:
        m = re.match(r"^(\d+)", p)
        nums.append(int(m.group(1)) if m else 0)
    return tuple(nums)


@pytest.mark.smoke
def test_smoke_88_release_pin():
    # 当前发布钉（冒烟 86 锁四锚一致，这里钉「这一版是几」——每次发布只改这一行）
    assert APP_VERSION == "0.12.0"

    pkg = json.loads((ROOT / "web" / "package.json").read_text(encoding="utf-8"))
    assert pkg["version"] == APP_VERSION

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"版本：v{APP_VERSION}" in readme

    cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert re.search(rf"^## \[{re.escape(APP_VERSION)}\] — 2026-10-02", cl, re.M)
    assert re.search(r"^## \[Unreleased\]", cl, re.M)  # 新空段在
