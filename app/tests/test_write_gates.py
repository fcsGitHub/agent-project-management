"""M80-I240 写门对齐矩阵（docs/01 §BY.1，OWASP API1 端点×对象×角色）：
M80 审计实证白名单 allow-if-matched 的缺口——cycles/milestones/features/
risks 的 id-path 写端点既不在中间件白名单、域内又零门禁（非成员可改期/
取消/关闭任意项目资源），assets 六写、runs/conversations 入口同题。补门
后矩阵证明：network 模式下非成员 403 / 成员 200 / local 可信不变。
M45-M76 读面矩阵（test_read_gates）的写面姊妹篇。"""
from __future__ import annotations

import pytest

from apm import config


@pytest.fixture()
def _net(client, tmp_data, isolated_ontologies):
    """network 模式 + 双身份（u_admin 建数据·qa-wang 非成员发起写）。"""
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user

    ensure_default_user()
    config.settings.auth_mode = "network"
    r = client.post("/api/auth/login", json={"user_id": "u_admin", "password": "admin-pass"})
    assert r.status_code == 200, r.text
    yield
    config.settings.auth_mode = "local"
    config.settings.user_id = "u_admin"


def _login(client, user_id: str, password: str) -> None:
    r = client.post("/api/auth/login", json={"user_id": user_id, "password": password})
    assert r.status_code == 200, r.text


def _mk_fixture_as_admin(client):
    """u_admin 建项目与各资源——返回 (project_id, 资源 id 字典)。"""
    r = client.post("/api/projects", json={"name": "写门矩阵", "ontology": "software-dev"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    r = client.post(f"/api/projects/{pid}/cycles",
                    json={"name": "Sprint 1", "start_date": "2026-10-05", "end_date": "2026-10-18"})
    assert r.status_code == 200, r.text
    cycle = r.json()["id"]
    r = client.post(f"/api/projects/{pid}/milestones",
                    json={"title": "M1", "due_date": "2026-10-15"})
    assert r.status_code == 200, r.text
    ms = r.json()["id"]
    r = client.post(f"/api/projects/{pid}/features",
                    json={"title": "特性甲", "description": "x"})
    assert r.status_code == 200, r.text
    feat = r.json()["id"]
    r = client.post(f"/api/projects/{pid}/risks",
                    json={"title": "风险甲", "probability": 2, "impact": 2})
    assert r.status_code == 200, r.text
    risk = r.json()["id"]
    return pid, {"cycle": cycle, "milestone": ms, "feature": feat, "risk": risk}


def test_nonmember_cannot_mutate_four_domains(client, _net):
    pid, ids = _mk_fixture_as_admin(client)
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "password": "qa-pass"})
    _login(client, "qa-wang", "qa-pass")

    # 非成员逐格 403（改/删/派生写）
    assert client.patch(f"/api/cycles/{ids['cycle']}", json={"name": "抢改"}).status_code == 403
    assert client.delete(f"/api/cycles/{ids['cycle']}").status_code == 403
    assert client.patch(f"/api/milestones/{ids['milestone']}", json={"title": "抢改"}).status_code == 403
    assert client.delete(f"/api/milestones/{ids['milestone']}").status_code == 403
    assert client.patch(f"/api/features/{ids['feature']}", json={"title": "抢改"}).status_code == 403
    assert client.post(f"/api/features/{ids['feature']}/archive").status_code == 403
    assert client.patch(f"/api/risks/{ids['risk']}", json={"probability": 3}).status_code == 403
    assert client.post(f"/api/risks/{ids['risk']}/close").status_code == 403
    # 非成员不可入会话/发起 run（POST 无 id 段不匹配白名单的入口）
    assert client.post("/api/conversations",
                       json={"project_id": pid, "kind": "drafting", "title": "闯入"}).status_code == 403


def test_member_can_mutate_and_viewer_cannot(client, _net):
    pid, ids = _mk_fixture_as_admin(client)
    client.post("/api/users", json={"id": "dev-zhang", "name": "Dev 张", "password": "dev-pass"})
    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "password": "qa-pass"})
    client.post(f"/api/projects/{pid}/members", json={"user_id": "dev-zhang", "role": "contributor"})
    client.post(f"/api/projects/{pid}/members", json={"user_id": "qa-wang", "role": "viewer"})

    _login(client, "qa-wang", "qa-pass")
    assert client.patch(f"/api/cycles/{ids['cycle']}", json={"name": "viewer 改"}).status_code == 403

    _login(client, "dev-zhang", "dev-pass")
    assert client.patch(f"/api/cycles/{ids['cycle']}", json={"name": "Sprint 1 改"}).status_code == 200
    assert client.patch(f"/api/milestones/{ids['milestone']}", json={"title": "M1 改"}).status_code == 200
    assert client.patch(f"/api/risks/{ids['risk']}", json={"probability": 3}).status_code == 200
    assert client.post("/api/conversations",
                       json={"project_id": pid, "kind": "drafting", "title": "成员会话"}).status_code == 200


def test_asset_write_gates(client, _net):
    pid, _ = _mk_fixture_as_admin(client)
    art = client.put(f"/api/projects/{pid}/artifacts/test/gate.md",
                     json={"content": "# 门禁样本", "message": "qa: gate"}).json()
    asset = client.post("/api/assets", json={
        "source_project_id": pid, "artifact_path": art["path"], "commit": art["commit"],
        "library": "test", "kind": "test-suite", "title": "门禁资产"}).json()["id"]

    client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "password": "qa-pass"})
    _login(client, "qa-wang", "qa-pass")
    # 非成员不可沉淀（from 侧项目写语义）
    assert client.post("/api/assets", json={
        "source_project_id": pid, "artifact_path": art["path"], "commit": art["commit"],
        "library": "test", "kind": "test-suite", "title": "非成员沉淀"}).status_code == 403
    # org 管理动作=实例成员门（登录即可——org 库成员共治语义·与读面同门）
    assert client.post(f"/api/assets/{asset}/deprecate").status_code == 200
    assert client.post(f"/api/assets/{asset}/archive").status_code == 200

    # 成员 deposit 正常
    _login(client, "u_admin", "admin-pass")
    assert client.post("/api/assets", json={
        "source_project_id": pid, "artifact_path": art["path"], "commit": art["commit"],
        "library": "test", "kind": "test-suite", "title": "成员沉淀"}).status_code == 200


def test_reconcile_script_covers_all():
    """路由×门禁对账：141 条写路由必须全部命中中间件/台账（I240 防腐本体）。"""
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    r = subprocess.run([sys.executable, "tools/check_write_gates.py"],
                       cwd=root, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
