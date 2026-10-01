"""System endpoints: health, projection rebuild, real-LLM status/ping."""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException

from apm import config

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    from apm.version import APP_VERSION

    return {
        "status": "ok",
        "app": "AgentPM",
        "version": APP_VERSION,  # M81-I243: 单源（原 0.1.0 死字面量）
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


@router.get("/system/event-store-stats")
def event_store_stats() -> dict:
    """M61-I183 (docs/01 §BF.1, 'measure first, then treat'): the event log
    grows forever by design (§K.3: archive = export, never delete — any prune
    breaks live==replay), so the governance baseline is pure observation: how
    big, what types are growing, how old the oldest event is. Read-only, no
    new mechanisms; if treatment is ever needed it composes existing export +
    backup tools."""
    from apm.core import db, events
    from apm.domains.members import is_instance_admin

    if not is_instance_admin(events.effective_actor()):
        raise HTTPException(status_code=403, detail="admin role required for event store stats")
    conn = db.get_conn()
    total = conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
    page_count = conn.execute("PRAGMA page_count").fetchone()[0]
    page_size = conn.execute("PRAGMA page_size").fetchone()[0]
    row = conn.execute("SELECT MIN(ts) AS oldest, MAX(ts) AS newest FROM events").fetchone()
    distribution = [
        {"agg_type": r["agg_type"], "event_type": r["event_type"], "count": r["n"]}
        for r in conn.execute(
            "SELECT agg_type, event_type, COUNT(*) AS n FROM events"
            " GROUP BY agg_type, event_type ORDER BY n DESC, event_type"
        ).fetchall()
    ]
    return {
        "total_events": total,
        "db_bytes": page_count * page_size,
        "oldest_ts": row["oldest"],
        "newest_ts": row["newest"],
        "distribution": distribution,
    }


@router.get("/system/slow-endpoints")
def slow_endpoints() -> dict:
    """M62-I186 (docs/01 §BG.1): in-memory latency view — per-route
    count/mean/max ordered by max, plus the bounded slow-sample ring. The
    middleware (main.perf_gate) does the accounting; this is a pure read with
    the same admin gate as the other system surfaces."""
    from apm.core import events
    from apm.domains.members import is_instance_admin
    from apm.runtime import perf

    if not is_instance_admin(events.effective_actor()):
        raise HTTPException(status_code=403, detail="admin role required for slow endpoints")
    return perf.snapshot()


# M67-I203 (docs/01 §BL.3): Prometheus scrape door — a hand-rolled text
# exposition (format 0.0.4, zero dependencies; prometheus_client is a no for
# this). Sources are the in-process telemetry the app already keeps: the M62
# perf ring becomes a latency histogram, the event ledger a per-type counter
# (红利十六：账本已在流中，出站只是读侧), plus two honest gauges. No built-in
# auth — config-gated and meant to sit behind a reverse proxy / loopback.
@router.get("/system/metrics")
def metrics() -> Response:
    if not config.settings.metrics_enabled:
        raise HTTPException(status_code=404, detail="metrics disabled (APM_METRICS_ENABLED)")
    from apm.core import db
    from apm.runtime import perf

    lines: list[str] = []

    # --- latency histogram (global; label cardinality stays flat) -----------
    h = perf.histogram()
    seconds = 1000.0
    lines.append("# HELP apm_http_request_duration_seconds HTTP request latency.")
    lines.append("# TYPE apm_http_request_duration_seconds histogram")
    for ub_ms, n in h["buckets"].items():
        le = "+Inf" if ub_ms == "+Inf" else f"{float(ub_ms) / seconds:g}"
        lines.append(f'apm_http_request_duration_seconds_bucket{{le="{le}"}} {n}')
    lines.append(f"apm_http_request_duration_seconds_count {h['count']}")
    lines.append(f"apm_http_request_duration_seconds_sum {h['total_ms'] / seconds:.6f}")

    # --- per-route request counter (bounded by the app's own route count) ---
    lines.append("# HELP apm_http_requests_total Requests accounted by route.")
    lines.append("# TYPE apm_http_requests_total counter")
    for route, n in sorted(h["per_route"].items()):
        lines.append(f'apm_http_requests_total{{route="{route}"}} {n}')

    # --- event ledger counter (low cardinality: agg_type × event_type) ------
    lines.append("# HELP apm_events_total Domain events in the append-only ledger.")
    lines.append("# TYPE apm_events_total counter")
    rows = db.get_conn().execute(
        "SELECT agg_type, event_type, COUNT(*) AS n FROM events"
        " GROUP BY agg_type, event_type ORDER BY agg_type, event_type").fetchall()
    for r in rows:
        lines.append(f'apm_events_total{{agg_type="{r["agg_type"]}",'
                     f'event_type="{r["event_type"]}"}} {r["n"]}')

    # --- gauges -------------------------------------------------------------
    running = db.get_conn().execute(
        "SELECT COUNT(*) AS n FROM runs WHERE status = 'running'").fetchone()["n"]
    pages = db.get_conn().execute("PRAGMA page_count").fetchone()[0]
    page_size = db.get_conn().execute("PRAGMA page_size").fetchone()[0]
    lines.append("# HELP apm_runs_active Runs currently in the running state.")
    lines.append("# TYPE apm_runs_active gauge")
    lines.append(f"apm_runs_active {running}")
    lines.append("# HELP apm_db_bytes SQLite database size (page_count × page_size).")
    lines.append("# TYPE apm_db_bytes gauge")
    lines.append(f"apm_db_bytes {pages * page_size}")

    from fastapi import Response

    return Response(content="\n".join(lines) + "\n",
                    media_type="text/plain; version=0.0.4; charset=utf-8")
