"""Smoke 73 (M68): factory personalization & deposition — ① a project × role
standing instruction (L1.5) shows up in the assembled context between L1 and
L2; ② a succeeded run's artifact auto-deposits as a draft asset (content-
deduped); ③ the report template drops a section and renames another."""
from __future__ import annotations

import time

import pytest

from apm import config
from apm.core import db, events


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.mark.smoke
def test_smoke_73_m68_role_instructions_auto_deposit_report_template(
        client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "冒烟个性化", "ontology": "software-dev"}).json()["id"]

    # --- ① 项目级角色指令：写入 → 上下文组装可见 --------------------------------
    r = client.put(f"/api/projects/{pid}/role-instructions",
                   json={"agent_role": "dev-agent",
                         "content": "本项目统一 pytest，禁止 unittest。"})
    assert r.status_code == 200, r.text
    conv = client.post("/api/conversations",
                       json={"project_id": pid, "kind": "executing"}).json()
    ctx = client.get(f"/api/conversations/{conv['id']}/context").json()
    merged = ctx["merged_preview"]
    assert merged.index("[L1 项目宪章") < merged.index("[L1.5 项目角色指令]") < merged.index("[L2 功能简报]")
    assert "pytest" in merged

    # --- ② 产物自动沉淀：开设置 → run 成功 → draft 资产入册（含 run 溯源）-------
    assert client.patch(f"/api/projects/{pid}", json={"auto_deposit": True}).status_code == 200
    from apm.content import gitrepo
    body = "# 认证 PRD\n\n只保留一种登录方式。\n"
    gitrepo.write_file(pid, "artifacts/prd/feature-auth.md", body,
                       message="seed artifact", actor_type="human", actor_id="u_admin")
    events.emit(event_type="run.requested", agg_type="run", agg_id="r_s73_1",
                project_id=pid, actor_type="human", actor_id="u_admin",
                payload={"agent_role": "planner-agent", "instruction": "产 PRD",
                         "conversation_id": conv["id"]})
    events.emit(event_type="run.started", agg_type="run", agg_id="r_s73_1",
                project_id=pid, actor_type="system", actor_id="runtime:r_s73_1",
                payload={"thread_id": "r_s73_1"})
    events.emit(event_type="run.succeeded", agg_type="run", agg_id="r_s73_1",
                project_id=pid, actor_type="system", actor_id="runtime:r_s73_1",
                payload={"outcome": "done",
                         "output": {"artifact_path": "artifacts/prd/feature-auth.md"}})
    asset_id = None
    deadline = time.time() + 8
    while time.time() < deadline and asset_id is None:
        for a in client.get("/api/assets").json()["assets"]:
            d = client.get(f"/api/assets/{a['id']}").json()
            if any(l["target"].get("project_id") == pid and l["target"].get("run_id") == "r_s73_1"
                   for l in d.get("provenance", [])):
                asset_id = a["id"]
                break
        time.sleep(0.05)
    assert asset_id, "auto deposit never produced a draft asset"
    detail = client.get(f"/api/assets/{asset_id}").json()
    assert detail["status"] == "draft" and detail["kind"] == "prd-template"

    # dedup: rerunning the same artifact must not double-deposit
    events.emit(event_type="run.requested", agg_type="run", agg_id="r_s73_2",
                project_id=pid, actor_type="human", actor_id="u_admin",
                payload={"agent_role": "planner-agent", "instruction": "再产 PRD",
                         "conversation_id": conv["id"]})
    events.emit(event_type="run.started", agg_type="run", agg_id="r_s73_2",
                project_id=pid, actor_type="system", actor_id="runtime:r_s73_2",
                payload={"thread_id": "r_s73_2"})
    events.emit(event_type="run.succeeded", agg_type="run", agg_id="r_s73_2",
                project_id=pid, actor_type="system", actor_id="runtime:r_s73_2",
                payload={"outcome": "done",
                         "output": {"artifact_path": "artifacts/prd/feature-auth.md"}})
    time.sleep(1.5)
    dupes = [a for a in client.get("/api/assets").json()["assets"] if a["id"] != asset_id
             and client.get(f"/api/assets/{a['id']}").json()["kind"] == "prd-template"]
    assert not dupes, "identical artifact deposited twice"

    # --- ③ 报告模板：关健康段 + 改交付段标题 -----------------------------------
    assert client.patch(f"/api/projects/{pid}", json={"report_template": {"sections": [
        {"key": "health", "enabled": False},
        {"key": "done", "enabled": True, "heading": "本期交付"},
        {"key": "advice", "enabled": True},
    ]}}).status_code == 200
    out = client.post(f"/api/projects/{pid}/status-report", json={}).json()
    report = gitrepo.read_file(pid, out["path"])
    assert "## 总体健康" not in report and "## 本期交付" in report
