"""Smoke 64 (M59): the action-required view and pack instantiation provenance
— /my/attention aggregates what waits for me across three sections (pending
approvals by decision rights, interrupted runs by visibility, due items by
assignment) and clears as actions are taken; template pack usages list which
projects were born from a pack and whether they lag the current version."""
from __future__ import annotations

from datetime import date

import pytest

from tests.conftest import wait_for


@pytest.fixture(autouse=True)
def _restore_identity():
    from apm import config
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.mark.smoke
def test_smoke_64_m59_attention_pack_usages(client, tmp_data, isolated_ontologies):
    # --- ① 行动聚合：真实 run 挂起 → owner 的「等待我」出现审批与运行分区 -------
    p = client.post("/api/projects",
                    json={"name": "冒烟行动聚合", "ontology": "software-dev",
                          "requirement": "attention"}).json()
    pid = p["id"]
    run = client.post("/api/runs", json={
        "conversation_id": p["bootstrap"]["conversation_id"],
        "agent_role": "pm-agent"}).json()
    wait_for(lambda: client.get(f"/api/runs/{run['id']}").json()["status"] == "interrupted")

    att = wait_for(lambda: client.get("/api/my/attention").json()
                   if client.get("/api/my/attention").json()["counts"]["runs"] else None)
    assert att["counts"]["runs"] == 1 and att["runs"][0]["id"] == run["id"]
    assert att["counts"]["approvals"] == 1  # owner 决策权

    # --- ② 临期分区：今天到期且指派给我的项 -------------------------------------
    today = date.today().isoformat()
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "冒烟临期项",
                           "due_date": today}).json()
    client.patch(f"/api/items/{it['id']}",
                 json={"assignee_type": "human", "assignee_id": "u_admin"})
    att2 = wait_for(lambda: client.get("/api/my/attention").json()
                    if client.get("/api/my/attention").json()["counts"]["due"] else None)
    assert att2["counts"]["due"] == 1 and att2["due"][0]["title"] == "冒烟临期项"

    # --- ③ 行动之后分区退场：批准 Gate → 审批与运行同时离开等待面 ---------------
    apr = wait_for(lambda: next(iter(
        client.get("/api/approvals",
                   params={"status": "pending", "project_id": pid}).json()["approvals"]), None))
    client.post(f"/api/approvals/{apr['id']}/decision", json={"decision": "approved"})
    wait_for(lambda: client.get(f"/api/runs/{run['id']}").json()["status"] != "interrupted")
    att3 = client.get("/api/my/attention").json()
    assert att3["counts"]["approvals"] == 0 and att3["counts"]["runs"] == 0
    assert att3["counts"]["due"] == 1  # 临期项仍在——直到完成

    # --- ④ 包实例溯源：两个实例 behind=0，版本对账 -------------------------------
    client.post("/api/template-packs/software-dev/instantiate",
                json={"project_name": "冒烟实例甲"})
    client.post("/api/template-packs/software-dev/instantiate",
                json={"project_name": "冒烟实例乙"})
    packs = client.get("/api/template-packs").json()["packs"]
    current = next(x["version"] for x in packs if x["name"] == "software-dev")
    u = client.get("/api/template-packs/software-dev/usages").json()
    assert u["current_version"] == current
    mine = {x["name"]: x for x in u["usages"]}
    assert mine["冒烟实例甲"]["behind"] == 0 and mine["冒烟实例乙"]["behind"] == 0
    assert mine["冒烟实例甲"]["born_version"] == current
    # 新实例排在旧实例之后（created_at 排序）
    names = [x["name"] for x in u["usages"]]
    assert names.index("冒烟实例甲") < names.index("冒烟实例乙")
