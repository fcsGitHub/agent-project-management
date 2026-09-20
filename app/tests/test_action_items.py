"""M49-I147 回顾行动项落地（immediate conversion）：回顾现场把行动项立即
转成受追踪的工作项——item.created payload 记 `retro_of` 审计链（同 I133
respawn 模式），owner→assignee、due→due_date；同名幂等跳过防重复；回顾
响应带出本周期与上届未结行动项（开场过账）。"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from apm import config
from apm.core import db, projections


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    return client.post("/api/projects",
                       json={"name": "行动项项目", "ontology": "software-dev"}).json()["id"]


def _d(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def test_action_items_convert_with_audit_chain(client, tmp_data, isolated_ontologies, project):
    c = client.post(f"/api/projects/{project}/cycles",
                    json={"name": "S1", "start_date": _d(-14), "end_date": _d(-1)}).json()
    r = client.post(f"/api/cycles/{c['id']}/action-items", json={"items": [
        {"title": "引入代码评审清单", "owner": "u_admin", "due_date": _d(7)},
        {"title": "压缩站会时长"},
    ]})
    assert r.status_code == 200, r.text
    created = r.json()["created"]
    assert len(created) == 2
    # 转换出的工作项带 owner/due 映射
    it = client.get(f"/api/items/{created[0]['id']}").json()
    assert it["assignee_id"] == "u_admin" and it["due_date"] == _d(7)
    # 审计链可查（retro_of 入事件流）
    ev = db.get_conn().execute(
        "SELECT payload FROM events WHERE event_type = 'item.created' AND agg_id = ?",
        (created[0]["id"],)).fetchone()["payload"]
    import json as _json

    assert _json.loads(ev)["retro_of"] == c["id"]


def test_action_items_dedupe_same_title(client, tmp_data, isolated_ontologies, project):
    c = client.post(f"/api/projects/{project}/cycles",
                    json={"name": "S1", "start_date": _d(-14), "end_date": _d(-1)}).json()
    body = {"items": [{"title": "改进部署流程"}]}
    r1 = client.post(f"/api/cycles/{c['id']}/action-items", json=body).json()
    assert len(r1["created"]) == 1
    r2 = client.post(f"/api/cycles/{c['id']}/action-items",
                     json={"items": [{"title": "改进部署流程"}, {"title": "新行动项"}]}).json()
    assert r2["skipped"] == [{"title": "改进部署流程", "reason": "already converted"}]
    assert len(r2["created"]) == 1


def test_retrospective_surfaces_open_actions(client, tmp_data, isolated_ontologies, project):
    c1 = client.post(f"/api/projects/{project}/cycles",
                     json={"name": "S1", "start_date": _d(-28), "end_date": _d(-15)}).json()
    c2 = client.post(f"/api/projects/{project}/cycles",
                     json={"name": "S2", "start_date": _d(-14), "end_date": _d(-1)}).json()
    client.post(f"/api/cycles/{c1['id']}/action-items",
                json={"items": [{"title": "上届未结行动项"}]})
    # S1 的行动项完成一项、留一项未结
    client.post(f"/api/cycles/{c1['id']}/action-items",
                json={"items": [{"title": "已结行动项"}]})
    db.get_conn().execute(
        "UPDATE items SET status = 'done', status_group = 'done'"
        " WHERE title = '已结行动项'")
    db.get_conn().commit()
    # S2 回顾：prev_open_actions 带出 S1 未结项；S2 自身无行动项
    rv = client.get(f"/api/cycles/{c2['id']}/retrospective").json()
    assert [x["title"] for x in rv["prev_open_actions"]] == ["上届未结行动项"]
    assert rv["open_actions"] == []
    rv1 = client.get(f"/api/cycles/{c1['id']}/retrospective").json()
    assert [x["title"] for x in rv1["open_actions"]] == ["上届未结行动项"]


def test_action_items_survive_rebuild(client, tmp_data, isolated_ontologies, project):
    c = client.post(f"/api/projects/{project}/cycles",
                    json={"name": "S1", "start_date": _d(-14), "end_date": _d(-1)}).json()
    r = client.post(f"/api/cycles/{c['id']}/action-items",
                    json={"items": [{"title": "重建后仍在"}]}).json()
    iid = r["created"][0]["id"]
    projections.rebuild()
    it = client.get(f"/api/items/{iid}").json()
    assert it["title"] == "重建后仍在"
    ev = db.get_conn().execute(
        "SELECT COUNT(*) AS n FROM events WHERE event_type = 'item.created' AND agg_id = ?",
        (iid,)).fetchone()["n"]
    assert ev == 1
