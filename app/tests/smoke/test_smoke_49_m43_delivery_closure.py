"""Smoke 49 (M43): the delivery-closure trio end-to-end — the risk register
scores and sorts by probability×impact with a full lifecycle, the closure
checklist refuses completion while work is open and hands out the
✅ 已交付 status once green, a completed task with recurrence_days respawns
as a fresh copy through the sweep, and a rebuild replays everything."""
from datetime import datetime, timedelta, timezone

import pytest

from apm import config
from apm.core import db, projections
from apm.domains import automations


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.mark.smoke
def test_smoke_49_m43_delivery_closure(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "冒烟交付闭环", "ontology": "software-dev",
                            "requirement": "s49"}).json()["id"]
    today = datetime.now(timezone.utc)

    # --- ① risk register: p×i scoring and lifecycle ------------------------------
    hi = client.post(f"/api/projects/{pid}/risks",
                     json={"title": "关键供应商延期", "probability": 3, "impact": 3,
                           "response": "提前签备用合同", "owner": "u_admin"}).json()
    lo = client.post(f"/api/projects/{pid}/risks",
                     json={"title": "小偏差", "probability": 1, "impact": 1}).json()
    assert hi["score"] == 9 and lo["score"] == 1
    rows = client.get(f"/api/projects/{pid}/risks").json()["risks"]
    assert [r["title"] for r in rows] == ["关键供应商延期", "小偏差"]  # score desc
    assert client.patch(f"/api/risks/{hi['id']}", json={"status": "mitigated"}).status_code == 200
    assert client.post(f"/api/risks/{hi['id']}/close").status_code == 200
    # open risk now blocks the closure checklist
    cl = client.get(f"/api/projects/{pid}/closure-checklist").json()
    assert cl["all_green"] is False and "open_risks" in [c["key"] for c in cl["checks"] if not c["ok"]]

    # --- ② closure checklist: refuses until green, then freezes -----------------
    assert client.post(f"/api/projects/{pid}/complete").status_code == 409
    # clear everything: risks closed (both), items resolved
    client.post(f"/api/risks/{lo['id']}/close")
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "最后任务"}).json()["id"]
    assert client.patch(f"/api/items/{it}", json={"recurrence_days": 7}).status_code == 200
    done = client.patch(f"/api/items/{it}", json={"status": "done"})
    assert done.status_code == 200
    cl2 = client.get(f"/api/projects/{pid}/closure-checklist").json()
    assert cl2["all_green"] is True
    done = client.post(f"/api/projects/{pid}/complete")
    assert done.status_code == 200
    assert client.get(f"/api/projects/{pid}").json()["status"] == "completed"
    # frozen: new items refused, /reopen revives
    assert client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "x"}).status_code == 409
    assert client.post(f"/api/projects/{pid}/reopen").status_code == 200

    # --- ③ respawn: completion-driven cadence ------------------------------------
    # last 任务 has recurrence_days=7 and is done — backdate its done arrival so
    # the 7-day window is already reached, then sweep
    conn = db.get_conn()
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM events").fetchone()["m"]
    when = today - timedelta(days=7)
    conn.execute(
        "INSERT INTO events (ts, actor_type, actor_id, project_id, agg_type, agg_id,"
        " event_type, payload, prev_event_id) VALUES (?,?,?,?,?,?,?,?,?)",
        (when.isoformat(), "human", "u_admin", pid, "item", it, "item.status_changed",
         '{"status": "done", "status_group": "done"}', row))
    conn.commit()
    assert automations._respawn_recurring(conn, today.date().isoformat()) == 1
    titles = [i["title"] for i in client.get(f"/api/projects/{pid}/items").json()["items"]
              if i["title"] == "最后任务"]
    assert len(titles) == 2                       # original done + fresh open copy
    assert automations._respawn_recurring(conn, today.date().isoformat()) == 0

    # --- rebuild: register, completion, respawn chain replay ---------------------
    projections.rebuild()
    rows = client.get(f"/api/projects/{pid}/risks").json()["risks"]
    assert rows == []                             # both risks closed → register empty
    assert client.get(f"/api/projects/{pid}").json()["status"] == "active"  # reopened
    ev = db.get_conn().execute(
        "SELECT payload FROM events WHERE event_type = 'item.respawned'").fetchone()
    import json
    assert json.loads(ev["payload"])["respawn_of"] == it
