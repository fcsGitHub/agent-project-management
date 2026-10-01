"""Smoke 83 (M78): interaction completeness — ① the relation lifecycle is
closed end to end (create → remove via either side → audit fact → rebuild →
re-create: I234, docs/01 §BW.1); ② the touch affordances are locked at
source level — timeline link dots stay visible below md (I235) and the
calendar two-tap pointer path exists with synthetic-mouse suppression;
③ removing an absent relation is 404 (idempotent absence)."""
from __future__ import annotations

from pathlib import Path

import pytest

from apm.core import projections

from tests.smoke.test_smoke_82_m77_delivery_surface import ROOT


@pytest.mark.smoke
def test_smoke_83_m78_relation_lifecycle(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "冒烟83", "ontology": "software-dev"}).json()["id"]
    a = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "前置甲"}).json()["id"]
    b = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "后继乙"}).json()["id"]
    assert client.post(f"/api/items/{b}/relations",
                       json={"to_item": a, "relation_type": "depends_on"}).status_code == 200
    assert len(client.get(f"/api/items/{b}").json()["relations"]) == 1

    # 解除（to 侧路径发起——任一侧可解）：事实落账 + 投影消失
    r = client.delete(f"/api/items/{a}/relations",
                      params={"to_item": b, "relation_type": "depends_on"})
    assert r.status_code == 200, r.text
    assert len(client.get(f"/api/items/{b}").json()["relations"]) == 0
    ev = client.get("/api/events", params={"event_type": "item.relation_removed"}).json()["events"]
    assert ev and ev[0]["payload"]["from_item"] == b and ev[0]["payload"]["to_item"] == a

    # 幂等缺席：再解 404
    assert client.delete(f"/api/items/{a}/relations",
                         params={"to_item": b, "relation_type": "depends_on"}).status_code == 404

    # rebuild 存活 + 创建面仍活
    projections.ensure_handlers_registered()
    projections.rebuild()
    assert len(client.get(f"/api/items/{b}").json()["relations"]) == 0
    assert client.post(f"/api/items/{b}/relations",
                       json={"to_item": a, "relation_type": "depends_on"}).status_code == 200


@pytest.mark.smoke
def test_smoke_83_m78_touch_affordance_lock():
    tl = (ROOT / "web" / "src" / "pages" / "TimelinePage.tsx").read_text(encoding="utf-8")
    # I235: 连线触点 <768px 恒可见（opacity-60 兜底·md 起 hover 增强）
    assert "opacity-60 md:opacity-0 md:group-hover:opacity-100" in tl
    # 父级 touch-none 仍就位（有效 touch-action 沿祖先链相交覆盖子触点）
    assert "touch-none" in tl

    sp = (ROOT / "web" / "src" / "pages" / "SchedulePage.tsx").read_text(encoding="utf-8")
    # I235: 休假日历两段点选（触屏 pointer 分支 + 合成 mouse 抑制 + 双击缩放豁免）
    assert 'pointerType === "mouse"' in sp
    assert "touch-manipulation" in sp

    api = (ROOT / "web" / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
    assert "removeRelation" in api
