"""M65-I196 看板泳道（docs/01 §BJ.2，Taiga/Kanboard 列外行维度语义）：
get_board 加 swimlane_by 第二分组维度（白名单 assignee_id/feature_id/priority
——None=无泳道·非法 422），bucket 内 items 附 swimlane 键 + 响应带泳道清单
（计数降序），saved_views 白名单加 swimlane_by 键持久化。纯读投影——零新表
零新事件，rebuild 无涉。"""
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
    p = client.post("/api/projects",
                    json={"name": "泳道项目", "ontology": "software-dev"}).json()
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    client.post("/api/users", json={"id": "dev-li", "name": "开发李"})
    a = client.post(f"/api/projects/{p['id']}/items",
                    json={"concept_id": "task", "title": "甲项", "priority": "high"}).json()
    b = client.post(f"/api/projects/{p['id']}/items",
                    json={"concept_id": "task", "title": "乙项", "priority": "low"}).json()
    c = client.post(f"/api/projects/{p['id']}/items",
                    json={"concept_id": "task", "title": "丙项"}).json()
    for it, uid in ((a, "qa-wang"), (b, "dev-li")):
        client.patch(f"/api/items/{it['id']}",
                     json={"assignee_type": "human", "assignee_id": uid})
    return p["id"]


def test_swimlane_by_assignee(client, project):
    b = client.get(f"/api/projects/{project}/board",
                   params={"swimlane_by": "assignee_id"}).json()
    assert b["swimlane_by"] == "assignee_id"
    # 两个已指派 + 一个未指派（（空）泳道）
    assert {s["id"] for s in b["swimlanes"]} == {"qa-wang", "dev-li", "（空）"}
    counts = {s["id"]: s["count"] for s in b["swimlanes"]}
    assert counts["qa-wang"] == 1 and counts["dev-li"] == 1 and counts["（空）"] == 1
    # bucket 内 items 带 swimlane 标注
    flat = [it for bucket in b["buckets"] for it in bucket["items"]]
    tagged = {it["id"]: it["swimlane"] for it in flat}
    assert set(tagged.values()) == {"qa-wang", "dev-li", "（空）"}


def test_swimlane_by_priority_and_none(client, project):
    b = client.get(f"/api/projects/{project}/board",
                   params={"swimlane_by": "priority"}).json()
    ids = {s["id"] for s in b["swimlanes"]}
    assert ids == {"high", "low", "（空）"}
    # None（不带参数）= 无泳道：响应无 swimlane 键，items 无标注
    b2 = client.get(f"/api/projects/{project}/board").json()
    assert "swimlane_by" not in b2
    flat2 = [it for bucket in b2["buckets"] for it in bucket["items"]]
    assert all("swimlane" not in it for it in flat2)
    # 非法值 422
    assert client.get(f"/api/projects/{project}/board",
                      params={"swimlane_by": "color"}).status_code == 422


def test_swimlane_via_saved_view(client, project):
    v = client.post(f"/api/projects/{project}/views", json={
        "name": "按执行者泳道",
        "definition": {"swimlane_by": "assignee_id"},
        "is_public": True}).json()
    vid = v["id"] if isinstance(v, dict) and "id" in v else v["view"]["id"]
    b = client.get(f"/api/projects/{project}/board", params={"view_id": vid}).json()
    assert b["swimlane_by"] == "assignee_id"  # 视图定义落盘并被应用
    # 白名单内的键才被视图接受（views 只校验键名，泳道值语义在 board 应用时校验）
    assert client.post(f"/api/projects/{project}/views", json={
        "name": "坏键", "definition": {"swimlane_color": "x"},
        "is_public": True}).status_code == 422
    # 非法泳道值在 board 应用时 422
    v_bad = client.post(f"/api/projects/{project}/views", json={
        "name": "坏泳道值", "definition": {"swimlane_by": "color"},
        "is_public": True}).json()
    vid_bad = v_bad["id"] if isinstance(v_bad, dict) and "id" in v_bad else v_bad["view"]["id"]
    assert client.get(f"/api/projects/{project}/board",
                      params={"view_id": vid_bad}).status_code == 422
