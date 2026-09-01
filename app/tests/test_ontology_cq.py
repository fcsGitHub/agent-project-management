"""M4-I16 competency question answerability: mappings → three-state report + evidence."""
from __future__ import annotations

import pytest

from apm.core import events


@pytest.fixture()
def project(client):
    r = client.post(
        "/api/projects",
        json={"name": "CQ 演示", "ontology": "software-dev", "requirement": "验收锚点检查"},
    )
    assert r.status_code == 200
    return r.json()


def test_cq_check_software_dev_answerable(client, tmp_data, isolated_ontologies, project):
    pid = project["id"]
    # Data surfaces: items + relation + approval lifecycle + asset.
    client.post(f"/api/projects/{pid}/items", json={"concept_id": "bug", "title": "崩溃", "priority": "P1"})
    client.post(f"/api/projects/{pid}/items", json={"concept_id": "task", "title": "修复崩溃"})
    items = client.get(f"/api/projects/{pid}/items").json()["items"]
    events.emit(event_type="item.related", agg_type="relation", agg_id="rel_cq1", project_id=pid,
                payload={"from_item": items[0]["id"], "to_item": items[1]["id"],
                         "relation_type": "depends_on"})
    events.emit(event_type="approval.requested", agg_type="approval", agg_id="apr_cq1", project_id=pid,
                payload={"kind": "gate", "snapshot": {"gate": "prd_review", "title": "PRD 评审"}})
    events.emit(event_type="approval.granted", agg_type="approval", agg_id="apr_cq1",
                payload={"comment": "通过"})
    events.emit(event_type="asset.drafted", agg_type="asset", agg_id="asset_cq1", project_id=pid,
                payload={"library": "test", "kind": "test-suite", "title": "套件",
                         "tags": [], "commit": "c0ffee", "status": "draft"})

    r = client.get("/api/ontologies/software-dev/cq-check")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["checked"] == 4
    assert all(q["status"] == "answerable" for q in out["questions"]), out
    assert out["summary"].startswith("可回答 4")

    by_q = {q["question"]: q for q in out["questions"]}
    ev = {e["source"]: e for e in by_q["需求是否都经过 PRD 评审才进入设计与计划？"]["evidence"]}
    assert ev["approvals"]["count"] == 1
    assert ev["events"]["count"] == 2  # requested + granted
    assert ev["approvals"]["summary"].startswith("gate×1")

    ev2 = {e["source"]: e for e in by_q["哪些任务被依赖阻塞，阻塞了多久？"]["evidence"]}
    assert ev2["relations"]["count"] == 1 and ev2["items"]["count"] == 2

    ev4 = {e["source"]: e for e in by_q["值得复用的工件是否都沉淀进了资产库？"]["evidence"]}
    assert ev4["assets"]["count"] == 1


def test_cq_check_generic_shows_no_data_and_unmapped(client, tmp_data, isolated_ontologies):
    client.post("/api/projects", json={"name": "轻项目", "ontology": "generic"})
    out = client.get("/api/ontologies/generic/cq-check").json()
    by_q = {q["question"]: q for q in out["questions"]}
    # Mapped but empty surfaces → no_data.
    assert by_q["每条目标是否有活动在支撑？"]["status"] == "no_data"
    assert by_q["交付物是否都通过了交付审批？"]["status"] == "no_data"
    # Never mapped → unmapped.
    assert by_q["哪些活动被依赖卡住？"]["status"] == "unmapped"
    assert out["summary"] == "可回答 0 · 缺数据 2 · 缺映射 1"


def test_cq_mapping_validation_errors(client, tmp_data, isolated_ontologies):
    from apm.domains.ontology import validate_ontology_dict

    errors = validate_ontology_dict({
        "name": "x",
        "competency_questions": ["真实问题？"],
        "concepts": [{"id": "a", "states": [{"id": "s", "group": "todo"}]}],
        "cq_mappings": [
            {"question": "不在列表里的问题？", "supports": [{"source": "items"}]},
            {"question": "真实问题？", "supports": []},
            {"question": "真实问题？", "supports": [{"source": "tarot"}]},
            {"question": "真实问题？", "supports": [{"source": "events"}]},
        ],
    })
    joined = "\n".join(errors)
    assert "not in competency_questions" in joined
    assert "supports is required" in joined
    assert "unknown support source" in joined
    assert "requires event_types" in joined
