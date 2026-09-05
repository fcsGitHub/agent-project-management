"""Smoke 37 (M31): the responsiveness trio end-to-end — approval latency
reconciled against the approvals projection, comment first-response excluding
the author's own replies, the per-kind preference gate round-trip (default on →
off → silent; mention refused off and still delivered), then a rebuild pass
proving prefs persist and numbers replay byte-stable."""
import pytest

from apm import config
from apm.core import events, projections


@pytest.fixture(autouse=True)
def _restore_identity():
    """Smoke 37 switches identity mid-flow; without restoring, the process-global
    settings.user_id leaks into tests that run later in the same session (the
    first smoke case ever to switch identity — timelog/users assert u_admin)."""
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.mark.smoke
def test_smoke_37_m31_responsiveness(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "冒烟响应力", "ontology": "software-dev", "requirement": "s37"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})

    # --- 1) approval latency: granted+rejected pair up, pending doesn't -------
    for i, decision in enumerate(("granted", "rejected", None)):
        aid = f"apr_s37_{i}"
        events.emit(event_type="approval.requested", agg_type="approval", agg_id=aid,
                    project_id=pid, actor_type="system", actor_id="system",
                    payload={"kind": "gate_review", "snapshot": {}})
        if decision:
            events.emit(event_type=f"approval.{decision}", agg_type="approval", agg_id=aid,
                        project_id=pid, actor_type="human", actor_id="u_admin",
                        payload={"kind": "gate_review", "comment": "ok"})
    resp = client.get(f"/api/projects/{pid}/responsiveness").json()
    assert resp["approvals"]["count"] == 2
    assert resp["approvals"]["avg_h"] < 1 and resp["approvals"]["over_48h"] == 0

    # --- 2) comment first response: author self-reply never counts ------------
    bug = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "bug", "title": "响应对象"}).json()
    client.post(f"/api/items/{bug['id']}/comments", json={"body": "求助"})
    client.post(f"/api/items/{bug['id']}/comments", json={"body": "自己顶"})  # self → not a response
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    client.post(f"/api/items/{bug['id']}/comments", json={"body": "来了"})  # the real response
    resp = client.get(f"/api/projects/{pid}/responsiveness").json()
    # qa-wang's reply answers BOTH admin comments (first response = next
    # non-author event after each comment); only qa-wang's own awaits an answer
    assert resp["comments"]["count"] == 2 and resp["comments"]["avg_h"] < 1
    assert resp["comments_unanswered"] == 1

    # --- 3) per-kind prefs roundtrip: off → silent; mention never off ---------
    it1 = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "task", "title": "指派一"}).json()
    client.patch(f"/api/items/{it1['id']}",
                 json={"assignee_type": "human", "assignee_id": "qa-wang"})
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert client.get("/api/notifications").json()["unread"] == 1  # default on

    assert client.put("/api/me/notification-prefs", json={
        "prefs": [{"kind": "assigned", "inapp": False, "email": True}]}).status_code == 200
    assert client.put("/api/me/notification-prefs", json={
        "prefs": [{"kind": "mention", "inapp": False, "email": True}]}).status_code == 422

    client.post("/api/session/identity", json={"user_id": "u_admin"})
    it2 = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "task", "title": "指派二"}).json()
    client.patch(f"/api/items/{it2['id']}",
                 json={"assignee_type": "human", "assignee_id": "qa-wang"})
    client.post(f"/api/items/{bug['id']}/comments", json={"body": "@QA 王 看这个"})
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    kinds = [n["kind"] for n in client.get("/api/notifications").json()["notifications"]]
    assert "mention" in kinds            # mention got through (unfailable)
    assert kinds.count("assigned") == 1  # only the pre-gate assignment; #2 gated

    # --- 4) rebuild: numbers replay byte-stable, prefs persist ----------------
    before = client.get(f"/api/projects/{pid}/responsiveness").json()
    projections.rebuild()
    after = client.get(f"/api/projects/{pid}/responsiveness").json()
    assert after["approvals"] == before["approvals"]
    assert after["comments"] == before["comments"]
    prefs = client.get("/api/me/notification-prefs").json()
    assigned_pref = next(k for k in prefs["kinds"] if k["kind"] == "assigned")
    assert assigned_pref["inapp"] is False  # runtime pref survives rebuild
