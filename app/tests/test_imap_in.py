"""I107 IMAP inbox-to-task (docs/01 §AH.1, Redmine/Jira mail-handler semantics):
a sender matching users.email lands a first-class item under their own identity
in their first project; unknown senders fall back to the intake identity in
IMAP_FALLBACK_PROJECT_ID or are ignored (Redmine --unknown-user=ignore);
Message-IDs are projected into imap_seen so re-polls and rebuilds never
duplicate. The imaplib seam (_fetch_messages) is stubbed like mailer's SMTP."""
from __future__ import annotations

import pytest

from apm import config
from apm.core import db, projections
from apm.domains import imap_in


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "邮箱演示", "ontology": "software-dev", "requirement": "I107"})
    assert r.status_code == 200
    return r.json()


@pytest.fixture()
def imap_env(monkeypatch):
    monkeypatch.setattr(config.settings, "imap_host", "imap.example.com")
    monkeypatch.setattr(config.settings, "imap_user", "inbox@example.com")
    monkeypatch.setattr(config.settings, "imap_pass", "secret")
    return True


def _stub_messages(monkeypatch, *messages):
    monkeypatch.setattr(imap_in, "_fetch_messages", lambda: list(messages))


def _register(client, user_id: str, email: str) -> None:
    assert client.post("/api/users",
                       json={"id": user_id, "name": user_id, "email": email}).status_code == 200


def test_known_sender_routes_to_own_identity(client, tmp_data, isolated_ontologies,
                                             project, imap_env, monkeypatch):
    pid = project["id"]
    _register(client, "qa-wang", "qa@x.com")
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200
    _stub_messages(monkeypatch, {
        "message_id": "<m1@x.com>", "from": "QA 王 <qa@x.com>",
        "subject": "导出按钮在周报页失效", "body": "点导出后浏览器控制台报 500，麻烦看看。",
    })

    out = imap_in.poll_inbox()
    assert out == {"enabled": True, "processed": 1}

    items = client.get(f"/api/projects/{pid}/items").json()["items"]
    mine = next(i for i in items if i["title"] == "导出按钮在周报页失效")
    assert mine["assignee_id"] in (None, "qa-wang")
    # the item event is authored by the matched user, not the logged-in admin
    ev = next(e for e in client.get("/api/events", params={
        "event_type": "item.created"}).json()["events"] if e["agg_id"] == mine["id"])
    assert ev["actor_id"] == "qa-wang"
    # email body became the first comment
    comments = client.get(f"/api/items/{mine['id']}/comments").json()["comments"]
    assert any("控制台报 500" in c["body"] for c in comments)
    # the outcome is evented and projected
    seen = db.get_conn().execute(
        "SELECT routed, from_email FROM imap_seen").fetchall()
    assert [(r["routed"], r["from_email"]) for r in seen] == [("user", "qa@x.com")]


def test_unknown_sender_fallback_then_ignore(client, tmp_data, isolated_ontologies,
                                             project, imap_env, monkeypatch):
    pid = project["id"]
    monkeypatch.setattr(config.settings, "imap_fallback_project_id", pid)
    _stub_messages(monkeypatch, {
        "message_id": "<m2@outside.com>", "from": "stranger@outside.com",
        "subject": "外部工单：登录页白屏", "body": "打开就白屏",
    })
    assert imap_in.poll_inbox()["processed"] == 1
    items = client.get(f"/api/projects/{pid}/items").json()["items"]
    assert any(i["title"] == "外部工单：登录页白屏" for i in items)
    ev = next(e for e in client.get("/api/events", params={
        "event_type": "item.created"}).json()["events"]
        if e["payload"]["title"] == "外部工单：登录页白屏")
    assert ev["actor_type"] == "intake" and ev["actor_id"] == "intake"

    # with no fallback configured, unknown senders are ignored (no item)
    monkeypatch.setattr(config.settings, "imap_fallback_project_id", "")
    _stub_messages(monkeypatch, {
        "message_id": "<m3@outside.com>", "from": "other@outside.com",
        "subject": "垃圾邮件", "body": "",
    })
    assert imap_in.poll_inbox()["processed"] == 1
    items = client.get(f"/api/projects/{pid}/items").json()["items"]
    assert not any(i["title"] == "垃圾邮件" for i in items)
    routed = {r["message_id"]: r["routed"] for r in db.get_conn().execute(
        "SELECT message_id, routed FROM imap_seen").fetchall()}
    assert routed["<m3@outside.com>"] == "skipped"


def test_message_id_idempotent_and_rebuild(client, tmp_data, isolated_ontologies,
                                           project, imap_env, monkeypatch):
    pid = project["id"]
    _register(client, "qa-wang", "qa@x.com")
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200
    msg = {"message_id": "<same@x.com>", "from": "qa@x.com",
           "subject": "只处理一次", "body": ""}
    _stub_messages(monkeypatch, msg)

    assert imap_in.poll_inbox()["processed"] == 1
    assert imap_in.poll_inbox()["processed"] == 0  # re-poll: seen projection holds
    count = len([i for i in client.get(f"/api/projects/{pid}/items").json()["items"]
                 if i["title"] == "只处理一次"])
    assert count == 1

    projections.rebuild()
    assert db.get_conn().execute(
        "SELECT 1 FROM imap_seen WHERE message_id = '<same@x.com>'").fetchone()
    assert imap_in.poll_inbox()["processed"] == 0  # still idempotent after replay
    count = len([i for i in client.get(f"/api/projects/{pid}/items").json()["items"]
                 if i["title"] == "只处理一次"])
    assert count == 1


def test_not_configured_is_honestly_off(client, tmp_data, isolated_ontologies, project):
    assert imap_in.poll_inbox() == {"enabled": False, "processed": 0}
    assert client.post("/api/imap/poll").status_code == 409


def test_subject_prefix_routes_to_member_project(client, tmp_data, isolated_ontologies,
                                                 project, imap_env, monkeypatch):
    """I113 (docs/01 §AJ.1): `[项目名]` routes to the sender's membership
    project with the prefix stripped; non-members and unknown names fall
    through to the default routing with the prefix kept."""
    pid = project["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "email": "qa@x.com"})
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200
    other = client.post("/api/projects",
                        json={"name": "别的项目", "ontology": "software-dev",
                              "requirement": "I113b"}).json()["id"]

    _stub_messages(monkeypatch, {
        "message_id": "<p1@x.com>", "from": "qa@x.com",
        "subject": f"[{project['name']}] 数据导出报错", "body": "",
    }, {
        "message_id": "<p2@x.com>", "from": "qa@x.com",
        "subject": "[别的项目] 越权尝试", "body": "",
    }, {
        "message_id": "<p3@x.com>", "from": "qa@x.com",
        "subject": "[不存在的项目] 落默认", "body": "",
    })
    assert imap_in.poll_inbox()["processed"] == 3

    items = {i["title"]: i["project_id"]
             for i in client.get("/api/projects/%s/items" % pid).json()["items"]}
    # member prefix route: right project, prefix stripped
    assert items.get("数据导出报错") == pid
    # non-member prefix and unknown-name prefix fall through to the default
    assert items.get("[别的项目] 越权尝试") == pid
    assert items.get("[不存在的项目] 落默认") == pid
    assert "越权尝试" not in [i["title"] for i in
                          client.get(f"/api/projects/{other}/items").json()["items"]]
