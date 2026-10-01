"""M46-I138 LLM 流式输出：增量经 event_bus 瞬态广播（绝不落事件库），
完整文本仍是 message.created 唯一落库真相；双协议 provider 流式解析；
replay 诚实非流式。网络从不触碰——openai 用假 SDK 流、anthropic 用
httpx2.MockTransport SSE。"""
from __future__ import annotations

import json

import httpx2
import pytest

from apm import config
from apm.core import db, events
from apm.core.bus import event_bus
from apm.runtime import provider as provider_mod
from apm.runtime.provider import (
    AnthropicCompatProvider,
    LLMError,
    ReplayProvider,
)


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def anthropic_env(monkeypatch):
    monkeypatch.setattr(config.settings, "llm_api_base", "https://open.bigmodel.cn/api/anthropic")
    monkeypatch.setattr(config.settings, "llm_api_key", "sk-test")
    monkeypatch.setattr(config.settings, "llm_max_tokens", 4096)
    monkeypatch.setattr(config.settings, "llm_timeout_s", 5)


class _FakeDelta:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.delta = _FakeDelta(content)


class _FakeChunk:
    def __init__(self, content=None, usage=None):
        self.choices = [_FakeChoice(content)] if content is not None else []
        self.usage = usage


class _FakeUsage:
    def __init__(self, prompt, completion):
        self.prompt_tokens = prompt
        self.completion_tokens = completion


class _FakeStreamAPI:
    """Programmable chat.completions.create replacement (stream path)."""

    def __init__(self, chunks, calls):
        self._chunks = chunks
        self._calls = calls

    def create(self, **kwargs):
        self._calls.append(kwargs)
        return iter(self._chunks)


def test_openai_stream_deltas_and_usage(monkeypatch):
    """stream=True：增量依次回调、文本拼接、usage 取自尾 chunk。"""
    from apm.runtime.provider import OpenAICompatProvider

    chunks = [
        _FakeChunk("你好"),
        _FakeChunk("，世界"),
        _FakeChunk(usage=_FakeUsage(11, 22)),
    ]
    calls: list[dict] = []
    p = OpenAICompatProvider.__new__(OpenAICompatProvider)
    p._client = type("C", (), {"chat": type("Chat", (), {"completions": _FakeStreamAPI(chunks, calls)})()})()
    deltas: list[str] = []
    c = p.complete(
        role="dev-agent", node="draft",
        messages=[{"role": "user", "content": "hi"}],
        context={"model": "glm-5.3"},
        on_delta=deltas.append,
    )
    assert deltas == ["你好", "，世界"]
    assert c.text == "你好，世界"
    assert (c.input_tokens, c.output_tokens) == (11, 22)
    assert calls[0]["stream"] is True
    assert calls[0]["stream_options"] == {"include_usage": True}


def test_openai_stream_without_stream_options_falls_back(monkeypatch):
    """兼容端不认 stream_options → 退回纯流式，usage 用估算。"""
    from apm.runtime.provider import OpenAICompatProvider

    good = [_FakeChunk("ok"), _FakeChunk(usage=_FakeUsage(1, 1))]

    class _Api:
        def __init__(self):
            self.calls: list[dict] = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs.get("stream_options"):
                raise TypeError("unexpected keyword 'stream_options'")
            return iter(good)

    api = _Api()
    p = OpenAICompatProvider.__new__(OpenAICompatProvider)
    p._client = type("C", (), {"chat": type("Chat", (), {"completions": api})()})()
    c = p.complete(
        role="r", node="draft", messages=[{"role": "user", "content": "x"}],
        context={"model": "m"}, on_delta=lambda d: None,
    )
    assert c.text == "ok"
    assert [k.get("stream_options") for k in api.calls] == [{"include_usage": True}, None]


def test_anthropic_sse_stream_parses_and_reports_usage(anthropic_env):
    """httpx SSE：content_block_delta 增量回调，usage 取 message_start/message_delta。"""
    lines = [
        'data: ' + json.dumps({"type": "message_start",
                               "message": {"usage": {"input_tokens": 7}}}),
        'data: ' + json.dumps({"type": "content_block_delta",
                               "delta": {"type": "text_delta", "text": "流式"}}),
        'data: ' + json.dumps({"type": "content_block_delta",
                               "delta": {"type": "text_delta", "text": "你好"}}),
        'data: ' + json.dumps({"type": "message_delta", "usage": {"output_tokens": 9}}),
        "",
    ]
    body = ("\n".join(lines) + "\n").encode("utf-8")

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=body, headers={"content-type": "text/event-stream"})

    p = AnthropicCompatProvider(transport=httpx2.MockTransport(handler))
    deltas: list[str] = []
    c = p.complete(
        role="dev-agent", node="draft",
        messages=[{"role": "user", "content": "hi"}],
        context={"model": "glm-5.3"}, on_delta=deltas.append,
    )
    assert deltas == ["流式", "你好"]
    assert c.text == "流式你好"
    assert (c.input_tokens, c.output_tokens) == (7, 9)


