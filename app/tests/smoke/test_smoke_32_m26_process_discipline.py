"""Smoke 32 (M26): the process-discipline trio end-to-end — the WIP limit
signal (soft, project-wide count), the comment edit revision chain with noise
suppression, and the transition whitelist matrix. Closes with a rebuild pass."""
import pytest

from apm import config
from apm.core import projections


@pytest.mark.smoke
def test_smoke_32_m26_process_discipline(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects", json={"name": "冒烟流程纪律", "ontology": "software-dev", "requirement": "s32"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    # --- 1) WIP limit: project-wide count over the declared limit ------------
    # software-dev declares wip_limits: {in_progress: 5}; the 6th transition is
    # NOT blocked (soft signal), but the board reports the overflow.
    for i in range(6):
        it = client.post(f"/api/projects/{pid}/items", json={"concept_id": "task", "title": f"在制品{i}"})
        assert it.status_code == 200, it.text
        assert client.patch(f"/api/items/{it.json()['id']}",
                            json={"status": "in_progress"}).status_code == 200
    board = client.get(f"/api/projects/{pid}/board").json()
    assert board["wip_limits"] == {"in_progress": 5}
    assert board["wip"] == {"in_progress": 6}

    # --- 2) comment edit revision chain ---------------------------------------
    client.post("/api/users", json={"id": "u_rev", "name": "修订员"})
    item = client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "被评论项"}).json()
    c = client.post(f"/api/items/{item['id']}/comments", json={"body": "第一版"}).json()
    saved = config.settings.user_id
    try:
        client.post("/api/session/identity", json={"user_id": "u_rev"})
        assert client.patch(f"/api/comments/{c['id']}", json={"body": "抢编辑"}).status_code == 403
    finally:
        client.post("/api/session/identity", json={"user_id": saved})
    assert client.patch(f"/api/comments/{c['id']}", json={"body": "第二版 @修订员"}).status_code == 200
    assert client.patch(f"/api/comments/{c['id']}", json={"body": "终版"}).status_code == 200
    rev = client.get(f"/api/comments/{c['id']}/revisions").json()["revisions"]
    assert [x["body"] for x in rev] == ["第二版 @修订员", "第一版"]  # newest first
    final = client.get(f"/api/items/{item['id']}/comments").json()["comments"][0]
    assert final["body"] == "终版" and final["edited_at"]
    # edit noise suppression: the new mention never got a notification
    try:
        client.post("/api/session/identity", json={"user_id": "u_rev"})
        notes = client.get("/api/notifications").json()["notifications"]
        assert all(n["kind"] != "mention" for n in notes)
    finally:
        client.post("/api/session/identity", json={"user_id": saved})

    # --- 3) transition whitelist matrix ---------------------------------------
    bug = client.post(f"/api/projects/{pid}/items",
                      json={"concept_id": "bug", "title": "冒烟缺陷"}).json()
    assert client.patch(f"/api/items/{bug['id']}", json={"status": "verified"}).status_code == 422
    assert client.patch(f"/api/items/{bug['id']}", json={"status": "fixing"}).status_code == 200
    assert client.patch(f"/api/items/{bug['id']}", json={"status": "verified"}).status_code == 422
    assert client.patch(f"/api/items/{bug['id']}", json={"status": "fixed"}).status_code == 200
    assert client.patch(f"/api/items/{bug['id']}", json={"status": "verified"}).status_code == 200

    # --- 4) rebuild: wip count, revision chain and guard all replay -----------
    projections.rebuild()
    board2 = client.get(f"/api/projects/{pid}/board").json()
    assert board2["wip"] == {"in_progress": 6} and board2["wip_limits"] == {"in_progress": 5}
    rev2 = client.get(f"/api/comments/{c['id']}/revisions").json()["revisions"]
    assert [x["id"] for x in rev2] == [x["id"] for x in rev]
    fresh = client.post(f"/api/projects/{pid}/items",
                        json={"concept_id": "bug", "title": "重建缺陷"}).json()
    assert client.patch(f"/api/items/{fresh['id']}", json={"status": "verified"}).status_code == 422
