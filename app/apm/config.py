"""Application settings (12-factor via env)."""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Storage root: events db + per-project content repos + assets repo.
    data_dir: Path = Path("data")
    # LLM provider: "replay" (default, deterministic fixtures), "record", "openai".
    provider_mode: str = "replay"
    llm_api_base: str = "http://localhost:8000/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4.1-mini"
    # UI-Agent (intent parsing) can use a cheaper model; falls back to llm_model.
    ui_agent_model: str = ""
    # Single-user MVP: the human actor behind every UI action.
    user_id: str = "u_admin"
    user_name: str = "李雷"

    model_config = {"env_prefix": "APM_", "env_file": ".env", "extra": "ignore"}

    @property
    def db_path(self) -> Path:
        return self.data_dir / "apm.db"

    @property
    def content_root(self) -> Path:
        return self.data_dir / "content"

    @property
    def assets_repo_path(self) -> Path:
        return self.data_dir / "assets-repo"

    @property
    def fixtures_dir(self) -> Path:
        return self.data_dir / "fixtures"

    @property
    def repo_root(self) -> Path:
        """Monorepo root (holds ontologies/, agents/, docs/)."""
        here = Path(__file__).resolve()  # app/apm/config.py
        return here.parents[2]

    @property
    def ontology_dir(self) -> Path:
        return self.repo_root / "ontologies"

    @property
    def agents_dir(self) -> Path:
        return self.repo_root / "agents"


settings = Settings()
