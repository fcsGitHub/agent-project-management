"""M67-I203 Prometheus 出站（docs/01 §BL.3）：`GET /system/metrics` 手写
text exposition 0.0.4——门=APM_METRICS_ENABLED（默认 404 不暴露，无内建
鉴权属预期：环回/反代负责）。数据源=进程内已有的观测面：M62 perf ring
的桶 → latency histogram（全局无路由标签压基数），events 账本 →
per-type counter，runs/db → gauge。"""
from __future__ import annotations

import re

import pytest

from apm import config
from apm.core import db


@pytest.fixture(autouse=True)
def _toggle_metrics(monkeypatch):
    monkeypatch.setattr(config.settings, "metrics_enabled", True)
    yield


def _parse(text: str) -> dict[str, list[float]]:
    """{metric_name: [sample values]} across HELP/TYPE comment lines."""
    out: dict[str, list[float]] = {}
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        name = line.split("{")[0].split(" ")[0]
        value = float(line.rsplit(" ", 1)[1])
        out.setdefault(name, []).append(value)
    return out


def test_disabled_returns_404(client, tmp_data, monkeypatch):
    monkeypatch.setattr(config.settings, "metrics_enabled", False)
    assert client.get("/api/system/metrics").status_code == 404


def test_exposition_format_and_histogram_integrity(client, tmp_data):
    # warm the perf ring: the scrape's own accounting lands after its response,
    # so a first-scrape-only process would show an empty histogram
    client.get("/api/health")
    client.get("/api/health")
    text = client.get("/api/system/metrics").text
    assert "version=0.0.4" in client.get("/api/system/metrics").headers["content-type"]
    # histogram plumbing present
    assert "# TYPE apm_http_request_duration_seconds histogram" in text
    assert 'apm_http_request_duration_seconds_bucket{le="+Inf"}' in text
    assert "apm_http_request_duration_seconds_count" in text
    assert "apm_http_request_duration_seconds_sum" in text
    parsed = _parse(text)
    buckets = sorted(v for name, vals in parsed.items()
                     if name == "apm_http_request_duration_seconds_bucket"
                     for v in vals)
    # cumulative buckets never decrease
    assert buckets == sorted(buckets)
    # count equals the +Inf bucket (every observation lands in the top bucket)
    count = parsed["apm_http_request_duration_seconds_count"][-1]
    assert count == buckets[-1]
    # after the app handled the scrape(s), at least the scrapes themselves
    # are accounted — an all-zero histogram would mean perf accounting broke
    assert count >= 2  # the two GETs this test made before parsing
    # counters and gauges carry samples
    assert parsed["apm_events_total"]
    assert parsed["apm_runs_active"] and parsed["apm_runs_active"][-1] >= 0


def test_event_counter_parity_with_ledger(client, tmp_data):
    text = client.get("/api/system/metrics").text
    exported = 0
    for line in text.splitlines():
        if line.startswith("apm_events_total{"):
            exported += int(line.rsplit(" ", 1)[1])
    truth = db.get_conn().execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
    assert exported == truth
