"""M65-I195 运行分叉（docs/01 §BJ.1，Git branch 隐喻的 run 域翻译——
LangGraph fork 语义：主线保留、支线试验）：POST /runs/{id}/fork 以原 run 的
conversation/item/role/instruction 为底开新 run（start_run 标准链·run_id
由 fork 端点先铸造——lineage emit 先于 requested），原 run 及其重试链不动；
lineage 端点 ?tree=1 沿 retry+fork 双边回溯返回分支树。不做 state 级编辑
续跑——Gate 审批已是人在环编辑点。"""
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
                       json={"name": "分叉项目", "ontology": "software-dev"}).json()["id"]


def _seed(client, project: str, run_id: str, instruction: str = "原始指令") -> dict:
    """Real conversation (fork's start_run reuses it) + run events."""
    conv = client.post("/api/conversations",
                       json={"project_id": project, "kind": "executing",
                             "instruction": instruction}).json()
    events.emit(event_type="run.requested", agg_type="run", agg_id=run_id,
                project_id=project, actor_type="human", actor_id="u_admin",
                payload={"agent_role": "dev-agent", "instruction": instruction,
                         "conversation_id": conv["id"]})
    events.emit(event_type="run.started", agg_type="run", agg_id=run_id,
                project_id=project, actor_type="system", actor_id="runtime:x",
                payload={"thread_id": run_id})
    events.emit(event_type="run.succeeded", agg_type="run", agg_id=run_id,
                project_id=project, actor_type="system", actor_id="runtime:x",
                payload={"outcome": "done", "output": {"outcome": "done"}})
    return client.get(f"/api/runs/{run_id}").json()


def test_fork_creates_branch_and_keeps_mainline(client, project):
    _seed(client, project, "r_fork_a")
    before = client.get("/api/runs/r_fork_a").json()

    r = client.post("/api/runs/r_fork_a/fork",
                    json={"instruction": "换一种思路：只做最小实现"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["forked_from"] == "r_fork_a"
    fork = body["new_run"]
    assert fork["id"] != "r_fork_a"
    assert fork["conversation_id"] == before["conversation_id"]
    assert fork["input"] == "换一种思路：只做最小实现"  # 修正指令覆盖

    # 主线不动：原 run 状态与字段一致
    after = client.get("/api/runs/r_fork_a").json()
    assert after["status"] == before["status"] == "succeeded"

    # 血缘事件在册
    evs = client.get("/api/events", params={"event_type": "run.forked"}).json()["events"]
    assert len(evs) == 1 and evs[0]["payload"]["forked_from"] == "r_fork_a"
    assert evs[0]["agg_id"] == fork["id"]  # 分叉血缘挂在支线 id 上

    # 超长修正指令 422
    assert client.post("/api/runs/r_fork_a/fork",
                       json={"instruction": "x" * 501}).status_code == 422
    assert client.post("/api/runs/r_missing/fork", json={}).status_code == 404


def test_fork_tree_lineage(client, project):
    _seed(client, project, "r_t_a")
    events.emit(event_type="run.retried_from_checkpoint", agg_type="run",
                agg_id="r_t_b", project_id=project, actor_type="human",
                actor_id="u_admin", payload={"original": "r_t_a"})
    _seed(client, project, "r_t_b")
    # a 的两个分支：重试链 b + 分叉支线 c
    client.post("/api/runs/r_t_a/fork", json={"instruction": "支线实验"})
    tree = client.get("/api/runs/r_t_a/retry-lineage", params={"tree": 1}).json()
    assert tree["retried"] is False  # a 自己没有重试父链
    nodes = tree["tree"]
    assert [n["run_id"] for n in nodes][:1] == ["r_t_a"]  # 根在前
    b = next(n for n in nodes if n["run_id"] == "r_t_b")
    c = next(n for n in nodes if n["via"] == "fork")
    assert b["via"] == "retry" and b["depth"] == 1
    assert c["depth"] == 1
    # 深链：c 的子分叉也在树里
    cc = client.post(f"/api/runs/{c['run_id']}/fork", json={}).json()["new_run"]["id"]
    tree2 = client.get("/api/runs/r_t_a/retry-lineage", params={"tree": 1}).json()
    deep = next(n for n in tree2["tree"] if n["run_id"] == cc)
    assert deep["depth"] == 2 and deep["via"] == "fork"

    # 默认（无 tree）保持 M64 线性语义：只回 retry 链
    plain = client.get("/api/runs/r_t_a/retry-lineage").json()
    assert "tree" not in plain and plain["length"] == 1

    # rebuild 一致（先等支线 run 到终态——replay provider 下 token 落完即 succeeded；
    # running 态的 duration/ended_at 仍在变化，直接对比会假红）
    from tests.conftest import wait_for

    def _settled():
        t = client.get("/api/runs/r_t_a/retry-lineage", params={"tree": 1}).json()
        return t if all(n["status"] in ("succeeded", "failed", "interrupted")
                        for n in t["tree"]) else None

    tree2 = wait_for(_settled)
    assert client.post("/api/system/rebuild-projections").status_code == 200
    tree3 = client.get("/api/runs/r_t_a/retry-lineage", params={"tree": 1}).json()
    assert tree3 == tree2
