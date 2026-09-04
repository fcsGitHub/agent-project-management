"""M12-I38 reports: read-only aggregates over existing projections — funnel,
pending gates, overdue/stale items, throughput, project-list health summary,
and the cross-project "my work" view. No new tables/events; numbers must be
identical after a rebuild (asserted, though it holds by construction)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from apm import config
from apm.core import events, projections


@pytest.fixture(autouse=True)
def _restore_identity():
    """/api/session/identity mutates settings.user_id globally; restore it."""
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "报表演示", "ontology": "software-dev", "requirement": "I38"})
    assert r.status_code == 200
    return r.json()


def _age_created_at(item_id: str, days: int) -> None:
    """Shift one item's created_at back (projection tweak to simulate age)."""
    old = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    from apm.core import db
    conn = db.get_conn()
    conn.execute("UPDATE items SET created_at = ? WHERE id = ?", (old, item_id))
    conn.commit()


def test_funnel_throughput_and_gates(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    a = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "bug", "title": "甲"}).json()
    client.post(f"/api/projects/{pid}/items", json={"concept_id": "bug", "title": "乙"})
    done_item = client.post(f"/api/projects/{pid}/items",
                            json={"concept_id": "task", "title": "丙"}).json()
    # task: open(backlog) → done
    assert client.patch(f"/api/items/{done_item['id']}", json={"status": "done"}).status_code == 200
    # a pending gate (real event → approval projection)
    events.emit(event_type="approval.requested", agg_type="approval", agg_id="ap_rep_1",
                project_id=pid, actor_type="system",
                payload={"kind": "gate", "snapshot": {"stage": "prd_review"}})

    rep = client.get(f"/api/projects/{pid}/report").json()
    assert rep["funnel"] == {"backlog": 2, "todo": 0, "in_progress": 0, "done": 1, "cancelled": 0}
    assert rep["funnel"]["backlog"] == 2 and rep["concepts"]["bug"] == 2
    assert [g["kind"] for g in rep["gates_pending"]] == ["gate"]
    tp = rep["throughput"]
    assert tp["created_total"] >= 3 and tp["done_total"] == 1
    assert tp["series"][-1]["done"] == 1 and tp["series"][-1]["created"] >= 3
    assert len(tp["series"]) == tp["days"] == 14

    # pure projection queries → identical after rebuild
    projections.rebuild()
    assert client.get(f"/api/projects/{pid}/report").json()["funnel"] == rep["funnel"]
    assert client.get(f"/api/projects/{pid}/report").json()["throughput"]["done_total"] == 1
    assert a["id"]  # silence unused-var linters


def test_unknown_project_404(client, tmp_data, isolated_ontologies):
    assert client.get("/api/projects/p_nope/report").status_code == 404


