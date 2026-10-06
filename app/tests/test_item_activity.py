"""M115-I344 工作项活动流（docs/01 §DF，Linear 吸纳轮——事件溯源是本项目
立身之本，本件把审计流以工作项为中心读出来）：item.updated payload 补
`_old` 旧值溯源（投影只读白名单键，向后兼容），item.assigned 补 from 侧；
读面复用 /events?agg_type=item（M114-I339 成员门）。"""
from __future__ import annotations

import json

import pytest

from apm import config
from apm.core import db


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def proj(client, tmp_data, isolated_ontologies) -> dict:
    return client.post("/api/projects",
                       json={"name": "活动流项目", "ontology": "software-dev"}).json()


def _last_event(item_id: str, etype: str) -> dict:
    row = db.get_conn().execute(
        "SELECT payload FROM events WHERE event_type=? AND agg_id=?"
        " ORDER BY id DESC LIMIT 1", (etype, item_id)).fetchone()
    assert row is not None, f"no {etype} for {item_id}"
    return json.loads(row["payload"])


def test_item_updated_payload_carries_old_values(client, proj):
    r = client.post(f"/api/projects/{proj['id']}/items", json={
        "concept_id": "task", "title": "改口径项",
        "priority": "high", "due_date": "2030-01-10", "description": "旧正文",
    })
    iid = r.json()["id"]
    p = client.patch(f"/api/items/{iid}", json={
        "priority": "low", "due_date": "2030-02-20", "description": "新正文",
    })
    assert p.status_code == 200, p.text
    payload = _last_event(iid, "item.updated")
    assert payload["priority"] == "low"
    assert payload["_old"]["priority"] == "high"
    assert payload["_old"]["due_date"] == "2030-01-10"
    assert payload["_old"]["description"] == "旧正文"
    # 未变更字段不进 _old
    assert "milestone_id" not in payload["_old"]


def test_item_assigned_payload_carries_from(client, proj):
    r = client.post(f"/api/projects/{proj['id']}/items", json={
        "concept_id": "task", "title": "转派项",
    })
    iid = r.json()["id"]
    mk = client.post("/api/users", json={"id": "u_dev", "name": "开发者", "password": "dev-password-1"})
    assert mk.status_code == 200, mk.text
    other = "u_dev"
    a1 = client.patch(f"/api/items/{iid}",
                      json={"assignee_type": "human", "assignee_id": other})
    assert a1.status_code == 200, a1.text
    p1 = _last_event(iid, "item.assigned")
    assert p1["assignee_id"] == other
    assert p1["from_assignee_id"] is None  # 首次指派无前值
    a2 = client.patch(f"/api/items/{iid}",
                      json={"assignee_type": "human", "assignee_id": "u_admin"})
    p2 = _last_event(iid, "item.assigned")
    assert p2["from_assignee_id"] == other  # 转派带前值
