"""安全加固回归（本轮漏洞修复）：匿名不继承管理员、feed_key 不外泄、
畸形会话 cookie 不 500、git 路径穿越拒绝、重建投影需管理员、
带密码账号仅管理员可建、commit 注入拒绝。"""
from __future__ import annotations

import pytest

from apm import config


@pytest.fixture()
def project(client, tmp_data, isolated_ontologies):
    r = client.post("/api/projects",
                    json={"name": "安全回归", "ontology": "software-dev"})
    assert r.status_code == 200
    return r.json()


def test_anonymous_does_not_inherit_admin_in_network_mode(client, project):
    """H1：network 模式无会话的 GET 请求身份是 anonymous，不再是默认管理员
    ——owner-only 的 intake-token 端点必须拒绝（修复前匿名可领有效投递 token）。"""
    saved = config.settings.auth_mode
    config.settings.auth_mode = "network"
    try:
        r = client.get(f"/api/projects/{project['id']}/intake-token")
        assert r.status_code == 403
    finally:
        config.settings.auth_mode = saved


def test_users_list_never_leaks_feed_key(client, project):
    """H2：/api/users 是开放读端点，feed_key（持久读凭据）不得出现在响应里。"""
    client.get("/api/me/feed-key")  # ensure one exists
    users = client.get("/api/users").json()["users"]
    assert users and all("feed_key" not in u for u in users)


def test_malformed_session_cookie_is_rejected_not_500(client, project):
    """M3：非数字 expiry 的伪造 cookie 必须按无效会话处理（401/回退本地），
    不得让每个请求抛 ValueError 变 500。"""
    saved = config.settings.auth_mode
    config.settings.auth_mode = "network"
    try:
        r = client.get("/api/auth/me", cookies={"apm_session": "u_admin.notanumber.deadbeef"})
        assert r.status_code == 401
    finally:
        config.settings.auth_mode = saved


def test_artifact_path_sibling_escape_rejected(client, project):
    """H4：rel_path 用 ../<同前缀>-evil/ 穿越到兄弟目录必须被拒
    （修复前字符串 startswith 前缀校验可被绕过）。直接对路径哨兵断言，
    绕开 HTTP 客户端可能做的 URL 归一化。"""
    from apm.content import gitrepo

    pid = project["id"]
    for evil in (f"../{pid}-evil/x.md", "../../etc/passwd", "a/../../b.md"):
        with pytest.raises(gitrepo.GitError):
            gitrepo._safe_relpath(pid, evil)
    # 合法相对路径不受影响
    ok = gitrepo._safe_relpath(pid, "docs/deep/nested/a.md")
    assert ok.name == "a.md"


def test_rebuild_projections_requires_admin(client, project):
    """H5：重建投影会抹掉 users 运行时列——network 模式下仅管理员可调用。"""
    from apm.domains.users import ensure_default_user

    saved_mode = config.settings.auth_mode
    saved_pw = config.settings.admin_password
    config.settings.admin_password = "admin-pass"
    ensure_default_user()
    client.post("/api/users", json={"id": "qa-sec", "name": "QA", "password": "qa-pass"})
    config.settings.auth_mode = "network"
    try:
        assert client.post("/api/auth/login",
                           json={"user_id": "qa-sec", "password": "qa-pass"}).status_code == 200
        assert client.post("/api/system/rebuild-projections").status_code == 403
        assert client.post("/api/auth/login",
                           json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
        assert client.post("/api/system/rebuild-projections").status_code == 200
    finally:
        config.settings.auth_mode = saved_mode
        config.settings.admin_password = saved_pw


def test_password_account_creation_requires_admin_in_network_mode(client, project):
    """M2：network 模式下带密码的账号只能由管理员创建（OIDC JIT 无密码不受限）。"""
    from apm.domains.users import ensure_default_user

    saved_mode = config.settings.auth_mode
    saved_pw = config.settings.admin_password
    config.settings.admin_password = "admin-pass"
    ensure_default_user()
    client.post("/api/users", json={"id": "qa-pw", "name": "QA", "password": "qa-pass"})
    config.settings.auth_mode = "network"
    try:
        assert client.post("/api/auth/login",
                           json={"user_id": "qa-pw", "password": "qa-pass"}).status_code == 200
        # 普通成员给第三方发登录凭据 → 403
        assert client.post("/api/users",
                           json={"id": "backdoor", "name": "后门", "password": "x-pass"}).status_code == 403
        # 切回管理员即可创建
        assert client.post("/api/auth/login",
                           json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
        assert client.post("/api/users",
                           json={"id": "by-admin", "name": "合规", "password": "y-pass"}).status_code == 200
    finally:
        config.settings.auth_mode = saved_mode
        config.settings.admin_password = saved_pw


def test_artifact_commit_ref_injection_rejected(client, project):
    """M5：?commit= 非 hex（如 git 选项注入 --output=…）必须拒绝。"""
    from apm.content import gitrepo

    pid = project["id"]
    client.put(f"/api/projects/{pid}/artifacts/docs/a.md", json={"content": "# A"})
    r = client.get(f"/api/projects/{pid}/artifacts/docs/a.md",
                   params={"commit": "--output=evil"})
    assert r.status_code == 404
    assert isinstance(gitrepo.GitError("x"), Exception)
