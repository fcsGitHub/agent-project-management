"""M73-I219 (docs/01 §BR.1): run kickoff instruction echo — runs.input has
carried the instruction since M4; this adds the read face. start_run with an
explicit instruction lands it in the projection and get_run surfaces it, so
what the requester asked and what the agent received are visible in one place
(GitHub Actions' dispatch-inputs-invisibility is the cautionary tale)."""
from __future__ import annotations

import pytest

from apm import config
from apm.core import events


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


def test_instruction_lands_and_surfaces(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "指令回显项目", "ontology": "software-dev"}).json()["id"]
    conv = client.post("/api/conversations",
                       json={"project_id": pid, "kind": "adhoc",
                             "instruction": "对话级默认指令"}).json()

    # kickoff with a one-shot instruction (distinct from the conversation's L3)
    events.emit(event_type="run.requested", agg_type="run", agg_id="r_echo1",
                project_id=pid, actor_type="human", actor_id="u_admin",
                payload={"agent_role": "dev-agent", "conversation_id": conv["id"],
                         "instruction": "本次只做登录接口的边界用例清单"})
    events.emit(event_type="run.started", agg_type="run", agg_id="r_echo1",
                project_id=pid, actor_type="system", actor_id="runtime:r_echo1",
                payload={"thread_id": "r_echo1"})

    r = client.get("/api/runs/r_echo1")
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["input"] == "本次只做登录接口的边界用例清单"  # the echo
    assert run["agent_role"] == "dev-agent"

    # runs listing carries it too (board/runs-page data source)
    mine = [x for x in client.get(f"/api/runs?project_id={pid}").json()["runs"]
            if x["id"] == "r_echo1"]
    assert mine and mine[0]["input"] == "本次只做登录接口的边界用例清单"

    # the conversation's L3 instruction is untouched (one-shot semantics)
    conv_after = client.get(f"/api/conversations/{conv['id']}").json()
    assert conv_after["instruction"] == "对话级默认指令"
