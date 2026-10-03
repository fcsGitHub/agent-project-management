"""Smoke 86 (M81): release engineering — ① version anchors agree: the single
source (apm/version.py), /api/health, web/package.json, and the README line
all carry 0.6.0 (M81-I243 — the old 0.1.0 dead literal is locked out);
② CHANGELOG.md is Keep-a-Changelog shaped: header, Unreleased, one section
per tag; ③ git carries both annotated tags (v0.5.0 retro-active on the M77
closure, v0.6.0 on this closure); ④ docs/11 stays unfrozen (M81 header)."""
from __future__ import annotations

import json
import re
import subprocess

import pytest

from apm.version import APP_VERSION

from tests.smoke.test_smoke_82_m77_delivery_surface import ROOT


@pytest.mark.smoke
def test_smoke_86_version_anchors_agree():
    # M83-I251：字面量钉改锚定一致性——「当前版本是几」由冒烟 88 钉，此处锁四锚一致与 semver 形态
    assert re.match(r"^\d+\.\d+\.\d+$", APP_VERSION)

    pkg = json.loads((ROOT / "web" / "package.json").read_text(encoding="utf-8"))
    assert pkg["version"] == APP_VERSION

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"版本：v{APP_VERSION}" in readme

    # /api/health 读单源（test_version 已断言运行时值——这里锁文件层不再出现死字面量）
    sysmod = (ROOT / "app" / "apm" / "domains" / "system.py").read_text(encoding="utf-8")
    assert '"0.1.0"' not in sysmod


@pytest.mark.smoke
def test_smoke_86_changelog_shape_and_tags():
    cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert re.search(r"^## \[Unreleased\]", cl, re.M)
    assert re.search(r"^## \[0\.6\.0\] — 2026-10-01", cl, re.M)
    assert re.search(r"^## \[0\.5\.0\] — 2026-09-30", cl, re.M)
    assert "### Security" in cl  # Keep a Changelog 分类在用

    def tags() -> list[str]:
        out = subprocess.run(["git", "tag"], cwd=ROOT, capture_output=True, text=True)
        return out.stdout.split()

    for t in ("v0.5.0", "v0.6.0"):
        assert t in tags(), f"missing tag {t}"
    # annotated（携带 tagger 元信息）
    out = subprocess.run(["git", "cat-file", "-t", "v0.6.0"], cwd=ROOT,
                         capture_output=True, text=True)
    assert out.stdout.strip() == "tag"

    docs11 = (ROOT / "docs" / "11-network-deploy.md").read_text(encoding="utf-8")
    # 解冻代标记随最新解冻轮更新（M81-I244 → M86-I262）——锁「docs/11 未冻结在旧代」
    assert "M105-I319 解冻" in docs11
