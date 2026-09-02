"""Smoke 9 (M5-I19): multi-identity collaboration — register → switch → act →
per-person audit streams, assignee validation + per-assignee board slice."""
import pytest

from apm import config


@pytest.mark.smoke
def test_smoke_09_multi_identity_collaboration(client, tmp_data):
    try:
        # Identity registry bootstrapped with the default user.
        users = client.get("/api/users").json()
        assert users["current"] == "u_admin" and users["current_name"] == "李雷"

        # Register a second identity and switch to it.
        u = client.post("/api/users", json={"id": "qa-li", "name": "qa-li"}).json()
        assert u["id"] == "qa-li"
        r = client.post("/api/session/identity", json={"user_id": "qa-li"}).json()
        assert r["current"] == "qa-li" and r["previous"] == "u_admin"

        # Work performed under the new identity is attributed to it.
        p = client.post(
            "/api/projects",
            json={"name": "协作冒烟", "ontology": "software-dev", "requirement": "双人协作"},
        ).json()
        pid = p["id"]
        r = client.post(f"/api/projects/{pid}/items",
                        json={"concept_id": "bug", "title": "登录失败", "priority": "P1",
                              "assignee_type": "human", "assignee_id": "qa-li"})
        assert r.status_code == 200, r.text

        # Per-person audit stream: qa-li's events are separable from u_admin's.
        qa_events = client.get("/api/events", params={"actor_id": "qa-li"}).json()["events"]
        assert qa_events, "qa-li should have attributable events"
        assert all(e["actor_id"] == "qa-li" for e in qa_events)
        assert any(e["event_type"] == "item.created" for e in qa_events)
        admin_events = client.get("/api/events",
                                  params={"actor_id": "u_admin",
                                          "event_type": "session.identity_switched"}).json()
        # The switch itself is in the audit stream with from/to.
        sw = client.get("/api/events",
                        params={"event_type": "session.identity_switched"}).json()["events"]
        assert sw and sw[0]["payload"]["from"] == "u_admin" and sw[0]["payload"]["to"] == "qa-li"

        # Unregistered human assignee fails closed.
        items = client.get(f"/api/projects/{pid}/items").json()["items"]
        item_id = items[0]["id"]
        assert client.patch(f"/api/items/{item_id}",
                            json={"assignee_type": "human", "assignee_id": "ghost"}
                            ).status_code == 422

        # Assignee name resolution + per-assignee filter (board slice).
        detail = client.get(f"/api/items/{item_id}").json()
        assert detail["assignee_name"] == "qa-li"
        mine = client.get(f"/api/projects/{pid}/items",
                          params={"assignee_id": "qa-li"}).json()["items"]
        assert len(mine) == 1

        # Switch back; identity change is itself auditable.
        r = client.post("/api/session/identity", json={"user_id": "u_admin"}).json()
        assert r["current"] == "u_admin"
    finally:
        config.settings.user_id = "u_admin"  # 进程级全局，绝不泄漏给其他用例
