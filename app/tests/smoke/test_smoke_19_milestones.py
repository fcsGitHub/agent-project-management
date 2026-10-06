"""Smoke 19 (M13-I43): milestones + timeline end-to-end — milestone CRUD with
progress, item scheduling dates feeding the upgraded report caliber, NDJSON
event export with a verifiable chain + checksum line, and rebuild stability."""
import json
from datetime import datetime, timedelta, timezone

import pytest


@pytest.mark.smoke
def test_smoke_19_milestones_and_export(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "冒烟里程碑", "ontology": "software-dev", "requirement": "s19"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    past = (datetime.now(timezone.utc) - timedelta(days=2)).date().isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=20)).date().isoformat()

    # milestone + linked scheduled items (create-time linkage)
    ms = client.post(f"/api/projects/{pid}/milestones",
                     json={"title": "Beta 发布", "due_date": past}).json()
    done = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "甲", "milestone_id": ms["id"],
                             "start_date": past, "due_date": past}).json()
    active = client.post(f"/api/projects/{pid}/items",
                         json={"concept_id": "bug", "title": "乙", "milestone_id": ms["id"],
                               "due_date": past}).json()
    assert client.patch(f"/api/items/{done['id']}", json={"status": "done"}).status_code == 200

    # dependency conflict seed: 乙 depends_on 甲 but starts before 甲 ends
    assert client.post(f"/api/items/{active['id']}/relations",
                       json={"to_item": done["id"], "relation_type": "depends_on"}).status_code == 200

    # progress: 2 linked items, 1 done, milestone due passed → 1 overdue item
    detail = client.get(f"/api/milestones/{ms['id']}").json()
    assert detail["progress"] == {"items_total": 2, "items_done": 1,
                                  "done_ratio": 0.5, "overdue_items": 1}

    # report overdue caliber: item.due_date (past) → both active items listed;
    # done item excluded even though its due date passed
    rep = client.get(f"/api/projects/{pid}/report").json()
    assert {o["title"]: o["reason"] for o in rep["overdue"]} == {"乙": "超期 2 天"}

    # NDJSON export: order-preserving lines + checksum line (per-project
    # exports start mid-global-chain, so the first prev link points outside)
    exp = client.get(f"/api/projects/{pid}/events/export")
    assert exp.status_code == 200 and "ndjson" in exp.headers["content-type"]
    lines = [json.loads(l) for l in exp.text.splitlines() if l.strip()]
    body, checksum = lines[:-1], lines[-1]["checksum_line"]
    assert checksum["events"] == len(body) >= 6  # project bootstrap + seeds
    assert checksum["first_prev_event_id"] == body[0]["prev_event_id"]
    assert checksum["gaps"] == 0  # no other project interleaved in this fresh DB
    for prev, cur in zip(body, body[1:]):
        assert cur["prev_event_id"] == prev["id"]
    types = {e["event_type"] for e in body}
    assert {"milestone.created", "item.created", "item.status_changed"} <= types

    # rebuild stability: progress and report unchanged
    # M114-I339: rebuild walks the endpoint so ensure_default_user restores the
    # bootstrap admin (M61-I199 discipline) — the direct projections.rebuild()
    # call silently drops the is_admin runtime flag (M41 appendix C) and the
    # now-gated events/export would 403 before reaching its 404.
    assert client.post("/api/system/rebuild-projections").status_code == 200
    assert client.get(f"/api/milestones/{ms['id']}").json()["progress"] == detail["progress"]
    rep2 = client.get(f"/api/projects/{pid}/report").json()
    assert {o["title"] for o in rep2["overdue"]} == {"乙"}

    # unknown project export → 404
    assert client.get("/api/projects/p_nope/events/export").status_code == 404
