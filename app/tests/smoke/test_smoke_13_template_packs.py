"""Smoke 13 (M7-I23): template pack registry — builtin + imported packs share one
list, preview exposes the phase graph and CQs, one-click instantiate lands a
project with bootstrap intact, unknown packs fail closed."""
import pytest


@pytest.mark.smoke
def test_smoke_13_template_pack_registry(client, tmp_data, isolated_ontologies):
    # Unified registry: builtin packs visible with summaries.
    packs = {p["name"]: p for p in client.get("/api/template-packs").json()["packs"]}
    assert "software-dev" in packs
    sd = packs["software-dev"]
    assert sd["valid"] and sd["concepts"] >= 3 and sd["competency_questions"] >= 1

    # Import a pack under a new name → same list, marked imported.
    pack = client.get("/api/ontologies/software-dev/export").json()
    r = client.post("/api/ontologies/import", json={"pack": pack, "as_name": "smoke13-lite"})
    assert r.status_code == 200, r.text
    packs = {p["name"]: p for p in client.get("/api/template-packs").json()["packs"]}
    lite = packs["smoke13-lite"]
    assert lite["source"] == "imported" and lite["concepts"] == sd["concepts"]

    # Preview exposes graph + CQs before spending a project on it.
    prev = client.get("/api/template-packs/smoke13-lite").json()
    assert prev["summary"]["phases"] == 7 and prev["competency_questions"]

    # One-click instantiate → project bootstrap with graph and CQ in place.
    prj = client.post("/api/template-packs/smoke13-lite/instantiate",
                      json={"project_name": "冒烟13实例", "requirement": "模板直建"}).json()
    assert prj["ontology"] == "smoke13-lite" and prj["bootstrap"]["conversation_id"]
    onto = client.get(f"/api/projects/{prj['id']}/ontology").json()
    assert [p["id"] for p in onto["phases"]] and onto["competency_questions"]
    assert {c["id"] for c in onto["concepts"]} >= {"requirement", "task", "bug"}

    # Unknown packs fail closed.
    assert client.get("/api/template-packs/ghost").status_code == 404
    assert client.post("/api/template-packs/ghost/instantiate",
                       json={"project_name": "X"}).status_code == 404

    # Asset → pack (M7-I24): register a project's ontology from an asset.
    a = client.post("/api/projects",
                    json={"name": "冒烟13来源", "ontology": "software-dev", "requirement": "沉淀"}).json()
    art = client.put(f"/api/projects/{a['id']}/artifacts/test/smoke13.md",
                     json={"content": "# 冒烟13工件", "message": "smoke13"}).json()
    asset = client.post("/api/assets", json={
        "source_project_id": a["id"], "artifact_path": art["path"], "commit": art["commit"],
        "library": "test", "kind": "test-suite", "title": "冒烟13资产"}).json()
    r = client.post("/api/template-packs/from-asset",
                    json={"asset_id": asset["id"], "pack_name": "smoke13-asset-pack"})
    assert r.status_code == 200, r.text
    packs = {p["name"]: p for p in client.get("/api/template-packs").json()["packs"]}
    assert packs["smoke13-asset-pack"]["source"] == "asset"
    prj2 = client.post("/api/template-packs/smoke13-asset-pack/instantiate",
                       json={"project_name": "冒烟13资产实例"}).json()
    assert prj2["ontology"] == "smoke13-asset-pack" and prj2["bootstrap"]["conversation_id"]
