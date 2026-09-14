"""M39-I121 completion forecast (docs/01 §AL.3, Jira velocity chart +
jira-agile-velocity): rate = median of weekly done-completions over the
complete ISO weeks inside project history (done first-arrival replayed, I85
caliber); remaining active ÷ rate → projected finish date; per-item due risk.
Fewer than two complete weeks or a zero rate → honest null with a reason.
History is manufactured by appending backdated done events (append-only
INSERT), each followed by the real API PATCH so live state and replay agree."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from apm import config
from apm.core import db, projections


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


def _mk_item(client, pid, title, due=None):
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": title}).json()
    if due:
        assert client.patch(f"/api/items/{it['id']}", json={"due_date": due}).status_code == 200
    return it["id"]


def _backdate_transition(conn, pid, agg_id, when: date, done: bool):
    """Append an item.status_changed dated `when` — manufacturing history the
    way append-only core demands (INSERT only). For completions the real API
    PATCH follows so live state and replay agree (first arrival per item is
    the backdated one, exactly what a past completion is)."""
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM events").fetchone()["m"]
    payload = ('{"status": "done", "status_group": "done"}' if done
               else '{"status": "in_progress", "status_group": "in_progress"}')
    conn.execute(
        "INSERT INTO events (ts, actor_type, actor_id, project_id, agg_type, agg_id,"
        " event_type, payload, prev_event_id) VALUES (?,?,?,?,?,?,?,?,?)",
        (datetime(when.year, when.month, when.day, 12, 0, 0,
                  tzinfo=timezone.utc).isoformat(),
         "human", "u_admin", pid, "item", agg_id, "item.status_changed", payload, row))
    conn.commit()


def _complete(client, conn, pid, item_id, when: date):
    _backdate_transition(conn, pid, item_id, when, done=True)
    assert client.patch(f"/api/items/{item_id}", json={"status": "done"}).status_code == 200


def test_insufficient_history_is_honest_null(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "预测空", "ontology": "software-dev",
                            "requirement": "I121"}).json()["id"]
    _mk_item(client, pid, "唯一任务")
    fc = client.get(f"/api/projects/{pid}/forecast").json()
    assert fc["forecast"] is None
    assert fc["reason"] == "insufficient history"
    assert fc["weeks"] == [] and fc["remaining"] == 1


def test_velocity_median_and_forecast(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "预测项目", "ontology": "software-dev",
                            "requirement": "I121"}).json()["id"]
    conn = db.get_conn()
    today = datetime.now(timezone.utc).date()
    this_monday = today - timedelta(days=today.weekday())
    w1 = this_monday - timedelta(days=7)    # last complete week
    w2 = this_monday - timedelta(days=14)   # the one before it

    # age the project past the start of week two so two complete weeks fall
    # inside its history (a benign non-done transition, no completions)
    _backdate_transition(conn, pid, "i_none", w2 - timedelta(days=3), done=False)

    # 3 completions last week, 1 the week before → median rate 2.0
    done_ids = [_mk_item(client, pid, f"已完成{i}") for i in range(4)]
    for iid in done_ids[:3]:
        _complete(client, conn, pid, iid, w1)
    _complete(client, conn, pid, done_ids[3], w2 + timedelta(days=1))

    # 2 active items, the first with a due date the velocity can't honor
    overdue = _mk_item(client, pid, "来不及的任务", due=(today - timedelta(days=3)).isoformat())
    _mk_item(client, pid, "无期限任务")

    fc = client.get(f"/api/projects/{pid}/forecast").json()
    assert fc["rate_per_week"] == 2.0                      # median(3, 1)
    assert [w["done"] for w in fc["weeks"]] == [3, 1]      # most recent first
    assert fc["remaining"] == 2
    from math import ceil
    assert fc["forecast"] == (today + timedelta(days=ceil(2 / 2 * 7))).isoformat()
    risk = next(r for r in fc["at_risk"] if r["id"] == overdue)
    assert risk["expected_by"] > risk["due_date"]

    # pure replay: identical after rebuild (modulo the generation timestamp)
    projections.rebuild()
    fc2 = client.get(f"/api/projects/{pid}/forecast").json()
    fc2.pop("generated_at")
    fc.pop("generated_at")
    assert fc2 == fc


def test_zero_velocity_is_honest_null(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "预测零速", "ontology": "software-dev",
                            "requirement": "I121"}).json()["id"]
    _mk_item(client, pid, "开着不动")
    # age the project by appending an old non-done transition (it counts
    # toward history depth, adds no completions), then expect the honest
    # zero-rate answer instead of a fabricated date
    conn = db.get_conn()
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM events").fetchone()["m"]
    old = datetime.now(timezone.utc).date() - timedelta(days=21)
    conn.execute(
        "INSERT INTO events (ts, actor_type, actor_id, project_id, agg_type, agg_id,"
        " event_type, payload, prev_event_id) VALUES (?,?,?,?,?,?,?,?,?)",
        (old.isoformat(), "human", "u_admin", pid, "item", "i_none",
         "item.status_changed", '{"status": "in_progress", "status_group": "in_progress"}',
         row))
    conn.commit()
    fc = client.get(f"/api/projects/{pid}/forecast").json()
    assert len(fc["weeks"]) >= 2
    assert fc["rate_per_week"] == 0
    assert fc["forecast"] is None and fc["reason"] == "no completion velocity"
