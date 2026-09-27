"""Smoke 66 (M61): governance observation & findable trajectory — the
"observe → find → carry" line. ① Event store stats reconcile against the
events table (measure-first baseline, docs/01 §BF.1: the log grows by
design, observation replaces pruning). ② A Chinese keyword hits conversation
message bodies through FTS bigrams (forgotten-conversation problem, §BF.3).
③ The conversation exports a structured Markdown transcript (human channel;
NDJSON event export stays the machine channel)."""
from __future__ import annotations

import pytest

from apm import config
from apm.core import db


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.mark.smoke
def test_smoke_66_m61_event_stats_conversation_search_export(client, tmp_data,
                                                              isolated_ontologies):
    # --- ① 真实数据：项目 + 会话 + 中文消息往返 --------------------------------
    p = client.post("/api/projects",
                    json={"name": "冒烟治理观测", "ontology": "software-dev",
                          "requirement": "observe"}).json()
    conv = client.post("/api/conversations", json={
        "project_id": p["id"], "kind": "adhoc", "title": "冒烟转写"}).json()
    cid = conv["id"]
    client.post(f"/api/conversations/{cid}/messages",
                json={"content": "讨论免打扰窗口与静默时段的边界语义"})
    client.post(f"/api/conversations/{cid}/messages",
                json={"content": "边界确认：窗口内仅邮件静默，站内照常投递。",
                      "role": "assistant"})

    # --- ② 事件库体积观测：计数对账 + 分布求和 = 总数（先测后治） ----------------
    s = client.get("/api/system/event-store-stats").json()
    n = db.get_conn().execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
    assert s["total_events"] == n
    assert sum(d["count"] for d in s["distribution"]) == s["total_events"]
    assert s["db_bytes"] > 0
    assert s["oldest_ts"] and s["newest_ts"] and s["oldest_ts"] <= s["newest_ts"]
    types = {(d["agg_type"], d["event_type"]) for d in s["distribution"]}
    assert ("project", "project.created") in types
    assert ("message", "message.created") in types

    # --- ③ 中文关键词命中会话消息体（FTS bigram，非标题匹配） -------------------
    r = client.get("/api/search",
                   params={"q": "静默时段", "types": "conversations"}).json()
    assert len(r["conversations"]) == 1
    hit = r["conversations"][0]
    assert hit["conversation_id"] == cid
    assert "静默时段" in hit["snippet"]
    # 无关词不命中
    r2 = client.get("/api/search",
                    params={"q": "kubernetes", "types": "conversations"}).json()
    assert not r2["conversations"]

    # --- ④ Markdown 转写导出：结构齐全（标题/项目/角色/正文） -------------------
    x = client.get(f"/api/conversations/{cid}/export").json()
    md = x["markdown"]
    assert x["filename"] == f"conversation-{cid}.md"
    assert "# 冒烟转写" in md
    assert "- 项目：冒烟治理观测" in md
    assert "user" in md and "assistant" in md
    assert "窗口内仅邮件静默，站内照常投递" in md
