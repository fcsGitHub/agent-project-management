"""M13-I41 milestones: event-sourced deadline anchors, item schedule dates
(items.start_date/due_date with ISO validation), milestone linkage with
fail-closed validation, progress computation (done ratio + overdue count),
and the upgraded report overdue caliber (item.due_date first)."""
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
                    json={"name": "里程碑演示", "ontology": "software-dev", "requirement": "I41"})
    assert r.status_code == 200
    return r.json()


def test_milestone_crud_and_rebuild(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    m = client.post(f"/api/projects/{pid}/milestones",
                    json={"title": "Beta 发布", "due_date": "2026-09-15",
                          "description": "首个公开版本"}).json()
    assert m["status"] == "planned" and m["due_date"] == "2026-09-15"
    assert m["progress"]["items_total"] == 0 and m["progress"]["done_ratio"] is None

    patched = client.patch(f"/api/milestones/{m['id']}",
                           json={"due_date": "2026-09-20", "status": "in_progress"}).json()
    assert patched["due_date"] == "2026-09-20" and patched["status"] == "in_progress"

    assert client.get(f"/api/milestones/{m['id']}").status_code == 200
    listing = client.get(f"/api/projects/{pid}/milestones").json()["milestones"]
    assert [x["title"] for x in listing] == ["Beta 发布"]

    # event-sourced: survives rebuild
    projections.rebuild()
    again = client.get(f"/api/milestones/{m['id']}").json()
    assert again["due_date"] == "2026-09-20" and again["status"] == "in_progress"


def test_milestone_validation_fail_closed(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    # bad due_date
    assert client.post(f"/api/projects/{pid}/milestones",
                       json={"title": "坏日期", "due_date": "09/15/2026"}).status_code == 422
    assert client.post(f"/api/projects/{pid}/milestones",
                       json={"title": "无日期"}).status_code == 422
    m = client.post(f"/api/projects/{pid}/milestones",
                    json={"title": "正常", "due_date": "2026-09-15"}).json()
    # bad status (ontology milestone concept declares planned/in_progress/achieved)
    assert client.patch(f"/api/milestones/{m['id']}",
                        json={"status": "deployed"}).status_code == 422
    # unknown milestone in item linkage
    item = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "任务"}).json()
    assert client.patch(f"/api/items/{item['id']}",
                        json={"milestone_id": "ms_nope"}).status_code == 422
    # unknown project
    assert client.get("/api/projects/p_nope/milestones").status_code == 200  # empty list is fine
    assert client.post("/api/projects/p_nope/milestones",
                       json={"title": "x", "due_date": "2026-09-15"}).status_code == 404


def test_progress_and_overdue(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    past = (datetime.now(timezone.utc) - timedelta(days=5)).date().isoformat()
    m = client.post(f"/api/projects/{pid}/milestones",
                    json={"title": "已过期里程碑", "due_date": past}).json()
    done_item = client.post(f"/api/projects/{pid}/items",
                            json={"concept_id": "task", "title": "完成项"}).json()
    active_item = client.post(f"/api/projects/{pid}/items",
                              json={"concept_id": "task", "title": "活跃项"}).json()
    client.patch(f"/api/items/{done_item['id']}", json={"status": "done"})
    for it in (done_item, active_item):
        assert client.patch(f"/api/items/{it['id']}",
                            json={"milestone_id": m["id"]}).status_code == 200

    detail = client.get(f"/api/milestones/{m['id']}").json()
    assert detail["progress"]["items_total"] == 2
    assert detail["progress"]["items_done"] == 1
    assert detail["progress"]["done_ratio"] == 0.5
    assert detail["progress"]["overdue_items"] == 1  # active item, due date passed
    assert {i["title"] for i in detail["items"]} == {"完成项", "活跃项"}

    projections.rebuild()
    assert client.get(f"/api/milestones/{m['id']}").json()["progress"] == detail["progress"]


def test_item_dates_and_report_caliber(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    past = (datetime.now(timezone.utc) - timedelta(days=3)).date().isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=10)).date().isoformat()
    fresh = client.post(f"/api/projects/{pid}/items",
                        json={"concept_id": "task", "title": "带日期",
                              "start_date": past, "due_date": past}).json()
    assert fresh["start_date"] == past and fresh["due_date"] == past

    # bad dates rejected on create and patch
    assert client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "坏日期",
                             "due_date": "明天"}).status_code == 422
    assert client.patch(f"/api/items/{fresh['id']}",
                        json={"due_date": "2026-13-01"}).status_code == 422

    # future due → not overdue; report caliber prefers item.due_date over age
    rep = client.get(f"/api/projects/{pid}/report").json()
    assert {r["title"] for r in rep["overdue"]} == {"带日期"}

    # push due_date into the future → drops out of overdue
    assert client.patch(f"/api/items/{fresh['id']}", json={"due_date": future}).status_code == 200
    rep2 = client.get(f"/api/projects/{pid}/report").json()
    assert rep2["overdue"] == []


def test_link_milestone_at_creation(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    m = client.post(f"/api/projects/{pid}/milestones",
                    json={"title": "建卡即关联", "due_date": "2026-09-15"}).json()
    ok = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "直接关联",
                           "milestone_id": m["id"]}).json()
    assert ok["milestone_id"] == m["id"]
    assert client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "坏关联",
                             "milestone_id": "ms_missing"}).status_code == 422
    detail = client.get(f"/api/milestones/{m['id']}").json()
    assert [i["title"] for i in detail["items"]] == ["直接关联"]
