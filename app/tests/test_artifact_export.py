"""M72-I218 (docs/01 §BQ.3): deliverable handoff — `git archive` the
artifacts/ subtree as a zip pinned to HEAD (clean snapshot, reproducible),
with an artifact.exported audit fact. Viewer/export gate: read-level, so any
member may export; the zip really contains the artifacts."""
import io
import zipfile

import pytest

from apm import config



@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "工件导出项目", "ontology": "software-dev"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    r = client.put(f"/api/projects/{pid}/artifacts/artifacts/prd/login.md",
                   json={"content": "# 登录 PRD\n\n一种方式。\n", "message": "seed"})
    assert r.status_code == 200, r.text
    return pid


def test_export_zip_contains_artifacts_and_audits(client, pid):
    r = client.get(f"/api/projects/{pid}/artifacts/export")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    assert "attachment" in r.headers["content-disposition"]

    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    assert any(n.endswith("artifacts/prd/login.md") for n in names)
    body = zf.read([n for n in names if n.endswith("artifacts/prd/login.md")][0]).decode("utf-8")
    assert "登录 PRD" in body

    # audit fact on the stream
    from apm.core import db

    row = db.get_conn().execute(
        "SELECT payload FROM events WHERE project_id = ? AND event_type = 'artifact.exported'",
        (pid,)).fetchone()
    assert row and '"count": 1' in row["payload"]

    # empty project → 404
    pid2 = client.post("/api/projects",
                       json={"name": "空工件项目", "ontology": "software-dev"}).json()["id"]
    assert client.get(f"/api/projects/{pid2}/artifacts/export").status_code == 404
