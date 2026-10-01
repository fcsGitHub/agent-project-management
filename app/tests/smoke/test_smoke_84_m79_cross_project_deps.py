"""Smoke 84 (M79): cross-project dependency surface — ① the API roundtrip
(create from the downstream side, event on the from-side ledger, remove,
rebuild-stable: M47-I143 × M78-I234 semantics composed); ② the graph
endpoint's「外部依赖」placeholder stays intact for a readable foreign item;
③ source-level locks for the /deps placeholder + blocked-caliber fix (I237)
and the two-level target selector (I238)."""
from __future__ import annotations

import pytest

from apm.core import projections

from tests.smoke.test_smoke_82_m77_delivery_surface import ROOT


@pytest.mark.smoke
def test_smoke_84_m79_cross_project_roundtrip(client, tmp_data, isolated_ontologies):
    pa = client.post("/api/projects",
                     json={"name": "冒烟84上", "ontology": "software-dev"}).json()["id"]
    pb = client.post("/api/projects",
                     json={"name": "冒烟84下", "ontology": "software-dev"}).json()["id"]
    ia = client.post(f"/api/projects/{pa}/items",
                     json={"concept_id": "task", "title": "上游交付件"}).json()["id"]
    ib = client.post(f"/api/projects/{pb}/items",
                     json={"concept_id": "task", "title": "下游实现"}).json()["id"]

    # 跨项目建链（from=下游）：事件聚合 from 侧项目
    r = client.post(f"/api/items/{ib}/relations",
                    json={"to_item": ia, "relation_type": "depends_on"})
    assert r.status_code == 200, r.text
    ev = client.get("/api/events", params={"event_type": "item.related"}).json()["events"]
    assert ev and ev[0]["project_id"] == pb

    # 下游详情 relations 双向可见（/deps 的数据源）
    rels = client.get(f"/api/items/{ib}").json()["relations"]
    assert [(x["from_item"], x["to_item"], x["relation_type"]) for x in rels] == [(ib, ia, "depends_on")]

    # graph 端点占位：可读外部项显真实标题 + 来源项目名（M47-I143 语义不回退）
    g = client.get(f"/api/projects/{pb}/graph").json()
    ext = [n for n in g["nodes"] if n.get("external")]
    assert len(ext) == 1 and ext[0]["label"] == "上游交付件"
    assert ext[0]["external_project_name"] == "冒烟84上"

    # 解除（M78 面·任一侧可解）+ rebuild 存活
    assert client.delete(f"/api/items/{ib}/relations",
                         params={"to_item": ia, "relation_type": "depends_on"}).status_code == 200
    projections.ensure_handlers_registered()
    projections.rebuild()
    assert client.get(f"/api/items/{ib}").json()["relations"] == []


@pytest.mark.smoke
def test_smoke_84_m79_cross_project_source_locks():
    dg = (ROOT / "web" / "src" / "pages" / "DependencyGraphPage.tsx").read_text(encoding="utf-8")
    # I237: /deps 占位渲染 + 阻塞口径修正的源码锁
    assert "external-unknown" in dg      # 不可读占位状态（宁缺勿假红）
    assert "🔒 外部依赖" in dg
    assert "data-dep-node" in dg
    bd = (ROOT / "web" / "src" / "pages" / "Board.tsx").read_text(encoding="utf-8")
    # I238: 二级选择器源码锁
    assert "relTargetItems" in bd
    assert "跨项目依赖已建立" in bd
