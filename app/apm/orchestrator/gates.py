"""Gate helpers: pending approvals per project/run, gate→approval conversions."""
from __future__ import annotations

import json

from apm.core import db


def pending_approvals(project_id: str | None = None) -> list[dict]:
    where, params = ["status = 'pending'"], []
    if project_id:
        where.append("project_id = ?")
        params.append(project_id)
    rows = db.get_conn().execute(
        f"SELECT * FROM approvals WHERE {' AND '.join(where)} ORDER BY requested_at DESC"
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["payload_snapshot"] = json.loads(d["payload_snapshot"] or "{}")
        out.append(d)
    return out


def pending_gate_count(project_id: str) -> int:
    return sum(1 for a in pending_approvals(project_id) if a["kind"] == "gate")
