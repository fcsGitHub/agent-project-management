"""Smoke 24 (M18-I58): comments & participation end-to-end — CRUD with soft
delete, @mention → targeted notification, the participation projection
(author/mentioned/assignee/watch), participant notifications on follow-up item
events, and rebuild consistency of all three projections."""
import json

import pytest

from apm.core import projections


@pytest.mark.smoke
def test_smoke_24_comments_subscription(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "冒烟评论", "ontology": "software-dev", "requirement": "s24"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    assert client.post("/api/users", json={"id": "u_qa", "name": "QA 王"}).status_code == 200
    assert client.post("/api/users", json={"id": "u_watch", "name": "观察者"}).status_code == 200

    r = client.post(f"/api/projects/{pid}/items", json={"concept_id": "task", "title": "评论冒烟目标"})
    assert r.status_code == 200, r.text
    item_id = r.json()["id"]

    def switch(uid):
        r = client.post("/api/session/identity", json={"user_id": uid})
        assert r.status_code == 200, r.text

    def inbox(uid):
        saved = client.get("/api/users").json()["current"]
        try:
            switch(uid)
            return client.get("/api/notifications").json()
        finally:
            switch(saved)

    # CRUD: create with a multi-word @mention; soft delete hides but keeps history
    r = client.post(f"/api/items/{item_id}/comments", json={"body": "请 @QA 王 复核边界"})
    assert r.status_code == 200, r.text
    c1 = r.json()
    assert c1["author_id"] == "u_admin" and json.loads(c1["mentions"]) == ["u_qa"]
    assert client.delete(f"/api/comments/{c1['id']}").status_code == 200
    assert client.get(f"/api/items/{item_id}/comments").json()["comments"] == []
    r = client.post(f"/api/items/{item_id}/comments", json={"body": "重发：请 @QA 王 复核边界"})
    c2 = r.json()

    # mention → the mentioned user's own inbox (kind=mention, item deep-link);
    # the soft-deleted first comment already sent its notification (no retraction)
    notes = inbox("u_qa")["notifications"]
    mention = [n for n in notes if n["kind"] == "mention"]
    assert len(mention) == 2 and all("评论冒烟目标" in n["summary"] for n in mention)
    assert mention[0]["item_id"] == item_id  # ref_event_id → agg_id resolution

    # participation: author + mentioned (+ assignee via item.assigned)
    assert client.patch(f"/api/items/{item_id}",
                        json={"assignee_type": "human", "assignee_id": "u_qa"}).status_code == 200
    # participation: author + mentioned (+ assignee via item.assigned);
    # first join wins — u_qa joined as "mentioned" from the comment, the later
    # assignee join is a no-op (INSERT OR IGNORE, deterministic under rebuild)
    parts = client.get(f"/api/items/{item_id}/comments").json()["participants"]
    by_user = {p["user_id"]: p["source"] for p in parts}
    assert by_user == {"u_admin": "author", "u_qa": "mentioned"}

    # watch: the observer subscribes, then hears about follow-up events
    switch("u_watch")
    assert client.post(f"/api/items/{item_id}/subscription").status_code == 200
    switch("u_admin")
    assert client.patch(f"/api/items/{item_id}", json={"status": "ready"}).status_code == 200
    _ = client.post(f"/api/items/{item_id}/comments", json={"body": "状态已同步，继续"})
    watch = inbox("u_watch")
    kinds = {n["kind"] for n in watch["notifications"]}
    assert "item" in kinds and "comment" in kinds
    assert watch["unread"] >= 2

    # rebuild consistency: comments, participants and notifications all survive
    before_comments = client.get(f"/api/items/{item_id}/comments").json()
    before_watch = [(n["id"], n["read"]) for n in inbox("u_watch")["notifications"]]
    before_qa = [(n["id"], n["read"]) for n in inbox("u_qa")["notifications"]]
    projections.rebuild()
    after = client.get(f"/api/items/{item_id}/comments").json()
    assert [c["id"] for c in after["comments"]] == [c["id"] for c in before_comments["comments"]]
    assert after["participants"] == before_comments["participants"]
    assert [(n["id"], n["read"]) for n in inbox("u_watch")["notifications"]] == before_watch
    assert [(n["id"], n["read"]) for n in inbox("u_qa")["notifications"]] == before_qa
