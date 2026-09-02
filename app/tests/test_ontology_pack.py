"""M5-I18 ontology template packs: export → rename-import → build a project."""
from __future__ import annotations

import pytest
import yaml


@pytest.fixture()
def project(client):
    r = client.post(
        "/api/projects",
        json={"name": "模板包演示", "ontology": "software-dev", "requirement": "复用"},
    )
    assert r.status_code == 200
    return r.json()


def test_export_pack_structure(client, tmp_data, isolated_ontologies, project):
    r = client.get("/api/ontologies/software-dev/export")
    assert r.status_code == 200, r.text
    pack = r.json()
    assert pack["format"] == "agentpm-ontology-pack" and pack["pack_version"] == 1
    assert pack["ontology"]["name"] == "software-dev"
    # All concept-bound roles exported with their prompt templates.
    role_ids = {x["id"] for x in pack["roles"]}
    assert {"pm-agent", "dev-agent", "qa-agent", "release-agent"} <= role_ids
    for x in pack["roles"]:
        assert x["config"]["id"] == x["id"]
        assert x["prompt"] and "AgentPM" in x["prompt"]
    assert pack["missing_roles"] == []


def test_export_missing_ontology_and_invalid(client, tmp_data, isolated_ontologies):
    assert client.get("/api/ontologies/no-such/export").status_code == 404
    (isolated_ontologies / "broken.yaml").write_text(
        "name: broken\nconcepts: []\n", encoding="utf-8")
    assert client.get("/api/ontologies/broken/export").status_code == 422


def test_import_renames_validates_and_enables_projects(
    client, tmp_data, isolated_ontologies, project
):
    pack = client.get("/api/ontologies/software-dev/export").json()

    r = client.post("/api/ontologies/import",
                    json={"pack": pack, "as_name": "software-dev-lite"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["name"] == "software-dev-lite" and out["version"] == 1
    # Existing roles are reused, never overwritten.
    assert all(x["action"] == "reused" for x in out["roles"])

    # New ontology file on disk, renamed, valid, hot-loaded.
    live = yaml.safe_load(
        (isolated_ontologies / "software-dev-lite.yaml").read_text(encoding="utf-8"))
    assert live["name"] == "software-dev-lite"
    listing = client.get("/api/ontologies").json()["ontologies"]
    entry = next(x for x in listing if x["name"] == "software-dev-lite")
    assert entry["valid"] and not entry["errors"]

    # The imported ontology builds a full project (7-phase graph inherited).
    p = client.post("/api/projects",
                    json={"name": "轻研发", "ontology": "software-dev-lite"}).json()
    graph = client.get(f"/api/projects/{p['id']}/graph").json()
    assert len([n for n in graph["nodes"] if n["kind"] == "phase"]) == 7

    # Import event lands in the audit stream.
    evs = client.get("/api/events", params={"agg_type": "ontology"}).json()["events"]
    assert any(e["event_type"] == "ontology.imported" and e["agg_id"] == "software-dev-lite"
               for e in evs)


def test_import_rejects_conflicts_and_bad_packs(client, tmp_data, isolated_ontologies, project):
    pack = client.get("/api/ontologies/software-dev/export").json()

    # Name conflict.
    r = client.post("/api/ontologies/import",
                    json={"pack": pack, "as_name": "software-dev"})
    assert r.status_code == 409

    # Wrong format marker.
    r = client.post("/api/ontologies/import",
                    json={"pack": {**pack, "format": "nope"}, "as_name": "x1"})
    assert r.status_code == 422

    # Ontology failing the small-ontology validator (no concepts).
    bad = {**pack, "ontology": {**pack["ontology"], "concepts": []}}
    r = client.post("/api/ontologies/import", json={"pack": bad, "as_name": "x2"})
    assert r.status_code == 422 and "invalid_pack" in str(r.json()["detail"])


def test_import_creates_new_role_and_prompt(client, tmp_data, isolated_ontologies, project):
    from apm import config

    pack = client.get("/api/ontologies/software-dev/export").json()
    new_role = {
        "id": "data-agent", "display_name": "数据 Agent", "concepts": ["task"],
        "model": {"provider": "openai_compat", "name": "gpt-4.1-mini", "temperature": 0.2},
        "system_prompt_file": "prompts/roles/data-agent.md", "tools": ["read_artifact"],
    }
    pack["roles"].append({"id": "data-agent", "config": new_role,
                          "prompt": "你是 AgentPM 的数据 Agent。"})
    # Bind it to a concept so the pack is realistic.
    pack["ontology"]["concepts"][1]["agent_roles"] = list(
        pack["ontology"]["concepts"][1].get("agent_roles", [])) + ["data-agent"]

    r = client.post("/api/ontologies/import",
                    json={"pack": pack, "as_name": "software-dev-ds"})
    assert r.status_code == 200, r.text
    actions = {x["id"]: x["action"] for x in r.json()["roles"]}
    assert actions["data-agent"] == "created"
    assert actions["pm-agent"] == "reused"

    base = config.settings.agents_dir
    assert (base / "roles" / "data-agent.yaml").exists()
    assert "数据 Agent" in (base / "prompts/roles/data-agent.md").read_text(encoding="utf-8")
    # Registry picked up the new role.
    from apm.runtime.roles import get_role

    assert get_role("data-agent").display_name == "数据 Agent"
