"""M18-I56: work-item comments — event-sourced threads, @mention → notification,
and the participation projection (author/assignee/mentioned, deduplicated)."""
import json

import pytest

from apm import config
from apm.core import projections


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "评论演示", "ontology": "software-dev", "requirement": "c"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _mk_item(client, pid, title, **kw):
    r = client.post(f"/api/projects/{pid}/items", json={"concept_id": "task", "title": title, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def _comment(client, pid, item_id, body):
    r = client.post(f"/api/items/{item_id}/comments", json={"body": body})
    assert r.status_code == 200, r.text
    return r.json()


def test_comment_crud_and_rebuild(client, pid):
    item = _mk_item(client, pid, "被评论的任务")
    c = _comment(client, pid, item["id"], "第一条评论")
    assert c["author_id"] == "u_admin" and c["deleted_at"] is None

    listing = client.get(f"/api/items/{item['id']}/comments").json()
    assert [x["id"] for x in listing["comments"]] == [c["id"]]

    assert client.delete(f"/api/comments/{c['id']}").status_code == 200
    listing = client.get(f"/api/items/{item['id']}/comments").json()
    assert listing["comments"] == []  # soft-deleted: hidden, event preserved

    # rebuild replays deletion consistently
    c2 = _comment(client, pid, item["id"], "第二条")
    projections.rebuild()
    listing = client.get(f"/api/items/{item['id']}/comments").json()
    assert [x["body"] for x in listing["comments"]] == ["第二条"]
    assert client.get(f"/api/items/{item['id']}/comments").status_code == 200

    # unknown item → 404 on both list and create
    assert client.get("/api/items/i_nope/comments").status_code == 404
    assert client.post("/api/items/i_nope/comments", json={"body": "x"}).status_code == 404


def test_mention_parses_and_notifies(client, pid, monkeypatch):
    client.post("/api/users", json={"id": "u_qa", "name": "QA 王"})
    client.post("/api/users", json={"id": "u_dev", "name": "张三丰"})
    item = _mk_item(client, pid, "提及目标")

    # multi-word names match exactly; unknown @x is ignored
    c = _comment(client, pid, item["id"], "请 @QA 王 和 @张三丰 关注；@路人 不存在")
    assert sorted(json.loads(c["mentions"])) == ["u_dev", "u_qa"]

    # notifications are per-identity: check each mentioned user's own inbox
    saved = config.settings.user_id
    try:
        for uid, name in (("u_qa", "QA 王"), ("u_dev", "张三丰")):
            client.post("/api/session/identity", json={"user_id": uid})
            notes = client.get("/api/notifications").json()["notifications"]
            mention_notes = [n for n in notes if n["kind"] == "mention"]
            assert len(mention_notes) == 1, (uid, notes)
            assert "的评论中提到了你" in mention_notes[0]["summary"]
            assert "提及目标" in mention_notes[0]["summary"]  # 摘要带标题而非裸 id
    finally:
        config.settings.user_id = saved

    # participants: author + mentioned (dedup, no self-dup for author)
    parts = client.get(f"/api/items/{item['id']}/comments").json()["participants"]
    by_user = {p["user_id"]: p["source"] for p in parts}
    assert by_user.get("u_admin") == "author"
    assert by_user.get("u_qa") == "mentioned"
    assert by_user.get("u_dev") == "mentioned"


def test_assignee_becomes_participant(client, pid):
    client.post("/api/users", json={"id": "u_impl", "name": "实现者"})
    item = _mk_item(client, pid, "指派任务")
    r = client.patch(f"/api/items/{item['id']}", json={"assignee_type": "human", "assignee_id": "u_impl"})
    assert r.status_code == 200, r.text
    parts = client.get(f"/api/items/{item['id']}/comments").json()["participants"]
    by_user = {p["user_id"]: p["source"] for p in parts}
    assert by_user.get("u_impl") == "assignee"
    # commenting later keeps a single participant row (INSERT OR IGNORE)
    _comment(client, pid, item["id"], "实现者也开始评论")
    parts = client.get(f"/api/items/{item['id']}/comments").json()["participants"]
    impl_rows = [p for p in parts if p["user_id"] == "u_impl"]
    assert len(impl_rows) == 1 and impl_rows[0]["source"] == "assignee"


def test_comment_permission_network(client, pid, monkeypatch):
    from apm import config
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    client.post("/api/users", json={"id": "outsider", "name": "外人", "password": "out-pass"})
    config.settings.auth_mode = "network"
    try:
        assert client.post("/api/auth/login", json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
        item = _mk_item(client, pid, "受门禁保护")
        # outsider: read and write are both 403
        assert client.post("/api/auth/login", json={"user_id": "outsider", "password": "out-pass"}).status_code == 200
        assert client.get(f"/api/items/{item['id']}/comments").status_code == 403
        assert client.post(f"/api/items/{item['id']}/comments", json={"body": "x"}).status_code == 403
    finally:
        config.settings.auth_mode = "local"
        config.settings.admin_password = ""


def test_subscription_and_participant_notifications(client, pid):
    """M18-I58: manual watch + participants notified on follow-up item events."""
    from apm.core import projections as _prj
    client.post("/api/users", json={"id": "u_watch", "name": "观察者"})
    item = _mk_item(client, pid, "订阅目标")

    def inbox(uid):
        saved = config.settings.user_id
        try:
            client.post("/api/session/identity", json={"user_id": uid})
            notes = client.get("/api/notifications").json()["notifications"]
        finally:
            client.post("/api/session/identity", json={"user_id": saved})
        return notes

    # watcher subscribes (double subscribe is idempotent)
    saved = config.settings.user_id
    try:
        client.post("/api/session/identity", json={"user_id": "u_watch"})
        assert client.post(f"/api/items/{item['id']}/subscription").json()["subscribed"] is True
        client.post(f"/api/items/{item['id']}/subscription")
    finally:
        client.post("/api/session/identity", json={"user_id": saved})

    # status change notifies the watcher-participant, never the actor (u_admin)
    assert client.patch(f"/api/items/{item['id']}", json={"status": "done"}).status_code == 200
    watch_notes = inbox("u_watch")
    status_notes = [n for n in watch_notes if n["kind"] == "item"]
    assert len(status_notes) == 1 and "订阅目标" in status_notes[0]["summary"]
    assert all(n["kind"] != "item" for n in inbox("u_admin"))  # actor excluded

    # a new comment (no mentions) notifies the watcher, not its author
    _comment(client, pid, item["id"], "第二条评论，无提及")
    watch_notes = inbox("u_watch")
    comment_notes = [n for n in watch_notes if n["kind"] == "comment"]
    assert len(comment_notes) == 1 and "第二条评论" in comment_notes[0]["summary"]

    # unsubscribe stops the noise; author/mentioned participation is untouched
    try:
        client.post("/api/session/identity", json={"user_id": "u_watch"})
        assert client.delete(f"/api/items/{item['id']}/subscription").json()["subscribed"] is False
    finally:
        client.post("/api/session/identity", json={"user_id": saved})
    assert client.patch(f"/api/items/{item['id']}", json={"status": "ready"}).status_code == 200
    assert len([n for n in inbox("u_watch") if n["kind"] == "item"]) == 1

    # rebuild consistency: participants and notification rows survive identically
    parts_before = client.get(f"/api/items/{item['id']}/comments").json()["participants"]
    watch_before = [(n["id"], n["read"]) for n in inbox("u_watch")]
    _prj.rebuild()
    assert client.get(f"/api/items/{item['id']}/comments").json()["participants"] == parts_before
    assert [(n["id"], n["read"]) for n in inbox("u_watch")] == watch_before


def test_status_change_attributes_real_actor(client, pid):
    """M18 审阅即修: PATCH 状态变更必须记真实操作者——change_status 的
    actor_id 默认硬编码 "u_admin"，使审计归因与参与者通知的操作者排除失真。"""
    client.post("/api/users", json={"id": "u_mover", "name": "流转者"})
    item = _mk_item(client, pid, "归因目标")
    saved = config.settings.user_id
    try:
        client.post("/api/session/identity", json={"user_id": "u_mover"})
        assert client.patch(f"/api/items/{item['id']}", json={"status": "ready"}).status_code == 200
    finally:
        client.post("/api/session/identity", json={"user_id": saved})
    ev = client.get("/api/events", params={"agg_id": item["id"]}).json()["events"]
    st = [e for e in ev if e["event_type"] == "item.status_changed"]
    assert st and st[-1]["actor_id"] == "u_mover"
