"""M7-I25 per-project custom-field activation: project.field_disabled/enabled
events → field_overrides projection; writes and board grouping respect it."""
from __future__ import annotations

import pytest


@pytest.fixture()
def project(client):
    r = client.post("/api/projects",
                    json={"name": "字段激活演示", "ontology": "software-dev", "requirement": "I25"})
    assert r.status_code == 200
    return r.json()


def test_disable_blocks_write_and_grouping(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]

    # Active by default: write + group both work.
    r = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "正常", "custom_fields": {"tags": ["frontend"]}})
    assert r.status_code == 200

    # Disable tags at the project level.
    r = client.patch(f"/api/projects/{pid}/fields", json={"field_id": "tags", "active": False})
    assert r.status_code == 200 and r.json()["disabled_fields"] == ["tags"]

    # Writes carrying the disabled field fail closed.
    r = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "X", "custom_fields": {"tags": ["frontend"]}})
    assert r.status_code == 422 and "disabled" in r.json()["detail"]
    item = client.get(f"/api/projects/{pid}/items").json()["items"][0]
    r = client.patch(f"/api/items/{item['id']}", json={"custom_fields": {"tags": ["infra"]}})
    assert r.status_code == 422 and "disabled" in r.json()["detail"]

    # Board carries the list and refuses the disabled grouping dimension.
    board = client.get(f"/api/projects/{pid}/board").json()
    assert board["disabled_fields"] == ["tags"]
    assert client.get(f"/api/projects/{pid}/board",
                      params={"group_by": "field:tags"}).status_code == 422

    # Re-enable → everything recovers.
    r = client.patch(f"/api/projects/{pid}/fields", json={"field_id": "tags", "active": True})
    assert r.status_code == 200 and r.json()["disabled_fields"] == []
    r = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "Y", "custom_fields": {"tags": ["infra"]}})
    assert r.status_code == 200
    board = client.get(f"/api/projects/{pid}/board", params={"group_by": "field:tags"}).json()
    assert board["group_by"] == "field:tags"


def test_activation_unknown_field_and_rebuild(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    # Undeclared field can't be toggled.
    r = client.patch(f"/api/projects/{pid}/fields", json={"field_id": "ghost", "active": False})
    assert r.status_code == 422 and "not declared" in r.json()["detail"]

    # Deactivation survives a projection rebuild (events are the truth).
    client.patch(f"/api/projects/{pid}/fields", json={"field_id": "regression", "active": False})
    assert client.post("/api/system/rebuild-projections").status_code == 200
    prj = client.get(f"/api/projects/{pid}").json()
    assert prj["disabled_fields"] == ["regression"]
    r = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "bug", "title": "B", "custom_fields": {"regression": True}})
    assert r.status_code == 422 and "disabled" in r.json()["detail"]
