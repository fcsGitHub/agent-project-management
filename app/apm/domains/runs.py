"""Run domain API: start runs, query status/spans/timeline, retry."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from apm.core import db, events
from apm.core.projections import on

router = APIRouter(tags=["runs"])


# ------------------------------------------------------------ projections
@on("run.requested")
def _proj_run_requested(conn, e):
    p = e.payload
    conn.execute(
        "INSERT OR REPLACE INTO runs (id, project_id, feature_id, item_id, conversation_id,"
        " agent_role, graph_node_id, status, thread_id, input) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            e.agg_id,
            e.project_id or None,
            p.get("feature_id"),
            p.get("item_id"),
            p.get("conversation_id"),
            p.get("agent_role"),
            p.get("graph_node_id"),
            "pending",
            e.agg_id,
            p.get("instruction"),
        ),
    )


@on("run.started")
def _proj_run_started(conn, e):
    conn.execute(
        "UPDATE runs SET status = 'running', started_at = ? WHERE id = ?", (e.ts, e.agg_id)
    )


@on("run.interrupted")
def _proj_run_interrupted(conn, e):
    conn.execute("UPDATE runs SET status = 'interrupted' WHERE id = ?", (e.agg_id,))


@on("run.resumed")
def _proj_run_resumed(conn, e):
    conn.execute("UPDATE runs SET status = 'running' WHERE id = ?", (e.agg_id,))


@on("run.succeeded")
def _proj_run_succeeded(conn, e):
    conn.execute(
        "UPDATE runs SET status = 'succeeded', ended_at = ?, output = ? WHERE id = ?",
        (e.ts, json.dumps(e.payload.get("output", {}), ensure_ascii=False), e.agg_id),
    )


@on("run.failed")
def _proj_run_failed(conn, e):
    conn.execute(
        "UPDATE runs SET status = 'failed', ended_at = ?, error = ? WHERE id = ?",
        (e.ts, e.payload.get("error"), e.agg_id),
    )


@on("run.tokens_recorded")
def _proj_run_tokens(conn, e):
    """Real-provider usage accumulates per generation node (M44). The replay
    provider never emits this, so its honest zeros survive untouched.
    M62-I188: the payload may carry estimated_cost_usd (computed by whoever
    knows the pricing) — the ledger accumulates it when present, so the
    read-side aggregations (/projects/{id}/runs/report, /portfolio/
    agent-usage) sum a real number instead of a dormant zero column."""
    p = e.payload
    conn.execute(
        "UPDATE runs SET total_input_tokens = total_input_tokens + ?,"
        " total_output_tokens = total_output_tokens + ?,"
        " estimated_cost_usd = estimated_cost_usd + ? WHERE id = ?",
        (int(p.get("input_tokens", 0)), int(p.get("output_tokens", 0)),
         float(p.get("estimated_cost_usd", 0) or 0), e.agg_id),
    )


# ------------------------------------------------------------------- API
class RunIn(BaseModel):
    conversation_id: str
    agent_role: str
    item_id: str | None = None
    graph_node_id: str | None = None
    instruction: str | None = None
    wait: bool = False


def _run_detail(run: dict) -> dict:
    from apm.domains.conversations import get_conversation
    from apm.domains.items import get_item

    conv = get_conversation(run["conversation_id"]) or {}
    run["conversation_title"] = conv.get("title")
    run["feature_id"] = run.get("feature_id") or conv.get("feature_id")
    if run.get("output"):
        run["output"] = json.loads(run["output"])
    if run.get("item_id"):
        item = get_item(run["item_id"])
        run["item_title"] = item["title"] if item else None
    return run


@router.post("/runs")
def post_run(body: RunIn) -> dict:
    from apm.runtime.engine import start_run

    try:
        run = start_run(
            conversation_id=body.conversation_id,
            agent_role=body.agent_role,
            item_id=body.item_id,
            graph_node_id=body.graph_node_id,
            instruction=body.instruction,
            wait=body.wait,
        )
    except KeyError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail=str(e))
    return _run_detail(run)


@router.get("/projects/{project_id}/runs/report")
def runs_report(project_id: str) -> dict:
    """Run aggregation report (M29-I91, docs/01 §AB.3, Langfuse observability
    semantics as a pure projection slice): per-role and per-status rollups of
    runs, success rate, average duration, gate-pending (interrupted) rate and
    steps per run. Token/cost columns exist and are summed as-is — the replay
    provider records zeros, so the numbers stay honest until a real provider
    fills them."""
    from apm.domains.projects import require_project

    require_project(project_id)
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT agent_role, status, started_at, ended_at, total_input_tokens,"
        " total_output_tokens, estimated_cost_usd FROM runs WHERE project_id = ?",
        (project_id,),
    ).fetchall()
    total = len(rows)
    by_status: dict[str, int] = {}
    by_role: dict[str, dict] = {}
    durations: list[float] = []
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        role = by_role.setdefault(r["agent_role"] or "unknown",
                                  {"agent_role": r["agent_role"] or "unknown",
                                   "runs": 0, "succeeded": 0, "failed": 0})
        role["runs"] += 1
        if r["status"] == "succeeded":
            role["succeeded"] += 1
        elif r["status"] == "failed":
            role["failed"] += 1
        if r["status"] in ("succeeded", "failed") and r["started_at"] and r["ended_at"]:
            try:
                from datetime import datetime
                delta = (datetime.fromisoformat(r["ended_at"])
                         - datetime.fromisoformat(r["started_at"])).total_seconds()
                durations.append(max(delta, 0))
            except ValueError:
                pass
    finished = by_status.get("succeeded", 0) + by_status.get("failed", 0)
    role_rows = []
    for role in by_role.values():
        decided = role["succeeded"] + role["failed"]
        role["success_rate"] = round(role["succeeded"] / decided, 2) if decided else None
        role_rows.append(role)
    role_rows.sort(key=lambda x: -x["runs"])
    steps = conn.execute(
        "SELECT COUNT(*) AS span_count, COUNT(DISTINCT run_id) AS run_count"
        " FROM spans s JOIN runs r ON r.id = s.run_id WHERE r.project_id = ?",
        (project_id,),
    ).fetchone()
    tokens = conn.execute(
        "SELECT COALESCE(SUM(total_input_tokens), 0) AS inp,"
        " COALESCE(SUM(total_output_tokens), 0) AS outp,"
        " COALESCE(SUM(estimated_cost_usd), 0) AS cost"
        " FROM runs WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    return {
        "total": total,
        "by_status": by_status,
        "success_rate": round(by_status.get("succeeded", 0) / finished, 2) if finished else None,
        "avg_duration_seconds": round(sum(durations) / len(durations), 1) if durations else None,
        "gate_pending_rate": round(by_status.get("interrupted", 0) / total, 2) if total else None,
        "avg_steps_per_run": round(steps["span_count"] / steps["run_count"], 1)
        if steps["run_count"] else None,
        "by_role": role_rows,
        "tokens": {"input": tokens["inp"], "output": tokens["outp"],
                   "estimated_cost_usd": tokens["cost"]},
    }


@router.get("/runs")
def list_runs(
    project_id: str | None = None,
    conversation_id: str | None = None,
    item_id: str | None = None,
    status: str | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    where, params = ["1=1"], []
    if project_id:
        where.append("project_id = ?")
        params.append(project_id)
    if conversation_id:
        where.append("conversation_id = ?")
        params.append(conversation_id)
    if item_id:
        where.append("item_id = ?")
        params.append(item_id)
    if status:
        where.append("status = ?")
        params.append(status)
    rows = db.get_conn().execute(
        f"SELECT * FROM runs WHERE {' AND '.join(where)} ORDER BY started_at DESC LIMIT ?",
        params + [limit],
    ).fetchall()
    return {"runs": [_run_detail(dict(r)) for r in rows]}


@router.get("/runs/{run_id}")
def get_run_detail(run_id: str) -> dict:
    from apm.runtime.engine import require_run

    return _run_detail(require_run(run_id))


@router.get("/runs/{run_id}/spans")
def get_run_spans(run_id: str) -> dict:
    from apm.runtime.engine import require_run
    from apm.runtime.spans import list_spans

    require_run(run_id)
    return {"spans": list_spans(run_id)}


@router.get("/runs/{run_id}/timeline")
def get_run_timeline(run_id: str) -> dict:
    """Human-machine interleaved timeline (docs/05 §3.3)."""
    from apm.runtime.engine import require_run
    from apm.runtime.spans import list_spans

    run = require_run(run_id)
    conv_id = run["conversation_id"]
    entries = []
    for s in list_spans(run_id):
        entries.append(
            {
                "ts": s["ts_start"],
                "actor_type": (s["attributes"] or {}).get("apm.actor_type", "agent"),
                "kind": "span",
                "span_kind": s["span_kind"],
                "name": s["name"],
                "status": s["status"],
                "run_id": run_id,
            }
        )
    evts, _ = events.query_events(project_id=run["project_id"], limit=1000)
    for e in evts:
        relevant = (
            (e.agg_type == "run" and e.agg_id == run_id)
            or (e.event_type.startswith("approval.") and e.payload.get("run_id") == run_id)
            or (e.event_type == "message.created" and e.payload.get("conversation_id") == conv_id)
            or (e.event_type.startswith("conversation.") and e.agg_id == conv_id)
        )
        if relevant:
            entries.append(
                {
                    "ts": e.ts,
                    "actor_type": e.actor_type,
                    "kind": "event",
                    "event_type": e.event_type,
                    "summary": _event_summary(e),
                    "run_id": run_id,
                }
            )
    entries.sort(key=lambda x: x["ts"])
    return {"run_id": run_id, "entries": entries}


def _event_summary(e) -> str:
    p = e.payload
    t = e.event_type
    if t == "message.created":
        return f"{p.get('role')}: {str(p.get('content'))[:80]}"
    if t.startswith("approval."):
        snap = p.get("snapshot") or {}
        return f"{t} {snap.get('gate') or snap.get('tool') or ''}".strip()
    if t.startswith("run."):
        return t
    if t.startswith("conversation."):
        return f"{t} {p.get('status') or ''}".strip()
    return t


@router.post("/runs/{run_id}/retry")
def retry_run(run_id: str) -> dict:
    from apm.runtime.engine import require_run, start_run

    run = require_run(run_id)
    events.emit(
        event_type="run.retried_from_checkpoint",
        agg_type="run",
        agg_id=run_id,
        project_id=run["project_id"] or "",
        payload={"original": run_id},
    )
    new = start_run(
        conversation_id=run["conversation_id"],
        agent_role=run["agent_role"] or "dev-agent",
        item_id=run.get("item_id"),
        graph_node_id=run.get("graph_node_id"),
        instruction=run.get("input"),
    )
    return {"original": run_id, "new_run": _run_detail(new)}


def _run_ring_scalars(run: dict) -> dict:
    """M64-I192: one link of the retry lineage — scalar comparison surface
    (the "what changed" answer; artifact bodies stay on the trajectory page)."""
    from apm.core.db import get_conn

    conn = get_conn()
    spans_n = conn.execute("SELECT COUNT(*) AS n FROM spans WHERE run_id = ?",
                           (run["id"],)).fetchone()["n"]
    duration = None
    if run.get("started_at") and run.get("ended_at"):
        from datetime import datetime

        try:
            t0 = datetime.fromisoformat(run["started_at"])
            t1 = datetime.fromisoformat(run["ended_at"])
            duration = round((t1 - t0).total_seconds(), 1)
        except ValueError:
            pass
    out = run.get("output")
    artifact = None
    if isinstance(out, str):
        try:
            out = json.loads(out)
        except ValueError:
            out = None
    if isinstance(out, dict):
        artifact = out.get("artifact") or out.get("artifact_path")
    return {
        "run_id": run["id"],
        "status": run["status"],
        "started_at": run.get("started_at"),
        "ended_at": run.get("ended_at"),
        "duration_s": duration,
        "steps": spans_n,
        "input_tokens": run.get("total_input_tokens") or 0,
        "output_tokens": run.get("total_output_tokens") or 0,
        "estimated_cost_usd": run.get("estimated_cost_usd") or 0,
        "artifact": artifact,
    }


@router.get("/runs/{run_id}/retry-lineage")
def retry_lineage(run_id: str, tree: int = 0) -> dict:
    """M64-I192 (docs/01 §BI.1): the retry chain, visualized — LangGraph
    deterministic-resume vs OpenHands independent-rollout consensus is that a
    retry's value is "what changed vs last time", so the chain walks
    run.retried_from_checkpoint.original links and returns per-link scalars
    (event-sourcing dividend #15: the chain facts are already in the stream).
    Read-only projection; the frontend diffs adjacent links."""
    conn = db.get_conn()
    chain_ids: list[str] = [run_id]
    seen = {run_id}
    # walk backwards: each retried link stores original=<predecessor>
    cursor = run_id
    while True:
        row = conn.execute(
            "SELECT payload FROM events WHERE event_type = 'run.retried_from_checkpoint'"
            " AND agg_id = ? ORDER BY id DESC LIMIT 1", (cursor,)).fetchone()
        if row is None:
            break
        prev = json.loads(row["payload"]).get("original")
        if not prev or prev in seen:
            break
        chain_ids.append(prev)
        seen.add(prev)
        cursor = prev
    chain_ids.reverse()  # oldest first

    links = []
    for rid in chain_ids:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (rid,)).fetchone()
        if row is None:
            continue
        links.append(_run_ring_scalars(dict(row)))
    if not links:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"run {run_id} not found")

    # M65-I195: tree awareness — walk both lineage edges (retry + fork) so a
    # branching history reads as a tree; default response keeps the linear
    # retry chain (M64 semantics unchanged).
    branches: list[dict] = []
    if tree:
        root = chain_ids[-1] if chain_ids else run_id
        edges = conn.execute(
            "SELECT event_type, agg_id, payload FROM events"
            " WHERE event_type IN ('run.retried_from_checkpoint','run.forked')"
            " ORDER BY id ASC").fetchall()
        parent_of: dict[str, str] = {}
        kinds: dict[str, str] = {}
        for e in edges:
            child = e["agg_id"]
            payload = json.loads(e["payload"])
            parent = payload.get("original") or payload.get("forked_from")
            if parent and child not in parent_of:
                parent_of[child] = parent
                kinds[child] = "fork" if e["event_type"] == "run.forked" else "retry"

        def _walk(node: str, depth: int, via: str | None) -> None:
            r = conn.execute("SELECT * FROM runs WHERE id = ?", (node,)).fetchone()
            if r is None:
                return
            branches.append({**_run_ring_scalars(dict(r)), "depth": depth, "via": via})
            for child, parent in parent_of.items():
                if parent == node:
                    _walk(child, depth + 1, kinds.get(child))

        _walk(root, 0, None)

    return {"run_id": run_id, "chain": links,
            "length": len(links), "retried": len(links) > 1,
            **({"tree": branches} if tree else {})}


class ForkIn(BaseModel):
    # M65-I195: optional correction brief for the forked branch (≤500 chars)
    instruction: str | None = None


@router.post("/runs/{run_id}/fork")
def fork_run(run_id: str, body: ForkIn) -> dict:
    """Branch a new run off an existing one (M65-I195, docs/01 §BJ.1 — the Git
    branch metaphor for runs: keep the mainline, run the experiment on a
    branch). The forked run inherits conversation/item/role/instruction from
    the source, carries `forked_from` lineage, and leaves the source run and
    its retry chain untouched. Unlike LangGraph's update_state this does NOT
    expose checkpoint state editing — Gate approvals remain the human-in-the-
    loop edit point."""
    from apm.core.ids import new_id
    from apm.runtime.engine import require_run, start_run

    src = require_run(run_id)
    if body.instruction and len(body.instruction) > 500:
        raise HTTPException(status_code=422, detail="instruction must be ≤500 chars")
    fork_id = new_id("r")
    events.emit(
        event_type="run.forked",
        agg_type="run",
        agg_id=fork_id,
        project_id=src["project_id"] or "",
        payload={"forked_from": run_id},
    )
    new = start_run(
        conversation_id=src["conversation_id"],
        agent_role=src["agent_role"] or "dev-agent",
        item_id=src.get("item_id"),
        graph_node_id=src.get("graph_node_id"),
        instruction=body.instruction or src.get("input"),
        run_id=fork_id,
    )
    return {"forked_from": run_id, "new_run": _run_detail(new)}
