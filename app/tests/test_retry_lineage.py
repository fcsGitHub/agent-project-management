"""M64-I192 run 重试对比（docs/01 §BI.1，LangGraph checkpoint resume vs
OpenHands 独立 rollout 的共识=重试价值在「与上次差哪」）：M4 的
run.retried_from_checkpoint 事件已是链锚（payload.original 指向原 run），
retry-lineage 纯读投影沿链回溯返回每环标量——事件溯源红利第十五例：链事实
已在流中，投影即得零埋点。diff 的是标量与工件清单不是正文。"""
from __future__ import annotations

import pytest

from apm import config
from apm.core import events


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    return client.post("/api/projects",
                       json={"name": "重试链项目", "ontology": "software-dev"}).json()["id"]


def _seed_run(client, project: str, run_id: str, outcome: str,
              steps: int = 2, tin: int = 100, tout: int = 50,
              artifact: str | None = None):
    """Deterministic run: requested → started → spans → terminal."""
    events.emit(event_type="run.requested", agg_type="run", agg_id=run_id,
                project_id=project, actor_type="human", actor_id="u_admin",
                payload={"agent_role": "dev-agent", "instruction": "x",
                         "conversation_id": f"conv_{run_id}"})
    events.emit(event_type="run.started", agg_type="run", agg_id=run_id,
                project_id=project, actor_type="system", actor_id="runtime:x",
                payload={"thread_id": run_id})
    for i in range(steps):
        events.emit(event_type="run.span_opened", agg_type="span", agg_id=f"sp_{run_id}_{i}",
                    project_id=project, actor_type="system", actor_id="runtime:x",
                    payload={"run_id": run_id, "span_kind": "generation",
                             "name": f"step{i}", "attributes": {}})
        events.emit(event_type="run.span_closed", agg_type="span", agg_id=f"sp_{run_id}_{i}",
                    project_id=project, actor_type="agent", actor_id="runtime:x",
                    payload={"run_id": run_id, "status": "ok"})
    events.emit(event_type="run.tokens_recorded", agg_type="run", agg_id=run_id,
                project_id=project, actor_type="system", actor_id="runtime:x",
                payload={"input_tokens": tin, "output_tokens": tout})
    if outcome == "succeeded":
        out = {"outcome": "done", "artifact_path": artifact} if artifact else {"outcome": "done"}
        events.emit(event_type="run.succeeded", agg_type="run", agg_id=run_id,
                    project_id=project, actor_type="system", actor_id="runtime:x",
                    payload={"outcome": "done", "output": out})
    else:
        events.emit(event_type="run.failed", agg_type="run", agg_id=run_id,
                    project_id=project, actor_type="system", actor_id="runtime:x",
                    payload={"error": "boom"})


def test_retry_lineage_single_run(client, project):
    _seed_run(client, project, "r_lin_base", "failed", steps=2, tin=100, tout=50)
    u = client.get("/api/runs/r_lin_base/retry-lineage").json()
    assert u["run_id"] == "r_lin_base"
    assert u["retried"] is False and u["length"] == 1
    link = u["chain"][0]
    assert link["status"] == "failed"
    assert link["steps"] == 2
    assert link["input_tokens"] == 100 and link["output_tokens"] == 50
    assert link["artifact"] is None
    assert client.get("/api/runs/r_missing/retry-lineage").status_code == 404


def test_retry_lineage_chain_and_artifact_diff(client, project):
    _seed_run(client, project, "r_lin_a", "failed", steps=3, tin=100, tout=50)
    # 重试事件：r_lin_b 源自 r_lin_a（与 retry_run 端点同 payload 形状）
    events.emit(event_type="run.retried_from_checkpoint", agg_type="run",
                agg_id="r_lin_b", project_id=project, actor_type="human",
                actor_id="u_admin", payload={"original": "r_lin_a"})
    _seed_run(client, project, "r_lin_b", "succeeded", steps=5, tin=260, tout=140,
              artifact="artifacts/report.md")

    u = client.get("/api/runs/r_lin_b/retry-lineage").json()
    assert u["retried"] is True and u["length"] == 2
    a, b = u["chain"]
    assert [x["run_id"] for x in u["chain"]] == ["r_lin_a", "r_lin_b"]  # 最老在前
    assert a["status"] == "failed" and b["status"] == "succeeded"
    assert a["steps"] == 3 and b["steps"] == 5          # 步数 diff 可见
    assert a["input_tokens"] == 100 and b["input_tokens"] == 260
    assert a["artifact"] is None and b["artifact"] == "artifacts/report.md"

    # 三级链：c 源自 b
    events.emit(event_type="run.retried_from_checkpoint", agg_type="run",
                agg_id="r_lin_c", project_id=project, actor_type="human",
                actor_id="u_admin", payload={"original": "r_lin_b"})
    _seed_run(client, project, "r_lin_c", "succeeded", steps=5, tin=300, tout=150)
    u2 = client.get("/api/runs/r_lin_c/retry-lineage").json()
    assert u2["length"] == 3
    assert [x["run_id"] for x in u2["chain"]] == ["r_lin_a", "r_lin_b", "r_lin_c"]

    # rebuild 一致（纯读投影，链沿事件查询）
    assert client.post("/api/system/rebuild-projections").status_code == 200
    u3 = client.get("/api/runs/r_lin_c/retry-lineage").json()
    assert u3 == u2
