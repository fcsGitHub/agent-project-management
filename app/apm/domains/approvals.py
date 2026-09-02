"""Approval domain: gate + dangerous-tool approvals, fail-closed, one-shot auth.

Gate approvals come from graph interrupts; tool approvals from the tool layer.
Both share the approvals table, the decision API and the audit trail
(docs/05 §2).
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apm import config
from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on

router = APIRouter(tags=["approvals"])


# ------------------------------------------------------------ projections
def _insert_approval(conn, e):
    p = e.payload
    conn.execute(
        "INSERT INTO approvals (id, project_id, run_id, item_id, conversation_id, kind,"
        " payload_snapshot, status, requested_at) VALUES (?,?,?,?,?,?,?,?,?)"
        " ON CONFLICT(id) DO UPDATE SET payload_snapshot = excluded.payload_snapshot,"
        " requested_at = excluded.requested_at",
        (
            e.agg_id,
            e.project_id or None,
            p.get("run_id"),
            p.get("item_id"),
            p.get("conversation_id"),
            p.get("kind", "gate"),
            json.dumps(p.get("snapshot", {}), ensure_ascii=False),
            "pending",
            e.ts,
        ),
    )


@on("approval.requested")
def _proj_approval_requested(conn, e):
    _insert_approval(conn, e)


@on("approval.granted")
def _proj_approval_granted(conn, e):
    conn.execute(
        "UPDATE approvals SET status = 'approved', decided_at = ?, reviewer_id = ?, comment = ?"
        " WHERE id = ?",
        (e.ts, e.actor_id, e.payload.get("comment"), e.agg_id),
    )


@on("approval.rejected")
def _proj_approval_rejected(conn, e):
    conn.execute(
        "UPDATE approvals SET status = 'rejected', decided_at = ?, reviewer_id = ?, comment = ?"
        " WHERE id = ?",
        (e.ts, e.actor_id, e.payload.get("comment"), e.agg_id),
    )


@on("approval.resumed_with_edit")
def _proj_approval_edit(conn, e):
    conn.execute(
        "UPDATE approvals SET status = 'pending', comment = ?, payload_snapshot = ? WHERE id = ?",
        (e.payload.get("comment"), json.dumps(e.payload.get("snapshot", {}), ensure_ascii=False), e.agg_id),
    )


@on("approval.auto_granted")
def _proj_approval_auto(conn, e):
    conn.execute(
        "UPDATE approvals SET status = 'auto_approved', decided_at = ?, reviewer_id = ? WHERE id = ?",
        (e.ts, f"policy:{e.payload.get('rule', 'unknown')}", e.agg_id),
    )


# ---------------------------------------------------------------- helpers
def get_approval(approval_id: str) -> dict | None:
    row = db.get_conn().execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["payload_snapshot"] = json.loads(d["payload_snapshot"] or "{}")
    return d


def require_approval(approval_id: str) -> dict:
    a = get_approval(approval_id)
    if not a:
        raise HTTPException(status_code=404, detail=f"approval {approval_id} not found")
    return a


def _request(
    *,
    kind: str,
    snapshot: dict,
    project_id: str = "",
    run_id: str | None = None,
    item_id: str | None = None,
    conversation_id: str | None = None,
    approval_id: str | None = None,
) -> dict:
    aid = approval_id or new_id("apr")
    events.emit(
        event_type="approval.requested",
        agg_type="approval",
        agg_id=aid,
        project_id=project_id,
        actor_type="system",
        actor_id=f"runtime:{run_id}" if run_id else "system",
        payload={
            "kind": kind,
            "run_id": run_id,
            "item_id": item_id,
            "conversation_id": conversation_id,
            "snapshot": snapshot,
        },
    )
    return get_approval(aid)  # type: ignore[return-value]


def request_gate_approval(
    *,
    run_id: str,
    project_id: str,
    conversation_id: str,
    item_id: str | None,
    gate: str,
    role_id: str,
    artifact_path: str,
    artifact_commit: str,
    summary: str,
) -> dict:
    """Idempotent per (run, gate): re-executions after resume reuse the row."""
    row = db.get_conn().execute(
        "SELECT id FROM approvals WHERE run_id = ? AND kind = 'gate'"
        " AND json_extract(payload_snapshot, '$.gate') = ? ORDER BY requested_at DESC LIMIT 1",
        (run_id, gate),
    ).fetchone()
    if row:
        return get_approval(row["id"])  # type: ignore[return-value]
    snapshot = {
        "gate": gate,
        "role": role_id,
        "artifact": {"path": artifact_path, "commit": artifact_commit},
        "summary": summary,
    }
    return _request(
        kind="gate",
        snapshot=snapshot,
        project_id=project_id,
        run_id=run_id,
        item_id=item_id,
        conversation_id=conversation_id,
    )


def request_tool_approval(
    *, run_id: str, project_id: str, conversation_id: str | None, tool: str,
    args: dict, call_hash: str,
) -> dict:
    snapshot = {
        "tool": tool,
        "args": args,
        "call_hash": call_hash,
        "summary": f"危险工具调用：{tool}",
    }
    return _request(
        kind="tool",
        snapshot=snapshot,
        project_id=project_id,
        run_id=run_id,
        conversation_id=conversation_id,
    )


def update_approval_snapshot(
    approval_id: str, *, artifact_path: str, artifact_commit: str, note: str | None
) -> None:
    approval = get_approval(approval_id)
    if not approval:
        return
    snapshot = approval["payload_snapshot"]
    snapshot["artifact"] = {"path": artifact_path, "commit": artifact_commit}
    if note:
        snapshot["revise_notes"] = (snapshot.get("revise_notes") or []) + [note]
    events.emit(
        event_type="approval.requested",  # re-request refreshes the snapshot
        agg_type="approval",
        agg_id=approval_id,
        project_id=approval["project_id"] or "",
        actor_type="system",
        actor_id=f"runtime:{approval['run_id']}" if approval["run_id"] else "system",
        payload={
            "kind": approval["kind"],
            "run_id": approval["run_id"],
            "item_id": approval["item_id"],
            "conversation_id": approval["conversation_id"],
            "snapshot": snapshot,
        },
    )


def find_pending_for_run(run_id: str) -> dict | None:
    row = db.get_conn().execute(
        "SELECT id FROM approvals WHERE run_id = ? AND status = 'pending'"
        " ORDER BY requested_at DESC LIMIT 1",
        (run_id,),
    ).fetchone()
    return get_approval(row["id"]) if row else None


def refresh_pending_snapshot_for_run(run_id: str, *, artifact_path: str, artifact_commit: str) -> None:
    approval = find_pending_for_run(run_id)
    if not approval or approval["kind"] != "gate":
        return
    update_approval_snapshot(approval["id"], artifact_path=artifact_path,
                             artifact_commit=artifact_commit, note=None)


# ---------------------------------------------------------------- decisions
class DecisionIn(BaseModel):
    decision: str  # approved | rejected | edit_and_resume
    comment: str | None = None


class BulkIn(BaseModel):
    ids: list[str]
    decision: str = "approved"
    comment: str | None = None


def _resume_engine_for_approval(approval: dict, decision: dict) -> None:
    from apm.runtime.engine import _get_or_rebuild_engine

    run_id = approval["run_id"]
    if not run_id:
        return
    engine = _get_or_rebuild_engine(run_id)
    if approval["kind"] == "tool" and decision.get("decision") == "approved":
        call_hash = approval["payload_snapshot"].get("call_hash")
        if call_hash:
            engine.tool_ctx.authorized_calls.add(call_hash)
    engine.resume(decision)


def decide(approval_id: str, body: DecisionIn) -> dict:
    approval = require_approval(approval_id)
    if approval["status"] != "pending":
        raise HTTPException(status_code=422, detail=f"approval already {approval['status']}")
    if body.decision not in ("approved", "rejected", "edit_and_resume"):
        raise HTTPException(status_code=422, detail="decision must be approved|rejected|edit_and_resume")
    if body.decision == "rejected" and not (body.comment or "").strip():
        raise HTTPException(status_code=422, detail="rejection requires a comment (fail-closed)")
    reviewer = config.settings.user_id

    from apm.runtime import spans

    if body.decision == "approved":
        events.emit(
            event_type="approval.granted",
            agg_type="approval",
            agg_id=approval_id,
            project_id=approval["project_id"] or "",
            payload={"comment": body.comment, "run_id": approval["run_id"],
                     "kind": approval["kind"]},
        )
        spans.record_human_action(
            project_id=approval["project_id"] or "",
            name=f"approval.granted:{approval_id}",
            io={"comment": body.comment},
            conversation_id=approval["conversation_id"],
        )
        try:  # asset_review gates publish the asset on grant
            from apm.domains.assets import publish_from_approval

            publish_from_approval(get_approval(approval_id) or {})
        except ImportError:
            pass
        _resume_engine_for_approval(approval, {"decision": "approved", "comment": body.comment})
    elif body.decision == "rejected":
        events.emit(
            event_type="approval.rejected",
            agg_type="approval",
            agg_id=approval_id,
            project_id=approval["project_id"] or "",
            payload={"comment": body.comment, "run_id": approval["run_id"],
                     "kind": approval["kind"]},
        )
        spans.record_human_action(
            project_id=approval["project_id"] or "",
            name=f"approval.rejected:{approval_id}",
            io={"comment": body.comment},
            conversation_id=approval["conversation_id"],
        )
        _resume_engine_for_approval(approval, {"decision": "rejected", "comment": body.comment})
    else:  # edit_and_resume
        snapshot = approval["payload_snapshot"]
        snapshot["edit_note"] = body.comment
        events.emit(
            event_type="approval.resumed_with_edit",
            agg_type="approval",
            agg_id=approval_id,
            project_id=approval["project_id"] or "",
            payload={"comment": body.comment, "snapshot": snapshot, "run_id": approval["run_id"]},
        )
        spans.record_human_action(
            project_id=approval["project_id"] or "",
            name=f"approval.edit_and_resume:{approval_id}",
            io={"comment": body.comment},
            conversation_id=approval["conversation_id"],
        )
        _resume_engine_for_approval(approval, {"decision": "revise", "note": body.comment})
    return get_approval(approval_id)  # type: ignore[return-value]


@router.get("/approvals")
def list_approvals(
    status: str | None = None,
    project_id: str | None = None,
    kind: str | None = None,
    decided_by: str | None = None,
    limit: int = 100,
) -> dict:
    where, params = ["1=1"], []
    if status:
        where.append("status = ?")
        params.append(status)
    if project_id:
        where.append("project_id = ?")
        params.append(project_id)
    if kind:
        where.append("kind = ?")
        params.append(kind)
    if decided_by:  # M5-I19: 审批按决策人过滤
        where.append("reviewer_id = ?")
        params.append(decided_by)
    rows = db.get_conn().execute(
        f"SELECT * FROM approvals WHERE {' AND '.join(where)} ORDER BY requested_at DESC LIMIT ?",
        params + [limit],
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["payload_snapshot"] = json.loads(d["payload_snapshot"] or "{}")
        out.append(d)
    return {"approvals": out}


@router.post("/approvals/{approval_id}/decision")
def post_decision(approval_id: str, body: DecisionIn) -> dict:
    return decide(approval_id, body)


@router.post("/approvals/bulk-decision")
def post_bulk_decision(body: BulkIn) -> dict:
    results = []
    for aid in body.ids:
        try:
            results.append(decide(aid, DecisionIn(decision=body.decision, comment=body.comment)))
        except HTTPException as e:
            results.append({"id": aid, "error": e.detail})
    return {"results": results}
