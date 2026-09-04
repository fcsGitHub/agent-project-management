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
    # Auth (M8-I26): "local" = single-user, no login (dev/demo default);
    # "network" = mutations require a logged-in session. SSO deferred (V3).
    auth_mode: str = "local"
    session_ttl_hours: int = 24
    # Instance secret for session signing; empty → generated once and persisted
    # to data_dir/secret.key so sessions survive restarts.
    secret_key: str = ""
    # APM_ADMIN_PASSWORD: (re)apply the default admin's password on boot.
    admin_password: str = ""
    # Email channel (M11-I35): entirely optional — when host/from are unset the
    # mailer stays off and behavior is identical to pre-M11. smtp_tls adds
    # STARTTLS (587); port 465 implies SMTP_SSL.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = ""
    smtp_tls: bool = True
    # OIDC single sign-on (M17): entirely optional — issuer/client_id/secret all
    # set enables the feature, otherwise it stays off (same semantics as SMTP).
    # allowed_groups: comma-separated IdP group names; empty disables the group
    # gate (any authenticated IdP user with a verified email may JIT).
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = ""
    oidc_allowed_groups: str = ""
    # Tests redirect ontology YAML here (learning writes back to this dir).
    ontology_dir_override: Path | None = None
    # Tests redirect agents/ here (ontology pack import writes role files).
    agents_dir_override: Path | None = None

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
        if self.ontology_dir_override is not None:
            return self.ontology_dir_override
        return self.repo_root / "ontologies"

    @property
    def agents_dir(self) -> Path:
        if self.agents_dir_override is not None:
            return self.agents_dir_override
        return self.repo_root / "agents"


settings = Settings()
