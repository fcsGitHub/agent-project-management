"""M14-I44 auto-scheduling: opt-in dependency propagation — a moved due date
shifts dependents that flagged auto_scheduled (OpenProject 15.4 pattern,
manual by default), each shift recorded as an explicit item.rescheduled
event; multi-level recursion is cycle-safe and rebuild-stable."""
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
def project(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "排程演示", "ontology": "software-dev", "requirement": "I44"})
    assert r.status_code == 200
    return r.json()


def _day(offset: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=offset)).date().isoformat()


def _mkitem(client, pid: str, title: str, **fields):
    r = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": title, **fields})
    assert r.status_code == 200, r.text
    return r.json()


def _depend_on(client, dep_id: str, on_id: str, lag_days: int | None = None) -> None:
    body = {"to_item": on_id, "relation_type": "depends_on"}
    if lag_days is not None:
        body["lag_days"] = lag_days
    assert client.post(f"/api/items/{dep_id}/relations", json=body).status_code == 200


def test_single_level_propagation(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    a = _mkitem(client, pid, "前置", start_date=_day(0), due_date=_day(5))
    b = _mkitem(client, pid, "后继", start_date=_day(3), due_date=_day(8))
    _depend_on(client, b["id"], a["id"])
    assert client.patch(f"/api/items/{b['id']}", json={"auto_scheduled": True}).status_code == 200

    new_due = _day(10)  # +5 days
    assert client.patch(f"/api/items/{a['id']}", json={"due_date": new_due}).status_code == 200

    b2 = client.get(f"/api/items/{b['id']}").json()
    assert b2["due_date"] == _day(13)          # shifted +5
    assert b2["start_date"] == _day(8)         # duration preserved
    a2 = client.get(f"/api/items/{a['id']}").json()
    assert a2["due_date"] == new_due and a2["start_date"] == _day(0)  # predecessor untouched

    evs = client.get("/api/events", params={"event_type": "item.rescheduled"}).json()["events"]
    assert len(evs) == 1
    assert evs[0]["payload"]["follow_of"] == a["id"] and evs[0]["payload"]["delta_days"] == 5
    assert evs[0]["agg_id"] == b["id"]


def test_manual_mode_not_shifted(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    a = _mkitem(client, pid, "前置", due_date=_day(5))
    b = _mkitem(client, pid, "手动后继", start_date=_day(3), due_date=_day(8))  # auto not set
    _depend_on(client, b["id"], a["id"])

    assert client.patch(f"/api/items/{a['id']}", json={"due_date": _day(10)}).status_code == 200
    b2 = client.get(f"/api/items/{b['id']}").json()
    assert b2["due_date"] == _day(8)  # untouched
    assert client.get("/api/events", params={"event_type": "item.rescheduled"}).json()["events"] == []


def test_multilevel_recursion_cycle_safe(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    a = _mkitem(client, pid, "A", start_date=_day(0), due_date=_day(5))
    b = _mkitem(client, pid, "B", start_date=_day(5), due_date=_day(10))
    c = _mkitem(client, pid, "C", start_date=_day(10), due_date=_day(15))
    for dep, on in ((b, a), (c, b)):
        _depend_on(client, dep["id"], on["id"])
        assert client.patch(f"/api/items/{dep['id']}", json={"auto_scheduled": True}).status_code == 200

    assert client.patch(f"/api/items/{a['id']}", json={"due_date": _day(9)}).status_code == 200  # +4
    assert client.get(f"/api/items/{b['id']}").json()["due_date"] == _day(14)
    assert client.get(f"/api/items/{c['id']}").json()["due_date"] == _day(19)

    # cycle: X↔Y both auto — must terminate, each shifted exactly once
    x = _mkitem(client, pid, "X", start_date=_day(0), due_date=_day(4))
    y = _mkitem(client, pid, "Y", start_date=_day(0), due_date=_day(2))
    _depend_on(client, x["id"], y["id"])
    _depend_on(client, y["id"], x["id"])
    for it in (x, y):
        assert client.patch(f"/api/items/{it['id']}", json={"auto_scheduled": True}).status_code == 200
    assert client.patch(f"/api/items/{x['id']}", json={"due_date": _day(6)}).status_code == 200  # +2
    assert client.get(f"/api/items/{y['id']}").json()["due_date"] == _day(4)   # +2 exactly once
    evs = client.get("/api/events", params={"event_type": "item.rescheduled"}).json()["events"]
    y_shifts = [e for e in evs if e["agg_id"] == y["id"]]
    assert len(y_shifts) == 1


def test_rescheduled_survives_rebuild(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    a = _mkitem(client, pid, "前置", due_date=_day(5))
    b = _mkitem(client, pid, "后继", start_date=_day(6), due_date=_day(9))
    _depend_on(client, b["id"], a["id"])
    client.patch(f"/api/items/{b['id']}", json={"auto_scheduled": True})
    client.patch(f"/api/items/{a['id']}", json={"due_date": _day(7)})
    before = client.get(f"/api/items/{b['id']}").json()

    projections.rebuild()
    after = client.get(f"/api/items/{b['id']}").json()
    assert (after["start_date"], after["due_date"]) == (before["start_date"], before["due_date"])
    assert after["auto_scheduled"] in (1, True)


def test_drag_move_semantics_and_audit(client, tmp_data, isolated_ontologies, project):
    """M20-I63: the timeline's drag-to-reschedule PATCHes start+due through the
    plain item endpoint — a manual move must land both dates and propagate to
    auto-scheduled dependents exactly like a hand-typed API edit."""
    pid = project["id"]
    a = _mkitem(client, pid, "拖动条", start_date=_day(0), due_date=_day(4))
    b = _mkitem(client, pid, "自动后继", start_date=_day(2), due_date=_day(6))
    _depend_on(client, b["id"], a["id"])
    assert client.patch(f"/api/items/{b['id']}", json={"auto_scheduled": True}).status_code == 200

    # drag payload = one PATCH carrying both shifted dates (frontend sends exactly this)
    new_start, new_due = _day(3), _day(7)  # +3 days
    assert client.patch(f"/api/items/{a['id']}",
                        json={"start_date": new_start, "due_date": new_due}).status_code == 200
    a2 = client.get(f"/api/items/{a['id']}").json()
    assert a2["start_date"] == new_start and a2["due_date"] == new_due

    # the auto dependent shifted +3 with duration preserved and explicit audit
    b2 = client.get(f"/api/items/{b['id']}").json()
    assert b2["start_date"] == _day(5) and b2["due_date"] == _day(9)
    evs = client.get("/api/events", params={"event_type": "item.rescheduled"}).json()["events"]
    assert len(evs) == 1 and evs[0]["agg_id"] == b["id"]
    assert evs[0]["payload"]["delta_days"] == 3

    # resize (due only, start untouched) — the right-edge handle payload
    assert client.patch(f"/api/items/{a['id']}", json={"due_date": _day(9)}).status_code == 200
    a3 = client.get(f"/api/items/{a['id']}").json()
    assert a3["start_date"] == new_start and a3["due_date"] == _day(9)


def test_lag_alignment_positive_negative_and_none(client, tmp_data, isolated_ontologies, project):
    """M27-I83: an explicit non-zero lag realigns an auto-scheduled dependent
    at relation time (successor start = predecessor due + 1 + lag; negative =
    lead overlap). None and 0 leave hand-set dates alone. Later shifts
    propagate relatively, preserving the lag gap."""
    pid = project["id"]

    # positive lag: start = pred due + 1 + 2
    pred = _mkitem(client, pid, "前序", start_date=_day(0), due_date=_day(4))
    succ = _mkitem(client, pid, "后继", start_date=_day(1), due_date=_day(5))
    _depend_on(client, succ["id"], pred["id"], lag_days=2)
    assert client.patch(f"/api/items/{succ['id']}", json={"auto_scheduled": True}).status_code == 200
    # relation created BEFORE the auto flag was on → no realignment yet;
    # realignment happens when the relation is created on an already-auto item
    auto = _mkitem(client, pid, "自动后继", start_date=_day(1), due_date=_day(5))
    assert client.patch(f"/api/items/{auto['id']}", json={"auto_scheduled": True}).status_code == 200
    _depend_on(client, auto["id"], pred["id"], lag_days=2)
    a = client.get(f"/api/items/{auto['id']}").json()
    assert a["start_date"] == _day(7) and a["due_date"] == _day(11)  # 4 + 1 + 2, span 4 kept

    # negative lag (lead): start = pred due (same day, overlap)
    lead = _mkitem(client, pid, "提前后继", start_date=_day(2), due_date=_day(5))
    assert client.patch(f"/api/items/{lead['id']}", json={"auto_scheduled": True}).status_code == 200
    _depend_on(client, lead["id"], pred["id"], lag_days=-1)
    l = client.get(f"/api/items/{lead['id']}").json()
    assert l["start_date"] == _day(4) and l["due_date"] == _day(7)  # 4 + 1 - 1

    # lag=None / 0 keep hand-set dates (opt-in semantics)
    keep = _mkitem(client, pid, "手排不动", start_date=_day(1), due_date=_day(2))
    assert client.patch(f"/api/items/{keep['id']}", json={"auto_scheduled": True}).status_code == 200
    _depend_on(client, keep["id"], pred["id"])
    k = client.get(f"/api/items/{keep['id']}").json()
    assert k["start_date"] == _day(1) and k["due_date"] == _day(2)

    # later relative shifts preserve the lag gap: pred +3 → both dependents +3
    assert client.patch(f"/api/items/{pred['id']}", json={"due_date": _day(7)}).status_code == 200
    a2 = client.get(f"/api/items/{auto['id']}").json()
    assert a2["start_date"] == _day(10) and a2["due_date"] == _day(14)  # +3, gap kept
    evs = client.get("/api/events", params={"event_type": "item.rescheduled"}).json()["events"]
    follow_evs = [e for e in evs if e["payload"].get("delta_days") == 3]
    assert {e["agg_id"] for e in follow_evs} >= {auto["id"], lead["id"], succ["id"]} | {auto["id"]}

    # rebuild replays the lag realignment deterministically
    projections.rebuild()
    a3 = client.get(f"/api/items/{auto['id']}").json()
    assert a3["start_date"] == _day(10) and a3["due_date"] == _day(14)
