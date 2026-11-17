"""Settings for the GUJRERA copilot.

Read from environment variables and ``.env`` (see ``.env.example``), the same
way as ``factcheck.config``.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
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


@lru_cache
def get_gujrera_settings() -> GujreraSettings:
    return GujreraSettings()
