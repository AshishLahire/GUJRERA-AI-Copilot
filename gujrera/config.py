"""Settings for the GUJRERA copilot.

Read from environment variables and ``.env`` (see ``.env.example``), the same
way as ``factcheck.config``.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class GujreraSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # SQLAlchemy URL. SQLite for the prototype; a postgresql+psycopg URL also works.
    GUJRERA_DB_URL: str = Field(default="sqlite:///data/gujrera/gujrera.sqlite")
    # Seed for the reproducible mock data generator.
    GUJRERA_MOCK_SEED: int = Field(default=2016)
    # Upper bound on rows returned by any analytics query.
    GUJRERA_MAX_ROWS: int = Field(default=500, gt=0)

    # Optional: let a self-hosted LLM (Ollama) rephrase template answers. The answer is kept only
    # if every sentence keeps a citation and no new number appears; otherwise the template is used.
    GUJRERA_LLM_PHRASING: bool = Field(default=False)
    GUJRERA_LLM_MODEL: str = Field(default="qwen3-vl:4b")
    GUJRERA_LLM_BASE_URL: str = Field(default="http://localhost:11434")
    GUJRERA_LLM_TIMEOUT_SECONDS: float = Field(default=20.0, gt=0)

    # Key for hashing complaint tracking codes and complainant mobiles (HMAC-SHA256).
    # The default is for local development only; set a long random value in any deployment.
    GUJRERA_HASH_SECRET: SecretStr = Field(default=SecretStr("dev-only-change-me"))


@lru_cache
def get_gujrera_settings() -> GujreraSettings:
    return GujreraSettings()
