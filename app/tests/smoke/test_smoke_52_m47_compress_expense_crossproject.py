"""Smoke 52 (M47): depth & collaboration in one pass — context compression
folds early constraints past the budget while storage stays byte-identical,
the expense track lands as first-class rows converting to the base currency
alongside labor in the dual-track cost report, and a cross-project dependency
chain propagates a schedule shift across projects with the graph showing the
external placeholder."""
from __future__ import annotations

import pathlib

import pytest

from apm import config
from apm.core import db
from apm.core.bus import event_bus
from apm.runtime import engine as engine_mod
from apm.runtime import provider as provider_mod
from apm.runtime.provider import Completion


@pytest.fixture(autouse=True)
def _restore_settings():
    saved = (config.settings.user_id, config.settings.context_budget_chars,
             config.settings.base_currency, config.settings.fx_rates)
    yield
    (config.settings.user_id, config.settings.context_budget_chars,
     config.settings.base_currency, config.settings.fx_rates) = saved


@pytest.mark.smoke
def test_smoke_52_m47_compress_expense_crossproject(client, tmp_data, isolated_ontologies):
    # --- ① I141 compression: fold past budget, storage byte-identical ----------
    config.settings.context_budget_chars = 2000
    pid = client.post("/api/projects",
                      json={"name": "冒烟压缩", "ontology": "software-dev"}).json()["id"]
    conv = client.post("/api/conversations",
                       json={"project_id": pid, "kind": "drafting",
                             "title": "压缩冒烟"}).json()
    cid = conv["id"]
    big = "注入约束细节" * 60
    for i in range(25):
        client.post(f"/api/conversations/{cid}/messages", json={"content": f"约束{i}{big}"})
    run = engine_mod.start_run(conversation_id=cid, agent_role="dev-agent")
    rid = run.id if hasattr(run, "id") else run["id"]
    from tests.conftest import wait_for

    wait_for(lambda: (db.get_conn().execute(
        "SELECT status FROM runs WHERE id = ?", (rid,)).fetchone()["status"]
        in ("succeeded", "interrupted")))
    from apm.domains.conversations import get_messages

    assert len([m for m in get_messages(cid) if m["role"] == "user"]) == 25  # 原文不动
    span = db.get_conn().execute(
        "SELECT attributes FROM spans WHERE run_id = ? AND span_kind = 'generation'"
        " ORDER BY id LIMIT 1", (rid,)).fetchone()
    assert span and "context_compressed" in (span["attributes"] or "{}")

    # --- ② I142 expense track: first-class rows, FX conversion, dual report ---
    config.settings.base_currency = "CNY"
    config.settings.fx_rates = {"USD": 7.2}
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "集成任务"}).json()
    client.post("/api/me/hourly-rate", json={"rate": 100, "currency": "CNY"})
    client.post(f"/api/items/{it['id']}/time_entries",
                json={"minutes": 120, "spent_on": "2026-09-21"})  # labor 200 CNY
    exp = client.post(f"/api/projects/{pid}/expenses",
                      json={"description": "冒烟差旅", "qty": 2, "unit_price": 350,
                            "currency": "USD", "spent_on": "2026-09-21",
                            "item_id": it["id"]})
    assert exp.status_code == 200
    rep = client.get(f"/api/projects/{pid}/cost-report").json()
    assert rep["labor_cost"] == 200.0 and rep["expense_cost"] == 5040.0
    assert rep["total_cost"] == 5240.0 and rep["expenses"][0]["fx_rate"] == 7.2
    # 前端报表卡消费双轨字段（源码级检查）
    web = pathlib.Path(__file__).resolve().parents[3] / "web"
    assert "expense_cost" in (web / "src" / "pages" / "ReportsPage.tsx").read_text(encoding="utf-8")

    # --- ③ I143 cross-project dependency: chain + shift + placeholder ---------
    pid2 = client.post("/api/projects",
                       json={"name": "冒烟下游", "ontology": "software-dev"}).json()["id"]
    it2 = client.post(f"/api/projects/{pid2}/items",
                      json={"concept_id": "task", "title": "下游实现"}).json()
    client.patch(f"/api/items/{it2['id']}", json={"auto_scheduled": True})

    from datetime import datetime, timedelta, timezone

    def _day(offset: int) -> str:
        base = (datetime.now(timezone.utc) + timedelta(days=7)).date()
        base += timedelta(days=(7 - base.weekday()) % 7)
        return (base + timedelta(days=offset)).isoformat()

    client.patch(f"/api/items/{it['id']}", json={"auto_scheduled": True,
                                                 "due_date": _day(0)})
    client.patch(f"/api/items/{it2['id']}",
                 json={"start_date": _day(0), "due_date": _day(4)})
    assert client.post(f"/api/items/{it2['id']}/relations",
                       json={"to_item": it["id"], "relation_type": "depends_on"}).status_code == 200
    client.patch(f"/api/items/{it['id']}", json={"due_date": _day(7)})
    moved = client.get(f"/api/items/{it2['id']}").json()
    assert moved["start_date"] == _day(7) and moved["due_date"] == _day(11)
    graph = client.get(f"/api/projects/{pid2}/graph").json()
    ext = next(n for n in graph["nodes"] if n["id"] == it["id"])
    assert ext.get("external") is True and ext["label"] == "集成任务"
    # rebuild 后投影与关系全部复现
    from apm.core import projections

    projections.rebuild()
    assert client.get(f"/api/items/{it2['id']}").json()["due_date"] == _day(11)
    assert client.get(f"/api/projects/{pid}/expenses").json()["expenses"]
    rels = db.get_conn().execute(
        "SELECT COUNT(*) AS n FROM item_relations WHERE from_item = ?",
        (it2["id"],)).fetchone()["n"]
    assert rels == 1
