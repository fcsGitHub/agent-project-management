"""M43-I132 project closure checklist (docs/01 §AP.2, PMBOK Closing Process
Group): closure is a checkable list — five projections (active items, pending
approvals, submitted timesheets, open risks, unfinished milestones) must all
be green before `project.completed` is accepted; completed is a distinct
frozen status (409 on writes, /reopen revives) and rebuild replays it."""
from __future__ import annotations

import pytest

from apm import config
from apm.core import projections


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "收尾演示", "ontology": "software-dev", "requirement": "I132"})
    assert r.status_code == 200
    return r.json()["id"]


def test_checklist_lists_failing_items_and_complete_works(client, pid, tmp_data, isolated_ontologies):
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "没做完"}).json()["id"]

    body = client.get(f"/api/projects/{pid}/closure-checklist").json()
    assert body["all_green"] is False
    failing = [c["key"] for c in body["checks"] if not c["ok"]]
    assert "active_items" in failing
    # completing with failing items → 409 carrying the failing keys
    r = client.post(f"/api/projects/{pid}/complete")
    assert r.status_code == 409

    # clear the item → all green → complete succeeds
    assert client.patch(f"/api/items/{it}", json={"status": "done"}).status_code == 200
    body2 = client.get(f"/api/projects/{pid}/closure-checklist").json()
    assert body2["all_green"] is True
    done = client.post(f"/api/projects/{pid}/complete")
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "completed"

    # completed is frozen — writes 409, /reopen revives
    assert client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "新任务"}).status_code == 409
    assert client.post(f"/api/projects/{pid}/reopen").status_code == 200
    assert client.get(f"/api/projects/{pid}").json()["status"] == "active"


def test_completed_survives_rebuild(client, pid, tmp_data, isolated_ontologies):
    from apm.core import projections as pr
    done = client.post(f"/api/projects/{pid}/complete")
    assert done.status_code == 200, done.text
    assert client.get(f"/api/projects/{pid}").json()["status"] == "completed"

    pr.rebuild()
    assert client.get(f"/api/projects/{pid}").json()["status"] == "completed"
