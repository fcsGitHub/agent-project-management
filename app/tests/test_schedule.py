"""M29-I89 (docs/01 §AB.1): personal cross-project schedule — every dated item
assigned to the caller (own-data caliber), archived projects excluded."""
from __future__ import annotations

import pytest

from apm import config


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


def test_my_schedule_own_data_and_dates(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "日程甲", "ontology": "software-dev", "requirement": "I89"})
    pid = r.json()["id"]
    r2 = client.post("/api/projects",
                     json={"name": "日程乙", "ontology": "software-dev", "requirement": "I89"})
    pid2 = r2.json()["id"]

    client.post("/api/users", json={"id": "u_s1", "name": "沈工"})

    def item(pid_, title, dates):
        it = client.post(f"/api/projects/{pid_}/items",
                         json={"concept_id": "task", "title": title,
                               "start_date": dates[0], "due_date": dates[1]}).json()
        client.patch(f"/api/items/{it['id']}",
                     json={"assignee_type": "human", "assignee_id": "u_s1"})
        return it

    item(pid, "甲任务", ("2026-10-01", "2026-10-05"))
    item(pid2, "乙任务", ("2026-10-04", "2026-10-04"))
    # undated items never enter the schedule
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "无日期"}).json()
    client.patch(f"/api/items/{it['id']}",
                 json={"assignee_type": "human", "assignee_id": "u_s1"})

    saved = config.settings.user_id
    try:
        client.post("/api/session/identity", json={"user_id": "u_s1"})
        sch = client.get("/api/my/schedule").json()
        titles = {i["title"] for i in sch["items"]}
        assert titles == {"甲任务", "乙任务"}  # own-data: u_admin's undated item excluded by assignee
        projects = {i["project_name"] for i in sch["items"]}
        assert projects == {"日程甲", "日程乙"}

        # reschedule via the same PATCH the calendar uses → reflects + rebuild
        target = next(i for i in sch["items"] if i["title"] == "甲任务")
        assert client.patch(f"/api/items/{target['id']}",
                            json={"start_date": "2026-10-02", "due_date": "2026-10-06"},
                            ).status_code == 200
        from apm.core import projections
        projections.rebuild()
        sch2 = client.get("/api/my/schedule").json()
        target2 = next(i for i in sch2["items"] if i["title"] == "甲任务")
        assert (target2["start_date"], target2["due_date"]) == ("2026-10-02", "2026-10-06")
    finally:
        client.post("/api/session/identity", json={"user_id": saved})


def test_my_schedule_excludes_archived(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "日程归档", "ontology": "software-dev", "requirement": "I89"})
    pid = r.json()["id"]
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "归档任务",
                           "due_date": "2026-11-01"}).json()
    client.patch(f"/api/items/{it['id']}",
                 json={"assignee_type": "human", "assignee_id": config.settings.user_id})
    assert client.post(f"/api/projects/{pid}/archive").status_code == 200

    sch = client.get("/api/my/schedule").json()
    assert "归档任务" not in {i["title"] for i in sch["items"]}
