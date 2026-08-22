"""I2 tests: ontology validation, project templates, items domain."""
from apm.domains.ontology import load_ontology, validate_ontology_dict


def test_builtin_ontologies_are_valid():
    for name in ("software-dev", "generic"):
        onto = load_ontology(name)
        assert onto.errors == [], f"{name}: {onto.errors}"
        assert onto.concepts
        assert onto.phases


def test_software_dev_ontology_shape():
    onto = load_ontology("software-dev")
    assert [p["id"] for p in onto.phases] == [
        "intake", "analysis", "design", "planning", "development", "testing", "release"
    ]
    assert onto.gate_of_phase("analysis") == "prd_review"
    assert onto.concepts["task"].state_group("awaiting_review") == "in_progress"
    libs = {l["id"] for l in onto.libraries}
    assert libs == {"product", "test", "doc"}
    kinds = {k["id"] for k in onto.asset_kinds}
    assert "test-suite" in kinds and "adr" in kinds


def test_generic_ontology_light_flow():
    onto = load_ontology("generic")
    assert [p["id"] for p in onto.phases] == ["intake", "execute", "deliver"]
    assert onto.gate_of_phase("deliver") == "delivery_approval"


def test_invalid_ontology_reported():
    bad = {
        "name": "bad",
        "concepts": [
            {"id": "x", "states": [{"id": "s", "group": "wat"}]},
        ],
        "phases": [{"id": "p1"}],
        "asset_kinds": [{"id": "k1", "library": "nolib"}],
        "libraries": [],
    }
    errors = validate_ontology_dict(bad)
    assert any("group" in e for e in errors)
    assert any("nolib" in e for e in errors)


def test_ontologies_api(client, tmp_data):
    r = client.get("/api/ontologies")
    assert r.status_code == 200
    names = {o["name"] for o in r.json()["ontologies"]}
    assert names >= {"software-dev", "generic"}
    r = client.get("/api/ontologies/software-dev")
    assert r.status_code == 200
    assert len(r.json()["phases"]) == 7


def test_create_project_applies_template(client, tmp_data):
    r = client.post(
        "/api/projects",
        json={"name": "周报工具", "ontology": "software-dev", "requirement": "自动生成周报"},
    )
    assert r.status_code == 200
    p = r.json()
    assert p["ontology"] == "software-dev"
    assert "目标" in p["charter"]
    assert p["bootstrap"]["feature_id"]

    detail = client.get(f"/api/projects/{p['id']}").json()
    assert [f["title"] for f in detail["features"]] == ["MVP"]
    assert detail["item_counts"]["backlog"] == 0

    graph = client.get(f"/api/projects/{p['id']}/graph").json()
    phase_nodes = [n for n in graph["nodes"] if n["kind"] == "phase"]
    gate_nodes = [n for n in graph["nodes"] if n["kind"] == "gate"]
    assert len(phase_nodes) == 7
    assert len(gate_nodes) == 6  # all phases except intake have a gate


def test_create_project_with_invalid_ontology_422(client, tmp_data):
    r = client.post("/api/projects", json={"name": "x", "ontology": "nope"})
    assert r.status_code in (404, 422)


def _mk_project(client, ontology="software-dev"):
    return client.post(
        "/api/projects", json={"name": "P", "ontology": ontology, "requirement": "r"}
    ).json()


def test_item_lifecycle_and_relations(client, tmp_data):
    p = _mk_project(client)
    pid = p["id"]

    r = client.post(
        f"/api/projects/{pid}/items",
        json={"concept_id": "task", "title": "T1 解析模块", "priority": "high", "feature_id": p["bootstrap"]["feature_id"]},
    )
    assert r.status_code == 200
    item = r.json()
    assert item["status"] == "open" and item["status_group"] == "backlog"

    # invalid status rejected (not in concept lifecycle)
    r = client.patch(f"/api/items/{item['id']}", json={"status": "nonexistent"})
    assert r.status_code == 422

    # valid transition + assignment
    r = client.patch(f"/api/items/{item['id']}", json={"status": "in_progress", "assignee_type": "agent", "assignee_id": "dev-agent"})
    assert r.status_code == 200
    assert r.json()["status_group"] == "in_progress"

    # second item + kernel relation
    r = client.post(f"/api/projects/{pid}/items", json={"concept_id": "task", "title": "T2 校验"})
    t2 = r.json()
    r = client.post(f"/api/items/{item['id']}/relations", json={"to_item": t2["id"], "relation_type": "depends_on"})
    assert r.status_code == 200
    rels = r.json()["relations"]
    assert any(x["relation_type"] == "depends_on" and x["to_item"] == t2["id"] for x in rels)

    # invalid relation type rejected
    r = client.post(f"/api/items/{item['id']}/relations", json={"to_item": t2["id"], "relation_type": "blocked_by"})
    assert r.status_code == 422

    # board reflects buckets
    board = client.get(f"/api/projects/{pid}/board").json()
    assert {b["id"] for b in board["buckets"]} == {
        "backlog", "todo", "in_progress", "done", "cancelled"
    }
    cols = {c["id"] for c in board["columns"]}
    assert "task:awaiting_review" in cols


def test_feature_crud(client, tmp_data):
    p = _mk_project(client)
    r = client.post(f"/api/projects/{p['id']}/features", json={"title": "导入解析", "brief": "支持 Excel"})
    f = r.json()
    assert f["status"] == "active"
    r = client.patch(f"/api/features/{f['id']}", json={"brief": "支持 Excel/CSV"})
    assert r.json()["brief"] == "支持 Excel/CSV"
    detail = client.get(f"/api/features/{f['id']}?include=items").json()
    assert detail["items"] == []
    r = client.post(f"/api/features/{f['id']}/archive")
    assert r.json()["status"] == "archived"
    listing = client.get(f"/api/projects/{p['id']}/features").json()["features"]
    assert f["id"] not in {x["id"] for x in listing}
