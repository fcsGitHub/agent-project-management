"""Smoke 77 (M72): artifact surface closure — ① the membership gate (network
mode: outsider 403, viewer read-only); ② the listing+delete face; ③ the zip
handoff really contains the artifacts subtree."""
from __future__ import annotations

import io
import zipfile

import pytest

from apm import config


@pytest.fixture(autouse=True)
def _restore_identity():
    saved = config.settings.user_id
    yield
    config.settings.user_id = saved


@pytest.mark.smoke
def test_smoke_77_m72_artifact_gate_listing_export(client, tmp_data, isolated_ontologies):
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user

    ensure_default_user()
    assert client.post("/api/auth/login",
                       json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
    pid = client.post("/api/projects",
                      json={"name": "冒烟工件收口", "ontology": "software-dev"}).json()["id"]
    assert client.post("/api/users",
                       json={"id": "u_viewer77", "name": "只读", "password": "v-pass"}).status_code == 200
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": "u_viewer77", "role": "viewer"}).status_code == 200
    # outsider 在切 network 前创建（建用户是 admin 动作——network 下 viewer/外人 403）
    assert client.post("/api/users",
                       json={"id": "u_outsider77", "name": "外人", "password": "o-pass"}).status_code == 200
    assert client.put(f"/api/projects/{pid}/artifacts/artifacts/prd/ship.md",
                      json={"content": "# 交付 PRD\n\n验收即打包。\n", "message": "seed"}).status_code == 200

    # --- ① 权限门（network 模式）：viewer 只读 / 外人 403 -----------------------
    config.settings.auth_mode = "network"
    try:
        assert client.post("/api/auth/login",
                           json={"user_id": "u_viewer77", "password": "v-pass"}).status_code == 200
        assert client.get(f"/api/projects/{pid}/artifacts").status_code == 200
        assert client.put(f"/api/projects/{pid}/artifacts/artifacts/prd/other.md",
                          json={"content": "x", "message": "m"}).status_code == 403
        # outsider：读也 403
        assert client.post("/api/auth/login",
                           json={"user_id": "u_outsider77", "password": "o-pass"}).status_code == 200
        assert client.get(f"/api/projects/{pid}/artifacts").status_code == 403

        # --- ③ 导出：成员可打包（admin 重登），viewer 也能读面导出 ------------------
        assert client.post("/api/auth/login",
                           json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
        r = client.get(f"/api/projects/{pid}/artifacts/export")
        assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        assert any(n.endswith("artifacts/prd/ship.md") for n in zf.namelist())
    finally:
        config.settings.auth_mode = "local"
        config.settings.admin_password = ""

    # --- ② 清单+删除（local 模式收尾）：删除→清单消失→导出 404 ------------------
    assert client.delete(f"/api/projects/{pid}/artifacts/artifacts/prd/ship.md").status_code == 200
    arts = client.get(f"/api/projects/{pid}/artifacts").json()["artifacts"]
    assert all(a["path"] != "artifacts/prd/ship.md" for a in arts)
