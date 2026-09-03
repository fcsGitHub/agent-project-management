"""Smoke 18 (M12-I40): reports end-to-end — funnel/throughput/gate numbers,
CSV export consistent with the JSON report, and rebuild-stable aggregates."""
import csv
import io

import pytest

from apm.core import events, projections


@pytest.mark.smoke
def test_smoke_18_reports(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "冒烟报表", "ontology": "software-dev", "requirement": "s18"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    # seed: 2 bugs stay in backlog, 1 task → done, 1 bug → fixing(in_progress)
    for title in ("甲", "乙"):
        assert client.post(f"/api/projects/{pid}/items",
                           json={"concept_id": "bug", "title": title}).status_code == 200
    task = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "丙"}).json()
    assert client.patch(f"/api/items/{task['id']}", json={"status": "done"}).status_code == 200
    bug = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "bug", "title": "丁"}).json()
    assert client.patch(f"/api/items/{bug['id']}", json={"status": "fixing"}).status_code == 200
    # one pending gate
    events.emit(event_type="approval.requested", agg_type="approval", agg_id="ap_smoke_18",
                project_id=pid, actor_type="system", payload={"kind": "gate"})

    rep = client.get(f"/api/projects/{pid}/report").json()
    assert rep["funnel"] == {"backlog": 2, "todo": 0, "in_progress": 1, "done": 1, "cancelled": 0}
    assert rep["concepts"] == {"bug": 3, "task": 1}
    assert [g["kind"] for g in rep["gates_pending"]] == ["gate"]
    assert rep["throughput"]["created_total"] >= 4 and rep["throughput"]["done_total"] == 1

    # my/work aggregation (admin default identity → sees the gate, no items)
    mine = client.get("/api/my/work").json()
    assert [a["project_id"] for a in mine["approvals"]] == [pid]

    # CSV consistent with JSON numbers
    csv_resp = client.get(f"/api/projects/{pid}/report.csv")
    assert csv_resp.status_code == 200 and "text/csv" in csv_resp.headers["content-type"]
    rows = list(csv.DictReader(io.StringIO(csv_resp.text)))
    funnel_csv = {r["key"]: int(r["value"]) for r in rows if r["section"] == "funnel"}
    assert funnel_csv == rep["funnel"]
    tp_csv = {r["key"]: int(r["value"]) for r in rows if r["section"] == "throughput"}
    assert tp_csv == {"created_total": rep["throughput"]["created_total"],
                      "done_total": rep["throughput"]["done_total"]}

    # project list health summary
    listing = client.get("/api/projects").json()["projects"]
    me = next(p for p in listing if p["id"] == pid)
    assert me["item_counts"] == rep["funnel"] and me["gates_pending"] == 1

    # pure projection queries → identical numbers after rebuild
    projections.rebuild()
    rep2 = client.get(f"/api/projects/{pid}/report").json()
    assert rep2["funnel"] == rep["funnel"]
    assert rep2["throughput"]["done_total"] == rep["throughput"]["done_total"]
    assert [g["id"] for g in rep2["gates_pending"]] == [g["id"] for g in rep["gates_pending"]]
