"""M29-I91 (docs/01 §AB.3): run aggregation report — Langfuse-style rollups
(per-status/per-role success rate, avg duration, gate-pending rate, steps per
run) as a pure projection; token/cost sums stay honest (zeros under replay).
Data is emitted as real run.* events; engine behavior itself is covered by
test_runtime."""
from __future__ import annotations

import pytest

from apm.core import events, projections


def _emit_run(pid: str, rid: str, role: str, conv: str, flow: str):
    events.emit(event_type="run.requested", agg_type="run", agg_id=rid,
                project_id=pid,
                payload={"conversation_id": conv, "agent_role": role})
    if flow == "success":
        events.emit(event_type="run.started", agg_type="run", agg_id=rid, project_id=pid, payload={})
        events.emit(event_type="run.succeeded", agg_type="run", agg_id=rid, project_id=pid,
                    payload={"output": {}})
    elif flow == "gate":
        events.emit(event_type="run.started", agg_type="run", agg_id=rid, project_id=pid, payload={})
        events.emit(event_type="run.interrupted", agg_type="run", agg_id=rid, project_id=pid, payload={})
    elif flow == "fail":
        events.emit(event_type="run.started", agg_type="run", agg_id=rid, project_id=pid, payload={})
        events.emit(event_type="run.failed", agg_type="run", agg_id=rid, project_id=pid,
                    payload={"error": "boom"})


def test_runs_report_aggregates(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "运行报表", "ontology": "software-dev", "requirement": "I91"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    _emit_run(pid, "run_a", "dev-agent", "conv-a", "success")
    _emit_run(pid, "run_b", "dev-agent", "conv-b", "gate")
    _emit_run(pid, "run_c", "qa-agent", "conv-c", "fail")
    # two spans on the one finished run → steps-per-run denominator is real
    for i, sid in enumerate(("sp_a1", "sp_a2")):
        events.emit(event_type="run.span_closed", agg_type="span", agg_id=sid,
                    project_id=pid,
                    payload={"run_id": "run_a", "span_kind": "tool", "name": f"step{i}"})

    rep = client.get(f"/api/projects/{pid}/runs/report").json()
    assert rep["total"] == 3
    assert rep["by_status"]["succeeded"] == 1
    assert rep["by_status"]["failed"] == 1
    assert rep["by_status"]["interrupted"] == 1
    assert rep["success_rate"] == 0.5                    # 1 of (1 succeeded + 1 failed)
    assert rep["gate_pending_rate"] == round(1 / 3, 2)   # interrupted / total
    roles = {x["agent_role"]: x for x in rep["by_role"]}
    assert roles["dev-agent"]["runs"] == 2 and roles["dev-agent"]["success_rate"] == 1.0
    assert roles["qa-agent"]["success_rate"] == 0.0
    assert rep["avg_steps_per_run"] == 2.0               # 2 spans / 1 run with spans
    assert rep["tokens"] == {"input": 0, "output": 0, "estimated_cost_usd": 0}  # honest zeros

    # pure projection: identical after rebuild
    projections.rebuild()
    assert client.get(f"/api/projects/{pid}/runs/report").json() == rep


def test_runs_report_empty(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "运行报表空", "ontology": "software-dev", "requirement": "I91"})
    pid = r.json()["id"]
    rep = client.get(f"/api/projects/{pid}/runs/report").json()
    assert rep["total"] == 0 and rep["success_rate"] is None
    assert rep["avg_steps_per_run"] is None and rep["gate_pending_rate"] is None
    assert rep["tokens"]["input"] == 0
