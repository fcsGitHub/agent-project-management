"""M30-I92 (docs/01 §AC.1): cross-project health score — four weighted factors
(overdue 40 / stale 20 / throughput momentum 30 / gate-pending 10) per
caller-visible project, worst-first, pure projection. The stale factor cannot
be integration-tested end-to-end (backdating requires writing the projection
directly, which a rebuild legitimately reverts — events are the only truth),
so its weight is covered at the formula level."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from apm import config
from apm.core import events, projections
from apm.domains.reports import _health_score


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


def _mk(client, name):
    r = client.post("/api/projects",
                    json={"name": name, "ontology": "software-dev", "requirement": "I92"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _item(client, pid, title, due=None):
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": title}).json()
    if due:
        client.patch(f"/api/items/{it['id']}", json={"due_date": due})
    return it


def test_health_score_formula():
    # all factors healthy, momentum capped at 1 → perfect 100
    assert _health_score({"active": 5, "overdue": 0, "stale": 0,
                          "done_7d": 9, "gates": 0}) == 100.0
    # hand-computed mixed case
    f = {"active": 3, "overdue": 1, "stale": 1, "done_7d": 1, "gates": 0}
    assert _health_score(f) == round(40 * (2 / 3) + 20 * (2 / 3) + 30 * (1 / 3) + 10, 1)
    # gates share the 10-point weight; stale alone costs at most 20
    assert _health_score({"active": 2, "overdue": 2, "stale": 2,
                          "done_7d": 0, "gates": 5}) == 0.0
    # no active work → nothing to be healthy about
    assert _health_score({"active": 0, "overdue": 0, "stale": 0,
                          "done_7d": 0, "gates": 3}) is None


def test_health_score_hand_computed(client, tmp_data, isolated_ontologies):
    pid_a = _mk(client, "健康甲")
    pid_b = _mk(client, "健康乙")
    today = datetime.now(timezone.utc).date()
    past = (today - timedelta(days=3)).isoformat()

    # 甲: 4 items — after the done transition 3 stay active (1 overdue)
    _item(client, pid_a, "甲超期", due=past)
    _item(client, pid_a, "甲一")
    done_it = _item(client, pid_a, "甲完成")
    _item(client, pid_a, "甲二")
    events.emit(event_type="item.status_changed", agg_type="item", agg_id=done_it["id"],
                project_id=pid_a,
                payload={"from": "ready", "status": "done", "status_group": "done"})

    # 乙: 2 active, all healthy, nothing done this week
    _item(client, pid_b, "乙一")
    _item(client, pid_b, "乙二")

    health = client.get("/api/portfolio/health").json()
    by = {p["name"]: p for p in health["projects"]}
    a, b = by["健康甲"], by["健康乙"]

    # done item left the active pool (projection semantics) → 3 active:
    # overdue 1/3 → 40*(2/3), momentum 1/3 → 10, no stale → 20, no gates → 10
    assert a["factors"]["active"] == 3
    assert a["factors"]["overdue"] == 1 and a["factors"]["done_7d"] == 1
    assert a["score"] == round(40 * (2 / 3) + 20 * 1.0 + 30 * (1 / 3) + 10, 1)
    # 乙: all-healthy factors, momentum 0 → 40 + 20 + 0 + 10 = 70
    assert b["score"] == 70.0

    # worst-first ordering: the sicker project leads
    assert health["projects"][0]["name"] == "健康甲"

    projections.rebuild()
    after = client.get("/api/portfolio/health").json()
    assert after["projects"] == health["projects"]  # generated_at excluded (wall clock)


def test_health_none_for_empty_project(client, tmp_data, isolated_ontologies):
    pid = _mk(client, "健康空")
    health = client.get("/api/portfolio/health").json()
    row = next(p for p in health["projects"] if p["project_id"] == pid)
    assert row["score"] is None and row["factors"]["active"] == 0
