"""M48-I144 角色模型分档与 cascade 降级：三档配置（cheap/standard/reasoning）
+ 角色 YAML tier 解析（显式 name 最高优先）+ 主档 LLMError 向上一档重试一次
——降级只在错误路径，span 留痕（apm.model_tier/model_degraded），两档皆败仍
fail；record 录制件 key 带上下文指纹，replay 读取端精确匹配回落兼容旧 key。"""
from __future__ import annotations

import pytest

from apm import config
from apm.core import db
from apm.runtime import provider as provider_mod
from apm.runtime.engine import _next_tier, _tier_model_name
from apm.runtime.provider import Completion, LLMError
from apm.runtime.roles import Role


@pytest.fixture(autouse=True)
def _restore_settings():
    saved = (config.settings.user_id, config.settings.provider_mode,
             config.settings.model_cheap, config.settings.model_standard,
             config.settings.model_reasoning)
    yield
    (config.settings.user_id, config.settings.provider_mode,
     config.settings.model_cheap, config.settings.model_standard,
     config.settings.model_reasoning) = saved


def test_tier_model_name_fallback_chain(monkeypatch):
    monkeypatch.setattr(config.settings, "model_cheap", "glm-flash")
    monkeypatch.setattr(config.settings, "model_standard", "")
    monkeypatch.setattr(config.settings, "llm_model", "glm-5.3")
    monkeypatch.setattr(config.settings, "model_reasoning", "")
    assert _tier_model_name("cheap") == "glm-flash"
    assert _tier_model_name("standard") == "glm-5.3"  # 回落 llm_model
    assert _tier_model_name("reasoning") == "glm-5.3"  # 回落 standard→llm_model


def test_next_tier_cascade_order():
    assert _next_tier("cheap") == "standard"
    assert _next_tier("standard") == "reasoning"
    assert _next_tier("reasoning") is None  # 到底
    assert _next_tier(None) is None and _next_tier("explicit") is None


def test_role_tier_resolution_explicit_name_wins(tmp_path):
    """显式 model.name 优先于 tier；tier-only 角色解析到档位模型名并打标。"""
    config.settings.model_cheap = "glm-5.3-flash"
    r_tier = Role({"id": "r1", "model": {"tier": "cheap", "temperature": 0.1}}, tmp_path / "x")
    assert r_tier.model["name"] == "glm-5.3-flash"
    assert r_tier.model["_tier_resolved"] is True
    r_named = Role({"id": "r2", "model": {"tier": "cheap", "name": "glm-5.3"}}, tmp_path / "y")
    assert r_named.model["name"] == "glm-5.3"  # 显式 name 赢
    assert not r_named.model.get("_tier_resolved")


def test_cascade_degrades_once_and_marks_span(client, tmp_data, isolated_ontologies, monkeypatch):
    """主档（cheap）LLMError → 升到 standard 重试成功；span 留 degraded 痕迹。"""
    config.settings.model_cheap = "glm-flash"
    config.settings.model_standard = "glm-5.3"
    config.settings.model_reasoning = "glm-5.3-max"
    calls: list[str] = []

    class _CascadeStub:
        mode = "openai"

        def complete(self, *, role, node, messages, context, on_delta=None):
            calls.append(context["model"])
            if context["model"] == "glm-flash":
                raise LLMError("429 rate limited")
            return Completion(text="降级后成功", input_tokens=5, output_tokens=3,
                              model=context["model"])

    monkeypatch.setattr(provider_mod, "get_provider", lambda: _CascadeStub())
    from apm.domains.conversations import create_conversation
    from apm.runtime import engine as engine_mod

    pid = client.post("/api/projects",
                      json={"name": "分档项目", "ontology": "software-dev"}).json()["id"]
    conv = create_conversation(project_id=pid, kind="drafting", title="级联", instruction="")
    role = engine_mod.roles.get_role("dev-agent")
    role.model = {"tier": "cheap", "name": "glm-flash", "_tier_resolved": True}
    try:
        run = engine_mod.start_run(conversation_id=conv["id"], agent_role="dev-agent")
        rid = run.id if hasattr(run, "id") else run["id"]
        from tests.conftest import wait_for

        wait_for(lambda: (db.get_conn().execute(
            "SELECT status FROM runs WHERE id = ?", (rid,)).fetchone()["status"]
            in ("succeeded", "interrupted")))
        # drafting 图 3 节点各降级一轮：每节点先主档失败再升档成功（交替对）
        assert len(calls) == 6 and set(calls) == {"glm-flash", "glm-5.3"}
        assert calls[0] == "glm-flash" and calls[1] == "glm-5.3"
        span = db.get_conn().execute(
            "SELECT attributes FROM spans WHERE run_id = ? AND span_kind = 'generation'"
            " ORDER BY id LIMIT 1", (rid,)).fetchone()
        assert span is not None
        attrs = span["attributes"] or "{}"
        assert "model_degraded" in attrs and "model_tier" in attrs
    finally:
        engine_mod.roles.reset_roles()


