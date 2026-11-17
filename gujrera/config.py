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
    # Upper bound on rows returned by any analytics query, and its time limit.
    GUJRERA_MAX_ROWS: int = Field(default=500, gt=0)
    GUJRERA_SQL_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0)
    # Officer questions that match no standard report are sent to the self-hosted LLM to write SQL.
    GUJRERA_ANALYTICS_LLM: bool = Field(default=True)
    GUJRERA_ANALYTICS_LLM_TIMEOUT_SECONDS: float = Field(default=150.0, gt=0)
    # Model that writes officer SQL. A non-thinking, SQL-capable model (e.g. qwen2.5-coder) is much faster.
    GUJRERA_SQL_MODEL: str = Field(default="qwen2.5:7b-instruct")

    # Optional: let a self-hosted LLM (Ollama) rephrase template answers. The answer is kept only
    # if every sentence keeps a citation and no new number appears; otherwise the template is used.
    GUJRERA_LLM_PHRASING: bool = Field(default=False)
    GUJRERA_LLM_MODEL: str = Field(default="qwen2.5:7b-instruct")
    GUJRERA_LLM_BASE_URL: str = Field(default="http://localhost:11434")
    GUJRERA_LLM_TIMEOUT_SECONDS: float = Field(default=60.0, gt=0)

    # Key for hashing complaint tracking codes and complainant mobiles (HMAC-SHA256).
    # The default is for local development only; set a long random value in any deployment.
    GUJRERA_HASH_SECRET: SecretStr = Field(default=SecretStr("dev-only-change-me"))

    # Legal RAG: embedding model (shared with Pramaan) and Tesseract for scanned PDFs and Gujarati OCR.
    GUJRERA_EMBEDDING_MODEL: str = Field(default="intfloat/multilingual-e5-small")
    # Let the LLM summarise retrieved provisions (kept only if the citation guard passes).
    GUJRERA_RAG_LLM: bool = Field(default=True)
    GUJRERA_TESSERACT_CMD: str = Field(default="C:/Program Files/Tesseract-OCR/tesseract.exe")

    # Login for the prototype's demo accounts. Production would use GUJRERA's own sign-in (SSO/OTP).
    GUJRERA_AUTH_SECRET: SecretStr = Field(default=SecretStr("dev-only-change-me-too"))
    GUJRERA_TOKEN_HOURS: float = Field(default=8.0, gt=0)
    # Password given to every seeded demo account by scripts/seed_gujrera.py.
    GUJRERA_DEMO_PASSWORD: SecretStr = Field(default=SecretStr("gujrera-demo"))


@lru_cache
def get_gujrera_settings() -> GujreraSettings:
    return GujreraSettings()
