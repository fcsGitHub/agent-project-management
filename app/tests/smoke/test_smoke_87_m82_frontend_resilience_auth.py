"""Smoke 87 (M82): frontend resilience & auth hardening — ① source locks:
the zero-dependency ErrorBoundary (class component, app+page levels, chunk
load fallback) and route-level code splitting (React.lazy pages + Suspense +
pg() wrappers, no eager page imports left in App.tsx); ② the login lockout
round trip: 4×401 → 5th failure engages → 429+Retry-After (correct password
refused too) → exactly one session.login_locked audit event (transition
semantics) → window slides out → login recovers and the session writes."""
from __future__ import annotations

import time

import pytest

from apm import config
from apm.domains import auth_api

from tests.smoke.test_smoke_82_m77_delivery_surface import ROOT


@pytest.mark.smoke
def test_smoke_87_frontend_resilience_source_locks():
    eb = (ROOT / "web" / "src" / "components" / "ErrorBoundary.tsx").read_text(encoding="utf-8")
    # 零依赖 class 边界：React 只允许 class 充当错误边界；两级语义在文件内。
    assert "class ErrorBoundary extends Component" in eb
    assert "getDerivedStateFromError" in eb and "componentDidCatch" in eb
    assert '"app"' in eb and '"page"' in eb
    assert "isChunkLoadError" in eb  # 重部署旧 hash chunk 404 → 刷新引导
    assert 'from "react-error-boundary"' not in eb  # 零第三方依赖裁决（只锁 import 语句）

    app_tsx = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    # 路由级代码分割：页面全量 lazy（AppShell 例外是 components 非页面）。
    lazy_count = app_tsx.count("lazy(() => import(\"./pages/")
    assert lazy_count >= 27, f"lazy pages = {lazy_count}"
    # App 级兜底 + Suspense 挂载。
    assert '<ErrorBoundary level="app">' in app_tsx
    assert "<Suspense" in app_tsx
    # 页面级边界经 pg() 包裹（key=路由形态）。
    assert "function pg(" in app_tsx and 'level="page"' in app_tsx
    # 无残留的页面 eager import（页面引用只允许出现在 lazy 行内）。
    import re

    eager = [ln for ln in app_tsx.splitlines()
             if re.search(r'^import .*from "\./pages/', ln)]
    assert not eager, f"eager page imports remain: {eager}"


@pytest.mark.smoke
def test_smoke_87_login_lockout_roundtrip(client, tmp_data, isolated_ontologies):
    config.settings.admin_password = "admin-pass"
    from apm.domains.users import ensure_default_user

    ensure_default_user()
    config.settings.auth_mode = "network"
    auth_api._login_failures.clear()
    try:
        # 4 次失败仍是 401；第 5 次（达阈值那次）也是 401——锁定自下次尝试生效。
        for _ in range(auth_api.LOCKOUT_MAX_FAILURES):
            assert client.post("/api/auth/login",
                               json={"user_id": "u_admin", "password": "wrong"}).status_code == 401
        # 锁定中：正确密码也 429 + Retry-After。
        r = client.post("/api/auth/login",
                        json={"user_id": "u_admin", "password": "admin-pass"})
        assert r.status_code == 429, r.text
        retry_after = int(r.headers["Retry-After"])
        assert 0 < retry_after <= auth_api.LOCKOUT_WINDOW_SECONDS

        # 窗口滑出 → 自动解除 → 登录恢复且会话可写（回归既有链路）。
        auth_api._login_failures["u_admin"] = [
            time.monotonic() - auth_api.LOCKOUT_WINDOW_SECONDS - 1]
        assert client.post("/api/auth/login",
                           json={"user_id": "u_admin", "password": "admin-pass"}).status_code == 200
        assert client.post("/api/projects",
                           json={"name": "冒烟87", "ontology": "software-dev"}).status_code == 200
        # 转折点语义：锁定审计事件恰好一条。
        # M114-I339: 事件流不再对匿名开放——审计读在恢复登录之后，断言强度不变。
        evs = client.get("/api/events",
                         params={"event_type": "session.login_locked"}).json()["events"]
        assert len(evs) == 1 and evs[0]["payload"]["user_id"] == "u_admin"
    finally:
        auth_api._login_failures.clear()
        config.settings.auth_mode = "local"
        config.settings.admin_password = ""