def test_both_tiers_exhausted_still_fails(client, tmp_data, isolated_ontologies, monkeypatch):
    """reasoning 档到底：两级皆败 → LLMError 传播（run.failed 可读错误）。"""
    from apm.domains.conversations import create_conversation
    from apm.runtime import engine as engine_mod

    class _AlwaysFail:
        mode = "openai"

        def complete(self, *, role, node, messages, context, on_delta=None):
            raise LLMError(f"down on {context['model']}")

    monkeypatch.setattr(provider_mod, "get_provider", lambda: _AlwaysFail())
    pid = client.post("/api/projects",
                      json={"name": "皆败项目", "ontology": "software-dev"}).json()["id"]
    conv = create_conversation(project_id=pid, kind="drafting", title="皆败", instruction="")
    role = engine_mod.roles.get_role("dev-agent")
    role.model = {"tier": "reasoning", "name": "glm-max", "_tier_resolved": True}
    try:
        run = engine_mod.start_run(conversation_id=conv["id"], agent_role="dev-agent")
        rid = run.id if hasattr(run, "id") else run["id"]
        from tests.conftest import wait_for

        wait_for(lambda: (db.get_conn().execute(
            "SELECT status FROM runs WHERE id = ?", (rid,)).fetchone()["status"] == "failed"))
        err = db.get_conn().execute(
            "SELECT error FROM runs WHERE id = ?", (rid,)).fetchone()["error"]
        assert "down on glm-max" in (err or "")
    finally:
        engine_mod.roles.reset_roles()


def test_record_fixture_key_carries_context_fingerprint(tmp_data, monkeypatch):
    """record key = role/node@fp8：不同上下文不互相覆盖；replay 端精确匹配
    优先、回落裸 key 兼容旧件。"""
    import hashlib

    from apm.runtime import replay_templates as rt
    from apm.runtime.provider import RecordProvider

    class _Real:
        mode = "openai"

        def complete(self, **kw):
            ctx = kw["context"]
            return Completion(text=f"rec-{ctx.get('instruction')}", input_tokens=1,
                              output_tokens=1, model="m")

    config.settings.provider_mode = "record"
    monkeypatch.setattr(provider_mod, "new_real_provider", lambda: _Real())
    rp = RecordProvider()
    ctx_a = {"instruction": "写 A", "constraints": []}
    ctx_b = {"instruction": "写 B", "constraints": []}
    ka = rp.complete(role="r", node="draft", messages=[], context=ctx_a).fixture_key
    kb = rp.complete(role="r", node="draft", messages=[], context=ctx_b).fixture_key
    assert ka != kb and "@" in ka and "@" in kb
    assert rt.render("r", "draft", ctx_a) == "rec-写 A"  # 指纹精确命中
    assert rt.render("r", "draft", ctx_b) == "rec-写 B"
    # 裸 key 兼容：手工写旧格式录制件可被 _recorded 直读
    import yaml as _yaml

    path = config.settings.fixtures_dir / "recordings.yaml"
    data = _yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data["r/legacy"] = "旧录制件"
    path.write_text(_yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    ctx_c = {"instruction": "legacy", "constraints": []}
    # 指纹不命中 → 回落模板/裸 key：裸 key 命中需要 render 回落逻辑（先指纹后裸）
    fp_c = hashlib.sha1("legacy|".encode()).hexdigest()[:8]
    assert rt._recorded(f"r/draft@{fp_c}") is None
    assert rt._recorded("r/legacy") == "旧录制件"
