"""M57-I172 资产使用洞察（docs/01 §BB.2，npm 信任信号的组织内翻译）：
asset.consumed / asset.linked 事实自 M6 就在流上——洞察是纯读侧投影
（零埋点，事件溯源红利第十例）；使用 Top 按消费计数排序；「久未复用」=
已发布 + 零消费 + 入库超 90 天（now 可注入保证确定）；rebuild 一致。"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from apm.core import events, projections
from apm.domains.assets import asset_insights


def _mk_asset(client, title) -> dict:
    a = client.post("/api/projects",
                    json={"name": f"来源-{title}", "ontology": "software-dev",
                          "requirement": "沉淀"}).json()
    r = client.put(f"/api/projects/{a['id']}/artifacts/test/suite.md",
                   json={"content": f"# {title}", "message": f"qa: {title}"})
    assert r.status_code == 200, r.text
    created = r.json()
    return client.post("/api/assets", json={
        "source_project_id": a["id"], "artifact_path": created["path"],
        "commit": created["commit"], "library": "test", "kind": "test-suite",
        "title": title}).json()


def _publish(asset_id: str, title: str) -> None:
    events.emit(event_type="asset.published", agg_type="asset", agg_id=asset_id,
                actor_type="human", actor_id="u_admin",
                payload={"status": "published", "title": title,
                         "library": "test", "kind": "test-suite"})


def test_asset_insights_usage_and_stale(client, tmp_data, isolated_ontologies):
    assert client.get("/api/assets/insights").json()["assets"] == []  # 空态诚实

    hot = _mk_asset(client, "热门套件")
    cold = _mk_asset(client, "吃灰套件")
    _publish(hot["id"], "热门套件")
    _publish(cold["id"], "吃灰套件")

    # 人面 link 端点 = asset.linked + asset.consumed 各一条；消费两次
    pid = client.post("/api/projects",
                      json={"name": "消费方", "ontology": "software-dev"}).json()["id"]
    assert client.post(f"/api/assets/{hot['id']}/link",
                       json={"project_id": pid}).status_code == 200
    assert client.post(f"/api/assets/{hot['id']}/link",
                       json={"project_id": pid}).status_code == 200

    ins = client.get("/api/assets/insights").json()["assets"]
    by_id = {a["id"]: a for a in ins}
    assert by_id[hot["id"]]["consumed_count"] == 2
    assert by_id[hot["id"]]["linked_count"] == 2
    assert by_id[hot["id"]]["last_consumed"]
    assert by_id[cold["id"]]["consumed_count"] == 0
    assert by_id[cold["id"]]["last_consumed"] is None
    assert ins[0]["id"] == hot["id"]  # 消费最多的排最前
    assert not by_id[cold["id"]]["stale"]  # 刚入库不满 90 天

    # now 注入 91 天后：零消费的已发布资产进入「久未复用」，有消费的不进
    created = datetime.fromisoformat(by_id[cold["id"]]["created_at"])
    now91 = (created + timedelta(days=91)).isoformat()
    ins91 = asset_insights(now=now91)["assets"]
    by91 = {a["id"]: a for a in ins91}
    assert by91[cold["id"]]["stale"] is True
    assert by91[cold["id"]]["age_days"] == 91
    assert by91[hot["id"]]["stale"] is False  # 有消费永不进吃灰清单

    # rebuild 一致（洞察是投影，重放后计数不变）
    projections.ensure_handlers_registered()
    projections.rebuild()
    ins3 = client.get("/api/assets/insights").json()["assets"]
    assert {a["id"]: a["consumed_count"] for a in ins3} \
        == {a["id"]: a["consumed_count"] for a in ins}
    assert {a["id"]: a["stale"] for a in asset_insights(now=now91)["assets"]} \
        == {a["id"]: (a["id"] == cold["id"]) for a in ins91}
