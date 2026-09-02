"""Span recording: OTel GenAI-aligned trajectories with apm.* extensions."""
from __future__ import annotations

import json
from typing import Any

from apm.core import db, events
from apm.core.ids import new_id
from apm.core.projections import on

REDACT_PATTERNS = ("sk-", "api_key", "password", "token=")


def redact(value: Any) -> Any:
    s = json.dumps(value, ensure_ascii=False, default=str)
    lowered = s.lower()
    for pat in REDACT_PATTERNS:
        if pat in lowered:
            s = "***redacted***"
            break
    return json.loads(s) if s != "***redacted***" else s


@on("run.span_opened")
def _proj_span_opened(conn, e):
    p = e.payload
    conn.execute(
        "INSERT OR REPLACE INTO spans (id, run_id, parent_id, span_kind, name, ts_start, status,"
        " attributes, io) VALUES (?,?,?,?,?,?, 'running', ?, ?)",
        (e.agg_id, p["run_id"], p.get("parent_id"), p["span_kind"], p["name"], e.ts,
         json.dumps(p.get("attributes", {}), ensure_ascii=False), None),
    )


@on("run.span_closed")
def _proj_span_closed(conn, e):
    p = e.payload
    existing = conn.execute(
        "SELECT attributes, ts_start, span_kind, name, parent_id FROM spans WHERE id = ?",
        (e.agg_id,),
    ).fetchone()
    merged: dict = {}
    if existing and existing["attributes"]:
        merged.update(json.loads(existing["attributes"]))
    merged.update(p.get("attributes") or {})
    io = json.dumps(p.get("io"), ensure_ascii=False) if p.get("io") is not None else None
    if existing:
        conn.execute(
            "UPDATE spans SET ts_end = ?, status = ?, attributes = ?,"
            " io = COALESCE(?, io) WHERE id = ?",
            (e.ts, p.get("status", "ok"), json.dumps(merged, ensure_ascii=False), io, e.agg_id),
        )
    else:
        conn.execute(
            "INSERT INTO spans (id, run_id, parent_id, span_kind, name, ts_start, ts_end, status,"
            " attributes, io) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                e.agg_id,
                p["run_id"],
                p.get("parent_id"),
                p.get("span_kind", "chain"),
                p.get("name", e.agg_id),
                e.ts,
                e.ts,
                p.get("status", "ok"),
                json.dumps(merged, ensure_ascii=False),
                io,
            ),
        )


def open_span(
    *,
    run_id: str,
    project_id: str,
    span_kind: str,
    name: str,
    parent_id: str | None = None,
    attributes: dict[str, Any] | None = None,
    actor_type: str = "agent",
) -> str:
    sid = new_id("sp")
    attrs = dict(attributes or {})
    attrs.setdefault("apm.actor_type", actor_type)
    attrs.setdefault("apm.conversation_id", None)
    events.emit(
        event_type="run.span_opened",
        agg_type="span",
        agg_id=sid,
        project_id=project_id,
        actor_type=actor_type,
        actor_id=f"runtime:{run_id}",
        payload={"run_id": run_id, "parent_id": parent_id, "span_kind": span_kind,
                 "name": name, "attributes": redact(attrs)},
    )
    return sid


def close_span(
    *,
    span_id: str,
    run_id: str,
    project_id: str,
    status: str = "ok",
    io: dict[str, Any] | None = None,
    extra_attrs: dict[str, Any] | None = None,
    span_kind: str = "chain",
    name: str | None = None,
    parent_id: str | None = None,
    ts_start: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "run_id": run_id,
        "span_kind": span_kind,
        "name": name or span_id,
        "parent_id": parent_id,
        "status": status,
    }
    if extra_attrs:
        payload["attributes"] = extra_attrs
    if io is not None:
        payload["io"] = redact(io)
    events.emit(
        event_type="run.span_closed",
        agg_type="span",
        agg_id=span_id,
        project_id=project_id,
        actor_type="agent",
        actor_id=f"runtime:{run_id}",
        payload=payload,
    )


def list_spans(run_id: str) -> list[dict]:
    rows = db.get_conn().execute(
        "SELECT * FROM spans WHERE run_id = ? ORDER BY ts_start, id", (run_id,)
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["attributes"] = json.loads(d["attributes"] or "{}")
        d["io"] = json.loads(d["io"]) if d["io"] else None
        out.append(d)
    return out


def record_human_action(
    *,
    project_id: str,
    name: str,
    io: dict[str, Any] | None = None,
    conversation_id: str | None = None,
    actor_id: str | None = None,
) -> str:
    """Human actions get trajectory spans too (docs/04 §4)."""
    sid = new_id("sp")
    attrs = {"apm.actor_type": "human", "apm.conversation_id": conversation_id}
    close_span(
        span_id=sid,
        run_id="",
        project_id=project_id,
        status="ok",
        io=io,
        extra_attrs=attrs,
        span_kind="human_action",
        name=name,
    )
    return sid
