"""M117 Triage 分诊队列轮（docs/01 §DH，候选池①转正）：Linear intake 语义
的 AgentPM 翻译——外部入流（intake/IMAP）落本体 triage 中间态等人决定；
accept（→initial_status+可选指派）/decline（→cancelled 组状态）/snooze
（items.snoozed_until+sweep 到期复浮）；队列读面走既有 list_items(status=)
零新读端点。task 无白名单（undeclared=open）出入自由；bug 有 M26 白名单
须声明 triage 出入。手工创建仍落 states[0]（initial_status 语义不变）。"""
from __future__ import annotations

import pytest

from apm import config
from apm.core import db, events


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.fixture()
def proj(client, tmp_data, isolated_ontologies) -> str:
    return client.post("/api/projects",
                       json={"name": "分诊项目", "ontology": "software-dev"}).json()["id"]


def _intake_token(client, pid: str, concept: str | None = None) -> str:
    body: dict = {}
    if concept:
        body["concept_id"] = concept
    return client.post(f"/api/projects/{pid}/intake-token", json=body).json()["token"]


def _land(client, pid: str, title: str, concept: str | None = None) -> str:
    token = _intake_token(client, pid, concept)
    r = client.post(f"/api/intake/{token}", json={"title": title})
    assert r.status_code == 200, r.text
    return r.json()["item_id"]


def _triage(client, iid: str, action: str, **kw) -> object:
    return client.post(f"/api/items/{iid}/triage", json={"action": action, **kw})


# ------------------------------------------------- I356 本体声明
def test_ontology_triage_states_and_bug_whitelist(client, proj):
    onto = client.get(f"/api/projects/{proj}/ontology").json()
    task = next(c for c in onto["concepts"] if c["id"] == "task")
    bug = next(c for c in onto["concepts"] if c["id"] == "bug")
    assert "triage" in [s["id"] for s in task["states"]]
    assert "triage" in [s["id"] for s in bug["states"]]

    it = client.post(f"/api/projects/{proj}/items",
                     json={"concept_id": "bug", "title": "分诊白名单 bug",
                           "status": "triage"}).json()
    # bug 白名单：triage→verified 未声明=非法；triage→open 合法
    assert client.patch(f"/api/items/{it['id']}",
                        json={"status": "verified"}).status_code == 422
    assert client.patch(f"/api/items/{it['id']}",
                        json={"status": "open"}).status_code == 200
    # open→triage 再入队合法
    assert client.patch(f"/api/items/{it['id']}",
                        json={"status": "triage"}).status_code == 200


def test_manual_create_lands_in_initial_status(client, proj):
    it = client.post(f"/api/projects/{proj}/items",
                     json={"concept_id": "task", "title": "手工任务"}).json()
    assert it["status"] == "open"  # states[0] 语义不变——手工创建不入队


# ------------------------------------------------- I357 落点+动作域
def test_intake_lands_in_triage(client, proj):
    iid = _land(client, proj, "外部报告的缺陷")
    it = client.get(f"/api/items/{iid}").json()
    assert it["status"] == "triage"
    assert it["status_group"] == "backlog"


def test_triage_accept_and_decline(client, proj):
    task_iid = _land(client, proj, "接受我")
    r = _triage(client, task_iid, "accept")
    assert r.status_code == 200, r.text
    assert client.get(f"/api/items/{task_iid}").json()["status"] == "open"

    bug_iid = _land(client, proj, "拒绝我", concept="bug")
    r = _triage(client, bug_iid, "decline")
    assert r.status_code == 200, r.text
    # bug 的 cancelled 组状态是 wont_fix（按概念解析，不是硬编码）
    assert client.get(f"/api/items/{bug_iid}").json()["status"] == "wont_fix"

    # accept 带指派：走 item.assigned 既有链
    client.post("/api/users", json={"id": "u_worker", "name": "工人"})
    client.post(f"/api/projects/{proj}/members",
                json={"user_id": "u_worker", "role": "contributor"})
    iid2 = _land(client, proj, "接受并指派")
    r = _triage(client, iid2, "accept", assignee_id="u_worker")
    assert r.status_code == 200
    it = client.get(f"/api/items/{iid2}").json()
    assert it["status"] == "open" and it["assignee_id"] == "u_worker"

    # rebuild 稳定（triage 决定走事件链）
    assert client.post("/api/system/rebuild-projections").status_code == 200
    assert client.get(f"/api/items/{iid2}").json()["status"] == "open"


