"""M7-I23 template pack registry: unified builtin+imported view, provenance,
preview, instantiate reusing the project-creation chain."""
from __future__ import annotations


def _import_lite(client) -> None:
    pack = client.get("/api/ontologies/software-dev/export").json()
    r = client.post("/api/ontologies/import", json={"pack": pack, "as_name": "lite-x"})
    assert r.status_code == 200, r.text


def test_registry_unifies_builtin_and_imported(client, tmp_data, isolated_ontologies):
    packs = {p["name"]: p for p in client.get("/api/template-packs").json()["packs"]}
    assert packs["software-dev"]["source"] == "builtin"
    assert packs["software-dev"]["competency_questions"] >= 1

    _import_lite(client)
    packs = {p["name"]: p for p in client.get("/api/template-packs").json()["packs"]}
    lite = packs["lite-x"]
    assert lite["source"] == "imported" and lite["imported_by"] == "u_admin"
    assert lite["concepts"] == packs["software-dev"]["concepts"]


def test_preview_and_instantiate_chain(client, tmp_data, isolated_ontologies):
    prev = client.get("/api/template-packs/software-dev").json()
    assert prev["summary"]["phases"] == 7 and prev["competency_questions"]
    assert {c["id"] for c in prev["concepts"]} >= {"task", "bug"}

    r = client.post("/api/template-packs/software-dev/instantiate",
                    json={"project_name": "模板实例", "requirement": "一键建项目"})
    assert r.status_code == 200, r.text
    prj = r.json()
    assert prj["ontology"] == "software-dev"
    assert prj["bootstrap"]["conversation_id"]  # 共链路 bootstrap 齐全
    onto = client.get(f"/api/projects/{prj['id']}/ontology").json()
    assert onto["phases"] and onto["competency_questions"]


def test_instantiate_fail_closed(client, tmp_data, isolated_ontologies):
    assert client.get("/api/template-packs/ghost").status_code == 404
    assert client.post("/api/template-packs/ghost/instantiate",
                       json={"project_name": "X"}).status_code == 404
    assert client.post("/api/template-packs/software-dev/instantiate",
                       json={"project_name": "  "}).status_code == 422


def test_startup_registration_is_idempotent(client, tmp_data, isolated_ontologies):
    from apm.domains.template_packs import register_builtin_packs

    # Lifespan already registered every builtin; a second pass is a no-op.
    assert register_builtin_packs() == 0


def _asset_with_provenance(client) -> dict:
    a = client.post("/api/projects",
                    json={"name": "资产来源项目", "ontology": "software-dev", "requirement": "沉淀"}).json()
    r = client.put(f"/api/projects/{a['id']}/artifacts/test/regression.md",
                   json={"content": "# 回归套件\n- case1", "message": "qa: suite"})
    assert r.status_code == 200, r.text
    created = r.json()
    asset = client.post("/api/assets", json={
        "source_project_id": a["id"], "artifact_path": created["path"], "commit": created["commit"],
        "library": "test", "kind": "test-suite", "title": "登录回归套件"}).json()
    return asset


def test_from_asset_registers_pack(client, tmp_data, isolated_ontologies):
    asset = _asset_with_provenance(client)

    r = client.post("/api/template-packs/from-asset",
                    json={"asset_id": asset["id"], "pack_name": "from-asset-x"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "asset" and body["origin_ontology"] == "software-dev"

    # Registry shows the pack with asset provenance, and it can instantiate.
    packs = {p["name"]: p for p in client.get("/api/template-packs").json()["packs"]}
    assert packs["from-asset-x"]["source"] == "asset"
    assert packs["from-asset-x"]["origin_ontology"] == "software-dev"
    prj = client.post("/api/template-packs/from-asset-x/instantiate",
                      json={"project_name": "资产模板实例"}).json()
    assert prj["ontology"] == "from-asset-x" and prj["bootstrap"]["conversation_id"]

    # Registration is a real auditable event.
    evs = client.get("/api/events", params={"event_type": "pack.registered"}).json()["events"]
    assert any(e["agg_id"] == "from-asset-x" and e["payload"]["source"] == "asset" for e in evs)


def test_from_asset_fail_closed(client, tmp_data, isolated_ontologies):
    asset = _asset_with_provenance(client)
    # Duplicate pack name → 409.
    assert client.post("/api/template-packs/from-asset",
                       json={"asset_id": asset["id"], "pack_name": "software-dev"}).status_code == 409
    # Invalid pack name → 422.
    assert client.post("/api/template-packs/from-asset",
                       json={"asset_id": asset["id"], "pack_name": "a/b"}).status_code == 422
    # Unknown asset → 404.
    assert client.post("/api/template-packs/from-asset",
                       json={"asset_id": "a_ghost", "pack_name": "nope"}).status_code == 404
