"""M63-I190 项目级通知降级（docs/01 §BH.2，GitHub watch 三档取两档）：
project_members.notify_level——"mentions_only" 静音参与类通知（评论参与面/
状态变更参与面），mention/approval/assignment/due_soon/watch 等治理必达与
显式订阅照常（Ignore 连提及都吞过于激进，取 Slack「保留直接提及」语义）。
本人可降级自己，他人需 owner/admin。"""
from __future__ import annotations

import pytest

from apm import config


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    return client.post("/api/projects",
                       json={"name": "降噪项目", "ontology": "software-dev"}).json()["id"]


def _add_member(client, pid: str, uid: str, role: str = "contributor") -> None:
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": uid, "role": role}).status_code == 200


def test_mentions_only_mutes_participant_noise(client, project):
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    _add_member(client, project, "qa-wang")
    it = client.post(f"/api/projects/{project}/items",
                     json={"concept_id": "task", "title": "参与项"}).json()
    # 显式指派 → item.assigned →参与者登记 + assigned 通知基线
    client.patch(f"/api/items/{it['id']}",
                 json={"assignee_type": "human", "assignee_id": "qa-wang"})

    # 降级前的参与面基线：状态变更通知参与者（open → ready）
    client.patch(f"/api/items/{it['id']}", json={"status": "ready"})
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    base_kinds = [n["kind"] for n in
                  client.get("/api/notifications").json()["notifications"]]
    assert "assigned" in base_kinds and "item" in base_kinds
    client.post("/api/notifications/read", json={"all": True})  # 清基线，后续只看新增
    # qa-wang 切「仅提及」（本人操作——降级自己无需 owner）
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    assert client.patch(f"/api/projects/{project}/members/qa-wang/notify-level",
                        json={"level": "mentions_only"}).status_code == 200

    client.patch(f"/api/items/{it['id']}", json={"status": "in_progress"})  # 参与面静音
    client.post(f"/api/items/{it['id']}/comments", json={
        "body": "普通讨论 @QA 王 请看"})
    it2 = client.post(f"/api/projects/{project}/items",
                      json={"concept_id": "task", "title": "指派照达"}).json()
    client.patch(f"/api/items/{it2['id']}",
                 json={"assignee_type": "human", "assignee_id": "qa-wang"})

    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    notes = [n for n in client.get("/api/notifications").json()["notifications"]
             if not n["read"]]  # 只看基线清空后的新增
    kinds = [n["kind"] for n in notes]
    # 参与类被静音：无 comment 参与/无 item 状态变更参与通知
    assert "comment" not in kinds
    assert not [n for n in notes if n["kind"] == "item"]
    # 治理必达照常：@提及 + 指派
    assert "mention" in kinds
    assert "assigned" in kinds
    client.post("/api/notifications/read", json={"all": True})

    # 列表透出档位；回退默认后参与面恢复
    members = client.get(f"/api/projects/{project}/members").json()["members"]
    me = next(m for m in members if m["user_id"] == "qa-wang")
    assert me["notify_level"] == "mentions_only"
    assert client.patch(f"/api/projects/{project}/members/qa-wang/notify-level",
                        json={"level": None}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    client.patch(f"/api/items/{it['id']}", json={"status": "awaiting_review"})
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    notes2 = [n for n in client.get("/api/notifications").json()["notifications"]
              if not n["read"]]
    assert any(n["kind"] == "item" for n in notes2), "回退默认后参与面应恢复"


def test_notify_level_permissions_and_validation(client, project, monkeypatch):
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "password": "qa-pass"})
    _add_member(client, project, "qa-wang")
    client.post("/api/users", json={"id": "helper", "name": "帮手", "password": "help-pass"})
    _add_member(client, project, "helper")
    # 非本人非 owner（network 模式已登录 qa-wang 改 helper）→ 403
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    monkeypatch.setattr(config.settings, "auth_mode", "network")
    try:
        assert client.post("/api/auth/login",
                           json={"user_id": "qa-wang", "password": "qa-pass"}).status_code == 200
        # 本人改自己 OK（无需 owner）
        assert client.patch(f"/api/projects/{project}/members/qa-wang/notify-level",
                            json={"level": "mentions_only"}).status_code == 200
        # 非本人非 owner 403
        assert client.patch(f"/api/projects/{project}/members/helper/notify-level",
                            json={"level": "mentions_only"}).status_code == 403
        # owner/admin 可改他人
        assert client.post("/api/auth/login",
                           json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
        assert client.patch(f"/api/projects/{project}/members/helper/notify-level",
                            json={"level": "mentions_only"}).status_code == 200
        # 坏档 422
        assert client.patch(f"/api/projects/{project}/members/helper/notify-level",
                            json={"level": "ignore"}).status_code == 422
        # 非成员 404
        assert client.patch(f"/api/projects/{project}/members/outsider/notify-level",
                            json={"level": "mentions_only"}).status_code == 404
    finally:
        config.settings.admin_password = ""


def test_notify_level_rebuild_consistent(client, project):
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    _add_member(client, project, "qa-wang")
    assert client.patch(f"/api/projects/{project}/members/qa-wang/notify-level",
                        json={"level": "mentions_only"}).status_code == 200
    before = client.get(f"/api/projects/{project}/members").json()["members"]

    from apm.core import projections
    projections.ensure_handlers_registered()
    projections.rebuild()
    after = client.get(f"/api/projects/{project}/members").json()["members"]
    assert after == before
