"""M115-I343 工作项描述域（docs/01 §DF，Linear 吸纳轮——Linear issue 的
正文是 issue 管理最高频缺口）：items.description 列（建表+轻量迁移）+
create/patch/投影/读面 + FTS 索引纳入 description（描述里的关键词可被
全局搜索命中——linear issue 全文可检索的同款预期）。"""
from __future__ import annotations

import json

import pytest

from apm import config
from apm.core import db, events


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def proj(client, tmp_data, isolated_ontologies) -> dict:
    return client.post("/api/projects",
                       json={"name": "描述域项目", "ontology": "software-dev"}).json()


def test_description_create_get_patch_roundtrip(client, proj):
    r = client.post(f"/api/projects/{proj['id']}/items", json={
        "concept_id": "task", "title": "登录页重构",
        "description": "统一 OAuth 登录入口，**旧密码登录保留**。",
    })
    assert r.status_code == 200, r.text
    item = r.json()
    assert item["description"] == "统一 OAuth 登录入口，**旧密码登录保留**。"

    got = client.get(f"/api/items/{item['id']}").json()
    assert got["description"] == "统一 OAuth 登录入口，**旧密码登录保留**。"

    # PATCH 更新描述（空串=清空是合法语义，非 None 过滤）
    p = client.patch(f"/api/items/{item['id']}",
                     json={"description": "改口径：只做 OAuth。"})
    assert p.status_code == 200, r.text
    assert p.json()["description"] == "改口径：只做 OAuth。"

    p2 = client.patch(f"/api/items/{item['id']}", json={"description": ""})
    assert p2.status_code == 200, r.text
    assert p2.json()["description"] == ""


def test_description_rebuild_survives(client, proj):
    r = client.post(f"/api/projects/{proj['id']}/items", json={
        "concept_id": "task", "title": "导入导出", "description": "NDJSON 描述正文",
    })
    iid = r.json()["id"]
    rr = client.post("/api/system/rebuild-projections")
    assert rr.status_code == 200, rr.text
    got = client.get(f"/api/items/{iid}").json()
    assert got["description"] == "NDJSON 描述正文"


def test_description_indexed_for_search(client, proj):
    r = client.post(f"/api/projects/{proj['id']}/items", json={
        "concept_id": "task", "title": "计费重构",
        "description": "迁移到 stripe-billing 新通道",
    })
    iid = r.json()["id"]
    # 标题不含关键词，描述含——描述必须进 FTS 索引
    res = client.get("/api/search", params={"q": "stripe-billing", "types": "items"})
    assert res.status_code == 200, res.text
    ids = [row["id"] for row in res.json()["items"]]
    assert iid in ids


def test_description_event_stream_carries_payload(client, proj):
    r = client.post(f"/api/projects/{proj['id']}/items", json={
        "concept_id": "task", "title": "事件载荷", "description": "正文入库",
    })
    iid = r.json()["id"]
    client.patch(f"/api/items/{iid}", json={"description": "正文更新"})
    row = db.get_conn().execute(
        "SELECT payload FROM events WHERE event_type='item.updated' AND agg_id=?"
        " ORDER BY id DESC LIMIT 1", (iid,)).fetchone()
    assert row is not None
    assert json.loads(row["payload"])["description"] == "正文更新"
