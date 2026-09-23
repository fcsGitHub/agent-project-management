"""Smoke 60 (M55): watch refinement & noise reduction — a conditional watch
(「仅当 status_group=done」) delivers on completion but stays silent on other
status changes, consecutive same-project watch facts stack on the stream for
the bell's display-layer bundling, and the per-kind pref gate still holds."""
from __future__ import annotations

import pytest

from apm import config


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.mark.smoke
def test_smoke_60_m55_conditional_watch_bundling(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "冒烟精修", "ontology": "software-dev"}).json()["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200

    # --- ① 条件化 watch：仅当完成 ---------------------------------------------
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    r = client.post(f"/api/projects/{pid}/watch-rules",
                    json={"event_type": "item.status_changed",
                          "condition": {"status_group": "done"}})
    assert r.status_code == 200, r.text
    rules = client.get("/api/watch-rules").json()["rules"]
    assert rules and "done" in (rules[0]["condition"] or "")
    client.post("/api/session/identity", json={"user_id": "u_admin"})

    # --- ② in_progress 不投递，done 投递（源头条件过滤）------------------------
    def _mk(title):
        it = client.post(f"/api/projects/{pid}/items",
                         json={"concept_id": "task", "title": title}).json()
        return it["id"]

    it1 = _mk("精修任务1")
    client.patch(f"/api/items/{it1}", json={"status": "in_progress"})   # 静默
    it2 = _mk("精修任务2")
    client.patch(f"/api/items/{it2}", json={"status": "done"})          # 命中
    it3 = _mk("精修任务3")
    client.patch(f"/api/items/{it3}", json={"status": "done"})          # 命中
    client.post("/api/session/identity", json={"user_id": "qa-wang"})

    notes = client.get("/api/notifications").json()["notifications"]
    wk = [n for n in notes if n["kind"] == "watch"]
    assert len(wk) == 2  # 两次 done，无 in_progress 噪声
    assert all("精修任务" in n["summary"] for n in wk)
    # 连续同类同项目 → 铃铛 bundling 数据面成立（相邻同 kind+project）
    kinds_proj = [(n["kind"], n["project_id"]) for n in notes]
    watch_positions = [i for i, (k, _) in enumerate(kinds_proj) if k == "watch"]
    assert watch_positions and len({kinds_proj[i][1] for i in watch_positions}) == 1

    # --- ③ 偏好门仍然最后把关 --------------------------------------------------
    assert client.put("/api/me/notification-prefs", json={
        "prefs": [{"kind": "watch", "inapp": False, "email": False}]}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    it4 = _mk("精修任务4")
    client.patch(f"/api/items/{it4}", json={"status": "done"})
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert len([n for n in client.get("/api/notifications").json()["notifications"]
                if n["kind"] == "watch"]) == 2  # 站内被闸
    sent = client.get("/api/events",
                      params={"event_type": "notification.sent"}).json()["events"]
    assert len([e for e in sent if e["payload"].get("kind") == "watch"]) == 3  # 事实照发
