"""M68-I205 运行产物自动沉淀（docs/01 §BM.2，CAS 去重零成本）：
projects.auto_deposit 开 + run.succeeded 且 output.artifact_path 有
deposits_to 归属 → post-emit hook 入队 → 后台 worker 走 deposit Path A
自动建 draft 资产（provenance 带 run_id·actor=runtime:* 不触发自动化）；
同内容二次 → sha256 去重跳过；设置关/无归属/失败 run → 不沉淀。"""
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


def _wait_assets(client, pid: str, want: int, timeout: float = 8.0) -> list[dict]:
    deadline = time.time() + timeout
    assets: list[dict] = []
    while time.time() < deadline:
        # /assets is instance-global — filter to this project via provenance
        assets = [a for a in client.get("/api/assets").json()["assets"]
                  if _linked_to(client, a["id"], pid)]
        if len(assets) >= want:
            return assets
        time.sleep(0.05)
    return assets


def _linked_to(client, asset_id: str, pid: str) -> bool:
    d = client.get(f"/api/assets/{asset_id}").json()
    return any(l["target"].get("project_id") == pid for l in d.get("provenance", []))


def _emit_run(pid: str, run_id: str, artifact_path: str, outcome: str = "succeeded") -> None:
    events.emit(event_type="run.requested", agg_type="run", agg_id=run_id,
                project_id=pid, actor_type="human", actor_id="u_admin",
                payload={"agent_role": "planner-agent", "instruction": "产 PRD",
                         "conversation_id": f"conv_{run_id}"})
    events.emit(event_type="run.started", agg_type="run", agg_id=run_id,
                project_id=pid, actor_type="system", actor_id=f"runtime:{run_id}",
                payload={"thread_id": run_id})
    if outcome == "succeeded":
        events.emit(event_type="run.succeeded", agg_type="run", agg_id=run_id,
                    project_id=pid, actor_type="system", actor_id=f"runtime:{run_id}",
                    payload={"outcome": "done",
                             "output": {"artifact_path": artifact_path}})
    else:
        events.emit(event_type="run.failed", agg_type="run", agg_id=run_id,
                    project_id=pid, actor_type="system", actor_id=f"runtime:{run_id}",
                    payload={"error": "boom"})


def test_auto_deposit_creates_draft_with_run_provenance(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "自动沉淀项目", "ontology": "software-dev"}).json()["id"]
    assert client.patch(f"/api/projects/{pid}",
                        json={"auto_deposit": True}).status_code == 200
    from apm.content import gitrepo

    gitrepo.write_file(pid, "artifacts/prd/feature-auth.md",
                       "# 认证 PRD\n\n登录只留一种方式。\n",
                       message="seed artifact", actor_type="human", actor_id="u_admin")

    _emit_run(pid, "r_ad1", "artifacts/prd/feature-auth.md")

    assets = _wait_assets(client, pid, 1)
    assert len(assets) == 1
    a = assets[0]
    assert a["status"] == "draft" and a["kind"] == "prd-template"
    assert "自动沉淀" in a["title"]
    # provenance rides the run id (actor runtime:* never re-triggers automations)
    detail = client.get(f"/api/assets/{a['id']}").json()
    assert detail["provenance"] and detail["provenance"][0]["target"]["run_id"] == "r_ad1"


def test_dedup_setting_off_and_failed_runs(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "去重项目", "ontology": "software-dev"}).json()["id"]
    from apm.content import gitrepo

    gitrepo.write_file(pid, "artifacts/prd/feature-auth.md",
                       "# 认证 PRD\n\n登录只留一种方式。\n",
                       message="seed artifact", actor_type="human", actor_id="u_admin")

    # setting OFF → nothing deposits
    _emit_run(pid, "r_ad2", "artifacts/prd/feature-auth.md")
    assert _wait_assets(client, pid, 1, timeout=2.0) == []

    # turn it on → first run deposits
    client.patch(f"/api/projects/{pid}", json={"auto_deposit": True})
    _emit_run(pid, "r_ad3", "artifacts/prd/feature-auth.md")
    assert len(_wait_assets(client, pid, 1)) == 1

    # identical content again → deduped, still exactly one asset
    _emit_run(pid, "r_ad4", "artifacts/prd/feature-auth.md")
    time.sleep(1.5)
    assets = _wait_assets(client, pid, 1, timeout=0.5)
    assert len(assets) == 1

    # a failed run never deposits (untrusted output)
    _emit_run(pid, "r_ad5", "artifacts/prd/other.md", outcome="failed")
    time.sleep(1.0)
    assert len(_wait_assets(client, pid, 1, timeout=0.5)) == 1


def test_setting_rides_project_updated_chain(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "开关项目", "ontology": "software-dev"}).json()["id"]
    client.patch(f"/api/projects/{pid}", json={"auto_deposit": True})
    assert client.get(f"/api/projects/{pid}").json()["auto_deposit"] in (True, 1)
    client.post("/api/system/rebuild-projections").status_code == 200
    assert client.get(f"/api/projects/{pid}").json()["auto_deposit"] in (True, 1)
