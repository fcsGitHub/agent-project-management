"""Smoke 51 (M46): streaming + multi-currency + dark theme in one pass —
token deltas broadcast transiently over the bus but never in the event log
(the assembled message.created stays the single persisted truth), the cost
report converts member rates to the base currency via the manual FX table
with honest unconverted disclosure, and the theme tokens ship the dark
variant + no-FOUC bootstrap in source and in the built PWA shell."""
from __future__ import annotations

import json
import pathlib

import pytest

from apm import config
from apm.core import db
from apm.core.bus import event_bus
from apm.runtime import engine as engine_mod
from apm.runtime import provider as provider_mod
from apm.runtime.provider import Completion


@pytest.fixture(autouse=True)
def _restore_settings():
    saved = (config.settings.user_id, config.settings.provider_mode,
             config.settings.base_currency, config.settings.fx_rates)
    yield
    (config.settings.user_id, config.settings.provider_mode,
     config.settings.base_currency, config.settings.fx_rates) = saved


@pytest.mark.smoke
def test_smoke_51_m46_stream_fx_theme(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "冒烟流式与主题", "ontology": "software-dev",
                            "requirement": "s51"}).json()["id"]

    # --- ① I138 streaming: deltas ride the bus, the log stays append-clean ------
    class _StreamingStub:
        mode = "openai"

        def complete(self, *, role, node, messages, context, on_delta=None):
            if on_delta:
                on_delta("增量一。")
                on_delta("增量二。")
            return Completion(text="增量一。增量二。", input_tokens=6, output_tokens=4,
                              model="glm-5.3")

    published: list[dict] = []
    real_publish = event_bus.publish
    monkey_publish = event_bus.publish
    event_bus.publish = lambda e: published.append(e) or real_publish(e)
    # engine 在方法内 `from apm.runtime.provider import get_provider` —— patch 模块属性
    provider_get = provider_mod.get_provider
    provider_mod.get_provider = lambda: _StreamingStub()
    try:
        conv = client.post("/api/conversations",
                           json={"project_id": pid, "kind": "drafting",
                                 "title": "流式冒烟"}).json()
        cid = conv["id"]
        run = engine_mod.start_run(conversation_id=cid, agent_role="dev-agent")
        from tests.conftest import wait_for

        rid = run.id if hasattr(run, "id") else run["id"]
        wait_for(lambda: (db.get_conn().execute(
            "SELECT status FROM runs WHERE id = ?", (rid,)).fetchone()["status"]
            in ("succeeded", "interrupted")))
        deltas = [e for e in published if e.get("event_type") == "run.token_delta"]
        assert deltas, "增量必须经 bus 瞬态广播"
        assert all(d["conversation_id"] == cid for d in deltas)
        by_node: dict[str, str] = {}
        for d in deltas:
            by_node[d["node"]] = by_node.get(d["node"], "") + d["delta"]
        assert by_node and all(v == "增量一。增量二。" for v in by_node.values())
        n_log = db.get_conn().execute(
            "SELECT COUNT(*) AS n FROM events WHERE event_type = 'run.token_delta'").fetchone()["n"]
        assert n_log == 0, "token_delta 绝不落事件库"
        n_msg = db.get_conn().execute(
            "SELECT COUNT(*) AS n FROM events WHERE event_type = 'message.created'"
            " AND json_extract(payload, '$.conversation_id') = ?", (cid,)).fetchone()["n"]
        assert n_msg >= 1, "完整消息仍是唯一落库真相"
    finally:
        event_bus.publish = monkey_publish
        provider_mod.get_provider = provider_get

    # --- ② I139 FX: member rate in USD converts to base CNY with disclosure -----
    config.settings.base_currency = "CNY"
    config.settings.fx_rates = {"USD": 7.2}
    client.post("/api/me/hourly-rate", json={"rate": 100, "currency": "USD"})
    assert client.get("/api/me/hourly-rate").json() == {"rate": 100, "currency": "USD"}
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "币种计时"}).json()
    assert client.post(f"/api/items/{it['id']}/time_entries",
                       json={"minutes": 120, "spent_on": "2026-09-19"}).status_code == 200
    rep = client.get(f"/api/projects/{pid}/cost-report").json()
    assert rep["base_currency"] == "CNY"
    mine = next(u for u in rep["by_user"] if u["user_id"] == "u_admin")
    assert mine["cost_native"] == 200.0 and mine["fx_rate"] == 7.2 and mine["cost"] == 1440.0
    assert rep["unconverted"] == []
    # 未配汇率的币种：原值计入 + 显式披露
    client.post("/api/me/hourly-rate", json={"rate": 300, "currency": "JPY"})
    rep2 = client.get(f"/api/projects/{pid}/cost-report").json()
    assert rep2["unconverted"] == [{"user_id": "u_admin", "currency": "JPY"}]
    mine2 = next(u for u in rep2["by_user"] if u["user_id"] == "u_admin")
    assert mine2["fx_rate"] is None and mine2["cost"] == 600.0  # 2h × 300 原值计入

    # --- ③ I140 theme: dark token group + no-FOUC bootstrap survive the build ---
    web = pathlib.Path(__file__).resolve().parents[3] / "web"
    css = (web / "src" / "index.css").read_text(encoding="utf-8")
    assert "html.theme-dark" in css and "--color-bg: #101012" in css
    assert "prefers-color-scheme: dark" in css
    html = (web / "index.html").read_text(encoding="utf-8")
    assert "apm-theme" in html and "theme-dark" in html  # 引导脚本
    assert 'media="(prefers-color-scheme: dark)"' in html  # theme-color 双值
    shell = (web / "src" / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    assert "ThemeToggle" in shell and "apm-theme" in shell
    dist = web / "dist" / "index.html"
    if dist.exists():  # 生产外壳保留引导脚本（SW precache 前首帧即正确主题）
        assert "apm-theme" in dist.read_text(encoding="utf-8")