def test_replay_is_honestly_non_streaming(tmp_data):
    """replay 无增量语义：on_delta 零回调，直返完整模板文本。"""
    got: list[str] = []
    c = ReplayProvider().complete(
        role="pm-agent", node="analyze",
        messages=[{"role": "user", "content": "x"}], context={}, on_delta=got.append,
    )
    assert got == [] and c.text


def test_token_delta_transient_never_lands_in_event_log(client, tmp_data, isolated_ontologies, monkeypatch):
    """核心不变量：token_delta 走 bus 瞬态广播（publish），零事件落库；
    message.created 仍是唯一持久化终点。"""
    from apm.domains.conversations import create_conversation
    from apm.runtime import engine as engine_mod
    from apm.runtime.provider import Completion

    r = client.post("/api/projects",
                    json={"name": "流式项目", "ontology": "software-dev"})
    pid = r.json()["id"]
    conv = create_conversation(project_id=pid, kind="drafting", title="流式对话", instruction="")

    published: list[dict] = []
    real_publish = event_bus.publish
    monkeypatch.setattr(event_bus, "publish",
                        lambda e: published.append(e) or real_publish(e))

    class _StreamingFakeProvider:
        mode = "openai"

        def complete(self, *, role, node, messages, context, on_delta=None):
            if on_delta:
                for chunk in ("第一段。", "第二段。"):
                    on_delta(chunk)
            return Completion(text="第一段。第二段。", input_tokens=3, output_tokens=4,
                              model="fake-stream")

    monkeypatch.setattr(engine_mod, "get_provider", lambda: _StreamingFakeProvider(),
                        raising=False)
    import apm.runtime.engine as eng
    monkeypatch.setattr(eng, "get_provider", lambda: _StreamingFakeProvider(), raising=False)
    # engine imports get_provider inside the method from apm.runtime.provider
    monkeypatch.setattr(provider_mod, "get_provider", lambda: _StreamingFakeProvider())

    run = eng.start_run(conversation_id=conv["id"], agent_role="dev-agent")
    # run executes on a worker thread — wait for it to settle
    import time as _t

    for _ in range(100):
        row = db.get_conn().execute("SELECT status FROM runs WHERE id = ?", (run.id if hasattr(run, "id") else run["id"],)).fetchone()
        if row and row["status"] in ("succeeded", "failed", "interrupted"):
            break
        _t.sleep(0.05)

    rid = run.id if hasattr(run, "id") else run["id"]
    # interrupted = 正常挂在 Gate（HANDOFF 语义）；analyze 节点已完成、消息已落库
    assert row and row["status"] in ("succeeded", "interrupted")
    deltas = [e for e in published if e.get("event_type") == "run.token_delta"]
    assert deltas, "流式增量必须经 bus 广播"
    assert all(d["conversation_id"] == conv["id"] for d in deltas)
    # drafting 图的每个节点（analyze/draft/self_check）各流式一轮，逐节点拼接完整
    by_node: dict[str, str] = {}
    for d in deltas:
        by_node[d["node"]] = by_node.get(d["node"], "") + d["delta"]
    assert by_node and all(v == "第一段。第二段。" for v in by_node.values())

    # 事件库里零 token_delta —— 瞬态不落账
    n = db.get_conn().execute(
        "SELECT COUNT(*) AS n FROM events WHERE event_type = 'run.token_delta'").fetchone()["n"]
    assert n == 0
    # 完整消息仍落库（agg_id 是消息 id，按 payload 的 conversation_id 查）
    ev = db.get_conn().execute(
        "SELECT COUNT(*) AS n FROM events WHERE event_type = 'message.created'"
        " AND json_extract(payload, '$.conversation_id') = ?",
        (conv["id"],)).fetchone()["n"]
    assert ev >= 1
