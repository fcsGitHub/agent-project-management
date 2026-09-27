"""M64-I194 清单转子任务（docs/01 §BI.3，BH.5 证据续期——GitLab #363613
hover 误触教训=端点是显式动作，防误触属前端职责）：checklist 项 → create_item
全校验链创建 task 概念工作项 + extracted_tasks 复用（加 source_item_id 维度
·同母项同文本 409 幂等——I67 评论面同构同链）+ checklist 项标记 extracted
（整列覆盖·done 与 extracted 正交——原始意图保留）。"""
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
def item(client, tmp_data, isolated_ontologies) -> dict:
    p = client.post("/api/projects",
                    json={"name": "清单升级项目", "ontology": "software-dev"}).json()
    it = client.post(f"/api/projects/{p['id']}/items",
                     json={"concept_id": "task", "title": "母项"}).json()
    client.patch(f"/api/items/{it['id']}/checklist", json={"items": [
        {"text": "写部署文档", "done": False},
        {"text": "核对回滚步骤", "done": True},
    ]})
    return it


def test_extract_creates_task_and_marks_entry(client, item):
    r = client.post(f"/api/items/{item['id']}/checklist/extract", json={"index": 0})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["text"] == "写部署文档"
    assert body["item"]["concept_id"] == "task"

    # 派生任务真实存在
    got = client.get(f"/api/items/{body['item']['id']}").json()
    assert got["title"] == "写部署文档" and got["project_id"] == item["project_id"]

    # checklist 项被标记 extracted；done 保持不动（正交）
    cl = json.loads(client.get(f"/api/items/{item['id']}").json()["checklist"])
    assert cl[0]["extracted"] == body["item"]["id"]
    assert cl[0]["done"] is False
    assert "extracted" not in cl[1]

    # extracted_tasks 记录（source_item_id 维度）
    row = db.get_conn().execute(
        "SELECT source_item_id, comment_id, item_id FROM extracted_tasks WHERE item_id = ?",
        (body["item"]["id"],)).fetchone()
    assert row["source_item_id"] == item["id"]


def test_extract_idempotent_and_validation(client, item):
    # 越界 422
    assert client.post(f"/api/items/{item['id']}/checklist/extract",
                       json={"index": 9}).status_code == 422
    r = client.post(f"/api/items/{item['id']}/checklist/extract", json={"index": 0})
    assert r.status_code == 200
    new_id = r.json()["item"]["id"]

    # 同项同文本 409（extracted_tasks 维度）
    # 注意整列覆盖语义：改第二项必须带上第一项的 extracted 标记（与前端行为一致）
    cl = json.loads(client.get(f"/api/items/{item['id']}").json()["checklist"])
    cl[1] = {"text": "写部署文档", "done": False}
    client.patch(f"/api/items/{item['id']}/checklist", json={"items": cl})
    assert client.post(f"/api/items/{item['id']}/checklist/extract",
                       json={"index": 1}).status_code == 409
    # （上面这次提交把 cl[0] 的标记抹掉了——整列覆盖下合法；重建标记以便 rebuild 断言）
    client.patch(f"/api/items/{item['id']}/checklist", json={"items": [
        {"text": "写部署文档", "done": False, "extracted": new_id},
        {"text": "写部署文档", "done": False}]})
    assert client.post(f"/api/items/{item['id']}/checklist/extract",
                       json={"index": 0}).status_code == 409
    # 已标记项直接 409（快速路径）
    assert client.post(f"/api/items/{item['id']}/checklist/extract",
                       json={"index": 0}).status_code == 409
    assert db.get_conn().execute(
        "SELECT COUNT(*) AS n FROM extracted_tasks WHERE source_item_id = ?",
        (item["id"],)).fetchone()["n"] == 1
    assert client.get(f"/api/items/{new_id}").json()["title"] == "写部署文档"

    # rebuild 一致（标记与 extracted_tasks 都在投影里复现）
    assert client.post("/api/system/rebuild-projections").status_code == 200
    cl2 = json.loads(client.get(f"/api/items/{item['id']}").json()["checklist"])
    assert cl2[0]["extracted"] == new_id
