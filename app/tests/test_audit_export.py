"""M41-I127 audit CSV export (docs/01 §AN.3, Jira native audit-CSV
semantics): the audit page is for humans, the export is for auditors —
admin-only streaming CSV over the project's event stream with a date-window
filter. The stream IS the audit log, so the export is a window, not a
second ledger."""
from __future__ import annotations

import csv
import io
import json

import pytest

from apm import config


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "审计导出", "ontology": "software-dev", "requirement": "I127"})
    assert r.status_code == 200
    pid = r.json()["id"]
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "有审计的任务"}).json()
    client.patch(f"/api/items/{it['id']}", json={"priority": "high"})
    return pid


def _rows(csv_text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(csv_text)))


def test_export_roundtrip_admin_only(client, pid, tmp_data, isolated_ontologies):
    saved = config.settings.user_id
    r = client.get(f"/api/projects/{pid}/audit.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    rows = _rows(r.text)
    types = {row["event_type"] for row in rows}
    assert "item.created" in types and "item.updated" in types
    assert all(len(row["payload"]) <= 200 for row in rows)

    # non-admin identity → 403
    client.post("/api/users", json={"id": "u_viewer", "name": "路人"})
    client.post("/api/session/identity", json={"user_id": "u_viewer"})
    assert client.get(f"/api/projects/{pid}/audit.csv").status_code == 403
    client.post("/api/session/identity", json={"user_id": saved})
    # unknown project → 404 (admin sees the difference)
    assert client.get("/api/projects/p_nope/audit.csv").status_code == 404


def test_days_window_filters_old_events(client, pid, tmp_data, isolated_ontologies):
    # everything so far is dated today; a 1-day window still includes it
    r1 = client.get(f"/api/projects/{pid}/audit.csv", params={"days": 1})
    n_now = len(_rows(r1.text))
    assert n_now >= 2
    # a 0-day-style window is clamped to 1; a huge one changes nothing here
    r2 = client.get(f"/api/projects/{pid}/audit.csv", params={"days": 3650})
    assert len(_rows(r2.text)) == n_now
