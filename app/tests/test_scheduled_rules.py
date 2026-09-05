"""I98 scheduled rules (docs/01 §AE.1, YouTrack On-schedule semantics):
`schedule:daily` rules are evaluated by the daily sweep — the derived `overdue`
field matches through the existing equality condition system, the
`automation.swept` heartbeat makes the sweep idempotent per day (an event-stream
fact, zero new tables), and create_recurring emits a first-class item.created."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from apm.core import events


@pytest.fixture(autouse=True)
def _restore_identity():
    from apm import config

    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "定时规则", "ontology": "software-dev", "requirement": "I98"})
    assert r.status_code == 200
    return r.json()


def _make_overdue(client, pid: str, title: str) -> dict:
    past = (date.fromisoformat(events.utcnow()[:10]) - timedelta(days=2)).isoformat()
    return client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "bug", "title": title, "due_date": past}).json()


def _titles(client, pid: str) -> list[str]:
    return [i["title"] for i in
            client.get(f"/api/projects/{pid}/items").json()["items"]]


def _priority(client, pid: str, title: str) -> str:
    return next(i["priority"] for i in
                client.get(f"/api/projects/{pid}/items").json()["items"]
                if i["title"] == title)


def test_sweep_upgrades_overdue_and_is_idempotent(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    assert client.post(f"/api/projects/{pid}/automations", json={
        "name": "逾期升级", "trigger_event": "schedule:daily",
        "condition": {"concept_id": "bug", "fields": {"overdue": True}},
        "action": {"type": "set_priority", "value": "high"}}).status_code == 200
    _make_overdue(client, pid, "逾期bug")
    client.post(f"/api/projects/{pid}/items",
                json={"concept_id": "bug", "title": "新鲜bug"})

    out = client.post("/api/automations/sweep", json={})
    assert out.status_code == 200
    body = out.json()
    assert body["swept"] is True and body["fired"] == 1
    assert _priority(client, pid, "逾期bug") == "high"
    assert _priority(client, pid, "新鲜bug") != "high"

    # same-day rerun is a no-op (heartbeat fact in the event stream)
    assert client.post("/api/automations/sweep", json={}).json()["swept"] is False
    # force re-runs and fires again (the item is still overdue)
    forced = client.post("/api/automations/sweep", json={"force": True}).json()
    assert forced["swept"] is True and forced["fired"] == 1


def test_create_recurring_emits_first_class_item(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    assert client.post(f"/api/projects/{pid}/automations", json={
        "name": "每日站会卡", "trigger_event": "schedule:daily",
        "condition": {},
        "action": {"type": "create_recurring", "concept_id": "task",
                   "title": "站会记录"}}).status_code == 200
    assert "站会记录" not in _titles(client, pid)

    out = client.post("/api/automations/sweep", json={}).json()
    assert out["created"] == 1
    made = [t for t in _titles(client, pid) if t == "站会记录"]
    assert len(made) == 1
    # heartbeat: the same-day rerun creates nothing more
    assert client.post("/api/automations/sweep", json={}).json()["swept"] is False
    assert len([t for t in _titles(client, pid) if t == "站会记录"]) == 1


def test_validation_and_zero_event_regression(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    # unknown trigger refused; schedule rules are never in the event TRIGGERS set
    assert client.post(f"/api/projects/{pid}/automations", json={
        "name": "坏触发器", "trigger_event": "schedule:hourly",
        "condition": {}, "action": {"type": "notify", "user_id": "u_admin"}}).status_code == 422
    assert client.post(f"/api/projects/{pid}/automations", json={
        "name": "坏概念", "trigger_event": "schedule:daily",
        "condition": {}, "action": {"type": "create_recurring",
                                    "concept_id": "nope", "title": "x"}}).status_code == 422
    # an event trigger still validates exactly as before (zero regression)
    assert client.post(f"/api/projects/{pid}/automations", json={
        "name": "事件规则", "trigger_event": "item.created",
        "condition": {}, "action": {"type": "set_priority", "value": "high"}}).status_code == 200
