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

    from apm.domains.events_api import router as events_router
    from apm.domains.stream import router as stream_router
    from apm.domains.system import router as system_router

    app.include_router(system_router, prefix="/api")
    app.include_router(events_router, prefix="/api")
    app.include_router(stream_router, prefix="/api")
    return app


app = create_app()
