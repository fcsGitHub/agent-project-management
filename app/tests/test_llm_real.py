"""M44 real-LLM wiring: dual-protocol providers, status/ping endpoints, and the
NL layer's L2 model fallback. Network is never touched — the Anthropic client
runs on httpx2.MockTransport and the LLM calls use stub providers."""
from __future__ import annotations

import json

import httpx2
import pytest

from apm import config
from apm.runtime import provider as provider_mod
from apm.runtime.provider import (
    AnthropicCompatProvider,
    Completion,
    LLMError,
    resolve_protocol,
)


@pytest.fixture(autouse=True)
def _restore_identity():
    # switch_identity mutates settings.user_id globally — leaking it would make
    # the next test's ensure_default_user promote the wrong user to admin.
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def anthropic_env(monkeypatch):
    monkeypatch.setattr(config.settings, "llm_api_base", "https://open.bigmodel.cn/api/anthropic")
    monkeypatch.setattr(config.settings, "llm_api_key", "sk-test")
    monkeypatch.setattr(config.settings, "llm_max_tokens", 4096)
    monkeypatch.setattr(config.settings, "llm_timeout_s", 5)


def test_resolve_protocol_auto(monkeypatch):
    monkeypatch.setattr(config.settings, "llm_protocol", "auto")
    assert resolve_protocol("https://open.bigmodel.cn/api/anthropic") == "anthropic"
    assert resolve_protocol("https://open.bigmodel.cn/api/coding/paas/v4") == "openai"
    monkeypatch.setattr(config.settings, "llm_protocol", "openai")
    assert resolve_protocol("https://open.bigmodel.cn/api/anthropic") == "openai"


def test_anthropic_blocks_parse_and_retry(client, tmp_data, isolated_ontologies, anthropic_env, monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls["n"] += 1
        assert request.url.path.endswith("/v1/messages")
        assert request.headers["x-api-key"] == "sk-test"
        body = json.loads(request.content)
        assert body["max_tokens"] == 4096
        if calls["n"] == 1:  # first attempt 5xx → retried
            return httpx2.Response(503, text="upstream")
        return httpx2.Response(200, json={
            "content": [
                {"type": "thinking", "thinking": "无声思考，不算产出"},
                {"type": "text", "text": "你好，真实世界"},
            ],
            "usage": {"input_tokens": 12, "output_tokens": 34},
            "stop_reason": "end_turn",
        })

    monkeypatch.setattr(provider_mod.time, "sleep", lambda s: None)
    p = AnthropicCompatProvider(transport=httpx2.MockTransport(handler))
    c = p.complete(
        role="dev-agent", node="draft",
        messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
        context={"model": "glm-5.3"},
    )
    assert c.text == "你好，真实世界"  # thinking block skipped
    assert (c.input_tokens, c.output_tokens) == (12, 34)
    assert c.model == "glm-5.3"
    assert calls["n"] == 2


def test_anthropic_empty_content_is_readable_error(client, tmp_data, isolated_ontologies, anthropic_env):
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={
            "content": [{"type": "thinking", "thinking": "想完了但没写字"}],
            "usage": {"input_tokens": 5, "output_tokens": 50},
            "stop_reason": "max_tokens",
        })

    p = AnthropicCompatProvider(transport=httpx2.MockTransport(handler))
    with pytest.raises(LLMError, match="APM_LLM_MAX_TOKENS"):
        p.complete(role="r", node="n", messages=[{"role": "user", "content": "x"}], context={})


def test_system_llm_status_replay_honest(client, tmp_data, isolated_ontologies):
    r = client.get("/api/system/llm").json()
    assert r["provider_mode"] == "replay"
    assert r["protocol"] is None  # replay never picks a wire protocol
    assert r["api_key_set"] is False
    assert "api_key" not in r  # status surface never carries key material


def test_llm_ping_replay_refuses_and_admin_gated(client, tmp_data, isolated_ontologies):
    r = client.post("/api/system/llm/ping")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False and body["provider_mode"] == "replay"

    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert client.post("/api/system/llm/ping").status_code == 403


def test_llm_ping_real_mode_reports_usage(client, tmp_data, isolated_ontologies, monkeypatch):
    monkeypatch.setattr(config.settings, "provider_mode", "openai")

    class _Stub:
        mode = "openai"

        def complete(self, **kw):
            return Completion(text="在线", input_tokens=8, output_tokens=2, model="glm-5.3")

    monkeypatch.setattr(provider_mod, "get_provider", lambda: _Stub())
    body = client.post("/api/system/llm/ping").json()
    assert body["ok"] is True
    assert body["model"] == "glm-5.3"
    assert body["usage"] == {"input": 8, "output": 2}
    assert "latency_ms" in body


def test_nl_l2_uses_ui_agent_model_fallback(client, tmp_data, isolated_ontologies, monkeypatch):
    """No ui_agent_model configured → L2 degrades to llm_model."""
    monkeypatch.setattr(config.settings, "provider_mode", "openai")
    monkeypatch.setattr(config.settings, "ui_agent_model", "")
    llm = _ScriptedLLM("[]")
    monkeypatch.setattr(provider_mod, "get_provider", lambda: llm)
    client.post("/api/ui_commands", json={"utterance": "帮我把火箭发射了", "page_state": {}})
    assert llm.seen_model == config.settings.llm_model


