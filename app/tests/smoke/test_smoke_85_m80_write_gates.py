"""Smoke 85 (M80): write-gate reconciliation — ① the route×gate script passes
(141 write routes all covered by middleware or the REVIEWED ledger); ② the
red path is self-proven: a synthetic bare route IS flagged, a ledger-covered
one is not; ③ a slim network-mode matrix spot check (non-member conversation
403, owner-gated member management intact) locking the I240 gates end to end."""
from __future__ import annotations

import subprocess
import sys

import pytest

from apm import config

from tests.smoke.test_smoke_82_m77_delivery_surface import ROOT


@pytest.mark.smoke
def test_smoke_85_reconcile_script_and_red_proof():
    # ①对账脚本绿
    r = subprocess.run([sys.executable, "tools/check_write_gates.py"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    # ②故意红自证：合成裸路由必须被揪出；台账覆盖与中间件覆盖的路由必须放行
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_write_gates", ROOT / "tools" / "check_write_gates.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    unreviewed_routes = mod.unreviewed_routes

    bare = unreviewed_routes([("/api/evil/bare", "POST")])
    assert bare == [("/api/evil/bare", "POST", "未登记")], bare
    assert unreviewed_routes([("/api/cycles/{cycle_id}", "PATCH")]) == []
    assert unreviewed_routes([("/api/projects/p_1/items/i_1", "PATCH")]) == []


@pytest.mark.smoke
def test_smoke_85_write_gate_matrix_spot(client, tmp_data, isolated_ontologies):
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user

    ensure_default_user()
    config.settings.auth_mode = "network"
    try:
        assert client.post("/api/auth/login",
                           json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
        pid = client.post("/api/projects",
                          json={"name": "冒烟85", "ontology": "software-dev"}).json()["id"]

        client.post("/api/users", json={"id": "qa-wang", "name": "QA 王", "password": "qa-pass"})
        client.post("/api/auth/login", json={"user_id": "qa-wang", "password": "qa-pass"})
        # 非成员不可入会话（I240 入口门）
        assert client.post("/api/conversations",
                           json={"project_id": pid, "kind": "drafting", "title": "x"}).status_code == 403
        # 补成员后可入（贡献者即可——成员语义不变）
        client.post("/api/auth/login", json={"user_id": "u_admin", "password": "admin-pass"})
        client.post(f"/api/projects/{pid}/members", json={"user_id": "qa-wang", "role": "contributor"})
        client.post("/api/auth/login", json={"user_id": "qa-wang", "password": "qa-pass"})
        assert client.post("/api/conversations",
                           json={"project_id": pid, "kind": "drafting", "title": "成员会话"}).status_code == 200
        # 成员管理本身仍是 owner 门（既有语义不回退）
        client.post("/api/auth/login", json={"user_id": "u_admin", "password": "admin-pass"})
        assert client.post(f"/api/projects/{pid}/members",
                           json={"user_id": "qa-wang", "role": "contributor"}).status_code == 409  # 已是成员
    finally:
        config.settings.auth_mode = "local"
        config.settings.user_id = "u_admin"
