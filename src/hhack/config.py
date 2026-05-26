from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str
    anthropic_match_model: str = "claude-sonnet-4-6"
    anthropic_letter_model: str = "claude-haiku-4-5-20251001"
    anthropic_chat_model: str = "claude-sonnet-4-6"

    database_url: str
    alembic_database_url: str | None = None

    browser_profile_dir: str = "./profile"
    resume_a_path: str
    resume_b_path: str

    match_threshold: float = 0.65
    max_applications_per_day: int = 20
    min_seconds_between_actions: int = 30
    active_hours_window: str = "09:00-23:00"

    dry_run: bool = True
    log_level: str = "INFO"

    model_config = {"env_file": ".env"}

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
