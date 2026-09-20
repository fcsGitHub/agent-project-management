"""Smoke 54 (M49): closure & expression — retro action items convert to
tracked work items through the create_item validation chain with the retro_of
audit chain, the status report assembles platform projections into a Markdown
artifact committed to the project git repo (new generation = new commit), and
the new duplicates/includes annotation relations build links without touching
the scheduling/blocks guards."""
from __future__ import annotations

import pytest

from apm import config
from apm.core import db, projections


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.mark.smoke
def test_smoke_54_m49_actions_report_relations(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "冒烟闭环", "ontology": "software-dev"}).json()["id"]

    # --- ① action items: convert, audit chain, dedupe ---------------------------
    c = client.post(f"/api/projects/{pid}/cycles",
                    json={"name": "冒烟S1", "start_date": _d(-14), "end_date": _d(-1)}).json()
    r = client.post(f"/api/cycles/{c['id']}/action-items", json={"items": [
        {"title": "冒烟行动项A", "owner": "u_admin"},
        {"title": "冒烟行动项B"},
    ]})
    assert r.status_code == 200 and len(r.json()["created"]) == 2
    iid_a = r.json()["created"][0]["id"]
    it = client.get(f"/api/items/{iid_a}").json()
    assert it["assignee_id"] == "u_admin"
    r2 = client.post(f"/api/cycles/{c['id']}/action-items",
                     json={"items": [{"title": "冒烟行动项A"}]})
    assert r2.json()["skipped"][0]["reason"] == "already converted"

    # --- ② status report: markdown artifact in git, new gen = new commit --------
    it_done = client.post(f"/api/projects/{pid}/items",
                          json={"concept_id": "task", "title": "冒烟完成项"}).json()
    client.patch(f"/api/items/{it_done['id']}", json={"status": "done"})
    rep1 = client.post(f"/api/projects/{pid}/status-report").json()
    assert rep1["path"].startswith("artifacts/reports/status-")
    art = client.get(f"/api/projects/{pid}/artifacts/{rep1['path']}").json()
    assert "## 总体健康" in art["content"] and "冒烟完成项" in art["content"]
    rep2 = client.post(f"/api/projects/{pid}/status-report").json()
    assert rep2["commit"] != rep1["commit"]  # 版本史追加
    ev = client.get("/api/events",
                    params={"event_type": "artifact.report_generated"}).json()["events"]
    assert len(ev) == 2

    # --- ③ new annotation relations: duplicates/includes, guards untouched ------
    ia = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "原始项"}).json()
    ib = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "重复项"}).json()
    assert client.post(f"/api/items/{ib['id']}/relations",
                       json={"to_item": ia["id"], "relation_type": "duplicates"}).status_code == 200
    assert client.post(f"/api/items/{ia['id']}/relations",
                       json={"to_item": ib["id"], "relation_type": "includes"}).status_code == 200
    # 标注型关系不触发 depends_on 排期/blocks 闭锁守卫：ia 可直接完成
    detail = client.get(f"/api/items/{ia['id']}").json()
    rel_types = {r["relation_type"] for r in detail.get("relations", [])}
    assert {"duplicates", "includes"} <= rel_types
    assert client.patch(f"/api/items/{ia['id']}", json={"status": "done"}).status_code == 200
    # rebuild 后关系与行动项全部复现
    projections.rebuild()
    detail2 = client.get(f"/api/items/{ia['id']}").json()
    rel_types2 = {r["relation_type"] for r in detail2.get("relations", [])}
    assert {"duplicates", "includes"} <= rel_types2
    n_actions = db.get_conn().execute(
        "SELECT COUNT(*) AS n FROM events WHERE event_type = 'item.created'"
        " AND json_extract(payload, '$.retro_of') = ?", (c["id"],)).fetchone()["n"]
    assert n_actions == 2


def _d(offset: int) -> str:
    from datetime import date, timedelta

    return (date.today() + timedelta(days=offset)).isoformat()
