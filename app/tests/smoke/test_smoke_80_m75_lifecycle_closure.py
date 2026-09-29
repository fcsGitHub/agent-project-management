"""Smoke 80 (M75): lifecycle closure — ① an asset walks the real publish
chain (submit_review → approve the asset_review gate → publish_from_approval),
then retires (exits the stale judgment, stays listed) and archives (vanishes
from listings, detail still readable, repeat archive 409); ② a cycle is
created and cancelled (vanishes from the cycles list — list_cycles filters
cancelled_at — items untouched); ③ a saved view is renamed via PATCH (the
I226 panel wires patchView)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from apm.domains.assets import asset_insights


@pytest.mark.smoke
def test_smoke_80_m75_lifecycle_closure(client, tmp_data, isolated_ontologies):
    # --- ① 资产：真审批门发布 → 退役退出吃灰 → 归档清单隐没 ----------------------
    src = client.post("/api/projects",
                      json={"name": "冒烟资产源", "ontology": "software-dev",
                            "requirement": "M75"}).json()
    art = client.put(f"/api/projects/{src['id']}/artifacts/test/smoke80.md",
                     json={"content": "# 冒烟资产", "message": "qa: smoke80"}).json()
    asset = client.post("/api/assets", json={
        "source_project_id": src["id"], "artifact_path": art["path"],
        "commit": art["commit"], "library": "test", "kind": "test-suite",
        "title": "冒烟退役资产", "tags": ["smoke"]}).json()

    r = client.post(f"/api/assets/{asset['id']}/submit_review")
    assert r.status_code == 200, r.text
    approval_id = r.json()["approval_id"]
    r = client.post(f"/api/approvals/{approval_id}/decision",
                    json={"decision": "approved"})
    assert r.status_code == 200, r.text
    detail = client.get(f"/api/assets/{asset['id']}").json()
    assert detail["status"] == "published"

    ins = {x["id"]: x for x in asset_insights()["assets"]}
    created = datetime.fromisoformat(ins[asset["id"]]["created_at"])
    now91 = (created + timedelta(days=91)).isoformat()
    assert {x["id"]: x for x in asset_insights(now=now91)["assets"]}[asset["id"]]["stale"] is True

    r = client.post(f"/api/assets/{asset['id']}/deprecate")
    assert r.status_code == 200, r.text
    assert r.json()["asset"]["status"] == "deprecated"
    assert {x["id"]: x for x in asset_insights(now=now91)["assets"]}[asset["id"]]["stale"] is False
    assert [x["id"] for x in client.get("/api/assets").json()["assets"]
            if x["id"] == asset["id"]]

    assert client.post(f"/api/assets/{asset['id']}/archive").status_code == 200
    assert not [x["id"] for x in client.get("/api/assets").json()["assets"]
                if x["id"] == asset["id"]]
    assert client.get(f"/api/assets/{asset['id']}").json()["status"] == "archived"
    assert client.post(f"/api/assets/{asset['id']}/archive").status_code == 409

    # --- ② 周期：create → cancel → 选择器退场，工作项不动 ------------------------
    item = client.post(f"/api/projects/{src['id']}/items",
                       json={"concept_id": "task", "title": "周期内存活项"}).json()
    cyc = client.post(f"/api/projects/{src['id']}/cycles",
                      json={"name": "冒烟周期", "start_date": "2026-09-28",
                            "end_date": "2026-10-11"}).json()
    assert client.patch(f"/api/items/{item['id']}",
                        json={"cycle_id": cyc["id"]}).status_code == 200
    assert [c["id"] for c in client.get(f"/api/projects/{src['id']}/cycles").json()["cycles"]]
    assert client.delete(f"/api/cycles/{cyc['id']}").status_code == 200
    assert client.get(f"/api/projects/{src['id']}/cycles").json()["cycles"] == []
    assert client.get(f"/api/items/{item['id']}").json()["title"] == "周期内存活项"

    # --- ③ 保存视图改名：create → PATCH → list 新名 ------------------------------
    view = client.post(f"/api/projects/{src['id']}/views",
                       json={"name": "冒烟试图", "definition": {"priority": "high"},
                             "is_public": False}).json()
    r = client.patch(f"/api/views/{view['id']}", json={"name": "冒烟视图（改名）"})
    assert r.status_code == 200, r.text
    names = [v["name"] for v in client.get(f"/api/projects/{src['id']}/views").json()["views"]]
    assert "冒烟视图（改名）" in names and "冒烟试图" not in names
