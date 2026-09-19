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
    llm_model: str = "glm-5.3"
    # Wire protocol for the real provider: "openai" (OpenAI SDK chat/completions)
    # or "anthropic" (messages API via httpx); "auto" picks anthropic when the
    # base URL contains "/anthropic" (e.g. Zhipu's coding-plan endpoint).
    llm_protocol: str = "auto"
    # Reasoning models spend completion budget on invisible thinking, so the
    # ceiling must be generous or `content` comes back empty (finish=length).
    # GLM-5.x thinks in hundreds of tokens before answering; artifact-writing
    # nodes need headroom — 16384 is a safe floor.
    llm_max_tokens: int = 16384
    llm_timeout_s: int = 180
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
    # Webhook SSRF 防护（默认开）：拒绝私网/环回/链路本地投递目标；测试或
    # 内网集成场景显式放开（APM_WEBHOOK_ALLOW_PRIVATE=true）。
    webhook_allow_private: bool = False
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
    # I98 daily-sweep ticker: enabled in production by default; the test suite
    # turns it off (conftest) so background sweeps can't race explicit ones.
    scheduler_enabled: bool = True
    # I105 due-date reminder window (days ahead, inclusive of today).
    due_soon_days: int = 3
    # I118 overload flag on the workload page: strictly more active items than
    # this marks a member 「⚠ 超载」— detection only, never auto-rescheduling.
    workload_overload_threshold: int = 5
    # I120 inbound-mail filters (comma-separated; a hit means silently ignore,
    # with the imap.message_processed event as the audit trail).
    imap_ignore_addresses: str = ""   # exact addresses or @domain suffixes
    imap_ignore_keywords: str = ""    # subject keywords
    # I123 item attachments: per-file size ceiling in MB (Redmine/Jira-DC style).
    attachment_max_mb: int = 10
    # I130 allowed file extensions (comma-separated, e.g. "pdf,png,docx");
    # empty means every extension is accepted (Jira 9.15 allowlist semantics).
    attachment_allowed_ext: str = ""
    # I126 approval reminder: gates pending longer than this get an owner
    # nudge from the daily sweep (ServiceNow timer→reminder semantics).
    approval_reminder_days: int = 3
    # I107 IMAP inbox-to-task: optional channel, unset host means off
    # (same env-gated shape as SMTP). Fallback project takes unknown senders
    # under the intake identity; without it unknown senders are ignored.
    imap_host: str = ""
    imap_port: int = 993
    imap_user: str = ""
    imap_pass: str = ""
    imap_fallback_project_id: str = ""

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
