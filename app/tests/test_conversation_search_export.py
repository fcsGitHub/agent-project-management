"""M61-I184 会话搜索与导出（docs/01 §BF.3，forgotten conversation problem
的组织内解法）：消息体接入 ⌘K FTS（CJK bigram 复用 `_bigrams`——事件溯源
红利第十三例，`message.created` 本就在事件流里）+ `_visible` 项目裁剪 +
Markdown 转写导出（人读通道；NDJSON 事件导出仍是机器通道——§K.3 语义）。
ChatGPT/Claude 侧栏只搜标题，内容级检索是两家共同缺口。"""
from __future__ import annotations

import pytest

from apm import config


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


def _mk_project(client, name: str) -> str:
    return client.post("/api/projects",
                       json={"name": name, "ontology": "software-dev",
                             "requirement": "search"}).json()["id"]


def test_conversation_search_bigram_hit(client):
    pid = _mk_project(client, "会话搜索项目")
    conv = client.post("/api/conversations", json={
        "project_id": pid, "kind": "adhoc", "title": "数据库迁移讨论"}).json()
    cid = conv["id"]
    client.post(f"/api/conversations/{cid}/messages",
                json={"content": "讨论 vendored 依赖升级 与 SQLite WAL checkpoint 策略"})
    client.post(f"/api/conversations/{cid}/messages",
                json={"content": "同意，先做只读压测再切流量"})

    r = client.get("/api/search", params={"q": "只读压测", "types": "conversations"}).json()
    assert len(r["conversations"]) == 1
    hit = r["conversations"][0]
    assert hit["conversation_id"] == cid
    assert hit["project_id"] == pid
    assert "只读压测" in hit["snippet"]
    assert hit["role"] == "user"

    # 中文 bigram 命中：标题不含关键词、消息体含——证明索引的是消息体而非标题
    r2 = client.get("/api/search", params={"q": "checkpoint", "types": "conversations"}).json()
    assert any(h["conversation_id"] == cid for h in r2["conversations"])
    # 无关词不命中
    r3 = client.get("/api/search", params={"q": "kubernetes", "types": "conversations"}).json()
    assert not r3["conversations"]


def test_conversation_search_visible_scoped(client, monkeypatch):
    pid = _mk_project(client, "可见项目")
    hidden = _mk_project(client, "隐藏项目")
    for owner in (pid, hidden):
        conv = client.post("/api/conversations", json={
            "project_id": owner, "kind": "adhoc"}).json()
        cid = conv["id"]
        client.post(f"/api/conversations/{cid}/messages",
                    json={"content": f"关于咖啡机采购决策的项目{owner[:6]}"})

    # network 模式下 qa-wang 非成员：只应看到其可见项目的命中
    # （本地模式第三分支全可见——故须 network+登录走真实会话）
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "password": "qa-pass"})
    monkeypatch.setattr(config.settings, "auth_mode", "network")
    try:
        assert client.post("/api/auth/login",
                           json={"user_id": "qa-wang", "password": "qa-pass"}).status_code == 200
        r = client.get("/api/search", params={"q": "咖啡机", "types": "conversations"}).json()
        assert all(h["project_id"] != hidden for h in r["conversations"])
    finally:
        config.settings.admin_password = ""


def test_conversation_export_transcript(client):
    pid = _mk_project(client, "导出项目")
    conv = client.post("/api/conversations", json={
        "project_id": pid, "kind": "adhoc", "title": "转写演练"}).json()
    cid = conv["id"]
    m1 = client.post(f"/api/conversations/{cid}/messages",
                     json={"content": "第一问：导出应包含哪些结构？"}).json()
    mid1 = m1["message"]["id"]
    client.post(f"/api/conversations/{cid}/messages",
                json={"content": "第一答：角色、时间、actor 与消息正文。", "role": "assistant"})

    x = client.get(f"/api/conversations/{cid}/export").json()
    md = x["markdown"]
    assert x["filename"] == f"conversation-{cid}.md"
    assert "# 转写演练" in md
    assert "- 项目：导出项目" in md
    assert "第一问：导出应包含哪些结构？" in md
    assert "assistant" in md
    assert f"conversation-{cid}" in x["filename"]


def test_conversation_export_hidden_404(client, monkeypatch):
    pid = _mk_project(client, "导出隐藏项目")
    conv = client.post("/api/conversations", json={
        "project_id": pid, "kind": "adhoc"}).json()
    cid = conv["id"]

    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "password": "qa-pass"})
    monkeypatch.setattr(config.settings, "auth_mode", "network")
    try:
        assert client.post("/api/auth/login",
                           json={"user_id": "qa-wang", "password": "qa-pass"}).status_code == 200
        assert client.get(f"/api/conversations/{cid}/export").status_code == 404
    finally:
        config.settings.admin_password = ""


def test_conversation_search_rebuild_consistent(client):
    from apm.core import db

    pid = _mk_project(client, "重建一致项目")
    conv = client.post("/api/conversations", json={
        "project_id": pid, "kind": "adhoc"}).json()
    cid = conv["id"]
    client.post(f"/api/conversations/{cid}/messages",
                json={"content": "重建后索引仍应一致地命中这段话"})

    before = client.get("/api/search", params={"q": "重建后索引", "types": "conversations"}).json()
    assert before["conversations"]

    assert client.post("/api/system/rebuild-projections").status_code == 200
    n = db.get_conn().execute("SELECT COUNT(*) AS n FROM messages_search").fetchone()["n"]
    after = client.get("/api/search", params={"q": "重建后索引", "types": "conversations"}).json()
    assert after["conversations"] == before["conversations"]
    # live 与 rebuild 索引规模一致：每条消息一行
    total_msgs = db.get_conn().execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"]
    assert n == total_msgs
