"""M49-I148 项目状态报告自动生成：POST 汇编平台自身投影为 Markdown 状态
报告，作为工件写入项目 git 内容仓（继承版本史/diff/审计，零新表）——
「平台数据自动汇编成草稿，人只做润色与结论」。AI 摘要失败降级纯数据版。"""
from __future__ import annotations

import pytest

from apm import config
from apm.core import db
from apm.runtime import provider as provider_mod


@pytest.fixture(autouse=True)
def _restore_settings():
    saved = (config.settings.user_id, config.settings.provider_mode)
    yield
    (config.settings.user_id, config.settings.provider_mode) = saved


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    return client.post("/api/projects",
                       json={"name": "报告项目", "ontology": "software-dev"}).json()["id"]


def test_status_report_generated_as_artifact(client, tmp_data, isolated_ontologies, project):
    # 造数据：2 done + 1 进行中（超期）+ 1 open risk
    for i in range(2):
        it = client.post(f"/api/projects/{project}/items",
                         json={"concept_id": "task", "title": f"完成项{i}"}).json()
        client.patch(f"/api/items/{it['id']}", json={"status": "done"})
    it = client.post(f"/api/projects/{project}/items",
                     json={"concept_id": "task", "title": "超期进行项",
                           "due_date": "2026-01-01"}).json()
    r = client.post(f"/api/projects/{project}/status-report")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["path"].startswith("artifacts/reports/status-") and out["path"].endswith(".md")
    # 工件入 git：可读、含分区标题与数字
    art = client.get(f"/api/projects/{project}/artifacts/{out['path']}").json()
    assert "## 总体健康" in art["content"]
    assert "完成度约" in art["content"] and "超期未结：**1**" in art["content"]
    # 重复生成 = 新 commit（版本史）
    r2 = client.post(f"/api/projects/{project}/status-report").json()
    assert r2["commit"] != out["commit"]
    # 审计事件
    ev = client.get("/api/events",
                    params={"event_type": "artifact.report_generated"}).json()["events"]
    assert len(ev) == 2


def test_status_report_ai_failure_degrades(client, tmp_data, isolated_ontologies, project, monkeypatch):
    """ai_summary=true 但 provider 挂 → 纯数据版照常交付（降级不失败）。"""
    class _Boom:
        mode = "openai"

        def complete(self, **kw):
            raise RuntimeError("provider down")

    monkeypatch.setattr(provider_mod, "get_provider", lambda: _Boom())
    monkeypatch.setattr(config.settings, "provider_mode", "openai")
    r = client.post(f"/api/projects/{project}/status-report",
                    params={"ai_summary": "true"})
    assert r.status_code == 200
    assert r.json()["ai_summary"] is None
    art = client.get(f"/api/projects/{project}/artifacts/{r.json()['path']}").json()
    assert "AI 摘要" not in art["content"]
