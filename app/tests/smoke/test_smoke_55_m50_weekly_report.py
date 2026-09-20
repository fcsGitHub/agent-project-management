"""Smoke 55 (M50): periodic automated status reports — the daily sweep's
seventh built-in pass generates one weekly report per active project on the
configured ISO weekday (per-project per-week heartbeat in the event payload,
zero new tables), owners get a report_weekly notification through the pref
gate, the Reports page list tells manual and weekly apart, and the next
period's report carries an honest 首期/delta comparison section."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from apm import config
from apm.core import db


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = (config.settings.user_id, config.settings.weekly_report_day)
    yield
    (config.settings.user_id, config.settings.weekly_report_day) = saved


@pytest.mark.smoke
def test_smoke_55_m50_weekly_report(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "冒烟周报", "ontology": "software-dev"}).json()["id"]

    # --- ① 项目数据：2 项任务完成 1 项（done_pct 50）--------------------------
    its = [client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": f"冒烟任务{i}"}).json()
           for i in range(2)]
    client.patch(f"/api/items/{its[0]['id']}", json={"status": "done"})

    # --- ② sweep 周报 pass：把 weekly_report_day 对齐 sweep 实际 UTC 今天 ------
    from apm.core import events as events_mod
    sweep_today = events_mod.utcnow()[:10]
    config.settings.weekly_report_day = date.fromisoformat(sweep_today).isoweekday()
    r = client.post("/api/automations/sweep", json={"force": True})
    assert r.status_code == 200, r.text
    assert r.json()["swept"] is True and r.json()["reported"] >= 1

    # 周报工件入 git 可读 · source=weekly · 环比首期诚实
    lst = client.get(f"/api/projects/{pid}/reports").json()["reports"]
    weekly = [x for x in lst if x["source"] == "weekly"]
    assert len(weekly) == 1 and weekly[0]["metrics"]["done_pct"] == 50
    art = client.get(f"/api/projects/{pid}/artifacts/{weekly[0]['path']}").json()
    assert "## 总体健康" in art["content"] and "首期报告，无上期数据可比" in art["content"]

    # --- ③ owner 通知（report_weekly 走 I96 偏好白名单投影）-------------------
    notes = client.get("/api/notifications").json()["notifications"]
    wk = [n for n in notes if n["kind"] == "report_weekly"]
    assert len(wk) == 1 and wk[0]["summary"].endswith(".md")

    # --- ④ 下一期：再完成 1 项 → 环比分区 Δ 完成度 +50pp ----------------------
    from apm.domains.automations import _report_status_weekly
    nxt = (date.fromisoformat(sweep_today) + timedelta(days=7)).isoformat()
    client.patch(f"/api/items/{its[1]['id']}", json={"status": "done"})
    assert _report_status_weekly(db.get_conn(), nxt) == 1
    lst2 = client.get(f"/api/projects/{pid}/reports").json()["reports"]
    weekly2 = [x for x in lst2 if x["source"] == "weekly"]
    assert len(weekly2) == 2 and weekly2[0]["metrics"]["done_pct"] == 100
    art2 = client.get(f"/api/projects/{pid}/artifacts/{weekly2[0]['path']}").json()
    assert "## 环比（vs" in art2["content"] and "完成度 50% → 100%（↑50pp）" in art2["content"]

    # --- ⑤ 同周幂等：再次调用不重复生成 --------------------------------------
    assert _report_status_weekly(db.get_conn(), nxt) == 0
    assert len(client.get(f"/api/projects/{pid}/reports").json()["reports"]) == 2
