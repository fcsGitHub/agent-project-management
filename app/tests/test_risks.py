"""M43-I131 risk register (docs/01 §AP.1, PMBOK probability×impact matrix +
OpenProject native risk module): risks are first-class register entries with
probability (1-3) × impact (1-3) scoring that sorts the page, a response
plan, owner, review date and an open → mitigated → closed lifecycle. Pure
projection — rebuild reproduces the register."""
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
                    json={"name": "风险演示", "ontology": "software-dev", "requirement": "I131"})
    assert r.status_code == 200
    return r.json()["id"]


def test_scoring_sort_and_validation(client, pid):
    hi = client.post(f"/api/projects/{pid}/risks",
                     json={"title": "供应商延期", "probability": 3, "impact": 3,
                           "response": "提前签备用合同", "owner": "u_admin"}).json()
    lo = client.post(f"/api/projects/{pid}/risks",
                     json={"title": "轻微延期", "probability": 1, "impact": 1}).json()
    assert hi["score"] == 9 and lo["score"] == 1

    # levels outside 1..3 are refused
    for p, i in ((0, 2), (4, 2), (2, 0), (2, 4)):
        assert client.post(f"/api/projects/{pid}/risks",
                           json={"title": "x", "probability": p, "impact": i}).status_code == 422

    rows = client.get(f"/api/projects/{pid}/risks").json()["risks"]
    assert [r["title"] for r in rows] == ["供应商延期", "轻微延期"]  # score desc
    assert all(r["status"] == "open" for r in rows)

    projections.rebuild()
    rows = client.get(f"/api/projects/{pid}/risks").json()["risks"]
    assert [r["title"] for r in rows] == ["供应商延期", "轻微延期"]


def test_lifecycle_and_related_item(client, tmp_data, isolated_ontologies, pid):
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "关联任务"}).json()["id"]
    rk = client.post(f"/api/projects/{pid}/risks",
                     json={"title": "接口变更", "probability": 2, "impact": 3}).json()
    # unknown related item refused
    assert client.patch(f"/api/risks/{rk['id']}",
                        json={"related_item_id": "i_nope"}).status_code == 404
    assert client.patch(f"/api/risks/{rk['id']}",
                        json={"related_item_id": it}).status_code == 200
    # lifecycle: open → mitigated → closed; illegal jumps refused
    assert client.patch(f"/api/risks/{rk['id']}",
                        json={"status": "closed"}).status_code == 422
    assert client.patch(f"/api/risks/{rk['id']}",
                        json={"status": "mitigated"}).status_code == 200
    assert client.patch(f"/api/risks/{rk['id']}",
                        json={"status": "closed"}).status_code == 200
    # closed is terminal
    assert client.patch(f"/api/risks/{rk['id']}",
                        json={"title": "x"}).status_code == 409
    assert client.post(f"/api/risks/{rk['id']}/close").status_code == 200  # idempotent close event
    rows = client.get(f"/api/projects/{pid}/risks").json()["risks"]
    assert rows == []  # closed risks leave the register page

    projections.rebuild()
    rows = client.get(f"/api/projects/{pid}/risks").json()["risks"]
    assert rows == []  # and the replay agrees
