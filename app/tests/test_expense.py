"""M47-I142 单元成本行项：OpenProject Budget 双轨语义——expense 是一等
记录（事件溯源、软删、rebuild 复现），金额带 ISO 币种并经 I139 汇率表折算
基准币；cost-report 双轨分区（labor 与 expense 并列，预算保持小时口径不混
算），total_cost = 两轨之和。"""
from __future__ import annotations

import pytest

from apm import config


@pytest.fixture(autouse=True)
def _restore_settings():
    saved = (config.settings.user_id, config.settings.base_currency, config.settings.fx_rates)
    yield
    (config.settings.user_id, config.settings.base_currency, config.settings.fx_rates) = saved


@pytest.fixture()
def fx_env(monkeypatch):
    monkeypatch.setattr(config.settings, "base_currency", "CNY")
    monkeypatch.setattr(config.settings, "fx_rates", {"USD": 7.2})


def _mk_project(client) -> str:
    return client.post("/api/projects",
                       json={"name": "行项项目", "ontology": "software-dev"}).json()["id"]


def test_expense_crud_soft_delete_and_rebuild(client, tmp_data, isolated_ontologies, fx_env):
    pid = _mk_project(client)
    r = client.post(f"/api/projects/{pid}/expenses",
                    json={"description": "差旅-高铁", "qty": 2, "unit_price": 350,
                          "currency": "USD", "spent_on": "2026-09-20", "vendor": "国铁"})
    assert r.status_code == 200, r.text
    eid = r.json()["id"]
    assert r.json()["currency"] == "USD"

    lst = client.get(f"/api/projects/{pid}/expenses").json()["expenses"]
    assert len(lst) == 1 and lst[0]["description"] == "差旅-高铁"

    # 软删后列表消失，rebuild 从事件流复现（deleted 也复现）
    assert client.delete(f"/api/projects/{pid}/expenses/{eid}").status_code == 200
    assert client.get(f"/api/projects/{pid}/expenses").json()["expenses"] == []
    from apm.core import projections

    projections.rebuild()
    assert client.get(f"/api/projects/{pid}/expenses").json()["expenses"] == []
    row = client.get("/api/events", params={"agg_type": "expense"}).json()["events"]
    assert {e["event_type"] for e in row} == {"expense.recorded", "expense.deleted"}


def test_expense_validation_matrix(client, tmp_data, isolated_ontologies, fx_env):
    pid = _mk_project(client)
    base = {"description": "x", "qty": 1, "unit_price": 10, "currency": "USD",
            "spent_on": "2026-09-20"}
    assert client.post(f"/api/projects/{pid}/expenses",
                       json={**base, "qty": 0}).status_code == 422
    assert client.post(f"/api/projects/{pid}/expenses",
                       json={**base, "unit_price": -1}).status_code == 422
    assert client.post(f"/api/projects/{pid}/expenses",
                       json={**base, "currency": "dollar"}).status_code == 422
    assert client.post(f"/api/projects/{pid}/expenses",
                       json={**base, "spent_on": "2026/09/20"}).status_code == 422
    assert client.post(f"/api/projects/{pid}/expenses",
                       json={**base, "item_id": "i_missing"}).status_code == 404


def test_cost_report_dual_track_with_fx(client, tmp_data, isolated_ontologies, fx_env):
    pid = _mk_project(client)
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "开发任务"}).json()
    # labor: 2h × 100 CNY = 200
    client.post("/api/me/hourly-rate", json={"rate": 100, "currency": "CNY"})
    client.post(f"/api/items/{it['id']}/time_entries",
                json={"minutes": 120, "spent_on": "2026-09-20"})
    # expense: 2 × 350 USD = 700 USD → ×7.2 = 5040 CNY
    client.post(f"/api/projects/{pid}/expenses",
                json={"description": "设备采购", "qty": 2, "unit_price": 350,
                      "currency": "USD", "spent_on": "2026-09-20",
                      "item_id": it["id"]})
    rep = client.get(f"/api/projects/{pid}/cost-report").json()
    assert rep["labor_cost"] == 200.0
    assert rep["expense_cost"] == 5040.0
    assert rep["total_cost"] == 5240.0
    assert rep["expenses"][0]["fx_rate"] == 7.2
    assert rep["expense_unconverted"] == []
    # 预算仍小时口径（不混算）
    assert "budget_hours" in rep and "expense" not in str(rep["burn_ratio"])


def test_cost_report_expense_unconverted_disclosed(client, tmp_data, isolated_ontologies, fx_env):
    pid = _mk_project(client)
    client.post(f"/api/projects/{pid}/expenses",
                json={"description": "日元采购", "qty": 1, "unit_price": 5000,
                      "currency": "JPY", "spent_on": "2026-09-20"})
    rep = client.get(f"/api/projects/{pid}/cost-report").json()
    assert rep["expense_unconverted"] and rep["expense_unconverted"][0]["currency"] == "JPY"
    assert rep["expenses"][0]["fx_rate"] is None
    assert rep["expenses"][0]["cost"] == 5000.0  # 原值计入
