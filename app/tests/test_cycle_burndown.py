"""M41-I125 cycle burndown (docs/01 §AN.1, Plane Cycles burndown + Jira
burnup lesson): remaining-per-day from done/cancelled first-arrival replay
plus the burnup total-scope stair line — a mid-cycle mount must RAISE the
total line, which a plain burndown would hide. Same replay caliber as the
milestone burndown (I85); pure replay, rebuild-stable."""
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
                    json={"name": "周期燃尽", "ontology": "software-dev", "requirement": "I125"})
    assert r.status_code == 200
    return r.json()["id"]


def _d(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def test_burndown_math_and_scope_change(client, tmp_data, isolated_ontologies, project):
    c = client.post(f"/api/projects/{project}/cycles",
                    json={"name": "Sprint 1", "start_date": _d(-6), "end_date": _d(6)}).json()
    ids = []
    for i in range(3):
        it = client.post(f"/api/projects/{project}/items",
                         json={"concept_id": "task", "title": f"任务{i}"}).json()
        assert client.patch(f"/api/items/{it['id']}",
                            json={"cycle_id": c["id"]}).status_code == 200
        ids.append(it["id"])
    # one finished inside the window (today = window day 6 of 13)
    assert client.patch(f"/api/items/{ids[0]}", json={"status": "done"}).status_code == 200

    bd = client.get(f"/api/cycles/{c['id']}/burndown").json()
    assert bd["series"], "series must cover start..today"
    last = bd["series"][-1]
    assert last["total"] == 3 and last["remaining"] == 2
    # window start precedes the mounts → scope line stairs up from zero
    assert bd["series"][0]["total"] == 0 and bd["series"][0]["remaining"] == 0

    # scope change: mount a fourth item NOW — the total stair line must rise
    late = client.post(f"/api/projects/{project}/items",
                       json={"concept_id": "task", "title": "中途加塞"}).json()
    assert client.patch(f"/api/items/{late['id']}",
                        json={"cycle_id": c["id"]}).status_code == 200
    bd2 = client.get(f"/api/cycles/{c['id']}/burndown").json()
    # scope line rose 3 → 4 with no removals — a plain burndown would hide this;
    # remaining stays 2+1 new open item = 3
    assert bd2["series"][-1]["total"] == 4 and bd2["series"][-1]["remaining"] == 3
    # ideal anchors at the first in-scope day's total — same-day mounts make
    # that commitment 4 (history cannot split 3→4 inside one day)
    assert bd2["ideal"][0]["remaining"] == 4
    assert bd2["ideal"][-1]["remaining"] == 0

    projections.rebuild()
    bd3 = client.get(f"/api/cycles/{c['id']}/burndown").json()
    bd3.pop("generated_at")
    bd2.pop("generated_at")
    assert bd3 == bd2                            # pure replay


def test_cancelled_cycle_is_404(client, tmp_data, isolated_ontologies, project):
    c = client.post(f"/api/projects/{project}/cycles",
                    json={"name": "短命", "start_date": _d(0), "end_date": _d(3)}).json()
    assert client.delete(f"/api/cycles/{c['id']}").status_code == 200
    assert client.get(f"/api/cycles/{c['id']}/burndown").status_code == 404


def test_unknown_cycle_is_404(client, tmp_data, isolated_ontologies, project):
    assert client.get("/api/cycles/cy_nope/burndown").status_code == 404
