"""Smoke 81 (M76): audit-round closure — ① the I228 read-gate matrix end to
end in network mode: anonymous gets 401 on the org library (assets / template
packs) and 403 on project ledgers (expenses / automations), a logged-in
outsider reads the org library but not the project ledger, the owner reads
everything; ② the M75 retire/archive state machine holds under the new gates
(retire → archive → repeat 409, all in a logged-in session); ③ local mode
remains trusted (no login anywhere)."""
from __future__ import annotations

import pytest

from apm import config


@pytest.fixture(autouse=True)
def _restore_mode():
    saved_mode = config.settings.auth_mode
    saved_admin = config.settings.admin_password
    yield
    config.settings.auth_mode = saved_mode
    config.settings.admin_password = saved_admin


@pytest.mark.smoke
def test_smoke_81_m76_audit_round(client, tmp_data, isolated_ontologies):
    pid = client.post("/api/projects",
                      json={"name": "冒烟审计", "ontology": "software-dev",
                            "requirement": "M76"}).json()["id"]
    art = client.put(f"/api/projects/{pid}/artifacts/test/smoke81.md",
                     json={"content": "# 冒烟81", "message": "qa: smoke81"}).json()
    asset = client.post("/api/assets", json={
        "source_project_id": pid, "artifact_path": art["path"], "commit": art["commit"],
        "library": "test", "kind": "test-suite", "title": "冒烟门禁资产"}).json()
    client.post(f"/api/projects/{pid}/expenses", json={
        "description": "冒烟门禁费用", "qty": 1, "unit_price": 9,
        "currency": "CNY", "spent_on": "2026-09-30"})
    client.post(f"/api/projects/{pid}/automations", json={
        "name": "冒烟门禁规则", "trigger_event": "item.created",
        "action": {"type": "set_field", "field_id": "severity", "value": "P0"}})

    # --- ① network 模式读门矩阵 ---------------------------------------------------
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user
    ensure_default_user()
    assert client.post("/api/users", json={"id": "s81out", "name": "外人", "password": "out81"}).status_code == 200
    config.settings.auth_mode = "network"

    assert client.get("/api/assets").status_code == 401
    assert client.get("/api/template-packs").status_code == 401
    assert client.get(f"/api/projects/{pid}/expenses").status_code == 403
    assert client.get(f"/api/projects/{pid}/automations").status_code == 403

    assert client.post("/api/auth/login", json={"user_id": "s81out", "password": "out81"}).status_code == 200
    assert client.get("/api/assets").status_code == 200
    assert client.get(f"/api/projects/{pid}/expenses").status_code == 403
    assert client.post("/api/auth/logout").status_code == 200

    assert client.post("/api/auth/login", json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
    assert client.get(f"/api/projects/{pid}/expenses").json()["expenses"]
    assert client.get(f"/api/projects/{pid}/automations").json()["rules"]

    # --- ② 退役/归档状态机在门禁会话内成立 ---------------------------------------
    assert client.post(f"/api/assets/{asset['id']}/deprecate").status_code == 200
    assert client.get(f"/api/assets/{asset['id']}").json()["status"] == "deprecated"
    assert client.post(f"/api/assets/{asset['id']}/archive").status_code == 200
    assert client.post(f"/api/assets/{asset['id']}/archive").status_code == 409
    assert [x for x in client.get("/api/assets").json()["assets"] if x["id"] == asset["id"]] == []
    assert client.get(f"/api/assets/{asset['id']}").json()["status"] == "archived"
    assert client.post("/api/auth/logout").status_code == 200

    # --- ③ local 模式保持免登录可信（显式切回；fixture 兜底恢复）------------------
    config.settings.auth_mode = "local"
    assert client.get("/api/assets").status_code == 200
