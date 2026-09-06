"""M23-I71: Gantt baselines — one active snapshot per project capturing item
and milestone dates; later edits never touch it; re-setting replaces it;
clearing removes it; everything replays identically."""
import pytest

from apm.core import projections


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "基线演示", "ontology": "software-dev", "requirement": "I71"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _mk_item(client, pid, title, **kw):
    r = client.post(f"/api/projects/{pid}/items", json={"concept_id": "task", "title": title, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_baseline_snapshot_drift_and_rebuild(client, pid):
    a = _mk_item(client, pid, "任务甲", start_date="2026-09-01", due_date="2026-09-05")
    b = _mk_item(client, pid, "任务乙", due_date="2026-09-10")
    undated = _mk_item(client, pid, "无日期项")
    assert client.post(f"/api/projects/{pid}/milestones",
                       json={"title": "发布", "due_date": "2026-09-20"}).status_code == 200

    # set baseline: dated items + milestone — the undated item is excluded
    r = client.post(f"/api/projects/{pid}/baseline")
    assert r.status_code == 200, r.text
    snap = r.json()["baseline"]
    assert set(snap["items"]) == {a["id"], b["id"]}
    assert undated["id"] not in snap["items"]
    assert list(snap["milestones"].values()) == ["2026-09-20"]

    # later edits never touch the snapshot
    assert client.patch(f"/api/items/{a['id']}",
                        json={"due_date": "2026-09-08"}).status_code == 200
    snap2 = client.get(f"/api/projects/{pid}/baseline").json()["baseline"]
    assert snap2["items"][a["id"]] == ["2026-09-01", "2026-09-05", None]

    # re-setting replaces the snapshot with current dates
    assert client.post(f"/api/projects/{pid}/baseline").status_code == 200
    snap3 = client.get(f"/api/projects/{pid}/baseline").json()["baseline"]
    assert snap3["items"][a["id"]] == ["2026-09-01", "2026-09-08", None]

    # clear removes it; getting returns None
    assert client.delete(f"/api/projects/{pid}/baseline").status_code == 200
    assert client.get(f"/api/projects/{pid}/baseline").json()["baseline"] is None

    # rebuild replays the whole set→set→clear history to the same end state
    client.post(f"/api/projects/{pid}/baseline")
    projections.rebuild()
    final = client.get(f"/api/projects/{pid}/baseline").json()["baseline"]
    assert final["items"][a["id"]] == ["2026-09-01", "2026-09-08", None]
    assert final["milestones"]

    # unknown project 404
    assert client.post("/api/projects/p_nope/baseline").status_code == 404


def test_baseline_variance_report(client, pid):
    """M25-I77: variance table — current minus baseline in days; unchanged
    items omitted unless include_same; items created after the baseline
    aren't listed."""
    a = _mk_item(client, pid, "偏差项", start_date="2026-09-01", due_date="2026-09-05")
    same = _mk_item(client, pid, "未动项", due_date="2026-09-06")
    assert client.post(f"/api/projects/{pid}/baseline").status_code == 200
    # drift: 偏差项 start +2 / due +3；未动项不动；基线后新增项
    client.patch(f"/api/items/{a['id']}",
                 json={"start_date": "2026-09-03", "due_date": "2026-09-08"})
    fresh = _mk_item(client, pid, "基线后新增", due_date="2026-09-20")

    # default: only drifted items
    r = client.get(f"/api/projects/{pid}/baseline-variance").json()
    assert len(r["variances"]) == 1
    v = r["variances"][0]
    assert v["item_id"] == a["id"] and v["start_deviation"] == 2 and v["due_deviation"] == 3
    assert r["summary"]["count"] == 1 and r["summary"]["max_due_delay"] == 3

    # include_same lists the untouched item with 0 deviations
    r = client.get(f"/api/projects/{pid}/baseline-variance",
                   params={"include_same": "true"}).json()
    assert {v["item_id"] for v in r["variances"]} == {a["id"], same["id"]}
    zero = next(v for v in r["variances"] if v["item_id"] == same["id"])
    assert zero["due_deviation"] == 0

    # item created after the baseline is not compared
    assert all(v["item_id"] != fresh["id"] for v in r["variances"])

    # unknown baseline_id 404
    assert client.get(f"/api/projects/{pid}/baseline-variance",
                      params={"baseline_id": "bl_nope"}).status_code == 404

    # clear baseline → 404 (nothing to compare against)
    client.delete(f"/api/projects/{pid}/baseline")
    assert client.get(f"/api/projects/{pid}/baseline-variance").status_code == 404


def test_multiple_baselines_history(client, pid):
    """M24-I76: setting a baseline appends to history — both snapshots stay
    queryable and the newest is the /baseline read."""
    a = _mk_item(client, pid, "任务甲", start_date="2026-09-01", due_date="2026-09-05")
    assert client.post(f"/api/projects/{pid}/baseline").status_code == 200
    assert client.patch(f"/api/items/{a['id']}", json={"due_date": "2026-09-08"}).status_code == 200
    assert client.post(f"/api/projects/{pid}/baseline").status_code == 200

    lst = client.get(f"/api/projects/{pid}/baselines").json()["baselines"]
    assert len(lst) == 2
    snaps = [b["snapshot"]["items"][a["id"]][1] for b in lst]
    assert snaps == ["2026-09-05", "2026-09-08"]  # ordered old → new
    assert client.get(f"/api/projects/{pid}/baseline").json()["baseline_id"] == lst[-1]["id"]

    # rebuild replays both snapshots in order
    projections.rebuild()
    lst2 = client.get(f"/api/projects/{pid}/baselines").json()["baselines"]
    assert [b["snapshot"]["items"][a["id"]][1] for b in lst2] == ["2026-09-05", "2026-09-08"]

    # clear wipes the whole history
    assert client.delete(f"/api/projects/{pid}/baseline").status_code == 200
    assert client.get(f"/api/projects/{pid}/baselines").json()["baselines"] == []

    # unknown project 404
    assert client.post("/api/projects/p_nope/baseline").status_code == 404
