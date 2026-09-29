"""M72-I217 (docs/01 §BQ.2): artifact deletion — git rm + artifact.deleted
fact; git history IS the soft delete (the blob stays in the repo log, the
audit event carries the commit). The global-search index drops the deleted
artifact via the read-failure path of the reindex projector."""
from __future__ import annotations

import pytest

from apm import config
from apm.content import gitrepo


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "工件删除项目", "ontology": "software-dev"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    r = client.put(f"/api/projects/{pid}/artifacts/artifacts/prd/doomed.md",
                   json={"content": "# 待删\n\n UniqueWordToSearch 标记。\n", "message": "seed"})
    assert r.status_code == 200, r.text
    return pid


def test_delete_drops_listing_search_but_keeps_git_history(client, pid):
    # deletable via the API, gate passes in local mode
    r = client.delete(f"/api/projects/{pid}/artifacts/artifacts/prd/doomed.md")
    assert r.status_code == 200, r.text
    assert "commit" in r.json()

    # listing no longer shows it
    arts = client.get(f"/api/projects/{pid}/artifacts").json()["artifacts"]
    assert all(a["path"] != "artifacts/prd/doomed.md" for a in arts)

    # global search drops it (the deleted row's reindex clears the FTS entry)
    r = client.get("/api/search", params={"q": "UniqueWordToSearch", "types": "artifacts"})
    assert r.json()["artifacts"] == []

    # git history IS the soft delete: the blob remains recoverable from log
    hist = gitrepo.file_history(pid, "artifacts/prd/doomed.md")
    assert hist  # commits touching the path are still traceable

    # deleting again → 404
    assert client.delete(f"/api/projects/{pid}/artifacts/artifacts/prd/doomed.md").status_code == 404
