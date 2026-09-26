"""Smoke 62 (M57): in-place watch rule edit & pause, plus asset usage
insights — change a condition without delete+recreate (old condition goes
silent, the new one hits), pause keeps the config while muting the rule,
resume delivers again, and the asset library surfaces real reuse (consumed
counts, usage Top) plus the never-reused staleness list."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from apm import config
from apm.core import events, projections
from apm.domains.assets import asset_insights


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.mark.smoke
def test_smoke_62_m57_watch_edit_asset_insights(client, tmp_data, isolated_ontologies):
    # --- ① 就地改条件：不删规则，旧条件静默、新条件命中 -------------------------
    pid = client.post("/api/projects",
                      json={"name": "冒烟治理", "ontology": "software-dev"}).json()["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert client.post(f"/api/projects/{pid}/watch-rules",
                       json={"event_type": "item.status_changed",
                             "condition": {"status": "done"}}).status_code == 200
    rules0 = client.get("/api/watch-rules").json()["rules"]
    assert client.patch(f"/api/projects/{pid}/watch-rules/item.status_changed",
                        json={"condition": {"status": "in_progress"}}).status_code == 200
    rules1 = client.get("/api/watch-rules").json()["rules"]
    assert len(rules1) == 1 and rules1[0]["created_at"] == rules0[0]["created_at"]
    assert rules1[0]["condition"] == '{"status": "in_progress"}'
    client.post("/api/session/identity", json={"user_id": "u_admin"})

    def _mk(title):
        it = client.post(f"/api/projects/{pid}/items",
                         json={"concept_id": "task", "title": title}).json()
        return it["id"]

    it1 = _mk("治理任务1")
    client.patch(f"/api/items/{it1}", json={"status": "done"})          # 旧条件→静默
    client.patch(f"/api/items/{it1}", json={"status": "in_progress"})   # 新条件→命中
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    wk = [n for n in client.get("/api/notifications").json()["notifications"]
          if n["kind"] == "watch"]
    assert len(wk) == 1 and "治理任务1" in wk[0]["summary"]

    # --- ② ⏸ 暂停静默（配置保留）→ ▶ 恢复再投递 --------------------------------
    assert client.patch(f"/api/projects/{pid}/watch-rules/item.status_changed",
                        json={"paused": True}).json()["paused"] is True
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    it2 = _mk("治理任务2")
    client.patch(f"/api/items/{it2}", json={"status": "in_progress"})   # 暂停期静默
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert len([n for n in client.get("/api/notifications").json()["notifications"]
                if n["kind"] == "watch"]) == 1
    assert client.patch(f"/api/projects/{pid}/watch-rules/item.status_changed",
                        json={"paused": False}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "u_admin"})
    it3 = _mk("治理任务3")
    client.patch(f"/api/items/{it3}", json={"status": "in_progress"})   # 恢复→再投递
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert len([n for n in client.get("/api/notifications").json()["notifications"]
                if n["kind"] == "watch"]) == 2

    # --- ③ 资产使用洞察：真实复用可看见，吃灰资产进清单 -------------------------
    def _mk_asset(title):
        a = client.post("/api/projects",
                        json={"name": f"冒烟来源-{title}", "ontology": "software-dev",
                              "requirement": "沉淀"}).json()
        r = client.put(f"/api/projects/{a['id']}/artifacts/test/suite.md",
                       json={"content": f"# {title}", "message": f"qa: {title}"})
        created = r.json()
        return client.post("/api/assets", json={
            "source_project_id": a["id"], "artifact_path": created["path"],
            "commit": created["commit"], "library": "test", "kind": "test-suite",
            "title": title}).json()

    hot, cold = _mk_asset("冒烟热门套件"), _mk_asset("冒烟吃灰套件")
    for aid, title in ((hot["id"], "冒烟热门套件"), (cold["id"], "冒烟吃灰套件")):
        events.emit(event_type="asset.published", agg_type="asset", agg_id=aid,
                    actor_type="human", actor_id="u_admin",
                    payload={"status": "published", "title": title,
                             "library": "test", "kind": "test-suite"})
    assert client.post(f"/api/assets/{hot['id']}/link",
                       json={"project_id": pid}).status_code == 200
    assert client.post(f"/api/assets/{hot['id']}/link",
                       json={"project_id": pid}).status_code == 200

    ins = client.get("/api/assets/insights").json()["assets"]
    by_id = {a["id"]: a for a in ins}
    assert by_id[hot["id"]]["consumed_count"] == 2
    assert by_id[hot["id"]]["linked_count"] == 2
    assert by_id[cold["id"]]["consumed_count"] == 0
    assert ins[0]["id"] == hot["id"]

    from datetime import datetime as _dt
    created = _dt.fromisoformat(by_id[cold["id"]]["created_at"])
    ins91 = asset_insights(now=(created + timedelta(days=91)).isoformat())["assets"]
    stale = {a["id"] for a in ins91 if a["stale"]}
    assert cold["id"] in stale and hot["id"] not in stale

    projections.ensure_handlers_registered()
    projections.rebuild()
    ins2 = client.get("/api/assets/insights").json()["assets"]
    assert {a["id"]: a["consumed_count"] for a in ins2} \
        == {a["id"]: a["consumed_count"] for a in ins}
