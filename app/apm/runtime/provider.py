"""LLM Provider Adapter: one interface, two implementations (docs/10 军规 5).

- ReplayProvider: deterministic templates keyed by (role, node), injecting the
  run context (instruction / constraints / digests). CI and smoke never touch a
  real model.
- OpenAICompatProvider: real model via OpenAI-compatible protocol (openai SDK).
- AnthropicCompatProvider: real model via the Anthropic messages protocol
  (httpx2) — auto-selected when the base URL is an /anthropic endpoint.
- RecordProvider: wraps any real provider and persists responses to data/fixtures
  for later replay.

The replay fixture key is (role, node) rather than a full-prompt hash: templates
*embed* context (so "interrupt → inject constraint → resume" changes the output
deterministically), which a hash-keyed store cannot express.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from apm import config
from apm.runtime.replay_templates import render


class LLMError(RuntimeError):
    """A readable, user-facing provider failure (lands in run.failed.error)."""


# I138: incremental token callback — transient deltas ride the event bus only
# (never the event log); the assembled text stays the single persisted truth.
DeltaCallback = Callable[[str], None]


@dataclass
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    fixture_key: str | None = None


def _count_tokens(messages: list[dict], text: str) -> tuple[int, int]:
    # Deterministic approximation; real usage comes from the API in openai mode.
    input_tokens = sum(len(str(m.get("content", ""))) for m in messages) // 2
    return input_tokens, max(1, len(text) // 2)


def resolve_protocol(base_url: str, protocol: str | None = None) -> str:
    p = protocol or config.settings.llm_protocol
    if p != "auto":
        return p
    return "anthropic" if "/anthropic" in (base_url or "") else "openai"


class ReplayProvider:
    mode = "replay"

    def complete(self, *, role: str, node: str, messages: list[dict], context: dict[str, Any],
                 on_delta: DeltaCallback | None = None) -> Completion:
        # 诚实非流式（M46-I138）：replay 无增量语义，一次性直返完整文本。
        text = render(role, node, context)
        input_tokens, output_tokens = _count_tokens(messages, text)
        return Completion(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model="replay-mock",
            fixture_key=f"{role}/{node}",
        )


class OpenAICompatProvider:
    mode = "openai"
    protocol = "openai"

    def __init__(self) -> None:
        from openai import OpenAI

        self._client = OpenAI(
            base_url=config.settings.llm_api_base,
            api_key=config.settings.llm_api_key or "none",
            timeout=config.settings.llm_timeout_s,
            max_retries=2,
        )

    def complete(self, *, role: str, node: str, messages: list[dict], context: dict[str, Any],
                 on_delta: DeltaCallback | None = None) -> Completion:
        model = context.get("model") or config.settings.llm_model
        try:
            if on_delta is not None:
                return self._complete_streaming(model=model, messages=messages, context=context,
                                                on_delta=on_delta)
            resp = self._client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore[arg-type]
                temperature=context.get("temperature", 0.3),
                max_tokens=config.settings.llm_max_tokens,
            )
        except Exception as e:  # SDK errors are verbose; keep the readable core
            raise LLMError(f"LLM 调用失败（openai 协议 · {model}）: {_brief(e)}") from e
        choice = resp.choices[0] if resp.choices else None
        msg = choice.message if choice else None
        text = (msg.content or "").strip() if msg else ""
        if not text:
            reason = getattr(choice, "finish_reason", None)
            hint = "（提高 APM_LLM_MAX_TOKENS）" if reason == "length" else ""
            raise LLMError(f"LLM 返回空内容 finish={reason}{hint}（模型 {model}）")
        usage = resp.usage
        return Completion(
            text=text,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            model=model,
        )

    def _complete_streaming(self, *, model: str, messages: list[dict],
                            context: dict[str, Any], on_delta: DeltaCallback) -> Completion:
        """I138: stream=True 增量读取；usage 走 include_usage 尾 chunk，兼容端
        不支持时退化为字符数估算（诚实近似，量级正确）。"""
        kwargs: dict[str, Any] = dict(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            temperature=context.get("temperature", 0.3),
            max_tokens=config.settings.llm_max_tokens,
            stream=True,
        )
        try:
            stream = self._client.chat.completions.create(
                **kwargs, stream_options={"include_usage": True})
        except Exception:
            # 兼容端不认 stream_options → 退回纯流式（usage 估算）
            stream = self._client.chat.completions.create(**kwargs)
        parts: list[str] = []
        usage: Any = None
        try:
            for chunk in stream:
                u = getattr(chunk, "usage", None)
                if u is not None:
                    usage = u
                choices = getattr(chunk, "choices", None) or []
                delta = getattr(getattr(choices[0], "delta", None), "content", None) if choices else None
                if delta:
                    parts.append(delta)
                    on_delta(delta)
        except Exception as e:
            raise LLMError(f"LLM 流式读取失败（openai 协议 · {model}）: {_brief(e)}") from e
        text = "".join(parts).strip()
        if not text:
            raise LLMError(f"LLM 流式返回空内容（模型 {model}）")
        return Completion(
            text=text,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0 if usage else _count_tokens(messages, text)[0],
            output_tokens=getattr(usage, "completion_tokens", 0) or 0 if usage else max(1, len(text) // 2),
            model=model,
        )


class AnthropicCompatProvider:
    """Anthropic messages protocol over httpx2 (httpx 已停维护——M83-I249 迁移). Thinking
    blocks are skipped; only text blocks form the completion."""

    mode = "openai"
    protocol = "anthropic"

    def __init__(self, transport: Any = None) -> None:
        import httpx2

        base = (config.settings.llm_api_base or "").rstrip("/")
        self._url = base + ("/messages" if base.endswith("/v1") else "/v1/messages")
        headers = {
            "x-api-key": config.settings.llm_api_key or "none",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        self._client = httpx2.Client(
            timeout=config.settings.llm_timeout_s, headers=headers, transport=transport
        )

    def complete(self, *, role: str, node: str, messages: list[dict], context: dict[str, Any],
                 on_delta: DeltaCallback | None = None) -> Completion:
        model = context.get("model") or config.settings.llm_model
        system = "\n".join(m["content"] for m in messages if m.get("role") == "system")
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": config.settings.llm_max_tokens,
            "messages": [
                {"role": m["role"], "content": m["content"]}
                for m in messages
                if m.get("role") != "system"
            ],
        }
        if system:
            body["system"] = system
        last_err = ""
        for attempt in range(3):  # 429/5xx backoff; transport errors retry too
            try:
                if on_delta is not None:
                    return self._complete_streaming(body=body, model=model, on_delta=on_delta)
                r = self._client.post(self._url, json=body)
            except Exception as e:
                last_err = _brief(e)
                time.sleep(1.0 * (attempt + 1))
                continue
            if r.status_code == 200:
                return self._parse(r.json(), model)
            if r.status_code not in (429, 500, 502, 503, 504):
                break
            last_err = f"HTTP {r.status_code}: {r.text[:200]}"
            time.sleep(1.0 * (attempt + 1))
        raise LLMError(f"LLM 调用失败（anthropic 协议 · {model}）: {last_err or 'unknown'}")

    def _complete_streaming(self, *, body: dict[str, Any], model: str,
                            on_delta: DeltaCallback) -> Completion:
        """I138: httpx2 SSE 流式——content_block_delta 逐块回调，usage 取自
        message_start（input）与 message_delta（output）；非 200 抛错交上游重试。"""
        import json as _json

        parts: list[str] = []
        input_tokens = output_tokens = 0
        try:
            with self._client.stream("POST", self._url, json=body) as resp:
                if resp.status_code != 200:
                    detail = resp.read().decode("utf-8", "replace")[:200]
                    raise LLMError(f"HTTP {resp.status_code}: {detail}")
                for line in resp.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload in ("", "[DONE]"):
                        continue
                    try:
                        evt = _json.loads(payload)
                    except ValueError:
                        continue
                    etype = evt.get("type")
                    if etype == "message_start":
                        u = (evt.get("message") or {}).get("usage") or {}
                        input_tokens = int(u.get("input_tokens", 0) or 0)
                    elif etype == "content_block_delta":
                        d = evt.get("delta") or {}
                        if d.get("type") == "text_delta" and d.get("text"):
                            parts.append(d["text"])
                            on_delta(d["text"])
                    elif etype == "message_delta":
                        u = evt.get("usage") or {}
                        output_tokens = int(u.get("output_tokens", 0) or 0)
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(f"LLM 流式读取失败（anthropic 协议 · {model}）: {_brief(e)}") from e
        text = "".join(parts).strip()
        if not text:
            raise LLMError(f"LLM 流式返回空内容（模型 {model}）")
        return Completion(text=text, input_tokens=input_tokens,
                          output_tokens=output_tokens or max(1, len(text) // 2), model=model)

    @staticmethod
    def _parse(data: dict, model: str) -> Completion:
        text = "".join(
            b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
        ).strip()
        if not text:
            types = [b.get("type") for b in data.get("content", [])]
            hint = "（提高 APM_LLM_MAX_TOKENS）" if data.get("stop_reason") == "max_tokens" else ""
            raise LLMError(f"LLM 返回空内容 blocks={types}{hint}（模型 {model}）")
        u = data.get("usage") or {}
        return Completion(
            text=text,
            input_tokens=int(u.get("input_tokens", 0) or 0),
            output_tokens=int(u.get("output_tokens", 0) or 0),
            model=model,
        )


def _brief(e: Exception) -> str:
    s = str(e).strip()
    return s if len(s) <= 300 else s[:297] + "..."


def new_real_provider(transport: Any = None) -> OpenAICompatProvider | AnthropicCompatProvider:
    cls = (
        AnthropicCompatProvider
        if resolve_protocol(config.settings.llm_api_base) == "anthropic"
        else OpenAICompatProvider
    )
    try:
        return cls(transport=transport)  # type: ignore[arg-type]
    except TypeError:
        return cls()  # OpenAI SDK path takes no transport


class RecordProvider:
    """Real model; every response is persisted to fixtures for later replay."""

    mode = "record"
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._real = new_real_provider()
        self._recordings: dict[str, str] = {}
        path = config.settings.fixtures_dir / "recordings.yaml"
        if path.exists():
            import yaml

            self._recordings = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    @property
    def protocol(self) -> str:
        return getattr(self._real, "protocol", "openai")

    def complete(self, *, role: str, node: str, messages: list[dict], context: dict[str, Any],
                 on_delta: DeltaCallback | None = None) -> Completion:
        c = self._real.complete(role=role, node=node, messages=messages, context=context,
                                on_delta=on_delta)  # 录制模式透传流式回调
        # M48-I144: key 带上下文指纹短哈希（instr+约束）——同 role/node 不同
        # 上下文的录制件不再互相覆盖；读取端兼容无指纹旧 key（精确匹配优先，
        # 回落裸 key 由 replay_templates._recorded 处理）。
        import hashlib

        fp_src = f"{context.get('instruction') or ''}|{'|'.join(context.get('constraints') or [])}"
        fp = hashlib.sha1(fp_src.encode("utf-8")).hexdigest()[:8]
        key = f"{role}/{node}@{fp}"
        with RecordProvider._lock:
            self._recordings[key] = c.text
            import yaml

            path = config.settings.fixtures_dir / "recordings.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                yaml.safe_dump(self._recordings, allow_unicode=True), encoding="utf-8"
            )
        c.fixture_key = key
        return c


_provider: Any = None
_provider_lock = threading.Lock()


def get_provider() -> ReplayProvider | OpenAICompatProvider | AnthropicCompatProvider | RecordProvider:
    global _provider
    with _provider_lock:
        if _provider is None:
            mode = config.settings.provider_mode
            if mode == "replay":
                _provider = ReplayProvider()
            elif mode == "record":
                _provider = RecordProvider()
            else:
                _provider = new_real_provider()
        return _provider


def reset_provider() -> None:
    global _provider
    with _provider_lock:
        _provider = None
