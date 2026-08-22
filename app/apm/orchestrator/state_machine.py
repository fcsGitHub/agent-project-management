"""Phase state machine: ontology phaseGraph drives project progression.

A phase is: pending (upstream gates not passed) / active / passed (its gate
approval granted). The same rules serve the Graph view badges and the
scheduler's continuation decisions.
"""
from __future__ import annotations

from apm.core import db


def approved_gates(project_id: str) -> set[str]:
    rows = db.get_conn().execute(
        "SELECT payload_snapshot FROM approvals WHERE project_id = ?"
        " AND status IN ('approved', 'auto_approved')",
        (project_id,),
    ).fetchall()
    import json

    gates = set()
    for r in rows:
        snap = json.loads(r["payload_snapshot"] or "{}")
        gate = snap.get("gate")
        if snap.get("kind", "gate") == "gate" and gate:
            gates.add(gate)
    return gates


def phase_statuses(project_id: str) -> list[dict]:
    from apm.domains.ontology import load_ontology
    from apm.domains.projects import require_project

    project = require_project(project_id)
    onto = load_ontology(project["ontology"])
    passed = approved_gates(project_id)
    statuses: list[dict] = []
    for p in onto.phases:
        gate = p.get("gate")
        gate_passed = gate is not None and gate in passed
        statuses.append(
            {
                "id": p["id"],
                "name": p.get("name", p["id"]),
                "gate": gate,
                "gate_label": onto.gate_label(gate) if gate else None,
                "gate_passed": gate_passed,
                "status": None,  # resolved below
            }
        )
    # passed → skipped (jumped over by a later approval) → active (first
    # remaining) → pending. No-gate phases pass when a later phase passed.
    n = len(statuses)
    later_passed = [False] * n
    acc = False
    for i in range(n - 1, -1, -1):
        later_passed[i] = acc
        acc = acc or statuses[i]["gate_passed"] or (statuses[i]["gate"] is None and acc)
    seen_active = False
    for i, s in enumerate(statuses):
        if s["gate_passed"]:
            s["status"] = "passed"
        elif s["gate"] is None and later_passed[i]:
            s["status"] = "passed"
        elif later_passed[i]:
            s["status"] = "skipped"
        elif seen_active:
            s["status"] = "pending"
        else:
            s["status"] = "active"
            if s["gate"] is not None:
                seen_active = True
    return statuses


# Post-approval continuation chain (role-level, ontology-agnostic).
ROLE_CHAIN = {
    "pm-agent": "planner-agent",
}
