"""Smoke 74 (M69): realtime & reuse — ① an instruction template CRUDs and its
body round-trips through the git pipeline; ② a run bound to a work item flows
its artifact back as a comment (idempotent per run); ③ the runs listing
carries item_id so the board can render live badges (I207 is a frontend
concern — its logic is unit-tested in runlive.test.ts)."""
from __future__ import annotations

import pytest

from apm import config
from apm.core import db, events


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.mark.smoke
def test_smoke_74_m69_templates_run_writeback_board_feed(
        client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "冒烟实时复用", "ontology": "software-dev"}).json()["id"]

    # --- ① 指令模板：创建 → 列表可读（git 管道往返）→ 版本递增 -------------------
    r = client.post(f"/api/projects/{pid}/prompt-templates",
                    json={"title": "生成 PRD", "body": "请为登录功能生成 PRD，覆盖认证与边界。",
                          "agent_role": "pm-agent"})
    assert r.status_code == 200, r.text
    tpl = r.json()
    listing = client.get(f"/api/projects/{pid}/prompt-templates").json()["templates"]
    assert len(listing) == 1 and "PRD" in listing[0]["body"]
    r = client.patch(f"/api/prompt-templates/{tpl['id']}",
                     json={"body": "请为登录功能生成 PRD，补充失败率指标。"})
    assert r.status_code == 200 and r.json()["version"] == 2

    # --- ② run 产物回流：带 item_id 的成功 run → 工件项自动评论（同 run 幂等）----
    item = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "认证功能"}).json()
    run_id = "r_s74_1"
    events.emit(event_type="run.requested", agg_type="run", agg_id=run_id,
                project_id=pid, actor_type="human", actor_id="u_admin",
                payload={"agent_role": "dev-agent", "instruction": "做认证",
                         "conversation_id": f"conv_{run_id}", "item_id": item["id"]})
    events.emit(event_type="run.started", agg_type="run", agg_id=run_id,
                project_id=pid, actor_type="system", actor_id=f"runtime:{run_id}",
                payload={"thread_id": run_id})
    events.emit(event_type="run.succeeded", agg_type="run", agg_id=run_id,
                project_id=pid, actor_type="system", actor_id=f"runtime:{run_id}",
                payload={"outcome": "done",
                         "output": {"artifact_path": "artifacts/prd/feature-auth.md"}})
    rows = client.get(f"/api/items/{item['id']}/comments").json()["comments"]
    assert len(rows) == 1, "write-back comment missing"
    assert "Agent 产出已回流" in rows[0]["body"]
    assert run_id in rows[0]["body"] and "artifacts/prd/feature-auth.md" in rows[0]["body"]

    # idempotency: re-emitting the same run must not double-comment
    events.emit(event_type="run.succeeded", agg_type="run", agg_id=run_id,
                project_id=pid, actor_type="system", actor_id=f"runtime:{run_id}",
                payload={"outcome": "done",
                         "output": {"artifact_path": "artifacts/prd/feature-auth.md"}})
    rows = client.get(f"/api/items/{item['id']}/comments").json()["comments"]
    assert len(rows) == 1, "write-back commented twice for one run"

    # --- ③ 看板数据面：runs 列表带 item_id（Board 实时徽标的权威数据源）----------
    runs = client.get(f"/api/runs?project_id={pid}").json()["runs"]
    mine = [x for x in runs if x["id"] == run_id]
    assert mine and mine[0]["item_id"] == item["id"]
