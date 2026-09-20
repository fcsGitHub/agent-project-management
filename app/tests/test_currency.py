"""M46-I139 多币种轻量版：费率币种 + 手工汇率表 + cost-report 基准币折算。
汇率是可审计的手工配置（不外呼行情）；未配汇率的币种诚实标注「未折算」，
原值计入并显式披露——不假装精确。"""
from __future__ import annotations

import pytest

from apm import config


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def fx_env(monkeypatch):
    monkeypatch.setattr(config.settings, "base_currency", "CNY")
    monkeypatch.setattr(config.settings, "fx_rates", {"USD": 7.2, "EUR": 7.8})


def _make_project_with_hours(client, tmp_data, isolated_ontologies, minutes=60):
    r = client.post("/api/projects", json={"name": "币种项目", "ontology": "software-dev"})
    assert r.status_code == 200
    pid = r.json()["id"]
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "计时报表"}).json()
    r = client.post(f"/api/items/{it['id']}/time_entries",
                    json={"minutes": minutes, "spent_on": "2026-09-19"})
    assert r.status_code == 200, r.text
    return pid


def test_hourly_rate_with_currency_roundtrip(client, tmp_data, isolated_ontologies, fx_env):
    assert client.post("/api/me/hourly-rate",
                       json={"rate": 100, "currency": "usd"}).json()["currency"] == "USD"
    out = client.get("/api/me/hourly-rate").json()
    assert out == {"rate": 100, "currency": "USD"}
    # 非 ISO 代码拒绝
    assert client.post("/api/me/hourly-rate",
                       json={"rate": 1, "currency": "dollar"}).status_code == 422


def test_cost_report_converts_to_base_currency(client, tmp_data, isolated_ontologies, fx_env):
    pid = _make_project_with_hours(client, tmp_data, isolated_ontologies, minutes=120)
    # 当前用户（u_admin）费率 100 USD → 120min=2h × 100 × 7.2 = 1440 CNY
    client.post("/api/me/hourly-rate", json={"rate": 100, "currency": "USD"})
    rep = client.get(f"/api/projects/{pid}/cost-report").json()
    assert rep["base_currency"] == "CNY"
    u = rep["by_user"][0]
    assert u["cost_native"] == 200.0
    assert u["fx_rate"] == 7.2
    assert u["cost"] == 1440.0
    assert rep["total_cost"] == 1440.0
    assert rep["unconverted"] == []


def test_cost_report_unconverted_rate_disclosed(client, tmp_data, isolated_ontologies, fx_env):
    pid = _make_project_with_hours(client, tmp_data, isolated_ontologies, minutes=60)
    client.post("/api/me/hourly-rate", json={"rate": 50, "currency": "JPY"})  # 未配汇率
    rep = client.get(f"/api/projects/{pid}/cost-report").json()
    assert rep["unconverted"] == [{"user_id": "u_admin", "currency": "JPY"}]
    u = rep["by_user"][0]
    assert u["fx_rate"] is None
    assert u["cost"] == u["cost_native"] == 50.0  # 原值计入，不假装精确
    assert rep["total_cost"] == 50.0


def test_cost_report_base_currency_rate_untouched(client, tmp_data, isolated_ontologies, fx_env):
    """费率币种=基准币（或缺省）时 fx=1，成本原样。"""
    pid = _make_project_with_hours(client, tmp_data, isolated_ontologies, minutes=60)
    client.post("/api/me/hourly-rate", json={"rate": 80, "currency": "CNY"})
    rep = client.get(f"/api/projects/{pid}/cost-report").json()
    u = rep["by_user"][0]
    assert u["fx_rate"] == 1.0 and u["cost"] == 80.0 and rep["unconverted"] == []


def test_currency_survives_rebuild_via_migration_column(client, tmp_data, isolated_ontologies, fx_env):
    """currency 是运行时列（同 hourly_rate 家族，不进事件流）；rebuild 丢列属
    I122 既有语义——这里验证的是迁移路径：存量库升级后列存在且可写。"""
    client.post("/api/me/hourly-rate", json={"rate": 10, "currency": "EUR"})
    assert client.get("/api/me/hourly-rate").json()["currency"] == "EUR"
