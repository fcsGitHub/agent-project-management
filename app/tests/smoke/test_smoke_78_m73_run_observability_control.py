"""Smoke 78 (M73): run observability & control — ① a kickoff with a one-shot
instruction echoes it on get_run and the runs listing (runs.input read face);
② the work-item view of run history (/runs?item_id=) lists that run; ③ a
role override at kickoff sticks (qa-agent on a drafting conversation — the
kind default would have been pm-agent)."""
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
def test_smoke_78_m73_run_observability_control(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "冒烟可观测", "ontology": "software-dev"}).json()["id"]
    item = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "冒烟观测工件"}).json()
    conv = client.post("/api/conversations",
                       json={"project_id": pid, "kind": "drafting"}).json()

    # --- ① 一次性指令发起 → runs.input 回显（对话 L3 不被污染）-------------------
    events.emit(event_type="run.requested", agg_type="run", agg_id="r_s78_1",
                project_id=pid, actor_type="human", actor_id="u_admin",
                payload={"agent_role": "dev-agent", "conversation_id": conv["id"],
                         "item_id": item["id"],
                         "instruction": "本次只出边界用例清单"})
    events.emit(event_type="run.started", agg_type="run", agg_id="r_s78_1",
                project_id=pid, actor_type="system", actor_id="runtime:r_s78_1",
                payload={"thread_id": "r_s78_1"})
    mine = [x for x in client.get(f"/api/runs?project_id={pid}").json()["runs"]
            if x["id"] == "r_s78_1"]
    assert mine and mine[0]["input"] == "本次只出边界用例清单"
    assert client.get(f"/api/conversations/{conv['id']}").json()["instruction"] in (None, "")

    # --- ② 工件项视角运行历史：/runs?item_id= 命中该 run -------------------------
    by_item = client.get(f"/api/runs?item_id={item['id']}").json()["runs"]
    assert [r["id"] for r in by_item if r["id"] == "r_s78_1"]

    # --- ③ 角色覆盖：drafting 对话用 qa-agent 发起（kind 默认是 pm-agent）--------
    events.emit(event_type="run.requested", agg_type="run", agg_id="r_s78_2",
                project_id=pid, actor_type="human", actor_id="u_admin",
                payload={"agent_role": "qa-agent", "conversation_id": conv["id"],
                         "item_id": item["id"], "instruction": None})
    events.emit(event_type="run.started", agg_type="run", agg_id="r_s78_2",
                project_id=pid, actor_type="system", actor_id="runtime:r_s78_2",
                payload={"thread_id": "r_s78_2"})
    by_item = client.get(f"/api/runs?item_id={item['id']}").json()["runs"]
    roles = {r["id"]: r["agent_role"] for r in by_item}
    assert roles["r_s78_2"] == "qa-agent"  # override sticks
    assert roles["r_s78_1"] == "dev-agent"
