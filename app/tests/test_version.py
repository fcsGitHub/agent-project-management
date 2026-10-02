"""M81-I243 version single source (docs/01 §BZ.1): /api/health must report
APP_VERSION from apm/version.py — the one place a release version is edited
for backend-facing anchors (package.json / README are locked to it by smoke
86's file assertions)."""
from __future__ import annotations

from apm.version import APP_VERSION


def test_health_reports_single_source_version(client, tmp_data, isolated_ontologies):
    assert client.get("/api/health").json()["version"] == APP_VERSION == "0.11.0"
