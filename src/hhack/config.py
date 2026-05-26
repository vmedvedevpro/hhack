from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Anthropic API key is only required for phases that call the LLM
    # (3+). Browser-only commands (Phase 1) start without it.
    anthropic_api_key: str | None = None
    anthropic_match_model: str = "claude-sonnet-4-6"
    # Letter writer used to default to Haiku, but live runs (see D-025/D-026)
    # showed Haiku ignored ~30% of "do not say X" rules — Sonnet follows
    # long-form prompt constraints more reliably. Cover-letter volume per
    # day is small enough that the cost delta is negligible.
    anthropic_letter_model: str = "claude-sonnet-4-6"
    anthropic_chat_model: str = "claude-sonnet-4-6"

    # Postgres URL is only required once we start writing jobs / matches /
    # applications (Phase 2+). Leave blank until then.
    database_url: str | None = None
    alembic_database_url: str | None = None

    browser_profile_dir: str = "./profile"
    browser_user_agent: str | None = None
    browser_locale: str | None = None
    browser_timezone: str | None = None
    browser_viewport_width: int = 1440
    browser_viewport_height: int = 900

    # Resumes are synced from HH applicant zone into this directory; the
    # matcher loads every .md file found there. Override only if you want
    # to keep them somewhere outside the repo (e.g. ~/.local/share/hhack/resumes).
    resumes_cache_dir: str | None = None

    match_threshold: float = 0.65
    max_applications_per_day: int = 20
    min_seconds_between_actions: int = 30
    active_hours_window: str = "09:00-23:00"

    dry_run: bool = True
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url", "alembic_database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, v: str | None) -> str | None:
        if not v:
            return None if v is None else v
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://") and not v.startswith("postgresql+"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v


# noinspection PyArgumentList
settings = Settings()
