"""Run engine: executes role graphs on LangGraph with checkpoint/interrupt/resume.

Each Run = one LangGraph thread (thread_id = run_id) built from the role YAML:
analyze → draft → self_check → gate (interrupt) [→ apply] → END.

Gate arrivals suspend the graph via interrupt() and create a pending approval;
human decisions (approve / reject / revise) resume it with a Command. User
messages injected mid-run become constraints that change the next draft.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import traceback
from typing import Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from apm import config
from apm.core import db, events
from apm.core.ids import new_id
from apm.runtime import roles, spans, tools
from apm.runtime.provider import LLMError

_TIER_ORDER = ["cheap", "standard", "reasoning"]

# M111：档位→模型名回落链唯一真源在 roles.tier_model_name（角色加载与
# cascade 升档共用，避免两份链漂移）；别名保留 engine._tier_model_name 旧引用面。
from apm.runtime.roles import tier_model_name as _tier_model_name  # noqa: E402


def _next_tier(tier: str | None) -> str | None:
    """cascade 升档：cheap→standard→reasoning；reasoning/未知档到底。"""
    if tier not in _TIER_ORDER:
        return None
    i = _TIER_ORDER.index(tier)
    return _TIER_ORDER[i + 1] if i + 1 < len(_TIER_ORDER) else None


class RunState(TypedDict, total=False):
    run_id: str
    conversation_id: str
    project_id: str
    item_id: str | None
    role: str
    instruction: str
    constraints: list[str]
    analysis: str
    draft: str
    artifact_path: str
    artifact_commit: str
    check_report: str
    attempts: int
    decision: dict
    outcome: str
    error: str


class InterruptRequested(Exception):
    """Raised between nodes when a human interrupts a running run."""


_saver: SqliteSaver | None = None
_saver_lock = threading.Lock()
_active_runs: dict[str, "RunEngine"] = {}
# M48-I146: per-conversation execution locks——同一对话的 run 互斥（防并发写
# 会话状态），不同对话并行。全局 _exec_lock 会把所有 run 串行化（一个挂起
# 的 LLM 调用阻塞全实例）；SQLite 写已由 db.tx 全局锁保护、LLM 长 IO 不持
# 锁，per-conversation 粒度安全。锁字典随对话数增长但每锁极小（对话数 << 事件数）。
_conv_locks: dict[str, threading.Lock] = {}
_conv_locks_guard = threading.Lock()


def _conversation_lock(conversation_id: str) -> threading.Lock:
    with _conv_locks_guard:
        lock = _conv_locks.get(conversation_id)
        if lock is None:
            lock = threading.Lock()
            _conv_locks[conversation_id] = lock
        return lock


def _release_active_run(run_id: str) -> None:
    """M48-I146: run 落入终态后从注册表移除——修复只进不出的内存泄漏。"""
    _active_runs.pop(run_id, None)
_resume_requests: dict[str, str | None] = {}  # run_id -> instruction
_active_execs = 0
_active_execs_lock = threading.Lock()


def wait_quiescent(timeout: float = 20.0) -> bool:
    """Wait until no engine execution is in flight (test isolation)."""
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        with _active_execs_lock:
            if _active_execs == 0:
                return True
        time.sleep(0.05)
    return False


class _ExecTracker:
    def __enter__(self):
        global _active_execs
        with _active_execs_lock:
            _active_execs += 1
        return self

    def __exit__(self, *exc):
        global _active_execs
        with _active_execs_lock:
            _active_execs -= 1
        return False


def get_saver() -> SqliteSaver:
    global _saver
    with _saver_lock:
        if _saver is None:
            path = config.settings.data_dir / "checkpoints.db"
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(path, check_same_thread=False)
            _saver = SqliteSaver(conn)
            _saver.setup()
        return _saver


def reset_saver_for_tests() -> None:
    global _saver
    with _saver_lock:
        if _saver is not None:
            try:
                _saver.conn.close()
            except Exception:
                pass
        _saver = None


# ============================================================ run lifecycle
def get_run(run_id: str) -> dict | None:
    row = db.get_conn().execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return dict(row) if row else None


def require_run(run_id: str) -> dict:
    r = get_run(run_id)
    if not r:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    return r


def start_run(
    *,
    conversation_id: str,
    agent_role: str,
    item_id: str | None = None,
    graph_node_id: str | None = None,
    instruction: str | None = None,
    actor_type: str = "human",
    actor_id: str | None = None,
    wait: bool = False,
    run_id: str | None = None,
) -> dict:
    from apm.domains.conversations import get_conversation

    role = roles.get_role(agent_role)
    conv = get_conversation(conversation_id)
    if not conv:
        raise KeyError(f"conversation {conversation_id} not found")
    budget_warning = _agent_governance_gate(agent_role)  # M116-I354
    if not budget_warning:
        budget_warning = _cost_budget_gate(conv["project_id"])  # M66-I200
    run_id = run_id or new_id("r")  # M65-I195: fork mints its own id first (lineage emit precedes requested)
    instruction = instruction or conv.get("instruction") or ""
    # M116-I352: item pre-flight BEFORE any emit — the cross-project check
    # (M114-I339) used to sit after run.requested/run.started/conversation.
    # status_changed, so a 422 left a ghost run forever "running" (and, once
    # the checkout lock below exists, would hold it forever). The lock is the
    # Paperclip "atomic task checkout" translation: an active run (pending/
    # running/interrupted — a gate-held run still owns its item until it
    # reaches a terminal state) refuses any second binding with 409.
    if item_id:
        from fastapi import HTTPException

        from apm.domains.items import get_item

        _bound = get_item(item_id)
        if _bound and _bound["project_id"] != conv["project_id"]:
            raise HTTPException(
                status_code=422,
                detail=f"item '{item_id}' belongs to another project")
        holder = db.get_conn().execute(
            "SELECT id FROM runs WHERE item_id = ?"
            " AND status IN ('pending', 'running', 'interrupted')"
            " ORDER BY id DESC LIMIT 1", (item_id,)).fetchone()
        if holder:
            raise HTTPException(
                status_code=409,
                detail=f"工作项已被运行 {holder['id']} 检出（原子检出锁——运行到终态后释放）")
    events.emit(
        event_type="run.requested",
        agg_type="run",
        agg_id=run_id,
        project_id=conv["project_id"],
        actor_type=actor_type,
        actor_id=actor_id or config.settings.user_id,
        payload={
            "conversation_id": conversation_id,
            "agent_role": agent_role,
            "item_id": item_id,
            "graph_node_id": graph_node_id,
            "instruction": instruction,
            "feature_id": conv.get("feature_id"),
        },
    )
    events.emit(
        event_type="run.started",
        agg_type="run",
        agg_id=run_id,
        project_id=conv["project_id"],
        actor_type="system",
        actor_id=f"runtime:{run_id}",
        payload={"thread_id": run_id},
    )
    events.emit(
        event_type="conversation.status_changed",
        agg_type="conversation",
        agg_id=conversation_id,
        project_id=conv["project_id"],
        actor_type="system",
        actor_id=f"runtime:{run_id}",
        payload={"status": "running", "run_id": run_id},
    )
    if item_id:
        _move_item(item_id, conv["project_id"], _item_status_for_start(agent_role))

    engine = RunEngine(run_id=run_id)
    _active_runs[run_id] = engine
    if wait:
        engine.execute()
    else:
        threading.Thread(target=engine.execute, daemon=True).start()
    run = get_run(run_id)  # type: ignore[return-value]
    if budget_warning:
        run["budget_warning"] = budget_warning  # ≥80% soft threshold (hard cap raised 402 above)
    return run


def _cost_budget_gate(project_id: str) -> dict | None:
    """M66-I200 (docs/01 §BK.3): pre-flight LLM spend guard. The runs
    projection has kept the cost ledger since M44, so the guard is a pure
    read-side comparison — LiteLLM semantics: hard cap at 100% (HTTPException
    402; the automation dispatch path already fails soft on HTTPException),
    soft warning at 80% riding on the API response. Budget is a project
    setting (project.updated chain); UTC month window matches started_at."""
    from fastapi import HTTPException

    from apm.core import db

    row = db.get_conn().execute(
        "SELECT cost_budget_usd FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    budget = row["cost_budget_usd"] if row else None
    if not budget or budget <= 0:
        return None
    spend = db.get_conn().execute(
        "SELECT COALESCE(SUM(estimated_cost_usd), 0) AS s FROM runs"
        " WHERE project_id = ?"
        " AND strftime('%Y-%m', COALESCE(started_at, '')) = strftime('%Y-%m', 'now')",
        (project_id,),
    ).fetchone()["s"]
    if spend >= budget:
        raise HTTPException(
            status_code=402,
            detail=f"本月 LLM 成本 ${spend:.2f} 已达预算 ${budget:.2f}，新 run 被拦截——调高项目预算后可继续",
        )
    if spend >= budget * 0.8:
        return {"month_spend_usd": round(spend, 4), "cost_budget_usd": budget}
    return None


def _agent_governance_gate(agent_role: str) -> dict | None:
    """M116-I354 (docs/01 §DG): agent-level governance pre-flight — a paused
    agent refuses new work (409; the automation dispatch path degrades to
    ok:false via its HTTPException catch), and an agent-level monthly budget
    mirrors the project gate exactly (LiteLLM semantics: 402 at 100%, soft
    warning at 80%). Both live in the agents projection overlay (org-level
    governance events), so the guard is a pure read-side comparison."""
    from fastapi import HTTPException

    row = db.get_conn().execute(
        "SELECT status, budget_usd FROM agents WHERE role_id = ?", (agent_role,)
    ).fetchone()
    if not row:
        return None
    if row["status"] == "paused":
        raise HTTPException(
            status_code=409,
            detail=f"Agent {agent_role} 已暂停（治理暂停中）——恢复后再派活")
    budget = row["budget_usd"]
    if not budget or budget <= 0:
        return None
    spend = db.get_conn().execute(
        "SELECT COALESCE(SUM(estimated_cost_usd), 0) AS s FROM runs"
        " WHERE agent_role = ?"
        " AND strftime('%Y-%m', COALESCE(started_at, '')) = strftime('%Y-%m', 'now')",
        (agent_role,),
    ).fetchone()["s"]
    if spend >= budget:
        raise HTTPException(
            status_code=402,
            detail=f"Agent {agent_role} 本月 LLM 成本 ${spend:.2f} 已达预算 ${budget:.2f}，新 run 被拦截——调高该 Agent 预算后可继续",
        )
    if spend >= budget * 0.8:
        return {"agent": agent_role, "month_spend_usd": round(spend, 4),
                "budget_usd": budget}
    return None


def _item_status_for_start(role_id: str) -> str:
    # Concept-specific statuses live in the ontology; the generic mapping is
    # refined by the orchestrator in I6.
    return "in_progress"


def fold_constraints(constraints: list[str], budget: int, instruction_chars: int) -> tuple[list[str], bool, int]:
    """I141: 预算内原样返回；超预算保留最近约束原文、早期折叠为一行摘要
    （计数 + 首条/末条前 80 字）。纯函数——存储与事件流永不触碰。
    返回 (折叠后列表, 是否发生折叠, 折叠条数)。"""
    total = instruction_chars + sum(len(c) for c in constraints)
    if budget <= 0 or total <= budget or len(constraints) <= 1:
        return constraints, False, 0
    keep_budget = max(budget - instruction_chars, budget // 3)
    kept: list[str] = []
    used = 0
    for c in reversed(constraints):
        if used + len(c) > keep_budget:
            break
        kept.insert(0, c)
        used += len(c)
    folded_count = len(constraints) - len(kept)
    if folded_count <= 0:
        return constraints, False, 0
    early = constraints[:folded_count]
    summary = (f"（前 {folded_count} 条约束已折叠：首条「{early[0][:80]}」"
               f"… 末条「{early[-1][:80]}」）")
    return [summary] + kept, True, folded_count


def _status_in_group(concept_id: str, project_id: str, group: str) -> str | None:
    """Find a status of this concept within a five-bucket group (I6)."""
    try:
        from apm.domains.items import project_ontology

        onto = project_ontology(project_id)
        concept = onto.concept(concept_id)
        for s in concept.states:
            if s.get("group") == group:
                return s["id"]
    except Exception:
        return None
    return None


def _move_item(item_id: str, project_id: str, status: str) -> None:
    from apm.domains.items import get_item

    item = get_item(item_id)
    if item and item["status"] != status:
        from apm.domains.items import project_ontology

        onto = project_ontology(project_id)
        try:
            group = onto.validate_item_status(item["concept_id"], status)
        except Exception:
            # Map through the bucket when the literal status doesn't exist in
            # this ontology's concept (e.g. generic 'activity' vs 'task').
            group = {"done": "done", "todo": "todo", "in_progress": "in_progress",
                     "backlog": "backlog"}.get(status)
            if group is None:
                return
            status = _status_in_group(item["concept_id"], project_id, group) or status
            if item["status"] == status:
                return
        events.emit(
            event_type="item.status_changed",
            agg_type="item",
            agg_id=item_id,
            project_id=project_id,
            actor_type="system",
            actor_id="orchestrator",
            payload={"from": item["status"], "status": status, "status_group": group},
        )


class RunEngine:
    """One LangGraph execution bound to a run id."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        run = require_run(run_id)
        self.run = run
        self.project_id = run["project_id"] or ""
        self.role = roles.get_role(run["agent_role"] or "dev-agent")
        self.conversation_id = run["conversation_id"]
        self.gate = self._resolve_gate()
        self.tool_ctx = tools.ToolContext(
            project_id=self.project_id,
            run_id=run_id,
            conversation_id=self.conversation_id,
            role=self.role.id,
            graph_node_id=run["graph_node_id"],
        )
        self.stop_requested = False
        self._interrupted_midrun = False
        self.graph = self._build()

    def _resolve_gate(self) -> str | None:
        """Gates come from the project ontology when the role's default gate is
        not part of it (generic projects remap prd_review → work_review etc.)."""
        role_gate = self.role.output.get("gate")
        if self.role.output.get("on_complete") != "request_gate_approval":
            return role_gate
        try:
            from apm.domains.projects import get_project

            project = get_project(self.project_id) or {}
            onto_name = project.get("ontology")
            if not onto_name:
                return role_gate
            from apm.domains.ontology import load_ontology

            onto = load_ontology(onto_name)
            gates = [p.get("gate") for p in onto.phases if p.get("gate")]
            if role_gate in gates:
                return role_gate
            if not gates:
                return None
            if role_gate in ("release_approval",):
                return gates[-1]
            return gates[0]
        except Exception:
            return role_gate

    # ------------------------------------------------------------ graph
    def _llm_summary(self, early: list[str]) -> str | None:
        """I141 可选 LLM 摘要（role.yaml `model.summarize: true` 且非 replay）：
        廉价档 ui_agent_model 压缩早期约束；任何失败退回规则摘要（返回 None），
        绝不 fail run。"""
        try:
            from apm.runtime.provider import get_provider

            c = get_provider().complete(
                role=self.role.id, node="summarize",
                messages=[
                    {"role": "system", "content": "把多条约束压缩为一段不超过 200 字的摘要，"
                     "保留数字、对象名与否定词；直接输出摘要正文。"},
                    {"role": "user", "content": "\n".join(f"- {x}" for x in early)},
                ],
                context={"model": config.settings.ui_agent_model,
                         "run_id": self.run_id, "item_id": self.run.get("item_id")},
            )
            return (c.text or "").strip() or None
        except Exception:
            return None  # 规则摘要保底，摘要失败不 fail run

    def _context(self, state: RunState) -> dict[str, Any]:
        from apm.domains.conversations import get_conversation, get_messages
        from apm.domains.projects import get_project

        conv = get_conversation(self.conversation_id) or {}
        project = get_project(self.project_id) or {}
        brief = None
        if conv.get("feature_id"):
            from apm.domains.features import get_feature

            f = get_feature(conv["feature_id"])
            brief = f.get("brief") if f else None
        constraints = list(state.get("constraints") or [])
        # user messages since the run started count as injected constraints
        for m in get_messages(self.conversation_id):
            if m["role"] == "user" and m["created_at"] > (self.run["started_at"] or ""):
                text = m["content"].strip()
                if text and text not in constraints:
                    constraints.append(text)
        item_title = None
        if self.run.get("item_id"):
            from apm.domains.items import get_item

            item = get_item(self.run["item_id"])
            item_title = item["title"] if item else None
        instruction = state.get("instruction") or conv.get("instruction") or ""
        # I141 上下文压缩（docs/01 §AR.1）：预算内的约束原样进 prompt；超预算
        # 时早期约束折叠为一行摘要（最近约束保原文）。**读路径优化——存储
        # 原文一字不动，压缩产物不落事件库**（与 I138 瞬态广播同纪律）。
        budget = config.settings.context_budget_chars
        raw_chars = len(instruction) + sum(len(c) for c in constraints)
        folded, compressed, folded_count = fold_constraints(constraints, budget, len(instruction))
        if compressed and self.role.model.get("summarize") and config.settings.provider_mode != "replay":
            summary = self._llm_summary(constraints[:folded_count])
            if summary:
                folded = [f"（前 {folded_count} 条约束摘要：{summary}）"] + folded[1:]
        return {
            "run_id": self.run_id,
            "project_name": project.get("name", ""),
            "instruction": instruction,
            "charter": project.get("charter") or "",
            "brief": brief,
            "constraints": folded,
            "context_chars": raw_chars,
            "context_budget": budget,
            "context_compressed": compressed,
            "item_id": self.run.get("item_id"),
            "item_title": item_title,
            "model": self.role.model.get("name"),
            "model_tier": self.role.model.get("tier") if self.role.model.get("_tier_resolved") else None,
            "temperature": self.role.model.get("temperature", 0.3),
            "draft": state.get("draft", ""),
        }

    def _messages(self, state: RunState) -> list[dict]:
        ctx = self._context(state)
        system = self.role.system_prompt()
        # M68-I204: L1.5 project × role instruction — deeper scope refines the
        # global role prompt (AGENTS.md semantics); appended so it can override
        try:
            from apm.domains.conversations import get_role_instruction

            proj = get_role_instruction(self.project_id, self.role.id)
            if proj:
                system += f"\n\n[L1.5 项目角色指令]\n{proj}"
        except Exception:  # prompt assembly must never crash the run
            pass
        user = f"任务指令：{ctx['instruction']}"
        if ctx["constraints"]:
            user += "\n补充约束：\n" + "\n".join(f"- {c}" for c in ctx["constraints"])
        if ctx.get("brief"):
            user += f"\n功能简报：{ctx['brief']}"
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    def _check_stop(self) -> None:
        if self.stop_requested:
            raise InterruptRequested()

    def _assistant_message(self, content: str, span_id: str | None = None) -> None:
        from apm.domains.conversations import add_message, get_conversation

        conv = get_conversation(self.conversation_id)
        if conv:
            add_message(
                conv,
                content=content,
                role="assistant",
                actor_type="agent",
                actor_id=f"{self.role.id}:{self.run_id}",
                span_id=span_id,
            )

    def _provider_complete(self, node: str, state: RunState):
        from apm.core.bus import event_bus
        from apm.runtime.provider import get_provider

        ctx = self._context(state)
        provider = get_provider()
        # I138: 真实 provider（含 record 包装）走流式；每个增量经 event_bus
        # **瞬态**广播（publish 不 emit——绝不落事件库，逐 token 入库会炸事件
        # 表并破坏 live==replay 可承受性），完整文本仍是 message.created 唯一真相。
        streaming = provider.mode in ("openai", "record")

        def _on_delta(chunk: str) -> None:
            event_bus.publish({
                "event_type": "run.token_delta",
                "run_id": self.run_id,
                "conversation_id": self.conversation_id,
                "project_id": self.project_id,
                "node": node,
                "delta": chunk,
            })

        sid = spans.open_span(
            run_id=self.run_id,
            project_id=self.project_id,
            span_kind="generation",
            name=f"{self.role.id}.{node}",
            parent_id=None,
            attributes={
                "gen_ai.operation.name": "chat",
                "gen_ai.request.model": ctx.get("model"),
                "gen_ai.agent.name": self.role.id,
                "apm.conversation_id": self.conversation_id,
                "apm.item_id": self.run.get("item_id"),
                "apm.graph_node_id": self.run["graph_node_id"],
                "apm.stream": streaming,
                "apm.context_chars": ctx.get("context_chars"),
                "apm.context_budget": ctx.get("context_budget"),
                "apm.context_compressed": ctx.get("context_compressed"),
                "apm.model_tier": ctx.get("model_tier"),
                "apm.model_degraded": False,
            },
        )
        # M48-I144 cascade：tier 声明的角色在主档 LLMError（限流/5xx/超时）时
        # 向上一档重试一次——降级只在错误路径，正常路由永不静默换模型；显式
        # model.name 的角色不参与（用户明确指定，不静默替换）。reasoning 档
        # 到底不再升级，两档皆败仍 fail（可读错误进 run.failed.error）。
        degraded = False
        try:
            completion = provider.complete(
                role=self.role.id, node=node, messages=self._messages(state), context=ctx,
                on_delta=_on_delta if streaming else None,
            )
        except LLMError:
            upgraded = _next_tier(ctx.get("model_tier"))
            if upgraded is None:
                raise
            ctx = {**ctx, "model": _tier_model_name(upgraded), "model_tier": upgraded}
            completion = provider.complete(
                role=self.role.id, node=node, messages=self._messages(state), context=ctx,
                on_delta=_on_delta if streaming else None,
            )
            degraded = True
        # M44: real usage lands on the run record (replay keeps its honest zeros)
        if provider.mode != "replay":
            events.emit(
                event_type="run.tokens_recorded",
                agg_type="run",
                agg_id=self.run_id,
                project_id=self.project_id,
                actor_type="system",
                actor_id=f"runtime:{self.run_id}",
                payload={"input_tokens": completion.input_tokens,
                         "output_tokens": completion.output_tokens,
                         "model": completion.model, "node": node},
            )
        spans.close_span(
            span_id=sid,
            run_id=self.run_id,
            project_id=self.project_id,
            status="ok",
            io={"input_preview": self._messages(state)[-1]["content"][:400], "output_preview": completion.text[:400]},
            extra_attrs={
                "gen_ai.usage.input_tokens": completion.input_tokens,
                "gen_ai.usage.output_tokens": completion.output_tokens,
                "gen_ai.response.model": completion.model,
                "apm.conversation_id": self.conversation_id,
                "apm.item_id": self.run.get("item_id"),
                "apm.graph_node_id": self.run["graph_node_id"],
                "apm.model_tier": ctx.get("model_tier"),
                "apm.model_degraded": degraded,
            },
            span_kind="generation",
            name=f"{self.role.id}.{node}",
        )
        return completion, ctx

    # ------------------------------------------------------------- nodes
    def _node_analyze(self, state: RunState) -> RunState:
        self._check_stop()
        sid = spans.open_span(
            run_id=self.run_id, project_id=self.project_id, span_kind="agent",
            name=f"{self.role.id}.analyze", attributes={"gen_ai.agent.name": self.role.id},
        )
        completion, ctx = self._provider_complete("analyze", state)
        spans.close_span(
            span_id=sid, run_id=self.run_id, project_id=self.project_id,
            status="ok", span_kind="agent", name=f"{self.role.id}.analyze",
        )
        return {**state, "analysis": completion.text}

    def _artifact_path(self) -> str:
        tpl = self.role.output.get("artifact", "artifacts/out.md")
        return tpl.replace("{item_id}", self.run.get("item_id") or "task")

    def _node_draft(self, state: RunState) -> RunState:
        self._check_stop()
        sid = spans.open_span(
            run_id=self.run_id, project_id=self.project_id, span_kind="agent",
            name=f"{self.role.id}.draft", attributes={"gen_ai.agent.name": self.role.id},
        )
        completion, ctx = self._provider_complete("draft", state)
        path = self._artifact_path()
        tool_sid = spans.open_span(
            run_id=self.run_id, project_id=self.project_id, span_kind="tool",
            name="tool.write_artifact",
            attributes={"gen_ai.tool.name": "write_artifact", "apm.conversation_id": self.conversation_id},
        )
        try:
            result = tools.execute(
                "write_artifact",
                {"path": path, "content": completion.text,
                 "message": f"{self.role.id}: draft {path}"},
                self.tool_ctx,
            )
        except tools.ToolDenied as e:
            spans.close_span(
                span_id=tool_sid, run_id=self.run_id, project_id=self.project_id,
                status="error", io={"error": str(e)}, span_kind="tool", name="tool.write_artifact",
            )
            raise
        spans.close_span(
            span_id=tool_sid, run_id=self.run_id, project_id=self.project_id,
            status="ok",
            io={"path": path, "bytes": len(completion.text)},
            extra_attrs={"apm.diff_ref": f"{path}@{result['commit'][:8]}"},
            span_kind="tool", name="tool.write_artifact",
        )
        spans.close_span(
            span_id=sid, run_id=self.run_id, project_id=self.project_id,
            status="ok", span_kind="agent", name=f"{self.role.id}.draft",
        )
        self._assistant_message(
            f"已起草 {path}（commit `{result['commit'][:8]}`）", span_id=sid
        )
        # A revised draft refreshes the pending gate approval's snapshot so the
        # human always reviews the newest artifact.
        try:
            from apm.domains.approvals import refresh_pending_snapshot_for_run

            refresh_pending_snapshot_for_run(
                self.run_id, artifact_path=path, artifact_commit=result["commit"]
            )
        except Exception:
            pass
        return {**state, "draft": completion.text, "artifact_path": path,
                "artifact_commit": result["commit"]}

    def _node_self_check(self, state: RunState) -> RunState:
        self._check_stop()
        completion, _ = self._provider_complete("self_check", state)
        return {**state, "check_report": completion.text}

    def _node_gate(self, state: RunState) -> RunState:
        self._check_stop()
        gate = self.gate
        on_complete = self.role.output.get("on_complete")
        if on_complete != "request_gate_approval" or not gate:
            return {**state, "decision": {"decision": "approved", "auto": True}}
        from apm.domains.approvals import request_gate_approval

        approval = request_gate_approval(
            run_id=self.run_id,
            project_id=self.project_id,
            conversation_id=self.conversation_id,
            item_id=self.run.get("item_id"),
            gate=gate,
            role_id=self.role.id,
            artifact_path=state.get("artifact_path", ""),
            artifact_commit=state.get("artifact_commit", ""),
            summary=f"{self.role.display_name} 完成，请求阶段门 {gate}",
        )
        sid = spans.open_span(
            run_id=self.run_id, project_id=self.project_id, span_kind="gate",
            name=f"gate.{gate}", attributes={"apm.graph_node_id": f"gate:{gate}"},
        )
        decision = interrupt(
            {
                "kind": "gate",
                "gate": gate,
                "approval_id": approval["id"],
                "artifact": {"path": state.get("artifact_path"), "commit": state.get("artifact_commit")},
            }
        )
        spans.close_span(
            span_id=sid, run_id=self.run_id, project_id=self.project_id,
            status="interrupted" if isinstance(decision, dict) and decision.get("decision") != "approved" else "ok",
            io={"decision": decision}, span_kind="gate", name=f"gate.{gate}",
        )
        return {**state, "decision": decision if isinstance(decision, dict) else {"decision": "approved"}}

    def _node_apply(self, state: RunState) -> RunState:
        """Post-approval side effects: planner creates work items from WBS;
        release tags the repo via a dangerous tool (one-shot authorization)."""
        apply_spec = self.role.output.get("apply") or {}
        if apply_spec.get("kind") == "create_items":
            return self._apply_create_items(state)
        if self.role.output.get("tag_on_approval"):
            return self._apply_tag(state)
        return state

    def _apply_tag(self, state: RunState) -> RunState:
        from apm.domains.approvals import request_tool_approval

        tag = f"{self.project_id or 'release'}-v0.1"
        try:
            result = tools.execute("create_git_tag", {"tag": tag}, self.tool_ctx)
            self._assistant_message(f"已创建标签 {result.get('tagged', tag)}")
            return {**state, "outcome": f"tagged {tag}"}
        except tools.ToolApprovalRequired as e:
            approval = request_tool_approval(
                run_id=self.run_id,
                project_id=self.project_id,
                conversation_id=self.conversation_id,
                tool=e.tool,
                args=e.args,
                call_hash=e.call_hash,
            )
            decision = interrupt(
                {"kind": "tool", "tool": e.tool, "args": e.args,
                 "approval_id": approval["id"], "call_hash": e.call_hash}
            )
            if isinstance(decision, dict) and decision.get("decision") == "approved":
                self.tool_ctx.authorized_calls.add(e.call_hash)  # allowed-once
                result = tools.execute("create_git_tag", {"tag": tag}, self.tool_ctx)
                self._assistant_message(f"批准后创建标签 {result.get('tagged', tag)}")
                return {**state, "outcome": f"tagged {tag}"}
            raise tools.ToolDenied(f"dangerous tool {e.tool} rejected")

    def _resolve_apply_concept(self, preferred: str) -> str:
        """Map the role's preferred concept onto the project ontology."""
        from apm.domains.items import project_ontology

        onto = project_ontology(self.project_id)
        if preferred in onto.concepts:
            return preferred
        for cid in self.role.concepts:  # role-declared concepts present here
            if cid in onto.concepts:
                return cid
        for cid, c in onto.concepts.items():  # concept binding this role
            if self.role.id in c.agent_roles:
                return cid
        if len(onto.phases) > 1:  # concept of the first working phase
            work_phase = onto.phases[1]["id"]
            for cid, c in onto.concepts.items():
                if c.default_phase == work_phase:
                    return cid
        return next(iter(onto.concepts))

    def _apply_create_items(self, state: RunState) -> RunState:
        apply_spec = self.role.output.get("apply") or {}
        concept_id = self._resolve_apply_concept(apply_spec.get("concept", "task"))
        wbs = _parse_wbs_tasks(state.get("draft", ""))
        from apm.domains.conversations import get_conversation
        from apm.domains.items import create_item

        conv = get_conversation(self.conversation_id) or {}
        feature_id = conv.get("feature_id")
        created: dict[str, str] = {}
        count = 0
        for t in wbs:
            item = create_item(
                project_id=self.project_id,
                concept_id=concept_id,
                title=t["title"],
                feature_id=feature_id,
                priority=t.get("priority"),
                estimate_hours=t.get("estimate_hours"),
                actor_type="agent",
                actor_id=f"{self.role.id}:{self.run_id}",
            )
            created[t["id"]] = item["id"]
            count += 1
        for t in wbs:
            for dep in t.get("depends_on", []):
                if dep in created and created[dep] != created[t["id"]]:
                    events.emit(
                        event_type="item.related",
                        agg_type="item",
                        agg_id=created[t["id"]],
                        project_id=self.project_id,
                        actor_type="agent",
                        actor_id=f"{self.role.id}:{self.run_id}",
                        payload={
                            "from_item": created[t["id"]],
                            "to_item": created[dep],
                            "relation_type": "depends_on",
                        },
                    )
        self._assistant_message(f"已按 WBS 创建 {count} 个工作项")
        return {**state, "outcome": f"created {count} items"}

    # ------------------------------------------------------------- edges
    def _route_after_check(self, state: RunState) -> str:
        report = state.get("check_report", "")
        attempts = state.get("attempts", 0)
        if report.startswith("ISSUES") and attempts < 1:
            return "draft"
        return "gate"

    def _route_after_gate(self, state: RunState) -> str:
        decision = (state.get("decision") or {}).get("decision", "approved")
        if decision == "revise":
            return "draft"
        has_apply = (self.role.output.get("apply") or {}).get("kind") == "create_items"
        if decision == "approved" and (has_apply or self.role.output.get("tag_on_approval")):
            return "apply"
        return END

    def _build(self):
        g: StateGraph = StateGraph(RunState)
        g.add_node("analyze", self._node_analyze)
        g.add_node("draft", self._node_draft)
        g.add_node("self_check", self._node_self_check)
        g.add_node("gate", self._node_gate)
        g.add_node("apply", self._node_apply)
        g.add_edge(START, "analyze")
        g.add_edge("analyze", "draft")
        g.add_edge("draft", "self_check")
        g.add_conditional_edges(
            "self_check", self._route_after_check, {"draft": "draft", "gate": "gate"}
        )
        g.add_conditional_edges(
            "gate", self._route_after_gate, {"draft": "draft", "apply": "apply", END: END}
        )
        g.add_edge("apply", END)
        return g.compile(checkpointer=get_saver())

    # --------------------------------------------------------- execution
    def _initial_state(self) -> RunState:
        return RunState(
            run_id=self.run_id,
            conversation_id=self.conversation_id,
            project_id=self.project_id,
            item_id=self.run.get("item_id"),
            role=self.role.id,
            instruction=self.run.get("input") or "",
            constraints=[],
            attempts=0,
        )

    def _emit_status(self, event_type: str, payload: dict | None = None) -> None:
        events.emit(
            event_type=event_type,
            agg_type="run",
            agg_id=self.run_id,
            project_id=self.project_id,
            actor_type="system",
            actor_id=f"runtime:{self.run_id}",
            payload=payload or {},
        )

    def _set_conversation(self, status: str) -> None:
        events.emit(
            event_type="conversation.status_changed",
            agg_type="conversation",
            agg_id=self.conversation_id,
            project_id=self.project_id,
            actor_type="system",
            actor_id=f"runtime:{self.run_id}",
            payload={"status": status, "run_id": self.run_id},
        )

    def execute(self) -> None:
        with _ExecTracker(), _conversation_lock(self.conversation_id):
            try:
                result = self.graph.invoke(
                    self._initial_state(), {"configurable": {"thread_id": self.run_id}}
                )
            except InterruptRequested:
                self._interrupted_midrun = True
                self._emit_status("run.interrupted", {"reason": "user_interrupt"})
                self._set_conversation("interrupted")
                _release_active_run(self.run_id)
                return
            except Exception as e:
                traceback.print_exc()
                self._emit_status("run.failed", {"error": str(e)})
                self._set_conversation("active")
                if self.run.get("item_id"):
                    _move_item(self.run["item_id"], self.project_id, "backlog")
                _release_active_run(self.run_id)
                return
            self._handle_result(result, resumed=False)

    def resume(self, decision: dict | None = None) -> None:
        """Resume a suspended run: None continues from checkpoint (mid-run
        interrupt), a decision dict answers a gate/tool interrupt."""
        from langgraph.types import Command

        with _ExecTracker(), _conversation_lock(self.conversation_id):
            self.stop_requested = False
            self._emit_status("run.resumed", {"decision": (decision or {}).get("decision")})
            try:
                if decision is None:
                    result = self.graph.invoke(None, {"configurable": {"thread_id": self.run_id}})
                else:
                    result = self.graph.invoke(
                        Command(resume=decision), {"configurable": {"thread_id": self.run_id}}
                    )
            except Exception as e:
                traceback.print_exc()
                self._emit_status("run.failed", {"error": str(e)})
                self._set_conversation("active")
                _release_active_run(self.run_id)
                return
            self._handle_result(result, resumed=True)

    def _handle_result(self, result: dict, resumed: bool) -> None:
        if result and "__interrupt__" in result:
            # suspended at gate or dangerous tool: approval already requested
            # （可恢复态——run 保留在 _active_runs 等 resume）
            self._emit_status("run.interrupted", {"reason": "awaiting_approval"})
            self._set_conversation("awaiting_review")
            return
        decision = (result or {}).get("decision") or {}
        outcome = decision.get("decision", "approved")
        if outcome == "rejected":
            self._emit_status("run.failed", {"error": "rejected at gate", "decision": decision})
            self._set_conversation("active")
            if self.run.get("item_id"):
                _move_item(self.run["item_id"], self.project_id, "backlog")
            _release_active_run(self.run_id)
            return
        self._emit_status(
            "run.succeeded",
            {
                "output": {"artifact": (result or {}).get("artifact_path"),
                           "outcome": (result or {}).get("outcome")},
                # M58-I174: top-level mirror so watch conditions (flat payload
                # equality) can target the outcome directly
                "outcome": (result or {}).get("outcome"),
                "decision": decision,
            },
        )
        self._set_conversation("active")
        if self.run.get("item_id"):
            _move_item(self.run["item_id"], self.project_id, "done")
        _notify_orchestrator(self.run_id, decision)
        _release_active_run(self.run_id)


