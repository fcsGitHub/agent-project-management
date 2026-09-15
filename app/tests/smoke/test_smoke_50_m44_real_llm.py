"""Smoke 50 (M44): the real-LLM wiring surface end-to-end — status never leaks
key material, the ping honestly refuses in replay mode and is admin-gated, the
NL layer records parser provenance (rules first), and a provider swap (record
mode stub) shows the L2 fallback answering where L1 rules can't."""
import json

import pytest

from apm import config
from apm.runtime import provider as provider_mod
from apm.runtime.provider import Completion


@pytest.fixture(autouse=True)
def _restore_settings():
    saved = (config.settings.user_id, config.settings.provider_mode, config.settings.ui_agent_model)
    yield
    (config.settings.user_id, config.settings.provider_mode, config.settings.ui_agent_model) = saved


@pytest.mark.smoke
def test_smoke_50_m44_real_llm(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "冒烟真实LLM", "ontology": "software-dev",
                            "requirement": "s50"}).json()["id"]

    # --- ① status surface: honest wiring facts, zero key material ---------------
    st = client.get("/api/system/llm").json()
    assert st["provider_mode"] == "replay" and st["protocol"] is None
    assert st["api_key_set"] is False and "api_key" not in st

    # --- ② ping: replay refuses honestly; non-admin gets 403 -------------------
    ping = client.post("/api/system/llm/ping").json()
    assert ping["ok"] is False and ping["provider_mode"] == "replay"
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert client.post("/api/system/llm/ping").status_code == 403
    client.post("/api/session/identity", json={"user_id": "u_admin"})

    # --- ③ NL L1 provenance: rules answer first, parser rides the event --------
    r = client.post("/api/ui_commands", json={
        "utterance": "打开看板", "page_state": {"project_id": pid}})
    assert r.json()["parser"] == "rules"
    ev = client.get("/api/events", params={"event_type": "ui_command.executed"}).json()["events"][0]
    assert ev["payload"]["parser"] == "rules"

    # --- ④ NL L2: in openai mode a rules-miss falls through to the model -------
    class _Stub:
        mode = "openai"

        def complete(self, *, role, node, messages, context):
            assert role == "ui-agent" and node == "parse"
            return Completion(
                text=json.dumps([
                    {"action": "navigate", "label": "打开审计页",
                     "params": {"path": f"/p/{pid}/audit"}},
                    {"action": "wipe_data", "params": {}},  # unknown → dropped
                ]),
                input_tokens=10, output_tokens=5, model="glm-5.3-flash")

    config.settings.provider_mode = "openai"
    config.settings.ui_agent_model = "glm-5.3-flash"
    monkey_provider = provider_mod.get_provider
    provider_mod.get_provider = lambda: _Stub()
    try:
        r2 = client.post("/api/ui_commands", json={
            "utterance": "看看这个项目都留了哪些痕迹",
            "page_state": {"project_id": pid}})
    finally:
        provider_mod.get_provider = monkey_provider
    assert r2.status_code == 200
    body = r2.json()
    assert body["parser"] == "llm" and len(body["actions"]) == 1  # whitelist enforced
    assert body["actions"][0]["params"]["path"].endswith("/audit")
    # read-only L2 action already executed → event provenance = llm
    evs = client.get("/api/events", params={"event_type": "ui_command.executed"}).json()["events"]
    assert any(e["payload"].get("parser") == "llm" for e in evs)
