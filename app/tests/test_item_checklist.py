"""M63-I191 工作项检查清单（docs/01 §BH.3，GitHub tasklist 语义减去
sub-issue 转换——清单价值在同屏轻量勾选）：items.checklist 列 + 全量提交
（整列覆盖——custom_fields 纪律同款，单事实携带全量新态）+ 校验（≤20 项/
单项 1-200 字）；advisory only——清单进度不进健康分/完成率口径。"""
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
                    json={"name": "清单项目", "ontology": "software-dev"}).json()
    return client.post(f"/api/projects/{p['id']}/items",
                       json={"concept_id": "task", "title": "清单项"}).json()


def test_checklist_roundtrip(client, item):
    # 全量提交：两行，一行已勾
    r = client.patch(f"/api/items/{item['id']}/checklist", json={"items": [
        {"text": "写部署文档", "done": True},
        {"text": "核对回滚步骤", "done": False},
    ]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["done"] == 1 and body["total"] == 2

    got = client.get(f"/api/items/{item['id']}").json()
    cl = json.loads(got["checklist"])
    assert [c["text"] for c in cl] == ["写部署文档", "核对回滚步骤"]
    assert [c["done"] for c in cl] == [True, False]

    # 翻转勾选（全量覆盖语义：客户端持整单提交）
    cl[1]["done"] = True
    assert client.patch(f"/api/items/{item['id']}/checklist",
                        json={"items": cl}).status_code == 200
    got2 = client.get(f"/api/items/{item['id']}").json()
    cl2 = json.loads(got2["checklist"])
    assert all(c["done"] for c in cl2)

    # 事件在册（单事实携带全量新态——rebuild 复现）
    evs = client.get("/api/events",
                     params={"event_type": "item.checklist_updated"}).json()
    assert evs["total"] == 2

    from apm.core import projections
    projections.ensure_handlers_registered()
    projections.rebuild()
    got3 = client.get(f"/api/items/{item['id']}").json()
    assert json.loads(got3["checklist"]) == cl2


def test_checklist_validation(client, item):
    # 超过 20 项 422
    assert client.patch(f"/api/items/{item['id']}/checklist", json={"items": [
        {"text": f"项{i}", "done": False} for i in range(21)]}).status_code == 422
    # 空文本/超长文本 422
    assert client.patch(f"/api/items/{item['id']}/checklist",
                        json={"items": [{"text": "   ", "done": False}]}).status_code == 422
    assert client.patch(f"/api/items/{item['id']}/checklist",
                        json={"items": [{"text": "x" * 201, "done": False}]}).status_code == 422
    # 空清单是合法提交（清空语义）
    assert client.patch(f"/api/items/{item['id']}/checklist",
                        json={"items": []}).status_code == 200
    got = client.get(f"/api/items/{item['id']}").json()
    assert json.loads(got["checklist"]) == []


def test_checklist_does_not_bump_version(client, item):
    """清单是 advisory 面：不推 version、不发 item.updated——完成率/健康分
    口径与 automation 触发都不受勾选干扰。"""
    v0 = client.get(f"/api/items/{item['id']}").json()["version"]
    updates0 = client.get("/api/events", params={
        "event_type": "item.updated"}).json()["total"]
    client.patch(f"/api/items/{item['id']}/checklist", json={"items": [
        {"text": "仅勾选", "done": True}]})
    v1 = client.get(f"/api/items/{item['id']}").json()["version"]
    updates1 = client.get("/api/events", params={
        "event_type": "item.updated"}).json()["total"]
    assert v1 == v0 and updates1 == updates0
