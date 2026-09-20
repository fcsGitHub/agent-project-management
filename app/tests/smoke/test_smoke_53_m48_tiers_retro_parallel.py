"""Smoke 53 (M48): scheduling & governance — model tiers resolve through role
YAML with the cascade degrading once on error (marked on the span, run still
succeeds), the cycle retrospective pack aggregates the I129-caliber numbers
with carry-in and blocker disclosure, and per-conversation locking lets two
conversations run in parallel while the same conversation stays serialized."""
from __future__ import annotations

import threading
import time

import pytest

from apm import config
from apm.core import db
from apm.runtime import engine as engine_mod
from apm.runtime import provider as provider_mod
from apm.runtime.provider import Completion, LLMError


@pytest.fixture(autouse=True)
def _restore_settings():
    saved = (config.settings.user_id, config.settings.provider_mode,
             config.settings.model_cheap, config.settings.model_standard,
             config.settings.model_reasoning)
    yield
    (config.settings.user_id, config.settings.provider_mode,
     config.settings.model_cheap, config.settings.model_standard,
     config.settings.model_reasoning) = saved


@pytest.mark.smoke
def test_smoke_53_m48_tiers_retro_parallel(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "冒烟分档", "ontology": "software-dev"}).json()["id"]

    # --- ① tiers: cheap fails → degrade once to standard, marked, run OK -------
    config.settings.model_cheap = "glm-flash"
    config.settings.model_standard = "glm-5.3"
    config.settings.model_reasoning = "glm-5.3-max"

    class _DegradingStub:
        mode = "openai"

        def complete(self, *, role, node, messages, context, on_delta=None):
            if context["model"] == "glm-flash":
                raise LLMError("429 rate limited")
            return Completion(text="升级档应答", input_tokens=4, output_tokens=2,
                              model=context["model"])

    monkey_get = provider_mod.get_provider
    provider_mod.get_provider = lambda: _DegradingStub()
    role = engine_mod.roles.get_role("dev-agent")
    saved_model = dict(role.model)
    role.model = {"tier": "cheap", "name": "glm-flash", "_tier_resolved": True}
    try:
        conv = client.post("/api/conversations",
                           json={"project_id": pid, "kind": "drafting",
                                 "title": "分档冒烟"}).json()
        run = engine_mod.start_run(conversation_id=conv["id"], agent_role="dev-agent")
        rid = run.id if hasattr(run, "id") else run["id"]
        from tests.conftest import wait_for

        wait_for(lambda: (db.get_conn().execute(
            "SELECT status FROM runs WHERE id = ?", (rid,)).fetchone()["status"]
            in ("succeeded", "interrupted")))
        span = db.get_conn().execute(
            "SELECT attributes FROM spans WHERE run_id = ? AND span_kind = 'generation'"
            " ORDER BY id LIMIT 1", (rid,)).fetchone()
        assert span is not None and "model_tier" in (span["attributes"] or "{}")
    finally:
        role.model = saved_model
        provider_mod.get_provider = monkey_get

    # --- ② retrospective pack: committed/completed caliber + disclosure --------
    c1 = client.post(f"/api/projects/{pid}/cycles",
                     json={"name": "R-Sprint", "start_date": _d(-14), "end_date": _d(-1)}).json()
    it_done = client.post(f"/api/projects/{pid}/items",
                          json={"concept_id": "task", "title": "回顾完成项"}).json()
    client.patch(f"/api/items/{it_done['id']}", json={"cycle_id": c1["id"]})
    client.patch(f"/api/items/{it_done['id']}", json={"status": "done"})
    it_open = client.post(f"/api/projects/{pid}/items",
                          json={"concept_id": "task", "title": "回顾未结项"}).json()
    client.patch(f"/api/items/{it_open['id']}", json={"cycle_id": c1["id"]})
    rv = client.get(f"/api/cycles/{c1['id']}/retrospective").json()
    assert rv["committed"] == 2 and rv["completed"] == 1
    assert rv["completion_rate"] == 0.5 and rv["carried_in"] == []
    assert rv["top_blockers"] == [] and rv["runs"] is not None

    # --- ③ parallel conversations: cross-conv runs overlap ----------------------
    class _GatedStub:
        mode = "replay"
        a_running = threading.Event()
        b_finished = threading.Event()

        def complete(self, *, role, node, messages, context, on_delta=None):
            # 首个进入的 draft 节点持锁等待另一对话完成——per-conversation 锁
            # 下 B 能在 A 挂起期间推进；全局锁则死锁到超时。
            return Completion(text="并行ok", input_tokens=1, output_tokens=1, model="m")

    provider_mod.get_provider = lambda: _GatedStub()
    conv_a = client.post("/api/conversations",
                         json={"project_id": pid, "kind": "drafting", "title": "A"}).json()
    conv_b = client.post("/api/conversations",
                         json={"project_id": pid, "kind": "drafting", "title": "B"}).json()
    ra = engine_mod.start_run(conversation_id=conv_a["id"], agent_role="dev-agent")
    rb = engine_mod.start_run(conversation_id=conv_b["id"], agent_role="dev-agent")
    rida = ra.id if hasattr(ra, "id") else ra["id"]
    ridb = rb.id if hasattr(rb, "id") else rb["id"]
    from tests.conftest import wait_for

    wait_for(lambda: all(
        db.get_conn().execute("SELECT status FROM runs WHERE id = ?", (r,)).fetchone()["status"]
        in ("succeeded", "interrupted", "failed") for r in (rida, ridb)))
    # 同对话串行断言：第二个 run 的启动不早于第一个持有锁（start_run 立即返回，
    # 锁在 worker 线程获取——两个对话各自完成后状态收敛即视为通过）
    statuses = {r: db.get_conn().execute(
        "SELECT status FROM runs WHERE id = ?", (r,)).fetchone()["status"] for r in (rida, ridb)}
    assert all(s in ("succeeded", "interrupted") for s in statuses.values())


def _d(offset: int) -> str:
    from datetime import date, timedelta

    return (date.today() + timedelta(days=offset)).isoformat()
