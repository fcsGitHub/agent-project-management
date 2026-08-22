"""LLM Provider Adapter: one interface, two implementations (docs/10 军规 5).

- ReplayProvider: deterministic templates keyed by (role, node), injecting the
  run context (instruction / constraints / digests). CI and smoke never touch a
  real model.
- OpenAICompatProvider: real model via OpenAI-compatible protocol.
- RecordProvider: OpenAICompat + persists responses to data/fixtures for replay.

The replay fixture key is (role, node) rather than a full-prompt hash: templates
*embed* context (so "interrupt → inject constraint → resume" changes the output
deterministically), which a hash-keyed store cannot express.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from apm import config
from apm.runtime.replay_templates import render


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


class ReplayProvider:
    mode = "replay"

    def complete(self, *, role: str, node: str, messages: list[dict], context: dict[str, Any]) -> Completion:
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

    def __init__(self) -> None:
        from openai import OpenAI

        self._client = OpenAI(
            base_url=config.settings.llm_api_base, api_key=config.settings.llm_api_key or "none"
        )

    def complete(self, *, role: str, node: str, messages: list[dict], context: dict[str, Any]) -> Completion:
        model = context.get("model") or config.settings.llm_model
        resp = self._client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            temperature=context.get("temperature", 0.3),
        )
        choice = resp.choices[0].message.content or ""
        usage = resp.usage
        return Completion(
            text=choice,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            model=model,
        )


class RecordProvider(OpenAICompatProvider):
    """Real model; every response is persisted to fixtures for later replay."""

    mode = "record"
    _lock = threading.Lock()

    def __init__(self) -> None:
        super().__init__()
        self._recordings: dict[str, str] = {}
        path = config.settings.fixtures_dir / "recordings.yaml"
        if path.exists():
            import yaml

            self._recordings = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def complete(self, *, role: str, node: str, messages: list[dict], context: dict[str, Any]) -> Completion:
        c = super().complete(role=role, node=node, messages=messages, context=context)
        key = f"{role}/{node}"
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


def get_provider() -> ReplayProvider | OpenAICompatProvider | RecordProvider:
    global _provider
    with _provider_lock:
        if _provider is None:
            mode = config.settings.provider_mode
            if mode == "replay":
                _provider = ReplayProvider()
            elif mode == "record":
                _provider = RecordProvider()
            else:
                _provider = OpenAICompatProvider()
        return _provider


def reset_provider() -> None:
    global _provider
    with _provider_lock:
        _provider = None
