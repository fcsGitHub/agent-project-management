"""System endpoints: health, projection rebuild, real-LLM status/ping."""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException

from apm import config

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "app": "AgentPM",
        "version": "0.1.0",
        "provider_mode": config.settings.provider_mode,
        "user": {"id": config.settings.user_id, "name": config.settings.user_name},
    }


@router.get("/system/llm")
def llm_status() -> dict:
    """Real-model wiring surface (M44): mode/protocol/model — never the key."""
    from apm.runtime.provider import resolve_protocol

    s = config.settings
    return {
        "provider_mode": s.provider_mode,
        "protocol": resolve_protocol(s.llm_api_base) if s.provider_mode != "replay" else None,
        "api_base": s.llm_api_base,
        "model": s.llm_model,
        "ui_agent_model": s.ui_agent_model or s.llm_model,
        "max_tokens": s.llm_max_tokens,
        "api_key_set": bool(s.llm_api_key),
    }


@router.post("/system/llm/ping")
def llm_ping() -> dict:
    """One real completion through the configured provider (admin only — it
    spends tokens). replay mode answers honestly instead of faking a ping."""
    from apm.core import events
    from apm.domains.members import is_instance_admin

    if not is_instance_admin(events.effective_actor()):
        raise HTTPException(status_code=403, detail="admin role required for LLM ping")
    if config.settings.provider_mode == "replay":
        return {
            "ok": False,
            "provider_mode": "replay",
            "error": "当前为 replay 回放模式，不发起真实调用；配置 APM_PROVIDER_MODE=openai 后可 ping 真实模型",
        }
    from apm.runtime.provider import get_provider

    t0 = time.time()
    try:
        c = get_provider().complete(
            role="system",
            node="ping",
            messages=[{"role": "user", "content": "连通性测试：只回复两个字「在线」"}],
            context={"model": config.settings.llm_model, "temperature": 0},
        )
    except Exception as e:
        return {
            "ok": False,
            "provider_mode": config.settings.provider_mode,
            "error": str(e)[:400],
            "latency_ms": int((time.time() - t0) * 1000),
        }
    return {
        "ok": True,
        "provider_mode": get_provider().mode,
        "model": c.model,
        "reply": c.text[:50],
        "usage": {"input": c.input_tokens, "output": c.output_tokens},
        "latency_ms": int((time.time() - t0) * 1000),
    }
