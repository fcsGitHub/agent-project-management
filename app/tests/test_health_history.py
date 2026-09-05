"""M30-I93 (docs/01 §AC.2): health score over time — the I92 composite
recomputed at ~5-day sample points by replaying item/approval events
(burndown-style replay, zero tables, rebuild-stable)."""
from __future__ import annotations

import pytest

from apm import config
from apm.core import events, projections


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


def test_health_history_replays_and_rebuilds(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "趋势项目", "ontology": "software-dev", "requirement": "I93"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    # two active items today → score 70 (healthy, momentum 0)
    for i in range(2):
        assert client.post(f"/api/projects/{pid}/items",
                           json={"concept_id": "task", "title": f"任务{i}"}).status_code == 200

    hist = client.get(f"/api/projects/{pid}/health/history?days=30").json()
    series = hist["series"]
    assert len(series) >= 7                       # 30 days at 5-day steps + today
    assert series[0]["score"] is None             # project did not exist yet
    tail = series[-1]
    assert tail["date"] and tail["active"] == 2 and tail["score"] == 70.0
    assert all(s["score"] is None for s in series[:-1])  # items created only today

    # overdue an item → today's score drops, replayed series reflects it
    items = client.get(f"/api/projects/{pid}/items").json()["items"]
    past = "2026-01-01"
    assert client.patch(f"/api/items/{items[0]['id']}", json={"due_date": past}).status_code == 200
    hist2 = client.get(f"/api/projects/{pid}/health/history?days=30").json()
    assert hist2["series"][-1]["overdue"] == 1
    assert hist2["series"][-1]["score"] == round(40 * 0.5 + 20 * 1.0 + 30 * 0.0 + 10, 1)  # 60.0

    # pure replay: identical after rebuild
    projections.rebuild()
    hist3 = client.get(f"/api/projects/{pid}/health/history?days=30").json()
    assert hist3["series"] == hist2["series"]


def test_health_history_empty_project(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "趋势空", "ontology": "software-dev", "requirement": "I93"})
    pid = r.json()["id"]
    hist = client.get(f"/api/projects/{pid}/health/history?days=14").json()
    assert hist["days"] == 14
    assert all(s["score"] is None and s["active"] == 0 for s in hist["series"])
