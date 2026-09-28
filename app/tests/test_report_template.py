"""M68-I206 报告模板定制（docs/01 §BM.3，骨架可配置数据零改动）：
projects.report_template = {"sections": [{key, enabled, heading?}]}——
段落开关跳过、自定义标题替换默认标题；NULL=现行骨架全开向后兼容；
手动报告与 sweep 周报同读一个模板（_render_status_lines 纯函数共享）。"""
from __future__ import annotations

import pytest

from apm import config
from apm.core import db


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    p = client.post("/api/projects",
                    json={"name": "模板项目", "ontology": "software-dev"}).json()
    # one done item so the 最近完成 section has a row
    it = client.post(f"/api/projects/{p['id']}/items",
                     json={"concept_id": "task", "title": "已完成的任务"}).json()
    client.patch(f"/api/items/{it['id']}", json={"status": "done"})
    return p["id"]


def test_default_template_keeps_full_skeleton(client, pid):
    assert client.get(f"/api/projects/{pid}").json()["report_template"] is None
    out = client.post(f"/api/projects/{pid}/status-report", json={}).json()
    md_path = out["path"]
    from apm.content import gitrepo
    body = gitrepo.read_file(pid, md_path)
    assert "## 总体健康" in body and "## 最近完成" in body and "## 待办与建议" in body


def test_section_toggle_and_custom_heading(client, pid):
    r = client.patch(f"/api/projects/{pid}", json={"report_template": {"sections": [
        {"key": "health", "enabled": False},
        {"key": "done", "enabled": True, "heading": "本期交付"},
        {"key": "advice", "enabled": True},
    ]}})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/projects/{pid}").json()["report_template"]["sections"][0]["enabled"] is False

    out = client.post(f"/api/projects/{pid}/status-report", json={}).json()
    from apm.content import gitrepo
    body = gitrepo.read_file(pid, out["path"])
    assert "## 总体健康" not in body       # toggled off → heading and data gone
    assert "工作项漏斗" not in body
    assert "## 本期交付" in body           # custom heading replaces the default
    assert "## 最近完成" not in body and "已完成的任务" in body
    assert "## 待办与建议" in body         # untouched key keeps default heading

    # the sweep's weekly layout shares the same core — spot-check the helper
    from apm.domains import reports
    project = db.get_conn().execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
    lines = reports._render_status_lines(project, "2026-09-28", {
        "funnel": {"backlog": 0, "todo": 0, "in_progress": 0, "done": 1, "cancelled": 0},
        "done_pct": 100, "overdue": 0, "gates_pending": 0, "risks_open": 0,
        "timelog": 0, "expense_cost": 0, "budget_hours": None, "recent_done": ["已完成的任务"],
    })
    text = "\n".join(lines)
    assert "## 本期交付" in text and "总体健康" not in text


def test_validation_and_rebuild_survives(client, pid):
    r = client.patch(f"/api/projects/{pid}", json={"report_template": {"sections": [
        {"key": "no-such", "enabled": True}]}})
    assert r.status_code == 422
    r = client.patch(f"/api/projects/{pid}", json={"report_template": {"sections": [
        {"key": "health", "enabled": "yes"}]}})
    assert r.status_code == 422

    client.patch(f"/api/projects/{pid}", json={"report_template": {"sections": [
        {"key": "health", "enabled": False}]}})
    client.post("/api/system/rebuild-projections").status_code == 200
    tpl = client.get(f"/api/projects/{pid}").json()["report_template"]
    assert tpl["sections"][0]["enabled"] is False
