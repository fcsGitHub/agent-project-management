"""I106 baseline S-curve (docs/01 §AG.3, EVM semantics): PV accrues baseline
weights (estimate_hours, fallback 1.0 on pre-I106 snapshots) by planned due,
EV by the replayed first-arrival day of done; SPI = EV/PV is honest None when
PV is zero. Pure replay + projection — rebuild leaves every sample identical."""
from __future__ import annotations

import pytest

from apm import config
from apm.core import db, events, projections


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "S曲线演示", "ontology": "software-dev", "requirement": "I106"})
    assert r.status_code == 200
    return r.json()


def _today() -> str:
    return events.utcnow()[:10]


def _mkitem(client, pid: str, title: str, due: str, estimate: float | None = None) -> str:
    fields: dict = {"concept_id": "task", "title": title, "due_date": due}
    if estimate is not None:
        fields["estimate_hours"] = estimate
    item = client.post(f"/api/projects/{pid}/items", json=fields).json()
    return item["id"]


def test_pv_ev_hand_computed_and_spi(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    today = _today()
    a = _mkitem(client, pid, "A 权重4", today, estimate=4)
    _mkitem(client, pid, "B 权重2", today, estimate=2)
    c = _mkitem(client, pid, "C 权重1", today, estimate=1)
    assert client.post(f"/api/projects/{pid}/baseline").status_code == 200

    # A reaches done: EV = 4 of a 7-hour plan
    assert client.patch(f"/api/items/{a}", json={"status": "done"}).status_code == 200

    r = client.get(f"/api/projects/{pid}/baseline-curve")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total"] == 7 and d["pv_total"] == 7 and d["ev_last"] == 4
    assert d["spi"] == 0.571  # 4 / 7, three decimals
    assert d["samples"] and d["samples"][-1]["date"] == today
    assert all(s["pv"] == 7 for s in d["samples"])          # every due ≤ today
    assert d["samples"][-1]["ev"] == 4

    # replay equality: C finishing moves EV to 5 but PV stays put
    assert client.patch(f"/api/items/{c}", json={"status": "done"}).status_code == 200
    d2 = client.get(f"/api/projects/{pid}/baseline-curve").json()
    assert d2["ev_last"] == 5 and d2["spi"] == round(5 / 7, 3)


def test_legacy_snapshot_weight_one_and_honest_none(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    today = _today()
    x = _mkitem(client, pid, "旧格式项", today)

    # hand-emit a pre-I106 two-tuple snapshot (no estimate_hours)
    events.emit(
        event_type="project.baseline_set", agg_type="baseline", agg_id="bl_legacy",
        project_id=pid, payload={"snapshot": {"items": {x: [today, today]},
                                              "milestones": {}}},
    )
    d = client.get(f"/api/projects/{pid}/baseline-curve",
                   params={"baseline_id": "bl_legacy"}).json()
    assert d["total"] == 1 and d["pv_total"] == 1        # weight fell back to 1.0
    assert d["ev_last"] == 0 and d["spi"] == 0

    # a project without any dated items yields PV=0 → honest None SPI
    r2 = client.post("/api/projects",
                     json={"name": "空盘", "ontology": "software-dev", "requirement": "I106b"})
    pid2 = r2.json()["id"]
    assert client.post(f"/api/projects/{pid2}/baseline").status_code == 200
    d2 = client.get(f"/api/projects/{pid2}/baseline-curve").json()
    assert d2["pv_total"] == 0 and d2["spi"] is None

    # unknown baseline id → 404; no baseline at all → 404
    assert client.get(f"/api/projects/{pid}/baseline-curve",
                      params={"baseline_id": "bl_nope"}).status_code == 404
    assert client.get(f"/api/projects/{pid2}/baselines").status_code == 200


def test_curve_survives_rebuild(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    today = _today()
    a = _mkitem(client, pid, "重建一致项", today, estimate=3)
    assert client.post(f"/api/projects/{pid}/baseline").status_code == 200
    assert client.patch(f"/api/items/{a}", json={"status": "done"}).status_code == 200
    before = client.get(f"/api/projects/{pid}/baseline-curve").json()

    projections.rebuild()
    after = client.get(f"/api/projects/{pid}/baseline-curve").json()
    assert after["samples"] == before["samples"]
    assert after["spi"] == before["spi"]


def test_ac_line_and_compare_baseline(client, tmp_data, isolated_ontologies, project):
    """I112: the AC third line replays time.logged (deleted entries never
    count) and ?compare= overlays a second baseline's PV on the same samples."""
    pid = project["id"]
    today = _today()
    a = _mkitem(client, pid, "A 权重4", today, estimate=4)
    b = _mkitem(client, pid, "B 权重2", today, estimate=2)
    assert client.post(f"/api/projects/{pid}/baseline").status_code == 200
    entry = client.post(f"/api/items/{a}/time_entries",
                        json={"minutes": 90, "spent_on": today}).json()
    assert client.post(f"/api/items/{b}/time_entries",
                       json={"minutes": 30, "spent_on": today}).status_code == 200

    d = client.get(f"/api/projects/{pid}/baseline-curve").json()
    assert d["ac_last"] == 2.0          # 90 + 30 minutes = 2h of AC

    # a second baseline (B's estimate drifted) overlays its own PV
    assert client.patch(f"/api/items/{b}", json={"estimate_hours": 6}).status_code == 200
    assert client.post(f"/api/projects/{pid}/baseline").status_code == 200
    rows = client.get(f"/api/projects/{pid}/baselines").json()["baselines"]
    oldest, newest = rows[0]["id"], rows[-1]["id"]
    d2 = client.get(f"/api/projects/{pid}/baseline-curve",
                    params={"compare": oldest}).json()
    assert d2["baseline_id"] == newest
    assert d2["compare"]["baseline_id"] == oldest
    assert d2["compare"]["pv_total"] == 6          # 4 + 2 as of the old snapshot
    assert d2["pv_total"] == 10                    # 4 + 6 as of now
    assert len(d2["compare"]["samples"]) == len(d2["samples"])

    # deleting a log entry removes it from AC (time.deleted never counts)
    client.delete(f"/api/time_entries/{entry['id']}")
    d3 = client.get(f"/api/projects/{pid}/baseline-curve").json()
    assert d3["ac_last"] == 0.5                    # only B's 30 minutes remain