def test_triage_snooze_sweep_resurface_and_clear(client, proj):
    iid = _land(client, proj, "暂缓我")
    r = _triage(client, iid, "snooze", days=3)
    assert r.status_code == 200, r.text
    it = client.get(f"/api/items/{iid}").json()
    assert it["snoozed_until"] is not None

    # 未到期：sweep 不动
    assert client.post("/api/automations/sweep", json={}).status_code == 200
    assert client.get(f"/api/items/{iid}").json()["snoozed_until"] is not None

    # 到期（合成回溯事件钉过期态）：sweep 复浮——清暂缓重新入队
    from datetime import date, timedelta
    events.emit(event_type="item.triage_snoozed", agg_type="item", agg_id=iid,
                project_id=proj, actor_type="human", actor_id="u_admin",
                payload={"until": (date.today() - timedelta(days=1)).isoformat()})
    swept = client.post("/api/automations/sweep", json={"force": True}).json()
    assert swept.get("resurfaced", 0) >= 1
    assert client.get(f"/api/items/{iid}").json()["snoozed_until"] is None

    # accept 清暂缓
    iid2 = _land(client, proj, "暂缓后接受")
    assert _triage(client, iid2, "snooze", days=5).status_code == 200
    assert _triage(client, iid2, "accept").status_code == 200
    it2 = client.get(f"/api/items/{iid2}").json()
    assert it2["snoozed_until"] is None and it2["status"] == "open"


def test_triage_action_guards(client, proj):
    it = client.post(f"/api/projects/{proj}/items",
                     json={"concept_id": "task", "title": "正常任务"}).json()
    # 非分诊态动作 → 409
    r = _triage(client, it["id"], "accept")
    assert r.status_code == 409
    # 分诊态非法动作 → 422
    iid = _land(client, proj, "乱动作")
    assert _triage(client, iid, "explode").status_code == 422
    # snooze 天数界
    assert _triage(client, iid, "snooze", days=0).status_code == 422
    assert _triage(client, iid, "snooze", days=31).status_code == 422


def test_triage_write_gate_network(client, proj):
    iid = _land(client, proj, "门禁项")  # local 模式先造数（intake-token 要 owner）
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    assert client.post("/api/users", json={
        "id": "u_out", "name": "外人", "password": "o-pass"}).status_code == 200
    config.settings.auth_mode = "network"
    try:
        assert client.post("/api/auth/logout").status_code == 200
        assert _triage(client, iid, "accept").status_code == 401
        assert client.post("/api/auth/login",
                           json={"user_id": "u_out", "password": "o-pass"}).status_code == 200
        assert _triage(client, iid, "accept").status_code == 403
    finally:
        config.settings.auth_mode = "local"


def test_dispatch_from_triage_moves_to_in_progress(client, proj):
    """引擎移动是可信路径（_move_item 不过白名单）——从分诊直接派 Agent
    自动出队进 in_progress（「派活即接受」，docs/01 §DH 如实入档）。"""
    iid = _land(client, proj, "派给我")
    conv = client.post("/api/conversations", json={
        "project_id": proj, "kind": "executing", "title": "分诊派活",
        "instruction": "处理", "item_id": iid}).json()
    r = client.post("/api/runs", json={"conversation_id": conv["id"],
                                       "agent_role": "dev-agent", "item_id": iid,
                                       "wait": True})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/items/{iid}").json()["status"] == "in_progress"


def test_queue_read_face_uses_list_filter(client, proj):
    for i in range(3):
        _land(client, proj, f"队列项{i}")
    # E2E 走查抓获：非分诊项在场才能照亮 status 显式参数曾未接线（被静默
    # 忽略——get_items 只认保存视图路径的 status，?status= 半传无效）
    client.post(f"/api/projects/{proj}/items",
                json={"concept_id": "task", "title": "正常在制品"})
    rows = client.get(f"/api/projects/{proj}/items", params={
        "status": "triage"}).json()["items"]
    assert len(rows) == 3
    assert all(x["status"] == "triage" for x in rows)
