"""Smoke 1 (first half, I2): create software-dev project → structure asserted."""
import pytest


@pytest.mark.smoke
def test_smoke_01_create_project_structure(client, tmp_data):
    r = client.post(
        "/api/projects",
        json={
            "name": "周报工具",
            "ontology": "software-dev",
            "requirement": "汇总 Git 提交与任务状态，自动生成周报",
        },
    )
    assert r.status_code == 200
    p = r.json()

    # Feature auto-created by template application.
    bootstrap = p["bootstrap"]
    assert bootstrap.get("feature_id")
    detail = client.get(f"/api/projects/{p['id']}").json()
    assert any(f["id"] == bootstrap["feature_id"] for f in detail["features"])

    # Charter (prompt L1) drafted with ontology concept table.
    assert "本体概念表" in p["charter"]

    # Phase graph matches the 7-phase ontology with gates.
    graph = client.get(f"/api/projects/{p['id']}/graph").json()
    phases = [n for n in graph["nodes"] if n["kind"] == "phase"]
    gates = [n for n in graph["nodes"] if n["kind"] == "gate"]
    assert len(phases) == 7 and len(gates) == 6

    # Generic project gets the light 3-phase structure.
    r = client.post("/api/projects", json={"name": "轻项目", "ontology": "generic"})
    g2 = client.get(f"/api/projects/{r.json()['id']}/graph").json()
    assert len([n for n in g2["nodes"] if n["kind"] == "phase"]) == 3

    # Template application events land in the audit stream.
    evs = client.get(f"/api/events", params={"project_id": p["id"], "agg_type": "project"}).json()
    types = [e["event_type"] for e in evs["events"]]
    assert "project.created" in types and "project.template_applied" in types
