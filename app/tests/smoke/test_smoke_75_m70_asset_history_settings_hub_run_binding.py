"""Smoke 75 (M70): visibility & reach — ① asset version history opens the git
ledger (history → diff → append-only restore); ② the settings hub's aggregate
read (project carries auto_deposit / cost_budget / report_template); ③ a run
bound to a work item at kickoff shows item_id in the runs listing and its
artifact flows back as a write-back comment."""
from __future__ import annotations

import pytest

from apm import config
from apm.content import assetsrepo
from apm.core import events


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.mark.smoke
def test_smoke_75_m70_asset_history_settings_hub_run_binding(
        client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "冒烟可见可达", "ontology": "software-dev"}).json()["id"]

    # --- ① 资产版本历史：git 账本翻开 → diff → append-only 恢复 ----------------
    aid = "a_s75"
    assetsrepo.write_asset("doc-lib", aid,
                           {"title": "冒烟资产", "kind": "doc", "library": "doc-lib",
                            "tags": [], "status": "draft"},
                           "# 一\n初始。\n")
    assetsrepo.write_asset("doc-lib", aid,
                           {"title": "冒烟资产", "kind": "doc", "library": "doc-lib",
                            "tags": [], "status": "draft"},
                           "# 二\n演进了。\n")
    events.emit(event_type="asset.drafted", agg_type="asset", agg_id=aid,
                payload={"library": "doc-lib", "kind": "doc", "title": "冒烟资产",
                         "tags": [], "commit": "seed", "status": "draft"})
    hist = client.get(f"/api/assets/{aid}/history").json()["history"]
    assert len(hist) == 2
    patch = client.get(f"/api/assets/{aid}/diff", params={
        "from_commit": hist[-1]["commit"], "to_commit": hist[0]["commit"]}).json()["patch"]
    assert "二" in patch
    r = client.post(f"/api/assets/{aid}/restore", json={"commit": hist[-1]["commit"]})
    assert r.status_code == 200 and "初始" in r.json()["content"]
    assert len(client.get(f"/api/assets/{aid}/history").json()["history"]) == 3

    # --- ② 设置中心聚合读：project 一处携带全部可配置项当前值 ------------------
    assert client.patch(f"/api/projects/{pid}", json={
        "auto_deposit": True, "cost_budget_usd": 25.0,
        "report_template": {"sections": [{"key": "health", "enabled": True},
                                          {"key": "done", "enabled": True},
                                          {"key": "advice", "enabled": False}]},
    }).status_code == 200
    p = client.get(f"/api/projects/{pid}").json()
    assert p["auto_deposit"] in (True, 1) and p["cost_budget_usd"] == 25.0
    assert p["report_template"]["sections"][2]["enabled"] is False

    # --- ③ run 发起绑定工件：runs 列表 item_id 透出 + 产物回流评论 --------------
    item = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "冒烟绑定工件"}).json()
    run_id = "r_s75_1"
    events.emit(event_type="run.requested", agg_type="run", agg_id=run_id,
                project_id=pid, actor_type="human", actor_id="u_admin",
                payload={"agent_role": "dev-agent", "instruction": "做绑定功能",
                         "conversation_id": f"conv_{run_id}", "item_id": item["id"]})
    events.emit(event_type="run.started", agg_type="run", agg_id=run_id,
                project_id=pid, actor_type="system", actor_id=f"runtime:{run_id}",
                payload={"thread_id": run_id})
    events.emit(event_type="run.succeeded", agg_type="run", agg_id=run_id,
                project_id=pid, actor_type="system", actor_id=f"runtime:{run_id}",
                payload={"outcome": "done",
                         "output": {"artifact_path": "artifacts/prd/bound.md"}})
    mine = [x for x in client.get(f"/api/runs?project_id={pid}").json()["runs"]
            if x["id"] == run_id]
    assert mine and mine[0]["item_id"] == item["id"]
    rows = client.get(f"/api/items/{item['id']}/comments").json()["comments"]
    assert len(rows) == 1 and run_id in rows[0]["body"]
