"""M6-I20 custom field values: boolean/multiselect types, validation, cf filter,
rebuild-stable projection."""
from __future__ import annotations

import pytest


@pytest.fixture()
def project(client):
    r = client.post(
        "/api/projects",
        json={"name": "自定义字段演示", "ontology": "software-dev", "requirement": "cf"},
    )
    assert r.status_code == 200
    return r.json()


def test_custom_field_types_roundtrip(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    r = client.post(f"/api/projects/{pid}/items", json={
        "concept_id": "bug", "title": "崩溃",
        "priority": "P1", "custom_fields": {"regression": True}})
    assert r.status_code == 200, r.text
    bug = r.json()
    assert bug["custom_fields"] == {"regression": True}

    r = client.post(f"/api/projects/{pid}/items", json={
        "concept_id": "task", "title": "改前端",
        "custom_fields": {"tags": ["frontend"]}})
    assert r.status_code == 200, r.text

    # multiselect membership filter + boolean filter
    hits = client.get(f"/api/projects/{pid}/items", params={"cf": "tags:frontend"}).json()["items"]
    assert [i["title"] for i in hits] == ["改前端"]
    hits = client.get(f"/api/projects/{pid}/items", params={"cf": "regression:true"}).json()["items"]
    assert [i["title"] for i in hits] == ["崩溃"]

    # patch updates merge-free (full replace) and filter reflects it
    r = client.patch(f"/api/items/{bug['id']}", json={"custom_fields": {"regression": False}})
    assert r.status_code == 200
    hits = client.get(f"/api/projects/{pid}/items", params={"cf": "regression:true"}).json()["items"]
    assert hits == []


def test_custom_field_validation_fail_closed(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    # Undeclared field
    r = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "bug", "title": "X", "custom_fields": {"nope": 1}})
    assert r.status_code == 422 and "not declared" in r.json()["detail"]

    # Wrong type for boolean
    r = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "bug", "title": "X", "custom_fields": {"regression": "yes"}})
    assert r.status_code == 422 and "regression" in r.json()["detail"]

    # multiselect value outside the declared enum
    r = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "task", "title": "X",
                          "custom_fields": {"tags": ["frontend", "marketing"]}})
    assert r.status_code == 422 and "tags" in r.json()["detail"]

    # Patch path validates too
    item = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "bug", "title": "Y"}).json()
    r = client.patch(f"/api/items/{item['id']}", json={"custom_fields": {"unknown": True}})
    assert r.status_code == 422


def test_custom_fields_survive_rebuild(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    r = client.post(f"/api/projects/{pid}/items", json={
        "concept_id": "task", "title": "改后端",
        "custom_fields": {"tags": ["backend", "infra"]}})
    assert r.status_code == 200
    # estimate_hours is a declared number field but flows through its own column;
    # custom_fields None value dropped (model_dump filtered None) — keep cf clean.
    r = client.post("/api/system/rebuild-projections")
    assert r.status_code == 200
    items = client.get(f"/api/projects/{pid}/items", params={"cf": "tags:infra"}).json()["items"]
    assert len(items) == 1 and items[0]["custom_fields"] == {"tags": ["backend", "infra"]}


def test_board_group_by_custom_field(client, tmp_data, isolated_ontologies, project):
    """M6-I21: board grouping by a custom field (`group_by=field:<id>`)."""
    pid = project["id"]
    client.post(f"/api/projects/{pid}/items", json={
        "concept_id": "task", "title": "前端页", "custom_fields": {"tags": ["frontend"]}})
    client.post(f"/api/projects/{pid}/items", json={
        "concept_id": "task", "title": "双端", "custom_fields": {"tags": ["frontend", "backend"]}})
    client.post(f"/api/projects/{pid}/items", json={"concept_id": "bug", "title": "崩溃"})

    # Default stays lifecycle: five buckets, no field groups.
    d = client.get(f"/api/projects/{pid}/board").json()
    assert d["group_by"] == "lifecycle" and d["groups"] is None and d["field"] is None
    assert [b["id"] for b in d["buckets"]] == ["backlog", "todo", "in_progress", "done", "cancelled"]

    # Declared values keep ontology order (empty kept); multiselect fans out into
    # one column per tag; items without the field land in _none, last.
    d = client.get(f"/api/projects/{pid}/board", params={"group_by": "field:tags"}).json()
    assert d["group_by"] == "field:tags" and d["field"]["name"] == "标签"
    assert [(g["id"], [i["title"] for i in g["items"]]) for g in d["groups"]] == [
        ("frontend", ["前端页", "双端"]),
        ("backend", ["双端"]),
        ("infra", []),
        ("_none", ["崩溃"]),
    ]

    # Boolean values group under the cf-filter literal keys true/false.
    client.post(f"/api/projects/{pid}/items", json={
        "concept_id": "bug", "title": "回归炸", "custom_fields": {"regression": True}})
    d = client.get(f"/api/projects/{pid}/board", params={"group_by": "field:regression"}).json()
    assert d["groups"][0]["id"] == "true"
    assert [i["title"] for i in d["groups"][0]["items"]] == ["回归炸"]

    # Fail-closed: undeclared field, unknown grouping mode.
    assert client.get(f"/api/projects/{pid}/board",
                      params={"group_by": "field:ghost"}).status_code == 422
    assert client.get(f"/api/projects/{pid}/board",
                      params={"group_by": "wat"}).status_code == 422


def test_validator_requires_values_for_enum_and_multiselect(client, tmp_data, isolated_ontologies):
    from apm.domains.ontology import validate_ontology_dict

    base = {
        "name": "cf-x",
        "concepts": [{"id": "a", "states": [{"id": "s", "group": "todo"}]}],
    }
    # multiselect without values → error
    bad = {**base, "concepts": [
        {"id": "a", "states": [{"id": "s", "group": "todo"}],
         "fields": [{"id": "labels", "type": "multiselect"}]}]}
    assert any("requires values" in e for e in validate_ontology_dict(bad))
    # unknown type → error
    bad2 = {**base, "concepts": [
        {"id": "a", "states": [{"id": "s", "group": "todo"}],
         "fields": [{"id": "weird", "type": "crystal"}]}]}
    assert any("unknown type" in e for e in validate_ontology_dict(bad2))
    # valid boolean + multiselect → clean
    good = {**base, "concepts": [
        {"id": "a", "states": [{"id": "s", "group": "todo"}],
         "fields": [{"id": "flag", "type": "boolean"},
                    {"id": "labels", "type": "multiselect", "values": ["x", "y"]}]}]}
    assert validate_ontology_dict(good) == []
