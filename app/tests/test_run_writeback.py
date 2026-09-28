"""M69-I209 run 产物回流工作项（docs/01 §BN.3，Copilot coding agent 语义）：
run.succeeded 且 runs 投影带 item_id 且产出 artifact_path → 工件项自动评论
（路径+run 溯源·actor=runtime:*）；同 run 幂等；无 item / 无产物 / 失败
run 不评；rebuild 走投影重放不重触发 hook，评论已在事件流中原样恢复。"""
from __future__ import annotations

import pytest

from apm import config
from apm.core import db, events


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


def _emit_run(pid: str, run_id: str, item_id: str | None, artifact_path: str | None,
              outcome: str = "succeeded") -> None:
    payload = {"agent_role": "dev-agent", "instruction": "做功能",
               "conversation_id": f"conv_{run_id}"}
    if item_id:
        payload["item_id"] = item_id
    events.emit(event_type="run.requested", agg_type="run", agg_id=run_id,
                project_id=pid, actor_type="human", actor_id="u_admin", payload=payload)
    events.emit(event_type="run.started", agg_type="run", agg_id=run_id,
                project_id=pid, actor_type="system", actor_id=f"runtime:{run_id}",
                payload={"thread_id": run_id})
    if outcome == "succeeded":
        output = {"artifact_path": artifact_path} if artifact_path else {}
        events.emit(event_type="run.succeeded", agg_type="run", agg_id=run_id,
                    project_id=pid, actor_type="system", actor_id=f"runtime:{run_id}",
                    payload={"outcome": "done", "output": output})
    else:
        events.emit(event_type="run.failed", agg_type="run", agg_id=run_id,
                    project_id=pid, actor_type="system", actor_id=f"runtime:{run_id}",
                    payload={"error": "boom"})


def _comments(client, item_id: str) -> list[dict]:
    return client.get(f"/api/items/{item_id}/comments").json()["comments"]


def test_writeback_on_success_and_idempotent(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "回流项目", "ontology": "software-dev"}).json()["id"]
    item = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "认证功能"}).json()
    _emit_run(pid, "r_wb1", item["id"], "artifacts/prd/feature-auth.md")

    rows = _comments(client, item["id"])
    assert len(rows) == 1
    assert "Agent 产出已回流" in rows[0]["body"]
    assert "r_wb1" in rows[0]["body"] and "artifacts/prd/feature-auth.md" in rows[0]["body"]
    assert rows[0]["author_id"] == "runtime:r_wb1"

    # same run re-emitted (runtime double-fire) → still exactly one comment
    _emit_run(pid, "r_wb1", item["id"], "artifacts/prd/feature-auth.md")
    assert len(_comments(client, item["id"])) == 1


def test_no_writeback_without_item_or_artifact_or_on_failure(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "回流负例项目", "ontology": "software-dev"}).json()["id"]
    item = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "无关联 run"}).json()

    _emit_run(pid, "r_wb2", None, "artifacts/prd/x.md")          # run 不挂工件
    _emit_run(pid, "r_wb3", item["id"], None)                    # 挂工件但无产物
    _emit_run(pid, "r_wb4", item["id"], "artifacts/prd/y.md",
              outcome="failed")                                  # 失败 run 产不可信

    assert _comments(client, item["id"]) == []


def test_writeback_survives_rebuild(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "回流重建项目", "ontology": "software-dev"}).json()["id"]
    item = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "重建后仍在"}).json()
    _emit_run(pid, "r_wb5", item["id"], "artifacts/prd/z.md")
    assert len(_comments(client, item["id"])) == 1

    assert client.post("/api/system/rebuild-projections").status_code == 200
    rows = _comments(client, item["id"])
    assert len(rows) == 1  # replay restores the comment; the hook does NOT re-fire
    assert "r_wb5" in rows[0]["body"]
