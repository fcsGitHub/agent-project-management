"""M40-I122 labor cost & budget (docs/01 §AM.1, OpenProject Time and cost):
cost = logged minutes × the member's hourly rate, derived from the time-entry
projection — never a second ledger. Members without a rate contribute hours
but zero cost (stated); the budget is hours and the burn ratio compares spent
hours against it. Pure projection — rebuild reproduces every number."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from apm import config
from apm.core import projections


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def ctx(client, tmp_data, isolated_ontologies):
    saved = config.settings.user_id
    r = client.post("/api/projects",
                    json={"name": "成本演示", "ontology": "software-dev", "requirement": "I122"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    client.post("/api/users", json={"id": "u_w1", "name": "王工"})
    client.post("/api/users", json={"id": "u_w2", "name": "赵工"})
    client.post("/api/users", json={"id": "u_free", "name": "无费率"})

    def log(user, minutes, title):
        it = client.post(f"/api/projects/{pid}/items",
                         json={"concept_id": "task", "title": title}).json()
        client.patch(f"/api/items/{it['id']}",
                     json={"assignee_type": "human", "assignee_id": user})
        client.post("/api/session/identity", json={"user_id": user})
        r_ = client.post(f"/api/items/{it['id']}/time_entries",
                         json={"minutes": minutes,
                               "spent_on": datetime.now(timezone.utc).date().isoformat()})
        client.post("/api/session/identity", json={"user_id": saved})
        assert r_.status_code == 200, r_.text

    return {"pid": pid, "log": log}


def test_hourly_rate_roundtrip(client, ctx):
    client.post("/api/session/identity", json={"user_id": "u_w1"})
    assert client.get("/api/me/hourly-rate").json()["rate"] is None  # unset stated as None
    assert client.post("/api/me/hourly-rate", json={"rate": 100}).status_code == 200
    assert client.get("/api/me/hourly-rate").json()["rate"] == 100
    assert client.post("/api/me/hourly-rate", json={"rate": -1}).status_code == 422
    # own-data: someone else cannot read or write through their session anyway,
    # and the endpoint only ever touches the effective actor


def test_cost_report_math_and_budget(client, ctx):
    pid = ctx["pid"]
    log = ctx["log"]
    # rates: 王工 100, 赵工 60, 无费率 unset → hours count, cost stays 0
    for user, rate in (("u_w1", 100), ("u_w2", 60)):
        client.post("/api/session/identity", json={"user_id": user})
        client.post("/api/me/hourly-rate", json={"rate": rate})
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    assert client.patch(f"/api/projects/{pid}", json={"budget_hours": 10}).status_code == 200

    log("u_w1", 120, "任务甲")   # 2h × 100 = 200
    log("u_w2", 180, "任务乙")   # 3h × 60 = 180
    log("u_free", 60, "任务丙")  # 1h, rate unset → 0 cost

    r = client.get(f"/api/projects/{pid}/cost-report").json()
    by_user = {u["user_id"]: u for u in r["by_user"]}
    # I139 多币种：行新增 currency/cost_native/fx_rate（缺省币种=基准币 fx=1）
    assert by_user["u_w1"] == {"user_id": "u_w1", "user_name": "王工",
                               "hours": 2.0, "rate": 100, "cost": 200.0,
                               "currency": None, "cost_native": 200.0, "fx_rate": 1.0}
    assert by_user["u_w2"]["cost"] == 180.0
    assert by_user["u_free"]["hours"] == 1.0 and by_user["u_free"]["cost"] == 0
    assert r["spent_hours"] == 6.0 and r["total_cost"] == 380.0
    assert r["budget_hours"] == 10 and r["burn_ratio"] == 0.6
    assert r["over_budget"] is False
    assert r["base_currency"] == "CNY" and r["unconverted"] == []

    # pushing past the budget flips the flag (budget 5h < 6h spent)
    assert client.patch(f"/api/projects/{pid}", json={"budget_hours": 5}).status_code == 200
    r2 = client.get(f"/api/projects/{pid}/cost-report").json()
    assert r2["burn_ratio"] == 1.2 and r2["over_budget"] is True

    # hours survive rebuild (projection); rates are runtime state (M11 family)
    # and reset — so post-rebuild cost is honestly 0 with rate=None stated
    projections.rebuild()
    r3 = client.get(f"/api/projects/{pid}/cost-report").json()
    r3.pop("generated_at")
    r2.pop("generated_at")
    assert r3["spent_hours"] == r2["spent_hours"]
    assert r3["budget_hours"] == r2["budget_hours"] and r3["burn_ratio"] == r2["burn_ratio"]
    assert all(u["rate"] is None and u["cost"] == 0 for u in r3["by_user"])


def test_no_budget_ratio_is_none(client, ctx):
    pid = ctx["pid"]
    ctx["log"]("u_w1", 30, "无预算")
    r = client.get(f"/api/projects/{pid}/cost-report").json()
    assert r["budget_hours"] is None and r["burn_ratio"] is None
    assert r["over_budget"] is False and r["spent_hours"] == 0.5