# ---------------------------------------------------------------- NL L2
class _ScriptedLLM:
    def __init__(self, text: str):
        self.text = text
        self.mode = "openai"
        self.seen_model: str | None = None

    def complete(self, *, role, node, messages, context):
        assert role == "ui-agent" and node == "parse"
        self.seen_model = context["model"]
        return Completion(text=self.text, input_tokens=1, output_tokens=1,
                          model=context["model"])


def test_normalize_llm_actions_whitelist():
    from apm.domains.nl import _normalize_llm_actions

    raw = json.dumps([
        {"action": "navigate", "label": "打开看板", "params": {"path": "/p/p1/board"}},
        {"action": "navigate", "params": {"path": "https://evil.example"}},   # path 不在白名单
        {"action": "delete_project", "params": {}},                            # 未知动作
        {"action": "set_filter", "params": {"priority": "high", "evil": 1}},  # 未知参数被剥离
        {"action": "set_filter", "params": {}},                                # 剥离后为空
    ])
    out = _normalize_llm_actions("```json\n" + raw + "\n```")
    assert len(out) == 2
    assert out[0]["params"]["path"] == "/p/p1/board" and out[0]["read_only"] is True
    assert out[1]["params"] == {"priority": "high"}
    assert _normalize_llm_actions("我不会解析") == []
    assert _normalize_llm_actions("[broken") == []


def test_nl_l2_fallback_parser_provenance(client, tmp_data, isolated_ontologies, monkeypatch):
    monkeypatch.setattr(config.settings, "provider_mode", "openai")
    monkeypatch.setattr(config.settings, "ui_agent_model", "glm-5.3-flash")
    llm = _ScriptedLLM(json.dumps([
        {"action": "navigate", "label": "打开依赖图", "params": {"path": "/p/p1/deps"}},
    ]))
    monkeypatch.setattr(provider_mod, "get_provider", lambda: llm)

    p = client.post("/api/projects",
                    json={"name": "P", "ontology": "software-dev", "requirement": "r"}).json()
    # rules miss → L2 answers, provenance recorded
    r = client.post("/api/ui_commands", json={
        "utterance": "看一下这个项目任务之间谁卡着谁",
        "page_state": {"project_id": p["id"]},
    })
    assert r.status_code == 200
    body = r.json()
    assert body["parser"] == "llm"
    assert llm.seen_model == "glm-5.3-flash"  # the cheap ui_agent_model wins
    assert body["actions"][0]["params"]["path"].endswith("/deps")
    evs = client.get("/api/events", params={"event_type": "ui_command.executed"}).json()["events"]
    assert evs[0]["payload"]["parser"] == "llm"

    # rules hit still wins (openai mode, deterministic first)
    r2 = client.post("/api/ui_commands", json={
        "utterance": "打开看板", "page_state": {"project_id": p["id"]},
    })
    assert r2.json()["parser"] == "rules"


def test_nl_l2_unparsable_still_422(client, tmp_data, isolated_ontologies, monkeypatch):
    monkeypatch.setattr(config.settings, "provider_mode", "openai")
    monkeypatch.setattr(provider_mod, "get_provider",
                        lambda: _ScriptedLLM("抱歉我不明白"))
    r = client.post("/api/ui_commands", json={"utterance": "帮我把火箭发射了", "page_state": {}})
    assert r.status_code == 422
    assert "L2" in r.json()["detail"]["message"]


# ------------------------------------------------------ run token ledger
def test_engine_records_real_tokens(client, tmp_data, isolated_ontologies, monkeypatch):
    """Real-provider runs accumulate usage on the run row; replay stays zero."""
    from tests.conftest import wait_for

    class _Stub:
        mode = "openai"

        def complete(self, **kw):
            return Completion(text="分析内容", input_tokens=11, output_tokens=7,
                              model="glm-5.3")

    monkeypatch.setattr(config.settings, "provider_mode", "openai")
    monkeypatch.setattr(provider_mod, "get_provider", lambda: _Stub())
    p = client.post("/api/projects",
                    json={"name": "P", "ontology": "software-dev", "requirement": "r"}).json()
    conv = p["bootstrap"]["conversation_id"]
    run = client.post("/api/runs", json={"conversation_id": conv, "agent_role": "pm-agent",
                                         "wait": True}).json()
    wait_for(lambda: client.get(f"/api/runs/{run['id']}").json()["status"] == "interrupted")
    # analyze + draft + self_check = 3 real calls × (11, 7)
    rep = client.get(f"/api/projects/{p['id']}/runs/report").json()
    assert rep["tokens"]["input"] == 33
    assert rep["tokens"]["output"] == 21


def test_run_tokens_replay_stays_zero(client, tmp_data, isolated_ontologies):
    p = client.post("/api/projects",
                    json={"name": "P", "ontology": "software-dev", "requirement": "r"}).json()
    run = client.post("/api/runs", json={"conversation_id": p["bootstrap"]["conversation_id"],
                                         "agent_role": "pm-agent", "wait": True}).json()
    from tests.conftest import wait_for
    wait_for(lambda: client.get(f"/api/runs/{run['id']}").json()["status"] == "interrupted")
    rep = client.get(f"/api/projects/{p['id']}/runs/report").json()
    assert rep["tokens"]["input"] == 0 and rep["tokens"]["output"] == 0
