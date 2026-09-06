"""Smoke 41 (M35): the channel-and-reply trio end-to-end — a stubbed mailbox
pass lands a first-class item under the sender's identity with the body as the
first comment and stays idempotent; saved replies round-trip as own-data
runtime state surviving rebuild; a quote-reply draft round-trips as plain text."""
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
def test_smoke_41_m35_channel_reply(client, tmp_data, isolated_ontologies, monkeypatch):
    r = client.post("/api/projects",
                    json={"name": "冒烟通道回复", "ontology": "software-dev", "requirement": "s41"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    # --- ① IMAP: known sender → own identity + first comment + idempotency ---
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "email": "qa@x.com"})
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200
    monkeypatch.setattr(config.settings, "imap_host", "imap.example.com")
    monkeypatch.setattr(config.settings, "imap_user", "inbox@example.com")
    monkeypatch.setattr(config.settings, "imap_pass", "secret")
    monkeypatch.setattr(imap_in, "_fetch_messages", lambda: [{
        "message_id": "<s41@x.com>", "from": "QA 王 <qa@x.com>",
        "subject": "冒烟邮件转任务", "body": "来自邮箱的正文。",
    }])
    assert imap_in.poll_inbox() == {"enabled": True, "processed": 1}
    items = [i for i in client.get(f"/api/projects/{pid}/items").json()["items"]
             if i["title"] == "冒烟邮件转任务"]
    assert len(items) == 1
    ev = next(e for e in client.get("/api/events", params={
        "event_type": "item.created"}).json()["events"] if e["agg_id"] == items[0]["id"])
    assert ev["actor_id"] == "qa-wang"
    comments = client.get(f"/api/items/{items[0]['id']}/comments").json()["comments"]
    assert any("来自邮箱的正文" in c["body"] for c in comments)
    assert imap_in.poll_inbox()["processed"] == 0  # Message-ID idempotency

    # --- ② saved replies: own-data roundtrip, rebuild keeps the library ------
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert client.post("/api/me/saved-replies",
                       json={"title": "冒烟常用语", "body": "已复现，安排修复。"}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    titles_admin = [x["title"] for x in client.get("/api/me/saved-replies").json()["replies"]]
    assert "冒烟常用语" not in titles_admin            # own-data isolation

    # --- ③ quote reply: the I94 draft format round-trips as plain text -------
    quote_draft = "@QA 王 引用：\n> 来自邮箱的正文。\n\n已收到，今天处理。"
    c = client.post(f"/api/items/{items[0]['id']}/comments", json={"body": quote_draft})
    assert c.status_code == 200 and c.json()["body"] == quote_draft  # byte-identical
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    kinds = [n["kind"] for n in client.get("/api/notifications").json()["notifications"]]
    client.post("/api/session/identity", json={"user_id": "u_admin"})

    # --- rebuild: mailbox projection, saved-reply library and quotes replay --
    projections.rebuild()
    assert db.get_conn().execute(
        "SELECT 1 FROM imap_seen WHERE message_id = '<s41@x.com>'").fetchone()
    assert imap_in.poll_inbox()["processed"] == 0     # still idempotent after replay
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    titles_qa = [x["title"] for x in client.get("/api/me/saved-replies").json()["replies"]]
    assert titles_qa == ["冒烟常用语"]                 # runtime state survives
    comments2 = client.get(f"/api/items/{items[0]['id']}/comments").json()["comments"]
    assert any(c["body"] == quote_draft for c in comments2)  # replayed byte-identical
