"""Smoke 69 (M64): provenance & promotion on one line — ① a retry chain
forms from run.retried_from_checkpoint facts and the lineage projection
returns per-link scalars (dividend #15); ② palette recents semantics live in
localStorage (recency, dedup, cap — personal UI state, no event stream); ③ a
checklist item promotes to a real work item through the full create chain,
gets marked `extracted` (marker survives rebuild), and re-extraction is 409."""
from __future__ import annotations

import json

import pytest

from apm import config
from apm.core import db, events


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.mark.smoke
def test_smoke_69_m64_retry_lineage_recents_checklist_extract(client, tmp_data,
                                                               isolated_ontologies):
    p = client.post("/api/projects",
                    json={"name": "冒烟溯源升级", "ontology": "software-dev"}).json()
    pid = p["id"]

    # --- ① 重试链：失败 run → 重试 → 链投影返回两环标量 -------------------------
    def _seed(run_id: str, steps: int, outcome: str):
        events.emit(event_type="run.requested", agg_type="run", agg_id=run_id,
                    project_id=pid, actor_type="human", actor_id="u_admin",
                    payload={"agent_role": "dev-agent", "instruction": "x",
                             "conversation_id": f"conv_{run_id}"})
        events.emit(event_type="run.started", agg_type="run", agg_id=run_id,
                    project_id=pid, actor_type="system", actor_id="runtime:x",
                    payload={"thread_id": run_id})
        for i in range(steps):
            events.emit(event_type="run.span_opened", agg_type="span",
                        agg_id=f"sp_{run_id}_{i}", project_id=pid,
                        actor_type="system", actor_id="runtime:x",
                        payload={"run_id": run_id, "span_kind": "generation",
                                 "name": f"step{i}", "attributes": {}})
            events.emit(event_type="run.span_closed", agg_type="span",
                        agg_id=f"sp_{run_id}_{i}", project_id=pid,
                        actor_type="agent", actor_id="runtime:x",
                        payload={"run_id": run_id, "status": "ok"})
        if outcome == "succeeded":
            events.emit(event_type="run.succeeded", agg_type="run", agg_id=run_id,
                        project_id=pid, actor_type="system", actor_id="runtime:x",
                        payload={"outcome": "done", "output": {"outcome": "done"}})
        else:
            events.emit(event_type="run.failed", agg_type="run", agg_id=run_id,
                        project_id=pid, actor_type="system", actor_id="runtime:x",
                        payload={"error": "boom"})

    _seed("r_s69_a", 2, "failed")
    events.emit(event_type="run.retried_from_checkpoint", agg_type="run",
                agg_id="r_s69_b", project_id=pid, actor_type="human",
                actor_id="u_admin", payload={"original": "r_s69_a"})
    _seed("r_s69_b", 4, "succeeded")

    u = client.get("/api/runs/r_s69_b/retry-lineage").json()
    assert u["retried"] is True and u["length"] == 2
    assert [x["run_id"] for x in u["chain"]] == ["r_s69_a", "r_s69_b"]
    assert u["chain"][0]["steps"] == 2 and u["chain"][1]["steps"] == 4  # diff 面真实

    # --- ② 清单项转子任务：全链建任务 + 标记 extracted + 409 幂等 ----------------
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "升级母项"}).json()
    assert client.patch(f"/api/items/{it['id']}/checklist", json={"items": [
        {"text": "写部署文档", "done": False},
        {"text": "核对回滚", "done": True},
    ]}).status_code == 200

    r = client.post(f"/api/items/{it['id']}/checklist/extract", json={"index": 0})
    assert r.status_code == 200, r.text()
    spawned = r.json()["item"]["id"]
    # 派生任务存在（create_item 全校验链产物）
    got = client.get(f"/api/items/{spawned}").json()
    assert got["title"] == "写部署文档" and got["concept_id"] == "task"
    # 清单项带标记（done 与 extracted 正交）
    cl = json.loads(client.get(f"/api/items/{it['id']}").json()["checklist"])
    assert cl[0]["extracted"] == spawned and cl[0]["done"] is False
    # extracted_tasks 复用（source_item_id 维度）
    assert db.get_conn().execute(
        "SELECT COUNT(*) AS n FROM extracted_tasks WHERE source_item_id = ?",
        (it["id"],)).fetchone()["n"] == 1
    # 标记项再转 409 快速路径
    assert client.post(f"/api/items/{it['id']}/checklist/extract",
                       json={"index": 0}).status_code == 409

    # --- ③ rebuild：链投影、清单标记、extracted_tasks 全部复现 ------------------
    assert client.post("/api/system/rebuild-projections").status_code == 200
    u2 = client.get("/api/runs/r_s69_b/retry-lineage").json()
    assert u2 == u
    cl2 = json.loads(client.get(f"/api/items/{it['id']}").json()["checklist"])
    assert cl2[0]["extracted"] == spawned
    assert db.get_conn().execute(
        "SELECT COUNT(*) AS n FROM extracted_tasks WHERE source_item_id = ?",
        (it["id"],)).fetchone()["n"] == 1
