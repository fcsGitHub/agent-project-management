"""I110 cross-project activity feed (docs/01 §AI.1, OpenProject 'My activity'
semantics): the visible slice of the event stream IS the feed — membership
trimming keeps invisible projects out, the whitelist keeps noise out, filters
narrow the slice, and the order is the event order (rebuild-stable by
construction: the feed reads events directly)."""
from __future__ import annotations

import pytest

from apm import config
from apm.core import projections


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


def _mkproject(client, name: str) -> str:
    r = client.post("/api/projects",
                    json={"name": name, "ontology": "software-dev", "requirement": "I110"})
    assert r.status_code == 200
    return r.json()["id"]


def test_visibility_trims_and_whitelist_holds(client, tmp_data, isolated_ontologies):
    from apm.core import db
    from apm.domains.feed import _visible

    pid_a = _mkproject(client, "动态甲")
    pid_b = _mkproject(client, "动态乙")
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    assert client.post(f"/api/projects/{pid_a}/members",
                       json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200
    # activity in A (qa-wang is a member) and in B (they are not)
    client.post(f"/api/projects/{pid_a}/items",
                json={"concept_id": "task", "title": "甲项目任务"})
    client.post(f"/api/projects/{pid_b}/items",
                json={"concept_id": "task", "title": "乙项目秘密任务"})

    # membership-level trimming, function-level: qa-wang (a plain member of A
    # only, and NOT the local implicit self — identity is still u_admin) sees
    # A but never B
    qa_row = db.get_conn().execute(
        "SELECT * FROM users WHERE id = 'qa-wang'").fetchone()
    assert _visible(pid_a, qa_row) is True
    assert _visible(pid_b, qa_row) is False

    # admin (the local implicit self) sees both, newest first
    acts_admin = client.get("/api/portfolio/activity").json()["activities"]
    assert "甲项目任务" in " | ".join(a["summary"] for a in acts_admin)
    assert "乙项目秘密任务" in " | ".join(a["summary"] for a in acts_admin)
    created_at = [a["ts"] for a in acts_admin if a["event_type"] == "item.created"]
    assert created_at == sorted(created_at, reverse=True)


def test_filters_and_limit(client, tmp_data, isolated_ontologies):
    pid = _mkproject(client, "动态过滤")
    it = client.post(f"/api/projects/{pid}/items",
                     json={"concept_id": "task", "title": "过滤对象"}).json()
    client.post(f"/api/items/{it['id']}/comments", json={"body": "一条评论"})
    client.patch(f"/api/items/{it['id']}", json={"status": "done"})

    # kind=item excludes the comment event
    acts = client.get("/api/portfolio/activity",
                      params={"project_id": pid, "kind": "item"}).json()["activities"]
    assert acts and all(a["kind"] == "item" for a in acts)
    # project filter keeps only that project
    acts2 = client.get("/api/portfolio/activity",
                       params={"project_id": pid}).json()["activities"]
    assert acts2 and all(a["project_id"] == pid for a in acts2)
    # limit clamps the slice
    acts3 = client.get("/api/portfolio/activity", params={"limit": 1}).json()["activities"]
    assert len(acts3) == 1


def test_feed_order_is_rebuild_stable(client, tmp_data, isolated_ontologies):
    pid = _mkproject(client, "动态重建")
    client.post(f"/api/projects/{pid}/items",
                json={"concept_id": "task", "title": "重建前后一致"})
    before = client.get("/api/portfolio/activity").json()["activities"]
    projections.rebuild()
    after = client.get("/api/portfolio/activity").json()["activities"]
    assert after == before  # the feed reads events — replay cannot change it
