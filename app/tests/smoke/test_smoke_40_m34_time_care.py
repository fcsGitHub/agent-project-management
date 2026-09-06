"""Smoke 40 (M34): the time-care trio end-to-end — a holiday moves an
auto-scheduled landing, the daily sweep reminds the assignee exactly once,
the baseline S-curve reconciles against hand-computed PV/EV/SPI, and a
rebuild replays all three byte-stable."""
from datetime import date, timedelta

import pytest

from apm import config
from apm.core import projections, events


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.mark.smoke
def test_smoke_40_m34_time_care(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "冒烟时间关怀", "ontology": "software-dev", "requirement": "s40"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    # anchor the fixture chain to the coming Monday's grid: every landing the
    # propagation produces is a workday unless a test puts a holiday there
    base = date.today() + timedelta(days=7)
    while base.weekday() != 0:
        base -= timedelta(days=1)
    iso = lambda offset: (base + timedelta(days=offset)).isoformat()  # noqa: E731

    # --- ① working calendar: a holiday pushes the auto landing ---------------
    a = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "前置A",
                          "start_date": iso(0), "due_date": iso(3)}).json()
    b = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "后继B",
                          "start_date": iso(4), "due_date": iso(6)}).json()
    assert client.post(f"/api/items/{b['id']}/relations",
                       json={"to_item": a["id"], "relation_type": "depends_on"}).status_code == 200
    assert client.patch(f"/api/items/{b['id']}", json={"auto_scheduled": True}).status_code == 200

    assert client.post("/api/calendar/holidays",
                       json={"date": iso(7), "note": "冒烟假日"}).status_code == 200
    # +3 shift: raw start = iso(4)+3 = iso(7) — the holiday itself → skip to 8;
    # raw due = iso(6)+3 = iso(9), an ordinary workday
    assert client.patch(f"/api/items/{a['id']}", json={"due_date": iso(6)}).status_code == 200
    b2 = client.get(f"/api/items/{b['id']}").json()
    assert b2["start_date"] == iso(8)
    assert b2["due_date"] == iso(9)

    holidays = client.get("/api/calendar/holidays").json()["holidays"]
    assert [h["date"] for h in holidays] == [iso(7)]
    assert client.delete(f"/api/calendar/holidays/{iso(7)}").status_code == 200

    # --- ② due-soon reminder: once per item per day ---------------------------
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    today = events.utcnow()[:10]
    t = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "临近截止项",
                          "due_date": today}).json()
    assert client.patch(f"/api/items/{t['id']}",
                        json={"assignee_type": "human", "assignee_id": "qa-wang"}).status_code == 200

    sweep = client.post("/api/automations/sweep", json={}).json()
    assert sweep["swept"] is True and sweep["notified"] == 1
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    kinds = [n["kind"] for n in client.get("/api/notifications").json()["notifications"]]
    assert kinds.count("due_soon") == 1
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    # force re-sweep: the event stream keeps it idempotent
    assert client.post("/api/automations/sweep", json={"force": True}).json()["notified"] == 0

    # --- ③ baseline S-curve: hand-computed PV/EV/SPI --------------------------
    # a fresh project keeps the weight pool clean — the schedule chain above
    # carries dated items whose weights would otherwise join the baseline
    r2 = client.post("/api/projects",
                     json={"name": "冒烟S曲线", "ontology": "software-dev", "requirement": "s40b"})
    assert r2.status_code == 200, r2.text
    pid2 = r2.json()["id"]
    w = client.post(f"/api/projects/{pid2}/items",
                    json={"concept_id": "task", "title": "权重项",
                          "due_date": today, "estimate_hours": 4}).json()
    v = client.post(f"/api/projects/{pid2}/items",
                    json={"concept_id": "task", "title": "小权重项",
                          "due_date": today, "estimate_hours": 2}).json()
    assert client.post(f"/api/projects/{pid2}/baseline").status_code == 200
    assert client.patch(f"/api/items/{w['id']}", json={"status": "done"}).status_code == 200

    curve = client.get(f"/api/projects/{pid2}/baseline-curve").json()
    assert curve["total"] == 6 and curve["pv_total"] == 6 and curve["ev_last"] == 4
    assert curve["spi"] == round(4 / 6, 3)     # 0.667

    # --- rebuild: calendar, reminder idempotency and curve replay -------------
    projections.rebuild()
    assert [h["date"] for h in
            client.get("/api/calendar/holidays").json()["holidays"]] == []  # removal replayed
    curve2 = client.get(f"/api/projects/{pid2}/baseline-curve").json()
    assert curve2["samples"] == curve["samples"] and curve2["spi"] == curve["spi"]
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    kinds2 = [n["kind"] for n in client.get("/api/notifications").json()["notifications"]]
    assert kinds2.count("due_soon") == 1  # deterministic id — replayed exactly once
