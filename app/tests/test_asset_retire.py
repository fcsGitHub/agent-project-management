"""M75-I225 资产退役与归档（docs/01 §BT.1）：asset.deprecated/archived 两个
事件此前有投影注册与读侧语义却零发射方（半截链第九例，唯一的 deprecated
生产者是 superseded 投影）——补齐发射方。退役=保留在库+退出吃灰判定
（stale 只认 published）；归档=清单消失（search 滤 status != 'archived'·
详情读无此过滤仍可读）——重复退役/重复归档 409（require_asset 对 archived
并不 404——archived 过滤只住 _reindex 与 search）。upsert 投影只认
payload.status/payload.tags——发射方漏带即状态落 draft、tags 被清空，
断言退役后状态与 tags 原样即是回归防护。"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from apm.core import events
from apm.domains.assets import asset_insights


def _mk_published_asset(client, title) -> dict:
    a = client.post("/api/projects",
                    json={"name": f"来源-{title}", "ontology": "software-dev",
                          "requirement": "沉淀"}).json()
    r = client.put(f"/api/projects/{a['id']}/artifacts/test/retire.md",
                   json={"content": f"# {title}", "message": f"qa: {title}"})
    assert r.status_code == 200, r.text
    created = r.json()
    asset = client.post("/api/assets", json={
        "source_project_id": a["id"], "artifact_path": created["path"],
        "commit": created["commit"], "library": "test", "kind": "test-suite",
        "title": title, "tags": ["regression"]}).json()
    events.emit(event_type="asset.published", agg_type="asset", agg_id=asset["id"],
                actor_type="human", actor_id="u_admin",
                payload={"status": "published", "title": title, "tags": ["regression"],
                         "library": "test", "kind": "test-suite"})
    return asset


def test_deprecate_exits_stale_and_archive_hides(client, tmp_data, isolated_ontologies):
    a = _mk_published_asset(client, "退役套件")
    ins = {x["id"]: x for x in asset_insights()["assets"]}
    created = datetime.fromisoformat(ins[a["id"]]["created_at"])
    now91 = (created + timedelta(days=91)).isoformat()
    assert {x["id"]: x for x in asset_insights(now=now91)["assets"]}[a["id"]]["stale"] is True

    # 退役：deprecated 保留在库 + tags 原样 + 退出吃灰判定 + 重复退役 409
    r = client.post(f"/api/assets/{a['id']}/deprecate")
    assert r.status_code == 200, r.text
    assert r.json()["asset"]["status"] == "deprecated"
    ins2 = {x["id"]: x for x in asset_insights(now=now91)["assets"]}
    assert ins2[a["id"]]["stale"] is False
    listed = [x for x in client.get("/api/assets").json()["assets"] if x["id"] == a["id"]]
    assert listed and listed[0]["tags"] == '["regression"]'
    assert client.post(f"/api/assets/{a['id']}/deprecate").status_code == 409

    # 归档：清单消失 + 详情仍可读（读侧无 archived 过滤）+ 重复归档 409
    assert client.post(f"/api/assets/{a['id']}/archive").status_code == 200
    assert client.post(f"/api/assets/{a['id']}/archive").status_code == 409
    assert not [x["id"] for x in client.get("/api/assets").json()["assets"]
                if x["id"] == a["id"]]
    detail = client.get(f"/api/assets/{a['id']}")
    assert detail.status_code == 200 and detail.json()["status"] == "archived"