def test_overdue_and_stale_caliber(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    fresh = client.post(f"/api/projects/{pid}/items",
                        json={"concept_id": "bug", "title": "新鲜"}).json()
    stale = client.post(f"/api/projects/{pid}/items",
                        json={"concept_id": "bug", "title": "滞留"}).json()
    due_past = client.post(f"/api/projects/{pid}/items",
                           json={"concept_id": "bug", "title": "过期"}).json()
    due_future = client.post(f"/api/projects/{pid}/items",
                             json={"concept_id": "bug", "title": "未到期"}).json()
    _age_created_at(stale["id"], days=20)
    from apm.core import db
    conn = db.get_conn()
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
    conn.execute("UPDATE items SET custom_fields = ? WHERE id = ?",
                 (f'{{"due": "{yesterday}"}}', due_past["id"]))
    conn.execute("UPDATE items SET custom_fields = ? WHERE id = ?",
                 (f'{{"due": "{tomorrow}"}}', due_future["id"]))
    conn.commit()

    rep = client.get(f"/api/projects/{pid}/report").json()
    titles = {r["title"]: r["reason"] for r in rep["overdue"]}
    assert "新鲜" not in titles and "未到期" not in titles
    assert "滞留超 14 天" in titles["滞留"]
    assert titles["过期"].startswith("超期")

    # done items never appear in overdue even when aged
    assert client.patch(f"/api/items/{fresh['id']}", json={"status": "verified"}).status_code == 200
    _age_created_at(fresh["id"], days=30)
    rep2 = client.get(f"/api/projects/{pid}/report").json()
    assert "新鲜" not in {r["title"] for r in rep2["overdue"]}
    assert rep2["funnel"]["done"] == 1


def test_my_work_and_list_health(client, tmp_data, isolated_ontologies):
    p1 = client.post("/api/projects",
                     json={"name": "项目一", "ontology": "software-dev", "requirement": "x"}).json()
    p2 = client.post("/api/projects",
                     json={"name": "项目二", "ontology": "software-dev", "requirement": "y"}).json()
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    for pid, title in ((p1["id"], "甲"), (p2["id"], "乙")):
        it = client.post(f"/api/projects/{pid}/items",
                         json={"concept_id": "bug", "title": title}).json()
        client.patch(f"/api/items/{it['id']}",
                     json={"assignee_type": "human", "assignee_id": "qa-wang"})
    # a pending gate in p1 (decision right: owner/admin only)
    events.emit(event_type="approval.requested", agg_type="approval", agg_id="ap_rep_2",
                project_id=p1["id"], actor_type="system", payload={"kind": "gate"})

    # assignee sees their work across projects (assignment is authorization)
    original = config.settings.user_id
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    mine = client.get("/api/my/work").json()
    assert {it["title"] for it in mine["items"]} == {"甲", "乙"}
    assert {p["name"] for p in mine["projects"]} == {"项目一", "项目二"}
    assert mine["approvals"] == []  # qa-wang holds no decision rights

    # admin sees pending gates, no assigned items
    client.post("/api/session/identity", json={"user_id": original})
    admin = client.get("/api/my/work").json()
    assert admin["items"] == []
    assert [a["project_id"] for a in admin["approvals"]] == [p1["id"]]

    # project list carries health summary
    listing = client.get("/api/projects").json()["projects"]
    by_id = {p["id"]: p for p in listing}
    assert by_id[p1["id"]]["item_counts"]["backlog"] == 1
    assert by_id[p1["id"]]["gates_pending"] == 1
    assert by_id[p2["id"]]["gates_pending"] == 0


def test_portfolio_report_aggregates_visible_projects(client, tmp_data, isolated_ontologies, project):
    """M23-I72: the portfolio card's numbers must equal the per-project
    reports summed over exactly the caller-visible projects."""
    from apm import config

    pid = project["id"]
    p2 = client.post("/api/projects", json={"name": "第二个项目", "ontology": "software-dev", "requirement": "p2"}).json()
    client.post(f"/api/projects/{pid}/items", json={"concept_id": "task", "title": "甲", "priority": "high"})
    client.post(f"/api/projects/{pid}/items", json={"concept_id": "task", "title": "乙", "due_date": "2026-01-01"})  # overdue
    client.post(f"/api/projects/{p2['id']}/items", json={"concept_id": "task", "title": "丙"})
    client.post(f"/api/projects/{pid}/milestones", json={"title": "M", "due_date": "2026-12-01"})
    client.post(f"/api/items/{list(client.get(f'/api/projects/{pid}/items').json()['items'])[0]['id']}/time_entries",
                json={"minutes": 60, "spent_on": "2026-09-05"})

    rep = client.get("/api/portfolio/report").json()
    by_id = {p["project_id"]: p for p in rep["projects"]}
    assert pid in by_id and p2["id"] in by_id
    assert by_id[pid]["overdue"] == 1 and by_id[p2["id"]]["overdue"] == 0
    assert by_id[pid]["timelog_minutes"] == 60 and by_id[p2["id"]]["timelog_minutes"] == 0
    assert rep["totals"]["timelog_minutes"] == 60
    assert rep["totals"]["overdue"] == sum(p["overdue"] for p in rep["projects"])
    assert rep["totals"]["items_active"] == sum(p["items_active"] for p in rep["projects"])

    # outsider (network mode) sees nothing; members see their projects
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    client.post("/api/users", json={"id": "outsider", "name": "外人", "password": "out-pass"})
    config.settings.auth_mode = "network"
    try:
        assert client.post("/api/auth/login", json={"user_id": "outsider", "password": "out-pass"}).status_code == 200
        assert client.get("/api/portfolio/report").json()["projects"] == []
    finally:
        config.settings.auth_mode = "local"
        config.settings.admin_password = ""
