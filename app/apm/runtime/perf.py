"""Endpoint latency observation (M62-I186, docs/01 §BG.1): the latency half
of "measure first, then treat" — sister of event-store size stats (M61-I183).
Telemetry lives in process memory ONLY (per-route ring buckets + a bounded
deque of slow samples): runtime metrics are not domain facts, so they never
enter the event stream — same ruling as the transient token_delta broadcast
(M46-I138). No new tables, no exporter; if treatment is ever needed it
composes the existing logs + this view."""
from __future__ import annotations

import threading
import time
from collections import deque

_LOCK = threading.Lock()
SLOW_THRESHOLD_MS = 500.0          # dev default; admin can read it back
_MAX_SLOW_SAMPLES = 50
_buckets: dict[str, dict] = {}     # route -> {count, total_ms, max_ms}
_slow: deque = deque(maxlen=_MAX_SLOW_SAMPLES)


def record(route: str, method: str, status: int, ms: float) -> None:
    """Account one request. Never raises into the request path."""
    try:
        with _LOCK:
            b = _buckets.get(route)
            if b is None:
                b = _buckets[route] = {"count": 0, "total_ms": 0.0, "max_ms": 0.0}
            b["count"] += 1
            b["total_ms"] += ms
            b["max_ms"] = max(b["max_ms"], ms)
            if ms >= SLOW_THRESHOLD_MS:
                _slow.appendleft({
                    "path": route, "method": method, "status": status,
                    "ms": round(ms, 1), "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                })
    except Exception:  # telemetry must never break the request it measures
        pass


def snapshot() -> dict:
    """Read-side view for /system/slow-endpoints (admin gate lives at the
    endpoint): per-route count/mean/max ordered by max desc, plus the bounded
    slow-sample ring."""
    with _LOCK:
        endpoints = [
            {
                "path": path,
                "count": b["count"],
                "mean_ms": round(b["total_ms"] / b["count"], 1) if b["count"] else 0.0,
                "max_ms": round(b["max_ms"], 1),
            }
            for path, b in _buckets.items()
        ]
        samples = [dict(s) for s in _slow]
    endpoints.sort(key=lambda e: (-e["max_ms"], -e["count"], e["path"]))
    return {
        "threshold_ms": SLOW_THRESHOLD_MS,
        "endpoints": endpoints,
        "slow_samples": samples,
    }


def reset() -> None:
    """Test hook: fresh observation state."""
    with _LOCK:
        _buckets.clear()
        _slow.clear()
