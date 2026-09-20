"""M50-I150 sweep 周期报告 pass：报告的价值在「准时发生」而非「手动可触
发」（Plane #5861 digest 语义）——run_daily_sweep 第七员 `report_status_weekly`
在配置的 ISO 周一对每个活跃项目生成周报；幂等是事件流事实（payload 记
source/week，零新表），重构后手动端点行为不变。"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from apm import config
from apm.core import db


@pytest.fixture(autouse=True)
def _restore_settings():
    saved = (config.settings.user_id, config.settings.provider_mode,
             config.settings.weekly_report_day)
    yield
    (config.settings.user_id, config.settings.provider_mode,
     config.settings.weekly_report_day) = saved


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    return client.post("/api/projects",
                       json={"name": "周报项目", "ontology": "software-dev"}).json()["id"]


def _weekly_reports(client):
    return client.get("/api/events", params={
        "event_type": "artifact.report_generated"}).json()["events"]


def test_manual_endpoint_behavior_unchanged_after_refactor(client, project):
    """重构回归：手动 POST 端点行为与 I148 完全一致（actor=human、无
    source/week 字段、分区文本不变）。"""
    it = client.post(f"/api/projects/{project}/items",
                     json={"concept_id": "task", "title": "完成项",
                           }).json()
    client.patch(f"/api/items/{it['id']}", json={"status": "done"})
    r = client.post(f"/api/projects/{project}/status-report")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["path"].startswith("artifacts/reports/status-")
    art = client.get(f"/api/projects/{project}/artifacts/{out['path']}").json()
    assert "## 总体健康" in art["content"] and "完成度约" in art["content"]
    ev = [e for e in _weekly_reports(client) if e["project_id"] == project]
    assert len(ev) == 1 and "source" not in ev[0]["payload"]


def test_weekly_pass_fires_on_configured_weekday(client, project):
    """ISO 周一（weekly_report_day=1）触发：每个活跃项目一份周报，
    payload 带 source=weekly + ISO 周键 + 结构化指标。"""
    monday = "2026-09-21"  # 该日确为周一
    conn = db.get_conn()
    from apm.domains.automations import _report_status_weekly
    n = _report_status_weekly(conn, monday)
    assert n >= 1
    ev = [e for e in _weekly_reports(client) if e["project_id"] == project
          and e["payload"].get("source") == "weekly"]
    assert len(ev) == 1
    p = ev[0]["payload"]
    iso = date.fromisoformat(monday).isocalendar()
    assert p["week"] == f"{iso[0]}-W{iso[1]:02d}"
    assert set(p["metrics"]) == {"done_pct", "overdue", "gates", "risks",
                                 "expense_cost", "timelog_h"}
    assert p["metrics"]["done_pct"] == 0
    assert ev[0]["actor_type"] == "automation" and ev[0]["actor_id"] == "scheduler"
    art = client.get(f"/api/projects/{project}/artifacts/{p['path']}").json()
    assert "## 总体健康" in art["content"]


def test_weekly_pass_idempotent_within_iso_week(client, project):
    """同 ISO 周第二次调用跳过（心跳事实：本周已有 weekly 报告即不再生成）。"""
    monday = "2026-09-21"
    conn = db.get_conn()
    from apm.domains.automations import _report_status_weekly
    assert _report_status_weekly(conn, monday) >= 1
    assert _report_status_weekly(conn, monday) == 0
    assert _report_status_weekly(conn, "2026-09-22") == 0  # 同周的周二也跳过
    ev = [e for e in _weekly_reports(client) if e["project_id"] == project
          and e["payload"].get("source") == "weekly"]
    assert len(ev) == 1


def test_weekly_pass_disabled_and_non_monday(client, project):
    """weekly_report_day=0 关闭；非配置日不生成。"""
    config.settings.weekly_report_day = 0
    conn = db.get_conn()
    from apm.domains.automations import _report_status_weekly
    assert _report_status_weekly(conn, "2026-09-21") == 0
    config.settings.weekly_report_day = 3  # 周三
    assert _report_status_weekly(conn, "2026-09-21") == 0  # 周一 ≠ 周三
    ev = [e for e in _weekly_reports(client) if e["project_id"] == project]
    assert ev == []


def test_weekly_pass_skips_archived_projects(client, tmp_data, isolated_ontologies):
    """归档项目不生成周报；活跃项目照常。"""
    active = client.post("/api/projects",
                         json={"name": "活跃项目", "ontology": "software-dev"}).json()["id"]
    archived = client.post("/api/projects",
                           json={"name": "归档项目", "ontology": "software-dev"}).json()["id"]
    assert client.post(f"/api/projects/{archived}/archive").status_code == 200
    conn = db.get_conn()
    from apm.domains.automations import _report_status_weekly
    assert _report_status_weekly(conn, "2026-09-21") == 1  # 仅活跃项目
    paths = [e["payload"]["path"] for e in _weekly_reports(client)]
    assert len(paths) == 1 and paths[0].startswith("artifacts/reports/status-")


def test_sweep_counter_reported_accounted(client, project, monkeypatch):
    """run_daily_sweep 对账：reported 计数进 automation.swept payload 与返回值
    （weekly_report_day 设为 sweep 实际 UTC 今天的 weekday，force 触发）。"""
    from apm.core import events as events_mod
    sweep_today = events_mod.utcnow()[:10]
    config.settings.weekly_report_day = date.fromisoformat(sweep_today).isoweekday()
    from apm.domains import automations as am
    out = am.run_daily_sweep(force=True)
    assert out["swept"] is True and out["reported"] >= 1
    swept = client.get("/api/events",
                       params={"event_type": "automation.swept"}).json()["events"]
    assert swept and swept[-1]["payload"]["reported"] >= 1


def test_rebuild_preserves_weekly_facts(client, project):
    """rebuild 后 weekly 事实与通知投影完整复现（事件流是唯一真相）。"""
    conn = db.get_conn()
    from apm.domains.automations import _report_status_weekly
    _report_status_weekly(conn, "2026-09-21")
    before = client.get("/api/events",
                        params={"event_type": "artifact.report_generated"}).json()["events"]
    from apm.core import projections
    projections.ensure_handlers_registered()
    projections.rebuild()
    after = client.get("/api/events",
                       params={"event_type": "artifact.report_generated"}).json()["events"]
    assert len(after) == len(before)


def test_weekly_report_notifies_owner_and_list(client, project):
    """I151：周报生成后 owner 收通知（kind=report_weekly，I96 偏好白名单），
    GET /reports 列表手动与周报可区分；手动生成不发通知。"""
    # creator is already owner (409 if re-added); the row is what the notify
    # query needs — verify it rather than asserting on the POST
    conn = db.get_conn()
    assert conn.execute(
        "SELECT 1 FROM project_members WHERE project_id = ? AND user_id = 'u_admin'"
        " AND role = 'owner'", (project,)).fetchone()
    from apm.domains.automations import _report_status_weekly
    assert _report_status_weekly(conn, "2026-09-21") == 1
    client.post(f"/api/projects/{project}/status-report")  # 手动版不发通知

    notes = client.get("/api/notifications").json()["notifications"]
    weekly = [n for n in notes if n["kind"] == "report_weekly"]
    assert len(weekly) == 1
    assert "2026-W" in weekly[0]["summary"] and weekly[0]["summary"].endswith(".md")

    lst = client.get(f"/api/projects/{project}/reports").json()["reports"]
    assert len(lst) == 2
    assert {r["source"] for r in lst} == {"manual", "weekly"}
    weekly_row = [r for r in lst if r["source"] == "weekly"][0]
    assert weekly_row["week"].startswith("2026-W")
    assert set(weekly_row["metrics"]) == {"done_pct", "overdue", "gates",
                                          "risks", "expense_cost", "timelog_h"}
    assert all(r["path"].startswith("artifacts/reports/status-") for r in lst)


def test_weekly_notification_pref_gate_holds(client, project):
    """I96 偏好关断：owner 关掉 report_weekly 的 inapp 后投影不发（事件照发）。"""
    assert client.put("/api/me/notification-prefs", json={
        "prefs": [{"kind": "report_weekly", "inapp": False, "email": False}]}).status_code == 200
    conn = db.get_conn()
    from apm.domains.automations import _report_status_weekly
    assert _report_status_weekly(conn, "2026-09-21") == 1
    notes = client.get("/api/notifications").json()["notifications"]
    assert not [n for n in notes if n["kind"] == "report_weekly"]  # in-app gate held
    sent = client.get("/api/events",
                      params={"event_type": "notification.sent"}).json()["events"]
    assert any(e["payload"].get("kind") == "report_weekly" for e in sent)  # fact still evented


def _latest_weekly_path(client, project) -> str:
    evs = [e for e in client.get("/api/events", params={
        "event_type": "artifact.report_generated"}).json()["events"]
        if e["project_id"] == project and e["payload"].get("source") == "weekly"]
    return max(evs, key=lambda e: e["id"])["payload"]["path"]


def test_weekly_comparison_first_period_then_delta(client, project):
    """I152：首期报告环比分区诚实标注「首期」；第二期 Δ 与指标对齐。"""
    # 首期（W38）：2 项任务，1 项完成 → done_pct 50
    its = [client.post(f"/api/projects/{project}/items",
                       json={"concept_id": "task", "title": f"项{i}"}).json()
           for i in range(2)]
    client.patch(f"/api/items/{its[0]['id']}", json={"status": "done"})
    conn = db.get_conn()
    from apm.domains.automations import _report_status_weekly
    assert _report_status_weekly(conn, "2026-09-14") == 1  # W38 周一
    art1 = client.get(f"/api/projects/{project}/artifacts/{_latest_weekly_path(client, project)}").json()
    assert "## 环比" in art1["content"] and "首期报告，无上期数据可比" in art1["content"]

    # 第二期（W39）：再完成 1 项 → done_pct 100，Δ +50pp
    client.patch(f"/api/items/{its[1]['id']}", json={"status": "done"})
    assert _report_status_weekly(conn, "2026-09-21") == 1
    art2 = client.get(f"/api/projects/{project}/artifacts/{_latest_weekly_path(client, project)}").json()
    assert "## 环比（vs 2026-W38）" in art2["content"]
    assert "完成度 50% → 100%（↑50pp）" in art2["content"]
    assert "超期 0 → 0（→0 项）" in art2["content"]

    # 两期 payload 指标可对账（I152 差值来源）
    lst = client.get(f"/api/projects/{project}/reports").json()["reports"]
    m38 = [r for r in lst if r["week"] == "2026-W38"][0]["metrics"]
    m39 = [r for r in lst if r["week"] == "2026-W39"][0]["metrics"]
    assert m38["done_pct"] == 50 and m39["done_pct"] == 100
    assert m39["done_pct"] - m38["done_pct"] == 50
