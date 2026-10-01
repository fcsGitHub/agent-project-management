"""Smoke 89 (M84): test-date robustness — ① the check_test_dates.py
reconciliation passes (every file with hardcoded ISO dates that also
references a real-clock-windowed endpoint is adjudicated in the REVIEWED
ledger); ② the red path is self-proven: a synthetic unregistered file with a
hardcoded date hitting /my/timelog IS flagged, and ledger-covered files are
not; ③ the ledger is complete: every entry exists on disk and names live
windowed endpoints."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.smoke.test_smoke_82_m77_delivery_surface import ROOT


@pytest.mark.smoke
def test_smoke_89_check_test_dates_and_red_proof():
    # ①对账脚本绿
    r = subprocess.run([sys.executable, "tools/check_test_dates.py"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    # ②故意红自证：合成「硬编码日期×窗口端点」的未登记文件必须被揪出；
    #   移入台账或删除后恢复绿。真扫真删——不 mock scan()。
    sentinel = ROOT / "app" / "tests" / "test_zz_smoke89_sentinel.py"
    sentinel.write_text(
        '"""临时哨兵：冒烟 89 故意红自证（跑完即删）。"""\n'
        'def test_zz_sentinel(client):\n'
        '    client.get("/api/my/timelog")\n'
        '    assert client.post("/api/items/x/time_entries",\n'
        '                       json={"minutes": 1, "spent_on": "2026-09-04"}).status_code == 404\n',
        encoding="utf-8")
    try:
        r = subprocess.run([sys.executable, "tools/check_test_dates.py"],
                           cwd=ROOT, capture_output=True, text=True)
        assert r.returncode == 1, "sentinel must be flagged"
        assert "test_zz_smoke89_sentinel.py" in r.stdout
    finally:
        sentinel.unlink()
    r = subprocess.run([sys.executable, "tools/check_test_dates.py"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0  # 删除哨兵后恢复绿

    # ③无日期字面量的窗口端点文件不误伤（test_timelog 已动态锚定但仍在台账——
    #   台账是「已定类」记录而非「有问题」记录；此处验证未登记的无日期文件不红）
    assert "app/tests/conftest.py" not in (r.stdout)


@pytest.mark.smoke
def test_smoke_89_ledger_integrity():
    sys.path.insert(0, str(ROOT / "tools"))
    import check_test_dates as ctd

    # 台账里每个文件都真实存在，且确实含窗口端点引用（登记有据）
    for rel in ctd.REVIEWED:
        p = ROOT / rel
        assert p.exists(), f"ledger file missing: {rel}"
        src = p.read_text(encoding="utf-8", errors="replace")
        assert any(ep in src for ep in ctd.WINDOWED_ENDPOINTS), \
            f"ledger entry has no windowed endpoint reference: {rel}"

    # 名册端点都真实存在（域源码里能找到路径定义）
    domain_src = "".join(
        (ROOT / "app" / "apm" / "domains" / f).read_text(encoding="utf-8")
        for f in ("timelog.py", "reports.py", "ical.py"))
    for ep in ctd.WINDOWED_ENDPOINTS:
        assert ep.replace("my/", "my/") and (
            ep in domain_src or ep.strip("/") in domain_src), f"endpoint not found: {ep}"
