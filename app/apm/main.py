"""AgentPM FastAPI application assembly."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apm import config


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Ensure storage directories exist before serving traffic.
        config.settings.data_dir.mkdir(parents=True, exist_ok=True)
        config.settings.content_root.mkdir(parents=True, exist_ok=True)
        config.settings.fixtures_dir.mkdir(parents=True, exist_ok=True)
        from apm.core import projections
        from apm.core.db import init_db

        init_db()
        projections.ensure_handlers_registered()
        from apm.runtime.engine import install_runkeeper_hooks, recover_interrupted_runs

        install_runkeeper_hooks()
        recover_interrupted_runs()  # crash compensation (dsh mode)
        from apm.domains.assets import install_agent_tools

        install_agent_tools()
        from apm.domains.users import ensure_default_user

        ensure_default_user()
        from apm.domains.template_packs import register_builtin_packs

        register_builtin_packs()  # 模板库启动登记（幂等，M7-I23）
        from apm.domains.automations import install_automation_engine

        install_automation_engine()  # 自动化引擎挂 post-emit hook（幂等，M9-I29）
        from apm.domains.webhooks import install_webhooks_engine

        install_webhooks_engine()  # webhook 入队 hook + 后台投递线程（幂等，M10-I32）
        from apm.domains.mailer import install_mailer

        install_mailer()  # 邮件通道入队 hook + 后台发送线程（幂等，M11-I35）
        yield

    app = FastAPI(title="AgentPM", version="0.1.0", lifespan=lifespan)

    from fastapi import Request
    from fastapi.responses import JSONResponse

    from apm.core import events
    from apm.core.security import SESSION_COOKIE, session_user

    @app.middleware("http")
    async def auth_gate(request: Request, call_next):
        """network 模式（M8-I26/I27/I28）：未登录拒绝一切 /api 写请求；有会话则
        按项目成员角色放行（owner/contributor 可写，viewer 与非成员 403 并落
        审计），并把登录人设为本请求的事件 actor（contextvar 随线程池继承）。
        GET 保持开放；local 模式零影响。"""
        actor_token = None
        if config.settings.auth_mode == "network":
            path = request.url.path
            user_id = None
            if path.startswith("/api/") and not path.startswith("/api/auth/"):
                user_id = session_user(request.cookies.get(SESSION_COOKIE))
                if request.method not in ("GET", "HEAD", "OPTIONS"):
                    if not user_id:
                        return JSONResponse({"detail": "login required"}, status_code=401)
                    from apm.domains.members import check_project_write, project_id_for_path

                    project_id = project_id_for_path(path)
                    if project_id:
                        allowed, role = check_project_write(project_id, user_id)
                        if not allowed:
                            events.emit(
                                event_type="access.denied",
                                agg_type="project",
                                agg_id=project_id,
                                project_id=project_id,
                                actor_type="human",
                                actor_id=user_id,
                                payload={"user_id": user_id, "role": role,
                                         "path": path,
                                         "summary": f"写入被拒绝：{user_id}（{role or '非成员'}）@ {project_id}"},
                            )
                            return JSONResponse({"detail": "forbidden"}, status_code=403)
            # 登录人即事件 actor（I28）：本请求内所有 emit 归到该身份。
            if user_id:
                actor_token = events.set_current_actor(user_id)
        try:
            return await call_next(request)
        finally:
            if actor_token is not None:
                events.reset_current_actor(actor_token)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from apm.content.artifacts import router as artifacts_router
    from apm.domains.approvals import router as approvals_router
    from apm.domains.assets import router as assets_router
    from apm.domains.automations import router as automations_router
    from apm.domains.auth_api import router as auth_router
    from apm.domains.conversations import router as conversations_router
    from apm.domains.events_api import router as events_router
    from apm.domains.features import router as features_router
    from apm.domains.feed import router as feed_router
    from apm.domains.items import router as items_router
    from apm.domains.members import router as members_router
    from apm.domains.nl import router as nl_router
    from apm.domains.notifications import router as notifications_router
    from apm.domains.ontology import router as ontology_router
    from apm.domains.ontology_learn import router as ontology_learn_router
    from apm.domains.ontology_versions import router as ontology_versions_router
    from apm.domains.ontology_cq import router as ontology_cq_router
    from apm.domains.ontology_pack import router as ontology_pack_router
    from apm.domains.orchestrator_api import router as orchestrator_router
    from apm.domains.projects import router as projects_router
    from apm.domains.reports import router as reports_router
    from apm.domains.runs import router as runs_router
    from apm.domains.stream import router as stream_router
    from apm.domains.system import router as system_router
    from apm.domains.template_packs import router as template_packs_router
    from apm.domains.users import router as users_router
    from apm.domains.webhooks import router as webhooks_router

    app.include_router(system_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(events_router, prefix="/api")
    app.include_router(stream_router, prefix="/api")
    app.include_router(ontology_router, prefix="/api")
    app.include_router(ontology_learn_router, prefix="/api")
    app.include_router(ontology_versions_router, prefix="/api")
    app.include_router(ontology_cq_router, prefix="/api")
    app.include_router(ontology_pack_router, prefix="/api")
    app.include_router(template_packs_router, prefix="/api")
    app.include_router(users_router, prefix="/api")
    app.include_router(webhooks_router, prefix="/api")
    app.include_router(notifications_router, prefix="/api")
    app.include_router(feed_router, prefix="/api")
    app.include_router(webhooks_router, prefix="/api")
    app.include_router(projects_router, prefix="/api")
    app.include_router(reports_router, prefix="/api")
    app.include_router(members_router, prefix="/api")
    app.include_router(automations_router, prefix="/api")
    app.include_router(features_router, prefix="/api")
    app.include_router(items_router, prefix="/api")
    app.include_router(conversations_router, prefix="/api")
    app.include_router(artifacts_router, prefix="/api")
    app.include_router(approvals_router, prefix="/api")
    app.include_router(assets_router, prefix="/api")
    app.include_router(runs_router, prefix="/api")
    app.include_router(orchestrator_router, prefix="/api")
    app.include_router(nl_router, prefix="/api")
    return app


app = create_app()
