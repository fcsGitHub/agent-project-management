"""M28-I87 (docs/01 §AA.2): cross-project member workload — active/overdue
item counts and 7-day logged time aggregated per assignee over every
caller-visible project (OpenProject resource-planner slice, pure projection).
Time logged in projects outside the caller's visibility never leaks in."""
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
def ctx(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "负载甲", "ontology": "software-dev", "requirement": "I87"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    r2 = client.post("/api/projects",
                     json={"name": "负载乙", "ontology": "software-dev", "requirement": "I87"})
    assert r2.status_code == 200, r2.text
    pid2 = r2.json()["id"]

    client.post("/api/users", json={"id": "u_w1", "name": "王工"})
    client.post("/api/users", json={"id": "u_w2", "name": "赵工"})

    def item(pid_, title, assignee, due=None):
        r_ = client.post(f"/api/projects/{pid_}/items",
                         json={"concept_id": "task", "title": title})
        assert r_.status_code == 200, r_.text
        iid = r_.json()["id"]
        if assignee:
            assert client.patch(f"/api/items/{iid}",
                                json={"assignee_type": "human", "assignee_id": assignee},
                                ).status_code == 200
        if due:
            assert client.patch(f"/api/items/{iid}", json={"due_date": due}).status_code == 200
        return iid

    today = datetime.now(timezone.utc).date()
    return {"pid": pid, "pid2": pid2, "item": item, "today": today}


def test_workload_aggregates_and_orders(client, ctx):
    pid, pid2, item, today = ctx["pid"], ctx["pid2"], ctx["item"], ctx["today"]
    past = (today - timedelta(days=2)).isoformat()
    future = (today + timedelta(days=10)).isoformat()

    # 王工: 2 active in 甲 (1 overdue) + 1 active in 乙 → 3 active / 1 overdue
    item(pid, "甲过期", "u_w1", due=past)
    item(pid, "甲正常", "u_w1", due=future)
    item(pid2, "乙正常", "u_w1")
    # 赵工: 1 done item only → not active, absent from the workload list
    done = item(pid, "甲已完成", "u_w2")
    assert client.patch(f"/api/items/{done}", json={"status": "done"}).status_code == 200
    # unassigned items never appear
    item(pid, "无主项", None)

    wl = client.get("/api/portfolio/workload").json()
    by_user = {m["user_id"]: m for m in wl["members"]}
    assert set(by_user) == {"u_w1"}  # only assignees with active work
    w1 = by_user["u_w1"]
    assert w1["user_name"] == "王工"
    assert w1["active"] == 3 and w1["overdue"] == 1
    assert w1["projects"] == {"负载甲": 2, "负载乙": 1}

    # 7-day logged time counts toward the member (project-scoped query);
    # logging happens as u_w1 — the workload is per-assignee
    its = client.get(f"/api/projects/{pid}/items?assignee_id=u_w1").json()["items"]
    target = next(i for i in its if i["title"] == "甲正常")
    saved = config.settings.user_id
    try:
        client.post("/api/session/identity", json={"user_id": "u_w1"})
        assert client.post(f"/api/items/{target['id']}/time_entries",
                           json={"minutes": 90, "spent_on": today.isoformat()},
                           ).status_code == 200
    finally:
        client.post("/api/session/identity", json={"user_id": saved})
    wl2 = client.get("/api/portfolio/workload").json()
    assert next(m for m in wl2["members"] if m["user_id"] == "u_w1")["minutes_7d"] == 90

    # pure projection: rebuild reproduces the same numbers
    projections.rebuild()
    wl3 = client.get("/api/portfolio/workload").json()
    assert wl3["members"] == wl2["members"]


def test_workload_rebuild_and_sort(client, ctx):
    pid, pid2, item, today = ctx["pid"], ctx["pid2"], ctx["item"], ctx["today"]
    item(pid, "甲一", "u_w1")
    item(pid, "甲二", "u_w1")
    item(pid2, "乙一", "u_w2")
    wl = client.get("/api/portfolio/workload").json()
    assert [m["user_id"] for m in wl["members"]] == ["u_w1", "u_w2"]  # by active desc

    projections.rebuild()
    wl2 = client.get("/api/portfolio/workload").json()
    assert [m["user_id"] for m in wl2["members"]] == ["u_w1", "u_w2"]


def test_workload_overload_flag(client, ctx):
    """I118 (docs/01 §AK.3): strictly-more-than-threshold active items flag a
    member as overloaded — detection only, threshold comes from config."""
    pid, pid2, item = ctx["pid"], ctx["pid2"], ctx["item"]
    for i in range(6):
        item(pid, f"甲超载{i}", "u_w1")
    for i in range(3):
        item(pid2, f"乙正常{i}", "u_w2")

    wl = client.get("/api/portfolio/workload").json()
    by_user = {m["user_id"]: m for m in wl["members"]}
    assert wl["overload_threshold"] == 5
    assert by_user["u_w1"]["overloaded"] is True   # 6 > 5
    assert by_user["u_w2"]["overloaded"] is False  # 3 ≤ 5

    saved = config.settings.workload_overload_threshold
    try:
        config.settings.workload_overload_threshold = 2
        wl2 = client.get("/api/portfolio/workload").json()
        by2 = {m["user_id"]: m for m in wl2["members"]}
        assert by2["u_w2"]["overloaded"] is True   # 3 > 2
        assert by2["u_w1"]["overloaded"] is True
    finally:
        config.settings.workload_overload_threshold = saved
