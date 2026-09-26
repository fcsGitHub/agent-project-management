"""Smoke 63 (M58): agent-run watch — run.succeeded/run.failed join the
watchable set so agent activity becomes notifications with actionable context
(completion summary, error first line) and a run_id the bell can deep-link to
the run drawer; a real bootstrap run (gate → approve → succeeded) notifies the
watcher; process facts like run.started stay unwatchable."""
from __future__ import annotations

import pytest

from apm import config
from apm.core import events
from tests.conftest import wait_for


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.mark.smoke
def test_smoke_63_m58_watch_agent_runs(client, tmp_data, isolated_ontologies):
    p = client.post("/api/projects",
                    json={"name": "冒烟动态", "ontology": "software-dev",
                          "requirement": "agent-watch"}).json()
    pid = p["id"]
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王"})
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "qa-wang", "role": "contributor"}).status_code == 200
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert client.post(f"/api/projects/{pid}/watch-rules",
                       json={"event_type": "run.succeeded"}).status_code == 200
    assert client.post(f"/api/projects/{pid}/watch-rules",
                       json={"event_type": "run.started"}).status_code == 422  # 过程面不可关注
    client.post("/api/session/identity", json={"user_id": "u_admin"})

    # --- ① 真实 run：bootstrap 发起 → Gate 挂起 → 批准 → succeeded --------------
    run = client.post("/api/runs", json={
        "conversation_id": p["bootstrap"]["conversation_id"],
        "agent_role": "pm-agent"}).json()
    wait_for(lambda: client.get(f"/api/runs/{run['id']}").json()["status"] == "interrupted")
    apr = wait_for(lambda: next(iter(
        client.get("/api/approvals",
                   params={"status": "pending", "project_id": pid}).json()["approvals"]), None))
    assert apr, "gate approval never appeared"
    client.post(f"/api/approvals/{apr['id']}/decision", json={"decision": "approved"})
    wait_for(lambda: client.get(f"/api/runs/{run['id']}").json()["status"] == "succeeded")

    # --- ② 关注者收到「运行完成」通知，带 run_id 直达数据 -----------------------
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    wk = wait_for(lambda: [n for n in client.get("/api/notifications").json()["notifications"]
                           if n["kind"] == "watch" and n.get("run_id") == run["id"]])
    assert wk, "run watch notification missing"
    assert "agent 运行完成" in wk[0]["summary"]

    # --- ③ 失败面：run.failed 事实 → 通知摘要带 error 首行 ----------------------
    # 注意 own-data 语义：规则必须由关注者本人（qa-wang）添加
    client.post("/api/session/identity", json={"user_id": "qa-wang"})
    assert client.post(f"/api/projects/{pid}/watch-rules",
                       json={"event_type": "run.failed"}).status_code == 200
    events.emit(event_type="run.failed", agg_type="run", agg_id="r_smoke_fail",
                project_id=pid, actor_type="system", actor_id="runtime:r_smoke_fail",
                payload={"error": "provider 超时：上游 504"})
    bad = wait_for(lambda: [n for n in client.get("/api/notifications").json()["notifications"]
                            if n["kind"] == "watch" and n.get("run_id") == "r_smoke_fail"])
    assert bad and "provider 超时" in bad[0]["summary"]
    client.post("/api/session/identity", json={"user_id": "u_admin"})
