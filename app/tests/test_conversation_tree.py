"""M66-I198 对话树导航（docs/01 §BK.1——ChatGPT 线性 UI 藏树的教训：
parent_conversation_id 自 MVP 有血缘存储但从未有写入方也从未有 UI）。
GET /projects/{id}/conversations/tree 纯投影组树 + ConversationIn 写入面
（Branch in new chat 语义：parent 须同项目存在）。"""
from __future__ import annotations

from apm.core import db, events


def _mk_project(client):
    return client.post(
        "/api/projects", json={"name": "树项目", "ontology": "software-dev"}
    ).json()


def _conv(client, project_id, **kw):
    return client.post("/api/conversations", json={"project_id": project_id, **kw}).json()


def test_tree_groups_branches_and_validates_parent(client, tmp_data):
    p = _mk_project(client)["id"]
    root1 = _conv(client, p, kind="drafting", title="主线 PRD")
    root2 = _conv(client, p, kind="executing", title="另一根")
    child = _conv(client, p, kind="executing", title="支线一",
                  parent_conversation_id=root1["id"])
    grandchild = _conv(client, p, kind="adhoc", title="孙代",
                       parent_conversation_id=child["id"])

    t = client.get(f"/api/projects/{p}/conversations/tree").json()
    # +1: project bootstrap ships its own drafting conversation (a root)
    assert t["total"] == 5
    by_id = {}

    def walk(nodes, depth=0):
        for n in nodes:
            by_id[n["id"]] = (n, depth)
            walk(n["children"], depth + 1)

    walk(t["roots"])
    assert {root1["id"], root2["id"], child["id"], grandchild["id"]} <= set(by_id)
    # lineage depths: roots at 0, child under its parent, grandchild one deeper
    assert by_id[root1["id"]][1] == 0 and by_id[root2["id"]][1] == 0
    assert by_id[child["id"]][1] == 1 and by_id[grandchild["id"]][1] == 2
    # run_status annotation rides along (None when no runs yet)
    assert all(n["run_status"] is None for n, _ in by_id.values())
    # cross-project parent is rejected at the write face
    p2 = _mk_project(client)["id"]
    r = client.post("/api/conversations", json={
        "project_id": p2, "kind": "adhoc", "parent_conversation_id": root1["id"]})
    assert r.status_code == 422
    r = client.post("/api/conversations", json={
        "project_id": p, "kind": "adhoc", "parent_conversation_id": "c_nope"})
    assert r.status_code == 422


def test_tree_orphan_falls_back_to_root_and_rebuild_is_stable(client, tmp_data):
    proj = _mk_project(client)
    p, boot_cid = proj["id"], proj["bootstrap"]["conversation_id"]
    root = _conv(client, p, kind="drafting", title="根")
    # orphan lineage: conversation.created with a parent id that never exists
    events.emit(event_type="conversation.created", agg_type="conversation",
                agg_id="c_orphan", project_id=p, actor_type="human", actor_id="u_admin",
                payload={"kind": "adhoc", "status": "active",
                         "parent_conversation_id": "c_ghost"})
    assert client.post("/api/system/rebuild-projections").status_code == 200

    t = client.get(f"/api/projects/{p}/conversations/tree").json()
    ids = {n["id"] for n in t["roots"]}
    # ghost parent not in the visible set ⇒ orphan hoisted to a root
    # (+1 bootstrap conversation, also a root)
    assert ids == {root["id"], "c_orphan", boot_cid}
    assert t["total"] == 3
    # the projection is rebuild-stable (read twice after rebuild)
    t2 = client.get(f"/api/projects/{p}/conversations/tree").json()
    assert t2 == t
    conn = db.get_conn()
    row = conn.execute(
        "SELECT parent_conversation_id FROM conversations WHERE id='c_orphan'"
    ).fetchone()
    assert row["parent_conversation_id"] == "c_ghost"
