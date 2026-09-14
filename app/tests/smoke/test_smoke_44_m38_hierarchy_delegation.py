"""Smoke 44 (M38): the hierarchy-and-delegation trio end-to-end — a
three-level parent chain exposes the exact data contract the weighted rollup
consumes (arithmetic itself lives in the vitest suite), a delegated time-off
stretch hands the vacationer's active items to the stand-in on day one and
hands them back on the last day through plain item.assigned events, overload
flags members beyond the configurable threshold, and a rebuild replays the
final state."""
import json
from datetime import date, timedelta

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
def test_smoke_44_m38_hierarchy_delegation(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "冒烟层级代位", "ontology": "software-dev",
                            "requirement": "s44"}).json()["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    client.post("/api/users", json={"id": "li-lei", "name": "李雷"})
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "li-lei", "role": "contributor"}).status_code == 200

    def item(title, parent=None, estimate=None, assignee=None, status=None):
        body = {"concept_id": "task", "title": title}
        if parent:
            body["parent_id"] = parent
        iid = client.post(f"/api/projects/{pid}/items", json=body).json()["id"]
        patch = {}
        if estimate is not None:
            patch["estimate_hours"] = estimate
        if assignee:
            patch.update({"assignee_type": "human", "assignee_id": assignee})
        if patch:
            assert client.patch(f"/api/items/{iid}", json=patch).status_code == 200
        if status:
            assert client.patch(f"/api/items/{iid}", json={"status": status}).status_code == 200
        return iid

    # --- ① three-level chain: the weighted-rollup data contract ----------------
    parent = item("父：会员体系")
    c1 = item("子：登录", parent=parent, estimate=4, status="done")
    c2 = item("子：积分", parent=parent)             # no estimate → weight 1.0
    g1 = item("孙：过期", parent=c2, status="done")  # grandchild rolls through c2
    rows = client.get(f"/api/projects/{pid}/items").json()["items"]
    by_id = {r["id"]: r for r in rows}
    assert by_id[parent]["parent_id"] is None
    assert by_id[c1]["parent_id"] == parent and by_id[c1]["estimate_hours"] == 4
    assert by_id[c1]["status_group"] == "done" and by_id[g1]["status_group"] == "done"

    # --- ② delegated time-off: first-day handoff, last-day handback ------------
    d0 = (date.today() + timedelta(days=0)).isoformat()
    d3 = (date.today() + timedelta(days=3)).isoformat()
    w1 = item("QA 活跃一", assignee="qa-wang")
    w2 = item("QA 活跃二", assignee="qa-wang")
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    off = client.post("/api/me/time-off",
                      json={"start_date": d0, "end_date": d3,
                            "reason": "年假", "delegate": "li-lei"}).json()
    conn = db.get_conn()
    assert automations._delegate_time_off(conn, d0) == 2
    assert [r["assignee_id"] for r in conn.execute(
        "SELECT assignee_id FROM items WHERE id IN (?,?)", (w1, w2))] == ["li-lei"] * 2
    p = json.loads(conn.execute(
        "SELECT payload FROM events WHERE event_type = 'item.assigned' AND agg_id = ?"
        " ORDER BY id DESC LIMIT 1", (w1,)).fetchone()["payload"])
    assert p["original_assignee"] == "qa-wang" and p["delegate_off"] == off["id"]
    assert conn.execute(
        "SELECT COUNT(*) AS c FROM notifications WHERE user_id = 'li-lei'"
        " AND kind = 'assigned'").fetchone()["c"] >= 2
    assert automations._delegate_time_off(conn, d3) == 2          # last day: back
    assert [r["assignee_id"] for r in conn.execute(
        "SELECT assignee_id FROM items WHERE id IN (?,?)", (w1, w2))] == ["qa-wang"] * 2
    assert automations._delegate_time_off(conn, d3) == 0          # idempotent

    # --- ③ overload flag: detection only, threshold from config ----------------
    for i in range(6):
        item(f"超载填充{i}", assignee="qa-wang")
    item("李雷的一件", assignee="li-lei")
    wl = client.get("/api/portfolio/workload").json()
    by_user = {m["user_id"]: m for m in wl["members"]}
    assert wl["overload_threshold"] == 5
    assert by_user["qa-wang"]["overloaded"] is True    # 8 active > 5
    assert by_user["li-lei"]["overloaded"] is False    # 1 active

    # --- rebuild: handback, chain, and flags all replay -------------------------
    projections.rebuild()
    conn = db.get_conn()
    assert [r["assignee_id"] for r in conn.execute(
        "SELECT assignee_id FROM items WHERE id IN (?,?)", (w1, w2))] == ["qa-wang"] * 2
    assert conn.execute(
        "SELECT delegate FROM user_time_off WHERE id = ?",
        (off["id"],)).fetchone()["delegate"] == "li-lei"
    rows = client.get(f"/api/projects/{pid}/items").json()["items"]
    by_id = {r["id"]: r for r in rows}
    assert by_id[c1]["status_group"] == "done" and by_id[c1]["parent_id"] == parent
    wl2 = client.get("/api/portfolio/workload").json()
    by2 = {m["user_id"]: m for m in wl2["members"]}
    assert by2["qa-wang"]["overloaded"] is True
