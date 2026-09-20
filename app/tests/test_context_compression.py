"""M47-I141 LLM 对话上下文压缩：prompt 组装读路径的字符预算——超限折叠
早期约束为一行摘要（最近约束保原文），预算内零行为；**存储原文一字不动，
压缩产物不落事件库**；role.yaml `summarize` 开关走廉价模型真实摘要，失败
退回规则摘要，绝不 fail run。"""
from __future__ import annotations

import pytest

from apm import config
from apm.core import db
from apm.runtime.engine import fold_constraints


@pytest.fixture(autouse=True)
def _restore_settings():
    saved = config.settings.context_budget_chars
    yield
    config.settings.context_budget_chars = saved


def test_fold_within_budget_is_zero_behavior():
    """预算内（或缺省/单条约束）零折叠——向后兼容的关键。"""
    cs = ["约束一", "约束二"]
    out, compressed, n = fold_constraints(cs, 8000, 100)
    assert out == cs and compressed is False and n == 0


def test_fold_disabled_with_zero_budget():
    config.settings.context_budget_chars = 0  # 0 = 不限制
    cs = ["x" * 100] * 50
    out, compressed, n = fold_constraints(cs, 0, 10)
    assert out == cs and compressed is False


def test_fold_keeps_recent_and_summarizes_early():
    """超预算：最近约束保原文、早期折叠为一行（计数+首末条摘录）。"""
    cs = [f"约束{i}：" + "细节" * 30 for i in range(20)]
    budget = 1000
    out, compressed, n = fold_constraints(cs, budget, 50)
    assert compressed is True and 0 < n < 20
    assert out[0].startswith("（前") and "条约束已折叠" in out[0]
    assert cs[0][:30] in out[0] and cs[n - 1][:30] in out[0]  # 首末条摘录
    assert out[1:] == cs[n:]  # 最近约束原文保留
    # 折叠后总量受控（明显小于原始量）
    assert sum(len(x) for x in out) < sum(len(x) for x in cs)


def test_folded_context_never_touches_storage(client, tmp_data, isolated_ontologies, monkeypatch):
    """集成：注入约束超预算触发折叠，但 messages 表原文完整、事件流零
    compression 事件——压缩只存在于 span 观测。"""
    from apm.domains.conversations import create_conversation, get_messages

    pid = client.post("/api/projects",
                      json={"name": "压缩项目", "ontology": "software-dev"}).json()["id"]
    conv = create_conversation(project_id=pid, kind="drafting", title="压缩对话",
                               instruction="起草 PRD")
    cid = conv["id"]
    # 借 send_message 造 30 条注入约束（每条 400 字 → 总量远超 8000 预算）
    big = "约束细节" * 100
    for i in range(30):
        client.post(f"/api/conversations/{cid}/messages", json={"content": f"约束{i}{big}"})
    stored = get_messages(cid)
    assert len([m for m in stored if m["role"] == "user"]) == 30

    from apm.runtime import engine as engine_mod

    run = engine_mod.start_run(conversation_id=cid, agent_role="dev-agent")
    rid = run.id if hasattr(run, "id") else run["id"]
    from tests.conftest import wait_for

    wait_for(lambda: (db.get_conn().execute(
        "SELECT status FROM runs WHERE id = ?", (rid,)).fetchone()["status"]
        in ("succeeded", "interrupted")))

    # 存储原文一字不动
    assert len([m for m in get_messages(cid) if m["role"] == "user"]) == 30
    # 事件流零压缩痕迹
    n = db.get_conn().execute(
        "SELECT COUNT(*) AS n FROM events WHERE event_type LIKE '%compress%'").fetchone()["n"]
    assert n == 0
    # span 观测落了压缩事实
    span = db.get_conn().execute(
        "SELECT attributes FROM spans WHERE run_id = ? AND span_kind = 'generation'"
        " ORDER BY id LIMIT 1", (rid,)).fetchone()
    assert span is not None
    attrs = span["attributes"] or "{}"
    assert "context_compressed" in attrs


def test_llm_summary_failure_falls_back(monkeypatch):
    """role.summarize 开 + 真实模式：provider 抛错 → 规则摘要保底，不炸。"""
    from apm.runtime.engine import RunEngine  # noqa: F401  (import sanity)

    class _BoomProvider:
        mode = "openai"

        def complete(self, **kw):
            raise RuntimeError("provider down")

    monkeypatch.setattr(config.settings, "provider_mode", "openai")

    class _Role:
        model = {"name": "glm-5.3", "summarize": True}

    class _FakeEngine:
        role = _Role()
        run_id = "r_x"
        run = {"item_id": None}
        _llm_summary = RunEngine._llm_summary

    fe = _FakeEngine()
    out = fe._llm_summary(["约束甲", "约束乙"])
    assert out is None  # 失败退回 None → 调用方保留规则摘要
