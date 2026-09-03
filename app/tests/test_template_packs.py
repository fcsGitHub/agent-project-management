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
