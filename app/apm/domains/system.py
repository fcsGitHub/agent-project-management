"""System endpoints: health, projection rebuild."""
from __future__ import annotations

from fastapi import APIRouter

from apm import config

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "app": "AgentPM",
        "version": "0.1.0",
        "provider_mode": config.settings.provider_mode,
        "user": {"id": config.settings.user_id, "name": config.settings.user_name},
    }
