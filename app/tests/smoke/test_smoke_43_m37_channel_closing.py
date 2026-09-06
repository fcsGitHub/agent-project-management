"""Smoke 43 (M37): the channel-closing trio end-to-end — a `[项目名]` subject
routes into the sender's membership project with the prefix stripped, a reply
in a known thread becomes a comment instead of a new task, the activity Atom
feed authenticates by feed_key and renders valid XML, and a rebuild replays
everything."""
import pytest

from apm import config
from apm.core import db, events, projections
from apm.domains import imap_in


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.mark.smoke
def test_smoke_43_m37_channel_closing(client, tmp_data, isolated_ontologies, monkeypatch):
    pid = client.post("/api/projects",
                      json={"name": "冒烟通道收尾", "ontology": "software-dev",
                            "requirement": "s43"}).json()["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "email": "qa@x.com"})
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200
    monkeypatch.setattr(config.settings, "imap_host", "imap.example.com")
    monkeypatch.setattr(config.settings, "imap_user", "inbox@example.com")
    monkeypatch.setattr(config.settings, "imap_pass", "secret")

    # --- ① subject routing: `[冒烟通道收尾]` lands in the member project ------
    _stub(monkeypatch, {"message_id": "<s43-1@x.com>", "from": "qa@x.com",
                        "subject": "[冒烟通道收尾] 主题路由建任务", "body": "",
                        "in_reply_to": "", "references": ""})
    assert imap_in.poll_inbox()["processed"] == 1
    items = client.get(f"/api/projects/{pid}/items").json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "主题路由建任务"       # prefix stripped
    thread_item = items[0]["id"]

    # --- ② reply becomes a comment on the threaded item -----------------------
    _stub(monkeypatch, {"message_id": "<s43-2@x.com>", "from": "qa@x.com",
                        "subject": "Re: [冒烟通道收尾] 主题路由建任务",
                        "body": "回复：问题已修复。", "in_reply_to": "<s43-1@x.com>",
                        "references": "<s43-1@x.com>"})
    assert imap_in.poll_inbox()["processed"] == 1
    assert len(client.get(f"/api/projects/{pid}/items").json()["items"]) == 1  # no new task
    comments = client.get(f"/api/items/{thread_item}/comments").json()["comments"]
    assert any("问题已修复" in c["body"] for c in comments)

    # --- ③ activity Atom: feed_key auth + valid XML ----------------------------
    assert client.get("/api/portfolio/activity.atom",
                      params={"key": "nope"}).status_code == 401
    key = client.get("/api/me/feed-key").json()["feed_key"]
    r = client.get("/api/portfolio/activity.atom", params={"key": key})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/atom+xml")
    assert "主题路由建任务" in r.text and "</feed>" in r.text

    # --- rebuild: seen-projection and thread attribution replay ----------------
    projections.rebuild()
    assert db.get_conn().execute(
        "SELECT routed FROM imap_seen WHERE message_id = '<s43-2@x.com>'"
    ).fetchone()["routed"] == "reply"
    _stub(monkeypatch, {"message_id": "<s43-3@x.com>", "from": "qa@x.com",
                        "subject": "Re: 主题路由建任务", "body": "再回复一次",
                        "in_reply_to": "<s43-1@x.com>", "references": ""})
    assert imap_in.poll_inbox()["processed"] == 1    # thread link survives replay
    assert len(client.get(f"/api/projects/{pid}/items").json()["items"]) == 1


def _stub(monkeypatch, *messages):
    monkeypatch.setattr(imap_in, "_fetch_messages", lambda: list(messages))
