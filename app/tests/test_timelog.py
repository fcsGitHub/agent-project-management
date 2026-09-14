"""M19-I59: work-item time entries — event-sourced spent-time log with CRUD,
fail-closed validation, spent totals on item reads, permission alignment and
the participation hook (logging time makes you a participant)."""
import json

import pytest

from apm import config
from apm.core import projections


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "工时演示", "ontology": "software-dev", "requirement": "c"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _mk_item(client, pid, title, **kw):
    r = client.post(f"/api/projects/{pid}/items", json={"concept_id": "task", "title": title, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def _log(client, item_id, minutes, spent_on="2026-09-04", note=""):
    r = client.post(f"/api/items/{item_id}/time_entries",
                    json={"minutes": minutes, "spent_on": spent_on, "note": note})
    assert r.status_code == 200, r.text
    return r.json()


def test_timelog_crud_rebuild_and_totals(client, pid):
    item = _mk_item(client, pid, "被记时的任务")
    e1 = _log(client, item["id"], 90, note="设计走查")
    e2 = _log(client, item["id"], 30, spent_on="2026-09-05")
    assert e1["user_id"] == "u_admin" and e1["deleted_at"] is None

    listing = client.get(f"/api/items/{item['id']}/time_entries").json()
    assert [x["id"] for x in listing["entries"]] == [e1["id"], e2["id"]]
    assert listing["total_minutes"] == 120

    # soft delete: hidden from list, excluded from totals, event preserved
    assert client.delete(f"/api/time_entries/{e2['id']}").status_code == 200
    listing = client.get(f"/api/items/{item['id']}/time_entries").json()
    assert listing["total_minutes"] == 90

    # edit survives rebuild
    r = client.patch(f"/api/time_entries/{e1['id']}", json={"minutes": 60, "note": "改"})
    assert r.status_code == 200 and r.json()["minutes"] == 60
    projections.rebuild()
    listing = client.get(f"/api/items/{item['id']}/time_entries").json()
    assert listing["total_minutes"] == 60
    assert listing["entries"][0]["note"] == "改"
    # and the deleted entry stays deleted after replay
    assert client.get(f"/api/time_entries/{e2['id']}").status_code == 404

    # spent totals ride on item reads (plan vs actual side by side)
    detail = client.get(f"/api/items/{item['id']}").json()
    assert detail["spent_minutes"] == 60
    listed = client.get(f"/api/projects/{pid}/items").json()["items"]
    assert next(i for i in listed if i["id"] == item["id"])["spent_minutes"] == 60

    # unknown item → 404 on both list and create
    assert client.get("/api/items/i_nope/time_entries").status_code == 404
    assert client.post("/api/items/i_nope/time_entries",
                       json={"minutes": 30, "spent_on": "2026-09-04"}).status_code == 404


def test_timelog_validation_fail_closed(client, pid):
    item = _mk_item(client, pid, "校验目标")
    for minutes in (0, -5, 1441):
        assert client.post(f"/api/items/{item['id']}/time_entries",
                           json={"minutes": minutes, "spent_on": "2026-09-04"}).status_code == 422
    assert client.post(f"/api/items/{item['id']}/time_entries",
                       json={"minutes": 30, "spent_on": "04/09/2026"}).status_code == 422
    # edit path validates too
    e = _log(client, item["id"], 30)
    assert client.patch(f"/api/time_entries/{e['id']}", json={"minutes": 0}).status_code == 422
    assert client.patch(f"/api/time_entries/{e['id']}", json={}).status_code == 422


def test_timelog_participation_and_first_source_wins(client, pid):
    client.post("/api/users", json={"id": "u_dev", "name": "开发"})
    item = _mk_item(client, pid, "参与目标")
    # u_dev logs time → becomes participant with source='time'
    saved = config.settings.user_id
    try:
        client.post("/api/session/identity", json={"user_id": "u_dev"})
        _log(client, item["id"], 45, note="编码")
    finally:
        client.post("/api/session/identity", json={"user_id": saved})
    parts = client.get(f"/api/items/{item['id']}/time_entries").json()["participants"]
    by_user = {p["user_id"]: p["source"] for p in parts}
    assert by_user.get("u_dev") == "time"
    # a later mention does NOT overwrite the existing row (first source wins)
    client.post(f"/api/items/{item['id']}/comments", json={"body": "请 @开发 确认"})
    parts = client.get(f"/api/items/{item['id']}/time_entries").json()["participants"]
    by_user = {p["user_id"]: p["source"] for p in parts}
    assert by_user.get("u_dev") == "time"


def test_timelog_permission_network(client, pid):
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    client.post("/api/users", json={"id": "outsider", "name": "外人", "password": "out-pass"})
    config.settings.auth_mode = "network"
    try:
        assert client.post("/api/auth/login", json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
        item = _mk_item(client, pid, "受门禁保护")
        # author logs time, then outsider is rejected on read and write
        e = _log(client, item["id"], 30)
        assert client.post("/api/auth/login", json={"user_id": "outsider", "password": "out-pass"}).status_code == 200
        assert client.get(f"/api/items/{item['id']}/time_entries").status_code == 403
        assert client.post(f"/api/items/{item['id']}/time_entries",
                           json={"minutes": 10, "spent_on": "2026-09-04"}).status_code == 403
        # non-author (even a member) cannot edit/delete someone else's entry;
        # admin can — switch back to the admin member
        assert client.post("/api/auth/login", json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
        assert client.post(f"/api/items/{item['id']}/time_entries",
                           json={"minutes": 10, "spent_on": "2026-09-04"}).status_code == 200
    finally:
        config.settings.auth_mode = "local"
        config.settings.admin_password = ""


def test_timelog_report_reconciles_with_entries(client, pid):
    """M19-I61: the project report's per-user/per-day aggregation must equal
    the raw entry lists (Plane GH #8045 的反面——项目级聚合与条目对账)."""
    from datetime import datetime, timedelta, timezone

    # dates anchored to the server's UTC today (reports.py _now), all inside
    # the by_day 14-day window and the my/work ISO week — a hardcoded date
    # stops being "this week"/in-window once the calendar moves (M38 审阅修)
    utc_today = datetime.now(timezone.utc).date()
    d_a1, d_a2, d_b1 = ((utc_today - timedelta(days=k)).isoformat() for k in (2, 1, 0))
    item_a = _mk_item(client, pid, "报表甲")
    item_b = _mk_item(client, pid, "报表乙")
    _log(client, item_a["id"], 90, spent_on=d_a1, note="a1")
    _log(client, item_a["id"], 30, spent_on=d_a2, note="a2")
    client.post("/api/users", json={"id": "u_qa2", "name": "测试王"})
    saved = config.settings.user_id
    try:
        client.post("/api/session/identity", json={"user_id": "u_qa2"})
        _log(client, item_b["id"], 60, spent_on=d_b1, note="b1")
    finally:
        client.post("/api/session/identity", json={"user_id": saved})

    entries_total = sum(e["minutes"] for it in (item_a, item_b)
                        for e in client.get(f"/api/items/{it['id']}/time_entries").json()["entries"])
    rep = client.get(f"/api/projects/{pid}/timelog_report").json()
    assert rep["total_minutes"] == entries_total == 180
    assert {u["user_id"]: u["minutes"] for u in rep["by_user"]} == {"u_admin": 120, "u_qa2": 60}
    assert sum(d["minutes"] for d in rep["by_day"]) == 180

    # my/work personal week total (u_qa2 logged exactly one entry this week)
    try:
        client.post("/api/session/identity", json={"user_id": "u_qa2"})
        mw = client.get("/api/my/work").json()
    finally:
        client.post("/api/session/identity", json={"user_id": saved})
    assert mw["week_minutes"] == 60

    # soft-deleted entries drop out of the report
    e = _log(client, item_a["id"], 15, spent_on="2026-09-03", note="临时")
    client.delete(f"/api/time_entries/{e['id']}")
    assert client.get(f"/api/projects/{pid}/timelog_report").json()["total_minutes"] == 180

    # unknown project 404
    assert client.get("/api/projects/p_nope/timelog_report").status_code == 404


def test_my_timelog_calendar_feed(client, pid):
    """M20-I62: personal calendar feed — own entries grouped by day with daily
    totals, soft-deleted entries dropped, window clamped, rebuild-stable."""
    from datetime import date as _date
    a = _mk_item(client, pid, "日历甲")
    b = _mk_item(client, pid, "日历乙")
    today = _date.today().isoformat()
    yesterday = _date.fromordinal(_date.today().toordinal() - 1).isoformat()
    _log(client, a["id"], 90, spent_on=today, note="今天")
    _log(client, b["id"], 30, spent_on=yesterday, note="昨天")

    feed = client.get("/api/my/timelog").json()
    by_day = {d["date"]: d for d in feed["days"]}
    assert by_day[today]["total_minutes"] == 90
    assert by_day[today]["entries"][0]["item_title"] == "日历甲"
    assert by_day[today]["entries"][0]["project_name"] == "工时演示"
    assert by_day[yesterday]["total_minutes"] == 30
    assert feed["total_minutes"] == 120
    assert feed["window"]["days"] == 28

    # only my own entries (other users' logs never show up in my feed)
    client.post("/api/users", json={"id": "u_other", "name": "别人"})
    saved = config.settings.user_id
    try:
        client.post("/api/session/identity", json={"user_id": "u_other"})
        _log(client, a["id"], 45, spent_on=today)
        other = client.get("/api/my/timelog").json()
        assert other["total_minutes"] == 45
        client.post("/api/session/identity", json={"user_id": saved})
        mine = client.get("/api/my/timelog?days=60").json()
        assert mine["total_minutes"] == 120 and mine["window"]["days"] == 60
        assert client.get("/api/my/timelog?days=0").json()["window"]["days"] == 1
        assert client.get("/api/my/timelog?days=999").json()["window"]["days"] == 60
    finally:
        client.post("/api/session/identity", json={"user_id": saved})

    # soft delete drops the entry out of the feed and survives rebuild
    e = _log(client, a["id"], 15, spent_on=yesterday, note="临时")
    assert client.get("/api/my/timelog").json()["total_minutes"] == 135
    client.delete(f"/api/time_entries/{e['id']}")
    projections.rebuild()
    feed = client.get("/api/my/timelog").json()
    assert feed["total_minutes"] == 120
    assert all(x["id"] != e["id"] for d in feed["days"] for x in d["entries"])
