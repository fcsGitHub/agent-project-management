"""Smoke 36 (M30): the governance-insight trio end-to-end — the health score
reconciled against hand-computed factors, the replayed history series matching
the live score at the last sample point, and the quote-reply text contract
(plain-text storage roundtrip) — then a rebuild pass. The quote button itself
is browser-side and is exercised in the review replay."""
from datetime import datetime, timedelta, timezone

import pytest

from apm import config
from apm.core import events, projections


@pytest.mark.smoke
def test_smoke_36_m30_governance_insight(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "冒烟治理洞察", "ontology": "software-dev", "requirement": "s36"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    me = config.settings.user_id
    today = datetime.now(timezone.utc).date()
    past = (today - timedelta(days=2)).isoformat()

    # --- 1) health: hand-computed factors ------------------------------------
    # 3 active items (1 overdue), 1 done this week, no gates
    it_overdue = client.post(f"/api/projects/{pid}/items",
                             json={"concept_id": "task", "title": "超期项",
                                   "due_date": past}).json()
    for i in range(2):
        client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": f"正常项{i}"})
    done_it = client.post(f"/api/projects/{pid}/items",
                          json={"concept_id": "task", "title": "完成项"}).json()
    events.emit(event_type="item.status_changed", agg_type="item", agg_id=done_it["id"],
                project_id=pid,
                payload={"from": "ready", "status": "done", "status_group": "done"})

    health = client.get("/api/portfolio/health").json()
    row = next(p for p in health["projects"] if p["project_id"] == pid)
    assert row["factors"]["active"] == 3 and row["factors"]["overdue"] == 1
    assert row["factors"]["done_7d"] == 1 and row["factors"]["gates"] == 0
    assert row["score"] == round(40 * (2 / 3) + 20 * 1.0 + 30 * (1 / 3) + 10, 1)  # 60.0

    # --- 2) history: last sample point == live score --------------------------
    hist = client.get(f"/api/projects/{pid}/health/history?days=30").json()
    assert hist["series"][-1]["score"] == row["score"]
    assert hist["series"][-1]["overdue"] == 1 and hist["series"][-1]["gates"] == 0
    # items only exist today: every earlier sample has no active work → None
    assert all(s["score"] is None for s in hist["series"][:-1])

    # --- 3) quote reply: plain-text storage contract --------------------------
    comment = client.post(f"/api/items/{it_overdue['id']}/comments",
                          json={"body": "第一行\n第二行 @李雷"}).json()
    # the quote text the UI composes and submits — stored and returned verbatim
    quoted = "@李雷 > 第一行\n> 第二行 @李雷\n\n"
    assert client.post(f"/api/items/{it_overdue['id']}/comments",
                       json={"body": quoted}).status_code == 200
    bodies = [c["body"] for c in client.get(f"/api/items/{it_overdue['id']}/comments").json()["comments"]]
    assert quoted in bodies  # stored byte-identical (plain-text contract)

    # --- 4) rebuild: score, history and comments all replay -------------------
    projections.rebuild()
    assert next(p for p in client.get("/api/portfolio/health").json()["projects"]
                if p["project_id"] == pid)["score"] == row["score"]
    assert client.get(f"/api/projects/{pid}/health/history?days=30").json()["series"] \
        == hist["series"]
    bodies2 = [c["body"] for c in client.get(f"/api/items/{it_overdue['id']}/comments").json()["comments"]]
    assert bodies2 == bodies
