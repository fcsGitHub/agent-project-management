"""M52-I157 周报订阅制（docs/01 §AW.2，Jira subscription 语义）：收件人不再
由角色单方决定——report.subscribed/unsubscribed 事件对 + report_subscribers
投影表（进 drop 清单 rebuild 复现）；仅项目成员可订（读权限即门）；sweep
收件人 = owner ∪ 订阅者去重；per-kind 偏好门对订阅者照常生效。"""
from __future__ import annotations

import pytest

from apm import config
from apm.core import db


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    return client.post("/api/projects",
                       json={"name": "订阅项目", "ontology": "software-dev"}).json()["id"]


def test_subscribe_roundtrip_and_rebuild(client, project):
    """订阅→已订→退订→未订 roundtrip；rebuild 后订阅关系复现。"""
    pid = project
    assert client.post(f"/api/projects/{pid}/report-subscription").status_code == 200
    assert client.get(f"/api/projects/{pid}/report-subscription").json()["subscribed"] is True
    # 第二次订阅 409
    assert client.post(f"/api/projects/{pid}/report-subscription").status_code == 409

    from apm.core import projections
    projections.ensure_handlers_registered()
    projections.rebuild()
    assert client.get(f"/api/projects/{pid}/report-subscription").json()["subscribed"] is True

    assert client.delete(f"/api/projects/{pid}/report-subscription").status_code == 200
    assert client.get(f"/api/projects/{pid}/report-subscription").json()["subscribed"] is False
    # 未订阅时再退订 404
    assert client.delete(f"/api/projects/{pid}/report-subscription").status_code == 404
    evs = client.get("/api/events", params={
        "event_type": "report.subscribed"}).json()["events"]
    assert len(evs) == 1 and evs[0]["payload"]["user_id"] == "u_admin"


def test_non_member_cannot_subscribe(client, tmp_data, isolated_ontologies, project):
    """非项目成员订阅 403（读权限即门）。"""
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert client.post(f"/api/projects/{project}/report-subscription").status_code == 403
    client.post("/api/session/identity", json={"user_id": "u_admin"})


def test_sweep_notifies_owner_and_subscriber_deduped(client, project):
    """sweep 收件人并集：owner 单独一份、订阅者一份、owner 兼订阅者仍一份
    （确定性去重）；退订后不再收。"""
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    # qa-wang 加入项目为 contributor 并订阅
    assert client.post(f"/api/projects/{project}/members",
                       json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert client.post(f"/api/projects/{project}/report-subscription").status_code == 200
    # owner u_admin 也订阅（owner ∪ 订阅者 → 仍只一份）
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    assert client.post(f"/api/projects/{project}/report-subscription").status_code == 200

    from apm.domains.automations import _report_status_weekly
    assert _report_status_weekly(db.get_conn(), "2026-09-21") == 1
    sent = client.get("/api/events",
                      params={"event_type": "notification.sent"}).json()["events"]
    weekly = [e for e in sent if e["payload"].get("kind") == "report_weekly"]
    assert sorted(e["payload"]["user_id"] for e in weekly) == ["qa-wang", "u_admin"]

    # 退订后下一期不再收（owner 仍收）
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    client.delete(f"/api/projects/{project}/report-subscription")
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    assert _report_status_weekly(db.get_conn(), "2026-09-28") == 1
    sent2 = client.get("/api/events",
                       params={"event_type": "notification.sent"}).json()["events"]
    weekly2 = [e for e in sent2 if e["payload"].get("kind") == "report_weekly"
               and e["payload"].get("week") == "2026-W40"]
    assert [e["payload"]["user_id"] for e in weekly2] == ["u_admin"]
