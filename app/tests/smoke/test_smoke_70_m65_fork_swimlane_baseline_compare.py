"""Smoke 70 (M65): orchestration depth — ① a run fork branches off with
`forked_from` lineage while the mainline run stays untouched, and the tree
view reads both the retry edge and the fork edge; ② board swimlanes split
each lifecycle column into per-assignee sub-rows with counts; ③ the two-
baseline compare reports shift/added/removed against real snapshots."""
from __future__ import annotations

import pytest

from apm import config
from apm.core import events


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.mark.smoke
def test_smoke_70_m65_fork_swimlane_baseline_compare(client, tmp_data,
                                                     isolated_ontologies):
    p = client.post("/api/projects",
                    json={"name": "冒烟编排纵深", "ontology": "software-dev"}).json()
    pid = p["id"]
    client.post("/api/users", json={"id": "dev-li", "name": "开发李"})

    # --- ① 运行分叉：主线不动，支线带 forked_from 血缘 --------------------------
    conv = client.post("/api/conversations",
                       json={"project_id": pid, "kind": "executing",
                             "instruction": "主线指令"}).json()
    events.emit(event_type="run.requested", agg_type="run", agg_id="r_s70_main",
                project_id=pid, actor_type="human", actor_id="u_admin",
                payload={"agent_role": "dev-agent", "instruction": "主线指令",
                         "conversation_id": conv["id"]})
    events.emit(event_type="run.started", agg_type="run", agg_id="r_s70_main",
                project_id=pid, actor_type="system", actor_id="runtime:x",
                payload={"thread_id": "r_s70_main"})
    events.emit(event_type="run.succeeded", agg_type="run", agg_id="r_s70_main",
                project_id=pid, actor_type="system", actor_id="runtime:x",
                payload={"outcome": "done", "output": {"outcome": "done"}})

    fr = client.post("/api/runs/r_s70_main/fork",
                     json={"instruction": "支线：只做最小实现"})
    assert fr.status_code == 200, fr.text
    fork_id = fr.json()["new_run"]["id"]
    assert client.get("/api/runs/r_s70_main").json()["status"] == "succeeded"  # 主线不动
    assert client.get(f"/api/events",
                      params={"event_type": "run.forked"}).json()["events"][0][
        "payload"]["forked_from"] == "r_s70_main"

    # 树视图：主线为根，支线 via=fork depth=1
    tree = client.get("/api/runs/r_s70_main/retry-lineage", params={"tree": 1}).json()
    assert [n["run_id"] for n in tree["tree"]][0] == "r_s70_main"
    fork_node = next(n for n in tree["tree"] if n["run_id"] == fork_id)
    assert fork_node["via"] == "fork" and fork_node["depth"] == 1

    # --- ② 看板泳道：按执行者分行 ----------------------------------------------
    a1 = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "甲项", "priority": "high"}).json()
    a2 = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "乙项"}).json()
    client.patch(f"/api/items/{a1['id']}",
                 json={"assignee_type": "human", "assignee_id": "dev-li"})
    b = client.get(f"/api/projects/{pid}/board",
                   params={"swimlane_by": "assignee_id"}).json()
    assert b["swimlane_by"] == "assignee_id"
    lanes = {s["id"]: s["count"] for s in b["swimlanes"]}
    assert lanes["dev-li"] == 1
    tagged = {it["id"]: it.get("swimlane") for bucket in b["buckets"] for it in bucket["items"]}
    assert tagged[a1["id"]] == "dev-li" and tagged[a2["id"]] == "（空）"

    # --- ③ 基线对比：两版快照的漂移/新增/消失 -----------------------------------
    x = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "漂移项",
                          "start_date": "2026-10-05", "due_date": "2026-10-09"}).json()
    w = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "归档项",
                          "start_date": "2026-10-05", "due_date": "2026-10-06"}).json()
    client.post(f"/api/projects/{pid}/baseline")
    client.patch(f"/api/items/{x['id']}",
                 json={"start_date": "2026-10-08", "due_date": "2026-10-14"})
    client.post(f"/api/items/{w['id']}/archive")
    client.post(f"/api/projects/{pid}/items",
                json={"concept_id": "task", "title": "新增项",
                      "start_date": "2026-10-12", "due_date": "2026-10-16"})
    client.post(f"/api/projects/{pid}/baseline")

    baselines = client.get(f"/api/projects/{pid}/baselines").json()["baselines"]
    cmp = client.get(f"/api/projects/{pid}/baselines/compare", params={
        "a": baselines[0]["id"], "b": baselines[1]["id"]}).json()
    assert cmp["summary"]["shifted"] == 1
    assert cmp["summary"]["removed"] == 1  # 归档项离开计划（M65 快照语义）
    assert cmp["summary"]["added"] == 1
    assert cmp["shifted"][0]["due_shift_days"] == 5
