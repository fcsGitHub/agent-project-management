"""M59-I177 「等待我」行动聚合（docs/01 §BD.1，Linear Inbox 行动视角）：
待我审批（owner 决策权，与 I96 approval 通知收件人同口径）/等我恢复的运行
（成员可见项目内 interrupted）/我的临期项（assignee=me·due≤3 天未完成）。
行动视角与任务视角正交：贡献者看得见等恢复的运行却看不见审批；rebuild 一致。"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from apm import config


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


def test_my_attention_three_sections(client, tmp_data, isolated_ontologies):
    from tests.conftest import wait_for

    p1 = client.post("/api/projects",
                     json={"name": "行动聚合甲", "ontology": "software-dev",
                           "requirement": "r"}).json()
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    assert client.post(f"/api/projects/{p1['id']}/members",
                       json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200

    # 临期面三例：今天到期（进）/10 天后（不进）/今天到期但已完成（不进）
    today = date.today().isoformat()
    far = (date.today() + timedelta(days=10)).isoformat()
    it_today = client.post(f"/api/projects/{p1['id']}/items",
                           json={"concept_id": "task", "title": "今天到期",
                                 "due_date": today}).json()
    client.patch(f"/api/items/{it_today['id']}",
                 json={"assignee_type": "human", "assignee_id": "qa-wang"})
    it_far = client.post(f"/api/projects/{p1['id']}/items",
                         json={"concept_id": "task", "title": "远期不进",
                               "due_date": far}).json()
    client.patch(f"/api/items/{it_far['id']}",
                 json={"assignee_type": "human", "assignee_id": "qa-wang"})
    it_done = client.post(f"/api/projects/{p1['id']}/items",
                          json={"concept_id": "task", "title": "已完成不进",
                                "due_date": today}).json()
    client.patch(f"/api/items/{it_done['id']}",
                 json={"assignee_type": "human", "assignee_id": "qa-wang"})
    client.patch(f"/api/items/{it_done['id']}", json={"status": "done"})

    # 运行面：真实 run → Gate 挂起（interrupted）
    run = client.post("/api/runs", json={
        "conversation_id": p1["bootstrap"]["conversation_id"],
        "agent_role": "pm-agent"}).json()
    wait_for(lambda: client.get(f"/api/runs/{run['id']}").json()["status"] == "interrupted")

    # qa-wang 视角（contributor）：run 可见、审批不可见（非 owner 无决策权）
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    att = client.get("/api/my/attention").json()
    assert att["counts"]["approvals"] == 0
    assert att["counts"]["runs"] == 1 and att["runs"][0]["id"] == run["id"]
    assert att["counts"]["due"] == 1 and att["due"][0]["title"] == "今天到期"
    client.post("/api/session/identity", json={"user_id": "u_admin"})

    # u_admin 视角（owner）：审批进入等待面
    att2 = client.get("/api/my/attention").json()
    assert att2["counts"]["approvals"] == 1
    assert att2["counts"]["runs"] == 1
    assert att2["counts"]["due"] == 0  # 未指派给 admin

    # 批准后 run 终结：两个分区同时退场
    apr = client.get("/api/approvals",
                     params={"status": "pending", "project_id": p1["id"]}).json()["approvals"][0]
    client.post(f"/api/approvals/{apr['id']}/decision", json={"decision": "approved"})
    wait_for(lambda: client.get(f"/api/runs/{run['id']}").json()["status"] != "interrupted")
    att3 = client.get("/api/my/attention").json()
    assert att3["counts"]["approvals"] == 0 and att3["counts"]["runs"] == 0

    # rebuild 一致（纯投影）
    from apm.core import projections
    projections.ensure_handlers_registered()
    projections.rebuild()
    assert client.get("/api/my/attention").json()["counts"] == att3["counts"]
