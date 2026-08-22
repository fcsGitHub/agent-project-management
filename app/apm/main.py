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
        yield

    app = FastAPI(title="AgentPM", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from apm.content.artifacts import router as artifacts_router
    from apm.domains.conversations import router as conversations_router
    from apm.domains.events_api import router as events_router
    from apm.domains.features import router as features_router
    from apm.domains.items import router as items_router
    from apm.domains.ontology import router as ontology_router
    from apm.domains.projects import router as projects_router
    from apm.domains.stream import router as stream_router
    from apm.domains.system import router as system_router

    app.include_router(system_router, prefix="/api")
    app.include_router(events_router, prefix="/api")
    app.include_router(stream_router, prefix="/api")
    app.include_router(ontology_router, prefix="/api")
    app.include_router(projects_router, prefix="/api")
    app.include_router(features_router, prefix="/api")
    app.include_router(items_router, prefix="/api")
    app.include_router(conversations_router, prefix="/api")
    app.include_router(artifacts_router, prefix="/api")
    return app


app = create_app()
