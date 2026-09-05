"""M34-I104 working calendar (docs/01 §AG.1, OpenProject 12.3 semantics):
global non-working days are admin-maintained event projections; auto-scheduled
landing dates (M14 propagation + I83 lag alignment) skip weekends and holidays
while manual items are untouched; the projection survives rebuild."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from apm import config
from apm.core import projections


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "日历演示", "ontology": "software-dev", "requirement": "I104"})
    assert r.status_code == 200
    return r.json()


def _next_saturday() -> date:
    d = date.today() + timedelta(days=1)
    while d.weekday() != 5:
        d += timedelta(days=1)
    return d


def _mkitem(client, pid: str, title: str, **fields):
    r = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": title, **fields})
    assert r.status_code == 200, r.text
    return r.json()


def test_holiday_admin_api_roundtrip(client, tmp_data, isolated_ontologies):
    sat = _next_saturday().isoformat()
    assert client.get("/api/calendar/holidays").json()["holidays"] == []

    r = client.post("/api/calendar/holidays", json={"date": sat, "note": "调试假日"})
    assert r.status_code == 200, r.text
    # duplicate landing is refused (409), bad dates 422, removal 404 on unknown
    assert client.post("/api/calendar/holidays", json={"date": sat}).status_code == 409
    assert client.post("/api/calendar/holidays", json={"date": "not-a-date"}).status_code == 422
    assert client.delete("/api/calendar/holidays/2026-01-01").status_code == 404

    assert client.get("/api/calendar/holidays").json()["holidays"] == [
        {"date": sat, "note": "调试假日", "created_at": client.get(
            "/api/calendar/holidays").json()["holidays"][0]["created_at"]}]

    assert client.delete(f"/api/calendar/holidays/{sat}").status_code == 200
    assert client.get("/api/calendar/holidays").json()["holidays"] == []


def test_propagation_skips_holiday_landing(client, tmp_data, isolated_ontologies, project):
    from apm.domains.calendar import advance_to_workday

    pid = project["id"]
    sat = _next_saturday()          # landing on the weekend is the core pain
    a = _mkitem(client, pid, "前置", due_date=(sat - timedelta(days=3)).isoformat())
    b = _mkitem(client, pid, "后继", start_date=(sat - timedelta(days=1)).isoformat(),
                due_date=(sat + timedelta(days=1)).isoformat())
    assert client.post(f"/api/items/{b['id']}/relations",
                       json={"to_item": a["id"], "relation_type": "depends_on"}).status_code == 200
    assert client.patch(f"/api/items/{b['id']}", json={"auto_scheduled": True}).status_code == 200

    # shift +2: b's raw start lands on Sunday, due on Tuesday
    assert client.patch(f"/api/items/{a['id']}",
                        json={"due_date": (sat - timedelta(days=1)).isoformat()}).status_code == 200
    b2 = client.get(f"/api/items/{b['id']}").json()
    assert b2["start_date"] == (sat + timedelta(days=2)).isoformat()   # Sun → Mon
    assert b2["due_date"] == (sat + timedelta(days=3)).isoformat()     # Tuesday, untouched

    # a holiday right after the weekend pushes the landing further
    assert client.post("/api/calendar/holidays",
                       json={"date": (sat + timedelta(days=2)).isoformat()}).status_code == 200
    assert advance_to_workday(sat + timedelta(days=1)) == sat + timedelta(days=3)  # Sun→Tue

    # a fresh propagation (another +2 shift) skips the holiday too:
    # raw start = Mon+holiday-shifted base +2 → Wednesday, raw due → Friday
    assert client.patch(f"/api/items/{a['id']}",
                        json={"due_date": (sat + timedelta(days=1)).isoformat()}).status_code == 200
    b3 = client.get(f"/api/items/{b['id']}").json()
    assert b3["start_date"] == (sat + timedelta(days=4)).isoformat()   # Wednesday
    assert b3["due_date"] == (sat + timedelta(days=5)).isoformat()     # Friday


def test_manual_items_and_rebuild_untouched(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    sat = _next_saturday()
    a = _mkitem(client, pid, "前置", due_date=(sat - timedelta(days=3)).isoformat())
    b = _mkitem(client, pid, "手动后继", start_date=(sat - timedelta(days=1)).isoformat(),
                due_date=(sat + timedelta(days=1)).isoformat())
    assert client.post(f"/api/items/{b['id']}/relations",
                       json={"to_item": a["id"], "relation_type": "depends_on"}).status_code == 200

    assert client.patch(f"/api/items/{a['id']}",
                        json={"due_date": (sat - timedelta(days=1)).isoformat()}).status_code == 200
    b2 = client.get(f"/api/items/{b['id']}").json()
    assert b2["start_date"] == (sat - timedelta(days=1)).isoformat()   # manual: untouched
    assert b2["due_date"] == (sat + timedelta(days=1)).isoformat()

    # holiday projection survives rebuild (drop_projections + replay)
    holiday = (sat + timedelta(days=2)).isoformat()
    assert client.post("/api/calendar/holidays", json={"date": holiday, "note": "重建存活"}).status_code == 200
    projections.rebuild()
    assert [h["date"] for h in client.get("/api/calendar/holidays").json()["holidays"]] == [holiday]
