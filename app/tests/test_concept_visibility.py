"""M67-I201 概念级可见性（docs/01 §BL.1，Jira issue security 的两级轻量化）：
projects.concept_visibility 声明 `{concept_id:"owner"}` 即仅 owner/实例
管理员可见；未声明=全员。读面（list/board/CSV/trash/detail/search）过滤，
写面 403（create）/404（隐匿项的存在性不泄露），参与类通知静默——
mention/审批/指派/watch 照常=治理必达。project.updated 链 rebuild 存活。"""
from __future__ import annotations

import pytest

from apm import config
from apm.core import db


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def setup(client, tmp_data, isolated_ontologies):
    """Project with a declared 'risk'-only visibility + owner/contributor pair."""
    pid = client.post("/api/projects",
                      json={"name": "可见性项目", "ontology": "software-dev"}).json()["id"]
    client.post("/api/users", json={"id": "owner-zhang", "name": "Owner 张",
                                    "password": "zhang-pass"})
    client.post("/api/users", json={"id": "dev-wang", "name": "开发王",
                                    "password": "wang-pass"})
    client.post(f"/api/projects/{pid}/members",
                json={"user_id": "owner-zhang", "role": "owner"})
    client.post(f"/api/projects/{pid}/members",
                json={"user_id": "dev-wang", "role": "contributor"})
    # declare: bug concept is owner-only (tasks stay open)
    assert client.patch(f"/api/projects/{pid}",
                        json={"concept_visibility": {"bug": "owner"}}).status_code == 200
    open_item = client.post(f"/api/projects/{pid}/items",
                            json={"concept_id": "task", "title": "公开任务"}).json()
    secret = client.post(f"/api/projects/{pid}/items",
                         json={"concept_id": "bug", "title": "机密缺陷"}).json()
    return pid, open_item["id"], secret["id"]


def _login(client, user_id: str, password: str) -> None:
    assert client.post("/api/auth/login",
                       json={"user_id": user_id, "password": password}).status_code == 200


def test_declared_concept_hidden_from_non_owner_read_faces(client, setup, monkeypatch):
    pid, open_id, secret_id = setup
    monkeypatch.setattr(config.settings, "auth_mode", "network")
    _login(client, "dev-wang", "wang-pass")

    # list face: hidden concept drops; declared concept param yields nothing
    r = client.get(f"/api/projects/{pid}/items").json()
    assert [it["id"] for it in r["items"]] == [open_id] and r["total"] == 1
    r = client.get(f"/api/projects/{pid}/items", params={"concept_id": "bug"}).json()
    assert r["items"] == [] and r["total"] == 0
    # board face: no secret item in any bucket
    board = client.get(f"/api/projects/{pid}/board").json()
    assert all(it["id"] != secret_id for b in board["buckets"] for it in b["items"])
    # CSV + trash faces stay silent too
    assert "机密缺陷" not in client.get(f"/api/projects/{pid}/items.csv").text
    # detail: 404 — existence not revealed
    assert client.get(f"/api/items/{secret_id}").status_code == 404
    assert client.get(f"/api/items/{open_id}").status_code == 200
    # search: the hidden title never matches for this viewer
    hits = client.get("/api/search", params={"q": "机密", "types": "items"}).json()
    assert all(h["id"] != secret_id for h in hits["items"])

    # the owner still sees everything
    _login(client, "owner-zhang", "zhang-pass")
    r = client.get(f"/api/projects/{pid}/items").json()
    assert {it["id"] for it in r["items"]} == {open_id, secret_id}


def test_write_faces_403_create_and_404_mutate(client, setup, monkeypatch):
    pid, open_id, secret_id = setup
    monkeypatch.setattr(config.settings, "auth_mode", "network")
    _login(client, "dev-wang", "wang-pass")

    # create with a restricted concept → 403 (project visible, concept denied)
    r = client.post(f"/api/projects/{pid}/items",
                    json={"concept_id": "bug", "title": "偷建缺陷"})
    assert r.status_code == 403
    # mutating the hidden item reads as 404 (existence not revealed)
    assert client.patch(f"/api/items/{secret_id}", json={"priority": "high"}).status_code == 404
    assert client.patch(f"/api/items/{secret_id}/checklist",
                        json={"items": [{"text": "x"}]}).status_code == 404
    # the open item mutates fine
    assert client.patch(f"/api/items/{open_id}",
                        json={"priority": "high"}).status_code == 200


def test_participation_silence_and_rebuild_survives(client, setup, monkeypatch):
    pid, open_id, secret_id = setup
    monkeypatch.setattr(config.settings, "auth_mode", "network")
    # dev-wang's PAT (I199) is the identity that survives the rebuild —
    # credentials never enter the event log, but the token's own events do
    _login(client, "dev-wang", "wang-pass")
    tok = client.post("/api/auth/tokens", json={"name": "可见性验证"}).json()["token"]
    client.post("/api/auth/logout")
    h = {"Authorization": f"Bearer {tok}"}

    # dev-wang is a participant of the secret item (added before the lockdown)
    from apm.core.events import utcnow
    db.get_conn().execute(
        "INSERT INTO item_participants (item_id, user_id, project_id, source, created_at)"
        " VALUES (?, 'dev-wang', ?, 'participant', ?)",
        (secret_id, pid, utcnow()))
    db.get_conn().commit()
    client.post("/api/notifications/read", json={"all": True})
    from apm.core import events
    events.emit(event_type="comment.created", agg_type="comment", agg_id="cm_secret",
                project_id=pid,
                actor_type="human", actor_id="owner-zhang",
                payload={"item_id": secret_id, "author_id": "owner-zhang",
                         "body": "机密缺陷的新评论", "mentions_json": "[]"})
    # participation silence: the comment notification never reaches dev-wang —
    # content they cannot read must not leak through the bell either
    msgs = client.get("/api/notifications", headers=h).json()["notifications"]
    assert [n for n in msgs if not n["read"]] == []

    # rebuild is instance-admin-gated — bootstrap u_admin with a password and
    # log in as it (project owner ≠ instance admin)
    config.settings.admin_password = "boot-admin"
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    _login(client, "u_admin", "boot-admin")
    assert client.post("/api/system/rebuild-projections").status_code == 200
    config.settings.admin_password = ""
    # the declaration rides project.updated — rebuild-stable
    assert client.get(f"/api/projects/{pid}").json()["concept_visibility"] == {"bug": "owner"}
    # logout: the u_admin cookie would shadow the Bearer identity (session wins)
    client.post("/api/auth/logout")
    # the PAT survived the replay (its own events) — and the item stays hidden
    assert client.get(f"/api/items/{secret_id}", headers=h).status_code == 404
    # undeclaring restores access for everyone (still via the surviving token)
    r = client.patch(f"/api/projects/{pid}", json={"concept_visibility": {}}, headers=h)
    assert r.status_code == 200, r.text
    assert client.get(f"/api/items/{secret_id}", headers=h).status_code == 200