def _notify_orchestrator(run_id: str, decision: dict) -> None:
    """Phase continuation hook (filled by the orchestrator in I6)."""
    try:
        from apm.orchestrator.scheduler import on_run_succeeded

        on_run_succeeded(run_id, decision)
    except ImportError:
        pass


def _parse_wbs_tasks(draft: str) -> list[dict]:
    m = re.search(r"```wbs\s*(.*?)```", draft, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
        return [t for t in data if isinstance(t, dict) and t.get("id") and t.get("title")]
    except json.JSONDecodeError:
        return []


# ------------------------------------------------------ runkeeper bridges
def _find_active_run(conversation_id: str) -> dict | None:
    row = db.get_conn().execute(
        "SELECT * FROM runs WHERE conversation_id = ? AND status IN ('running', 'interrupted')"
        " ORDER BY started_at DESC LIMIT 1",
        (conversation_id,),
    ).fetchone()
    return dict(row) if row else None


def _mark_interrupted(conversation_id: str) -> None:
    run = _find_active_run(conversation_id)
    if not run or run["status"] != "running":
        return
    engine = _active_runs.get(run["id"])
    if engine:
        engine.stop_requested = True
    else:
        events.emit(
            event_type="run.interrupted",
            agg_type="run",
            agg_id=run["id"],
            project_id=run["project_id"] or "",
            actor_type="system",
            actor_id="runtime",
            payload={"reason": "user_interrupt"},
        )


def _request_resume(conversation_id: str, instruction: str | None) -> None:
    from apm.domains.approvals import find_pending_for_run

    run = _find_active_run(conversation_id)
    if not run:
        return
    pending = find_pending_for_run(run["id"])
    if pending and run["status"] == "interrupted":
        # suspended at a gate: revise with the injected instruction
        engine = _get_or_rebuild_engine(run["id"])
        engine.resume({"decision": "revise", "instruction": instruction or ""})
    elif run["status"] == "interrupted":
        engine = _get_or_rebuild_engine(run["id"])
        engine.resume(None)
    _resume_requests.pop(run["id"], None)


def _get_or_rebuild_engine(run_id: str) -> RunEngine:
    engine = _active_runs.get(run_id)
    if engine is None:
        engine = RunEngine(run_id=run_id)
        _active_runs[run_id] = engine
    return engine


def install_runkeeper_hooks() -> None:
    from apm.runtime import runkeeper

    runkeeper.set_interrupt_handler(_mark_interrupted)
    runkeeper.set_resume_handler(_request_resume)


def recover_interrupted_runs() -> int:
    """Crash compensation (dsh): runs left 'running' by a dead process become
    interrupted, so the log never shows a zombie execution."""
    rows = db.get_conn().execute("SELECT id FROM runs WHERE status = 'running'").fetchall()
    for r in rows:
        events.emit(
            event_type="run.interrupted",
            agg_type="run",
            agg_id=r["id"],
            project_id="",
            actor_type="system",
            actor_id="runtime",
            payload={"reason": "crash_compensation"},
        )
    return len(rows)
