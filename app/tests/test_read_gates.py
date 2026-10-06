"""M76-I228: read-side gate audit (docs/01 §BU.1, API1:2023 BOLA matrix) —
auth_gate has left GETs open since M8 and pushed read gates into the domains;
items/comments/artifacts(M72) had them but the assets org library, template
packs, expense ledger and automation rules did not. Matrix: org-level reads
(assets / template-packs) gate on LOGIN (401 anonymous — there is no project
to be a member of); project-level reads (expenses / automations) gate on
PROJECT MEMBERSHIP (403 for anonymous and outsiders alike). Local mode stays
trusted (every other test depends on it)."""
import pytest

from apm import config


@pytest.fixture()
def pid(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "读门审计", "ontology": "software-dev", "requirement": "I228"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    # seed one row on each audited surface (local mode — trusted)
    assert client.put(f"/api/projects/{pid}/artifacts/test/g.md",
                      json={"content": "# g", "message": "qa: gate"}).status_code == 200
    art = client.get(f"/api/projects/{pid}/artifacts").json()["artifacts"][0]
    client.post("/api/assets", json={
        "source_project_id": pid, "artifact_path": art["path"], "commit": art["commit"],
        "library": "test", "kind": "test-suite", "title": "门禁资产"})
    client.post(f"/api/projects/{pid}/expenses", json={
        "description": "门禁费用", "qty": 1, "unit_price": 1,
        "currency": "CNY", "spent_on": "2026-09-30"})
    client.post(f"/api/projects/{pid}/automations", json={
        "name": "读门审计规则", "trigger_event": "item.created",
        "condition": {"concept_id": "bug"},
        "action": {"type": "set_field", "field_id": "severity", "value": "P0"}})
    return pid


def _switch_network_with(client, users: list[tuple[str, str]]):
    """Create users BEFORE the switch (POST /users is admin-only in network
    mode — smoke 77 lesson), then flip auth_mode."""
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    for uid, pwd in users:
        assert client.post("/api/users", json={"id": uid, "name": uid, "password": pwd}).status_code == 200, uid
    config.settings.auth_mode = "network"


def _login(client, uid, pwd):
    assert client.post("/api/auth/login", json={"user_id": uid, "password": pwd}).status_code == 200


def test_org_reads_gate_on_login(client, pid):
    _switch_network_with(client, [("outsider", "out-pass")])
    try:
        # anonymous: org reads 401 (login required), project reads 403 (no membership)
        assert client.get("/api/assets").status_code == 401
        assert client.get("/api/assets/insights").status_code == 401
        assert client.get("/api/template-packs").status_code == 401
        assert client.get(f"/api/projects/{pid}/expenses").status_code == 403
        assert client.get(f"/api/projects/{pid}/automations").status_code == 403

        # logged-in outsider: org library readable (instance member), project ledger not
        _login(client, "outsider", "out-pass")
        assert client.get("/api/assets").status_code == 200
        assert client.get("/api/template-packs").status_code == 200
        assert client.get(f"/api/projects/{pid}/expenses").status_code == 403
        assert client.get(f"/api/projects/{pid}/automations").status_code == 403

        # logged-in owner: everything readable
        assert client.post("/api/auth/logout").status_code == 200
        _login(client, "u_admin", "admin-pass")
        assert client.get(f"/api/projects/{pid}/expenses").json()["expenses"]
        assert client.get(f"/api/projects/{pid}/automations").json()["rules"]

        # feed surfaces keep their M45 feed_key semantics (keyless → 422), untouched here
        assert client.get(f"/api/projects/{pid}/feed.atom").status_code == 422
    finally:
        config.settings.auth_mode = "local"
        config.settings.admin_password = ""
        client.post("/api/auth/logout")


def test_local_mode_stays_trusted(client, pid):
    # no login at all — local mode gates return early (every other test relies on this)
    assert client.get("/api/assets").status_code == 200
    assert client.get("/api/template-packs").status_code == 200
    assert client.get(f"/api/projects/{pid}/expenses").status_code == 200
    assert client.get(f"/api/projects/{pid}/automations").status_code == 200


# ---------------------------------------------------------------- M114-I339
# 读面门禁第二轮（docs/01 §DE）：M76 第一轮收了 org/项目级列表面，但全局 id 单
# 资源读（runs/milestones/cycles/features/attachments/time_entries/conversations
# detail）与聚合列表（runs/conversations/approvals/events）仍是同域写面有门、
# 读面裸奔——「修缝要问同类门还有几道口」（docs/10 附录 C M110 ②）。外加跨项目
# 写收口：bulk-decision / ui_command confirm 的批量审批、run 绑定别家 item、
# expense/risks/conversations 的跨项目外键引用。


@pytest.fixture()
def rich(client, tmp_data, isolated_ontologies):
    """本地模式（trusted）造齐被审计资源：项目 A 全资源类型 + 项目 B 外部引用源。"""
    from datetime import date

    from apm.core import events

    pid = client.post("/api/projects", json={
        "name": "读门矩阵A", "ontology": "software-dev", "requirement": "I339"}).json()["id"]
    pid_b = client.post("/api/projects", json={
        "name": "读门矩阵B", "ontology": "software-dev", "requirement": "I339"}).json()["id"]
    assert client.post(f"/api/projects/{pid}/items",
                       json={"concept_id": "task", "title": "矩阵任务"}).status_code == 200
    item = client.get(f"/api/projects/{pid}/items").json()["items"][0]
    assert client.post(f"/api/projects/{pid_b}/items",
                       json={"concept_id": "task", "title": "B项目任务"}).status_code == 200
    item_b = client.get(f"/api/projects/{pid_b}/items").json()["items"][0]
    assert client.post(f"/api/projects/{pid}/milestones",
                       json={"title": "矩阵里程碑", "due_date": "2026-12-01"}).status_code == 200
    ms = client.get(f"/api/projects/{pid}/milestones").json()["milestones"][0]
    assert client.post(f"/api/projects/{pid}/cycles", json={
        "name": "矩阵周期", "start_date": "2026-10-01", "end_date": "2026-10-14"}).status_code == 200
    cyc = client.get(f"/api/projects/{pid}/cycles").json()["cycles"][0]
    assert client.post(f"/api/projects/{pid}/features",
                       json={"title": "矩阵功能"}).status_code == 200
    feat = client.get(f"/api/projects/{pid}/features").json()["features"][0]
    assert client.post(f"/api/projects/{pid_b}/features",
                       json={"title": "B项目功能"}).status_code == 200
    feat_b = client.get(f"/api/projects/{pid_b}/features").json()["features"][0]
    conv = client.post("/api/conversations",
                       json={"project_id": pid, "kind": "drafting"}).json()
    assert client.post(f"/api/items/{item['id']}/time_entries", json={
        "minutes": 30, "spent_on": date.today().isoformat()}).status_code == 200
    te = client.get(f"/api/items/{item['id']}/time_entries").json()["entries"][0]
    r = client.post(f"/api/items/{item['id']}/attachments",
                    files={"file": ("matrix.txt", b"matrix", "text/plain")})
    assert r.status_code == 200, r.text
    att = r.json()
    # 合成 run/span/审批（M64 惯例：run.requested 必带 conversation_id）
    events.emit(event_type="run.requested", agg_type="run", agg_id="run_matrix",
                project_id=pid,
                payload={"conversation_id": conv["id"], "agent_role": "dev-agent",
                         "instruction": "矩阵"})
    events.emit(event_type="run.span_opened", agg_type="span", agg_id="span_matrix",
                project_id=pid,
                payload={"run_id": "run_matrix", "name": "analyze", "span_kind": "llm"})
    events.emit(event_type="approval.requested", agg_type="approval", agg_id="apr_matrix",
                project_id=pid,
                payload={"kind": "gate", "snapshot": {"gate": "prd_review", "title": "矩阵门"}})
    # 一条待确认的 ui_command（批量批准语义，L1 规则可解析）
    uic = client.post("/api/ui_commands", json={
        "utterance": "批量批准", "page_state": {"project_id": pid}}).json()
    return {"pid": pid, "pid_b": pid_b, "item": item, "item_b": item_b,
            "milestone": ms, "cycle": cyc, "feature": feat, "feature_b": feat_b,
            "conv": conv, "time_entry": te, "attachment": att, "uic": uic}


def test_id_path_reads_gate_on_membership(client, rich):
    _switch_network_with(client, [("outsider", "out-pass")])
    try:
        pid, cid = rich["pid"], rich["conv"]["id"]
        # anonymous: raw event stream and user directory demand login (401)
        assert client.get("/api/events").status_code == 401
        assert client.get("/api/users").status_code == 401
        _login(client, "outsider", "out-pass")
        # id-path single reads: 403 outsiders (M76 project-read convention);
        # conversation detail 404s like its export sibling (_visible family)
        assert client.get("/api/runs/run_matrix").status_code == 403
        assert client.get("/api/runs/run_matrix/spans").status_code == 403
        assert client.get("/api/runs/run_matrix/timeline").status_code == 403
        assert client.get("/api/runs").json()["runs"] == []
        assert client.get(f"/api/conversations/{cid}").status_code == 404
        assert client.get(f"/api/conversations/{cid}/messages").status_code == 404
        assert client.get("/api/conversations").json()["conversations"] == []
        assert client.get("/api/approvals").json()["approvals"] == []
        assert client.get(f"/api/milestones/{rich['milestone']['id']}").status_code == 403
        assert client.get(f"/api/milestones/{rich['milestone']['id']}/burndown").status_code == 403
        assert client.get(f"/api/cycles/{rich['cycle']['id']}/burndown").status_code == 403
        assert client.get(f"/api/cycles/{rich['cycle']['id']}/retrospective").status_code == 403
        assert client.get(f"/api/features/{rich['feature']['id']}").status_code == 403
        assert client.get(f"/api/time_entries/{rich['time_entry']['id']}").status_code == 403
        assert client.get(f"/api/items/{rich['item']['id']}/attachments").status_code == 403
        assert client.get("/api/events", params={"project_id": pid}).status_code == 403
        assert client.get(f"/api/projects/{pid}/events/export").status_code == 403
        # member (bootstrap admin owns project A) sees everything
        assert client.post("/api/auth/logout").status_code == 200
        _login(client, "u_admin", "admin-pass")
        assert client.get("/api/runs/run_matrix").status_code == 200
        assert client.get("/api/runs/run_matrix/spans").json()["spans"]
        assert client.get("/api/runs/run_matrix/timeline").json()["entries"]
        assert client.get("/api/runs").json()["runs"]
        assert client.get(f"/api/conversations/{cid}").status_code == 200
        assert client.get("/api/conversations").json()["conversations"]
        assert client.get("/api/approvals").json()["approvals"]
        assert client.get(f"/api/milestones/{rich['milestone']['id']}").status_code == 200
        assert client.get(f"/api/milestones/{rich['milestone']['id']}/burndown").status_code == 200
        assert client.get(f"/api/cycles/{rich['cycle']['id']}/burndown").status_code == 200
        assert client.get(f"/api/cycles/{rich['cycle']['id']}/retrospective").status_code == 200
        assert client.get(f"/api/features/{rich['feature']['id']}").status_code == 200
        assert client.get(f"/api/time_entries/{rich['time_entry']['id']}").status_code == 200
        assert client.get(f"/api/items/{rich['item']['id']}/attachments").status_code == 200
        assert client.get("/api/events", params={"project_id": pid}).json()["events"]
        assert client.get(f"/api/projects/{pid}/events/export").status_code == 200
    finally:
        config.settings.auth_mode = "local"
        config.settings.admin_password = ""
        client.post("/api/auth/logout")


def test_cross_project_writes_refused(client, rich):
    from apm.core import db

    _switch_network_with(client, [("outsider", "out-pass")])
    _login(client, "outsider", "out-pass")
    try:
        # ① bulk-decision: outsider must not decide project A's gate (B1)
        r = client.post("/api/approvals/bulk-decision",
                        json={"ids": ["apr_matrix"], "decision": "approved"}).json()
        assert r["results"][0].get("error"), r
        row = db.get_conn().execute(
            "SELECT status FROM approvals WHERE id = 'apr_matrix'").fetchone()
        assert row["status"] == "pending"
        # ② ui_command confirm: per-approval gate keeps the outsider at zero (B3)
        r = client.post(f"/api/ui_commands/{rich['uic']['id']}/confirm").json()
        assert r["results"][0]["approved"] == 0, r
        assert db.get_conn().execute(
            "SELECT status FROM approvals WHERE id = 'apr_matrix'").fetchone()["status"] == "pending"
        # ③ member of A: the same bulk confirm approves (positive control)
        assert client.post("/api/auth/logout").status_code == 200
        _login(client, "u_admin", "admin-pass")
        r = client.post(f"/api/ui_commands/{rich['uic']['id']}/confirm")
        assert r.status_code in (200, 422)  # 422 = already executed by ② above
        r = client.post("/api/approvals/bulk-decision",
                        json={"ids": ["apr_matrix"], "decision": "approved"})
        assert r.status_code == 200
        assert db.get_conn().execute(
            "SELECT status FROM approvals WHERE id = 'apr_matrix'").fetchone()["status"] == "approved"
        # ④ run bound to a foreign item is refused 422 (B2)
        r = client.post("/api/runs", json={
            "conversation_id": rich["conv"]["id"], "item_id": rich["item_b"]["id"]})
        assert r.status_code == 422, r.text
        # ⑤ foreign FK references on write faces: 422 same-project validation (B4)
        r = client.post(f"/api/projects/{rich['pid']}/expenses", json={
            "description": "外键", "qty": 1, "unit_price": 1, "currency": "CNY",
            "spent_on": "2026-10-06", "item_id": rich["item_b"]["id"]})
        assert r.status_code == 422, r.text
        r = client.post(f"/api/projects/{rich['pid']}/risks", json={
            "title": "外键风险", "probability": 2, "impact": 2,
            "related_item_id": rich["item_b"]["id"]})
        assert r.status_code == 422, r.text
        r = client.post("/api/conversations", json={
            "project_id": rich["pid"], "kind": "drafting",
            "feature_id": rich["feature_b"]["id"]})
        assert r.status_code == 422, r.text
    finally:
        config.settings.auth_mode = "local"
        config.settings.admin_password = ""
        client.post("/api/auth/logout")
