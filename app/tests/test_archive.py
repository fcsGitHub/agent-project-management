"""I103 archive & trash (docs/01 §AF.3): soft delete via item.archived /
item.restored events — archived items leave every default view, land in the
project trash, and come back intact; rebuild replays the archived state."""
from __future__ import annotations

import pytest

from apm.core import projections


@pytest.fixture(autouse=True)
def _restore_identity():
    from apm import config

    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "回收站演示", "ontology": "software-dev", "requirement": "I103"})
    assert r.status_code == 200
    return r.json()


def test_archive_excludes_then_restore_returns(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "要归档的任务"}).json()
    keep = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "留下的任务"}).json()

    assert client.post(f"/api/items/{it['id']}/archive").status_code == 200

    # excluded from the default list and the board
    titles = [i["title"] for i in client.get(f"/api/projects/{pid}/items").json()["items"]]
    assert "要归档的任务" not in titles and "留下的任务" in titles
    board = client.get(f"/api/projects/{pid}/board").json()
    board_titles = [i["title"] for b in board["buckets"] for i in b["items"]]
    assert "要归档的任务" not in board_titles

    # it IS in the trash
    trash = client.get(f"/api/projects/{pid}/trash").json()["items"]
    assert [t["title"] for t in trash] == ["要归档的任务"]

    # restore brings it back
    assert client.post(f"/api/items/{it['id']}/restore").status_code == 200
    titles2 = [i["title"] for i in client.get(f"/api/projects/{pid}/items").json()["items"]]
    assert "要归档的任务" in titles2
    assert client.get(f"/api/projects/{pid}/trash").json()["items"] == []


def test_double_archive_and_restore_conflicts(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "重复操作"}).json()
    assert client.post(f"/api/items/{it['id']}/archive").status_code == 200
    assert client.post(f"/api/items/{it['id']}/archive").status_code == 409
    assert client.post(f"/api/items/{it['id']}/restore").status_code == 200
    assert client.post(f"/api/items/{it['id']}/restore").status_code == 409


def test_archived_state_survives_rebuild(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "bug", "title": "重建后仍在回收站"}).json()
    client.post(f"/api/items/{it['id']}/archive")
    keep = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "bug", "title": "重建后仍可见"}).json()

    projections.rebuild()

    titles = [i["title"] for i in client.get(f"/api/projects/{pid}/items").json()["items"]]
    assert "重建后仍在回收站" not in titles and "重建后仍可见" in titles
    trash = client.get(f"/api/projects/{pid}/trash").json()["items"]
    assert [t["title"] for t in trash] == ["重建后仍在回收站"]
