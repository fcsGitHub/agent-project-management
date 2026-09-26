"""Smoke 65 (M60): ops resilience & portfolio insight — the backup/restore
drill proves a restore actually works (backup a populated data dir, restore
into a fresh one, verify event count + sqlite integrity + artifacts +
ontologies), and the portfolio health trend carries per-project flow metrics
(median cycle time, 4-week throughput, WIP) as event-pair projections."""
from __future__ import annotations

import sqlite3

import pytest

from apm import config
from apm.ops import create_backup, restore_backup


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.mark.smoke
def test_smoke_65_m60_backup_drill_portfolio_trend(client, tmp_data,
                                                   isolated_ontologies, tmp_path):
    # --- ① 真实数据：项目 + 工件 + 周期项（done）+ WIP 项 -----------------------
    p = client.post("/api/projects",
                    json={"name": "冒烟运维组合", "ontology": "software-dev",
                          "requirement": "ops"}).json()
    r = client.put(f"/api/projects/{p['id']}/artifacts/docs/drill.md",
                   json={"content": "# 演练", "message": "docs: drill"})
    assert r.status_code == 200, r.text
    it = client.post(f"/api/projects/{p['id']}/items",
                     json={"concept_id": "task", "title": "冒烟周期项"}).json()
    client.patch(f"/api/items/{it['id']}", json={"status": "in_progress"})
    client.patch(f"/api/items/{it['id']}", json={"status": "done"})
    wip = client.post(f"/api/projects/{p['id']}/items",
                      json={"concept_id": "task", "title": "冒烟WIP"}).json()
    client.patch(f"/api/items/{wip['id']}", json={"status": "in_progress"})

    # --- ② 组合趋势与流指标：中位周期 0 天 · 吞吐 0.25 · WIP 1 ------------------
    trend = client.get("/api/portfolio/health-trend").json()
    proj = next(x for x in trend["projects"] if x["project_id"] == p["id"])
    assert proj["median_cycle_days"] == 0
    assert proj["throughput_4w"] == 0.25
    assert proj["wip"] == 1
    assert len(proj["series"]) >= 2
    assert trend["portfolio_median"] is not None

    # --- ③ 备份→全新目录恢复（等价系统已毁）→文件级校验 -------------------------
    out = tmp_path / "apm-drill.zip"
    created = create_backup(out)
    fresh = tmp_path / "restored"
    fresh_ont = tmp_path / "ont"
    restore_backup(out, fresh, fresh_ont)
    conn = sqlite3.connect(fresh / "apm.db")
    count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    conn.close()
    assert count == created["manifest"]["event_count"]
    assert integrity == "ok"
    assert (fresh / "content" / p["id"] / "artifacts" / "docs" / "drill.md").exists()
    assert (fresh_ont / "software-dev.yaml").exists()
