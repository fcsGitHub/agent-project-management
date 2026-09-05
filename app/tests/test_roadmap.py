"""M27-I84 (docs/01 §Z.2): cross-project milestone roadmap — milestones of
every caller-visible project on one axis, with done progress and overdue
flags. Pure projection aggregation over the same _visible scope as the
portfolio report; archived projects and milestone-less projects are absent."""
import pytest

from apm.core import projections


@pytest.fixture()
def pids(client, tmp_data, isolated_ontologies):
    out = []
    for name in ("路线图甲", "路线图乙"):
        r = client.post("/api/projects", json={"name": name, "ontology": "software-dev", "requirement": "I84"})
        assert r.status_code == 200, r.text
        out.append(r.json()["id"])
    return out


def _ms(client, pid, title, due, status="planned"):
    r = client.post(f"/api/projects/{pid}/milestones", json={"title": title, "due_date": due})
    assert r.status_code == 200, r.text
    m = r.json()
    if status != "planned":
        r = client.patch(f"/api/milestones/{m['id']}", json={"status": status})
        assert r.status_code == 200, r.text
    return m


def test_roadmap_aggregates_visible_projects(client, pids):
    from datetime import datetime, timedelta, timezone
    future = (datetime.now(timezone.utc) + timedelta(days=14)).date().isoformat()
    past = (datetime.now(timezone.utc) - timedelta(days=3)).date().isoformat()

    m1 = _ms(client, pids[0], "甲里程碑", future)
    _ms(client, pids[1], "乙里程碑", past, status="achieved")

    # link items to the first milestone: 1 of 2 done → 50% (M12 ratio semantics)
    for i, status in enumerate(("done", "in_progress")):
        it = client.post(f"/api/projects/{pids[0]}/items",
                         json={"concept_id": "task", "title": f"关联项{i}", "milestone_id": m1["id"]})
        assert it.status_code == 200, it.text
        assert client.patch(f"/api/items/{it.json()['id']}", json={"status": status}).status_code == 200

    rm = client.get("/api/portfolio/roadmap").json()
    by_name = {p["name"]: p for p in rm["projects"]}
    assert "路线图甲" in by_name and "路线图乙" in by_name
    row = by_name["路线图甲"]["milestones"][0]
    assert row["title"] == "甲里程碑" and row["overdue"] is False
    assert row["progress"]["items_total"] == 2 and row["progress"]["items_done"] == 1
    assert row["progress"]["done_ratio"] == 0.5
    # an achieved milestone is never overdue, even past its due date
    row2 = by_name["路线图乙"]["milestones"][0]
    assert row2["overdue"] is False and row2["status"] == "achieved"

    # ordering inside a project is by due_date
    _ms(client, pids[0], "更早", past)
    rm2 = client.get("/api/portfolio/roadmap").json()
    titles = [m["title"] for p in rm2["projects"] if p["name"] == "路线图甲" for m in p["milestones"]]
    assert titles == ["更早", "甲里程碑"]


def test_roadmap_excludes_archived_and_empty(client, pids):
    _ms(client, pids[0], "将保留", "2027-01-15")
    # an archived project with a milestone must not appear
    r = client.post("/api/projects", json={"name": "归档项目", "ontology": "software-dev", "requirement": "x"})
    aid = r.json()["id"]
    _ms(client, aid, "归档里程碑", "2027-02-15")
    assert client.post(f"/api/projects/{aid}/archive").status_code == 200

    rm = client.get("/api/portfolio/roadmap").json()
    names = [p["name"] for p in rm["projects"]]
    assert "归档项目" not in names
    assert "路线图甲" in names
    # milestone-less projects never produce rows
    assert "路线图乙" not in names


def test_roadmap_survives_rebuild(client, pids):
    _ms(client, pids[0], "重建里程碑", "2027-03-15")
    projections.rebuild()
    rm = client.get("/api/portfolio/roadmap").json()
    titles = [m["title"] for p in rm["projects"] for m in p["milestones"]]
    assert "重建里程碑" in titles
