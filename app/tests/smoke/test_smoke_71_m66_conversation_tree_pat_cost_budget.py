"""Smoke 71 (M66): factory access & governance — ① conversation lineage tree:
a branch created via the Branch-in-new-chat write face shows up as a child in
`GET /projects/{id}/conversations/tree`; ② a personal access token authenticates
a real API write as its creator, records last_used, and dies on revoke; ③ the
cost-budget guard: month spend past the budget blocks new runs with 402 while
the soft band warns but allows."""
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
def test_smoke_71_m66_conversation_tree_pat_cost_budget(client, tmp_data,
                                                        isolated_ontologies,
                                                        monkeypatch):
    p = client.post("/api/projects",
                    json={"name": "冒烟工厂接入", "ontology": "software-dev"}).json()
    pid = p["id"]

    # --- ① 对话树：分支写入面 + 血缘投影 ----------------------------------------
    root = client.post("/api/conversations",
                       json={"project_id": pid, "kind": "executing",
                             "title": "主线会话", "instruction": "主线"}).json()
    branch = client.post("/api/conversations",
                         json={"project_id": pid, "kind": "executing",
                               "title": "主线会话 · 分支", "instruction": "支线",
                               "parent_conversation_id": root["id"]}).json()
    cross = client.post("/api/projects",
                        json={"name": "冒烟他项目", "ontology": "software-dev"}).json()
    assert client.post("/api/conversations", json={
        "project_id": cross["id"], "kind": "adhoc",
        "parent_conversation_id": root["id"]}).status_code == 422

    tree = client.get(f"/api/projects/{pid}/conversations/tree").json()
    root_node = next(n for n in tree["roots"] if n["id"] == root["id"])
    assert [c["id"] for c in root_node["children"]] == [branch["id"]]
    assert root_node["children"][0]["parent_conversation_id"] == root["id"]

    # --- ② PAT：display-once → Bearer 写入 → last_used → 吊销 -------------------
    config.settings.admin_password = "smoke-admin"
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    client.post("/api/users", json={"id": "ci-runner", "name": "CI Runner",
                                    "password": "smoke-ci"})
    monkeypatch.setattr(config.settings, "auth_mode", "network")
    try:
        assert client.post("/api/auth/login",
                           json={"user_id": "ci-runner",
                                 "password": "smoke-ci"}).status_code == 200
        tok = client.post("/api/auth/tokens",
                          json={"name": "外部 agent", "expires_in_days": 30}).json()
        assert tok["token"].startswith("apm_")
        client.post("/api/auth/logout")

        h = {"Authorization": f"Bearer {tok['token']}"}
        # anonymous write is refused; the same write via Bearer lands as its creator
        assert client.post("/api/projects", json={"name": "x"}).status_code == 401
        made = client.post("/api/projects",
                           json={"name": "令牌项目", "ontology": "software-dev"},
                           headers=h)
        assert made.status_code == 200

        assert client.post("/api/auth/login",
                           json={"user_id": "ci-runner",
                                 "password": "smoke-ci"}).status_code == 200
        row = client.get("/api/auth/tokens").json()["tokens"][0]
        assert row["last_used_at"] and row["revoked_at"] is None
        assert client.delete(f"/api/auth/tokens/{tok['id']}").status_code == 200
        client.post("/api/auth/logout")
        assert client.post("/api/projects", json={"name": "x"}, headers=h).status_code == 401
    finally:
        config.settings.admin_password = ""
        monkeypatch.setattr(config.settings, "auth_mode", "local")

    # --- ③ 成本预算护栏：硬顶 402 / 软阈 warning --------------------------------
    client.patch(f"/api/projects/{pid}", json={"cost_budget_usd": 0.05})
    for i, cost in enumerate(("0.04", "0.03"), start=1):
        events.emit(event_type="run.requested", agg_type="run", agg_id=f"r_s71_{i}",
                    project_id=pid, actor_type="human", actor_id="u_admin",
                    payload={"agent_role": "dev-agent", "instruction": "造账",
                             "conversation_id": root["id"]})
        events.emit(event_type="run.started", agg_type="run", agg_id=f"r_s71_{i}",
                    project_id=pid, actor_type="system", actor_id="runtime:x",
                    payload={"thread_id": f"r_s71_{i}"})
        events.emit(event_type="run.tokens_recorded", agg_type="run", agg_id=f"r_s71_{i}",
                    project_id=pid, actor_type="system", actor_id="runtime:x",
                    payload={"input_tokens": 100, "output_tokens": 50,
                             "estimated_cost_usd": float(cost)})

    budget = client.get(f"/api/projects/{pid}/cost-budget").json()
    assert budget["month_spend_usd"] == pytest.approx(0.07)
    assert budget["ratio"] >= 1
    assert client.post("/api/runs", json={"conversation_id": root["id"],
                                          "agent_role": "dev-agent"}).status_code == 402

    # raising the budget to the soft band (0.07/0.08 = 87.5%) lets runs start
    # again, with the warning riding on the response
    client.patch(f"/api/projects/{pid}", json={"cost_budget_usd": 0.08})
    r = client.post("/api/runs", json={"conversation_id": root["id"],
                                       "agent_role": "dev-agent", "wait": True})
    assert r.status_code == 200
    assert r.json()["budget_warning"]["cost_budget_usd"] == 0.08
