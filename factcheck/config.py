"""Application settings.

All values are read from environment variables and, if present, a ``.env``
file in the working directory. See ``.env.example`` for documentation of
every setting.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the factcheck pipeline."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Fully offline mode & engine preferences
    OFFLINE_MODE: bool = Field(default=False)
    OCR_ENGINE_PREFERENCE: str = Field(default="gemini_first")
    LOCAL_LLM_MODEL: str = Field(default="qwen3-vl:4b")

    # Local VLM served by Ollama
    OLLAMA_ENABLED: bool = True
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    VLM_MODEL: str = "qwen3-vl:8b"

    # Optional hosted fallback (Gemini)
    GEMINI_API_KEY: SecretStr | None = None
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    # Tried in order for claim extraction when GEMINI_MODEL is overloaded (503/429) or not found (404)
    GEMINI_FALLBACK_MODELS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["gemini-flash-latest"]
    )
    GEMINI_TIMEOUT_SECONDS: int = Field(default=30, gt=0)
    GEMINI_MEDIA_RESOLUTION: str = "default"
    API_DAILY_CALL_LIMIT: int = Field(default=50, ge=0)

    # OCR
    OCR_LANGUAGES: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["hi", "en"]
    )
    TIER1_CONFIDENCE_THRESHOLD: float = Field(default=0.80, ge=0.0, le=1.0)
    CACHE_DB_PATH: Path = Path("data/cache/ocr_cache.sqlite")
    MAX_IMAGE_LONG_SIDE: int = Field(default=1600, gt=0)

    # Stage 4: Retrieval & source matching thresholds (calibrated from eval_retrieval.py)
    INDEX_DIR: Path = Path("data/index")
    EMBEDDING_MODEL: str = "intfloat/multilingual-e5-small"
    RRF_K: int = Field(default=60, gt=0)
    DEBUNK_STRONG_THRESHOLD: float = Field(default=0.88, ge=0.0, le=1.0)
    DEBUNK_POSSIBLE_THRESHOLD: float = Field(default=0.84, ge=0.0, le=1.0)
    OFFICIAL_STRONG_THRESHOLD: float = Field(default=0.88, ge=0.0, le=1.0)
    OFFICIAL_POSSIBLE_THRESHOLD: float = Field(default=0.84, ge=0.0, le=1.0)
    BM25_STRONG_THRESHOLD: float = Field(default=18.0, ge=0.0)
    BM25_POSSIBLE_THRESHOLD: float = Field(default=9.0, ge=0.0)

    # Stage 8: Narrative detection and indicator linking
    NARRATIVES_INDEX_PATH: Path = Path("data/index/narratives.json")
    INDICATOR_GRAPH_PATH: Path = Path("data/index/indicator_graph.json")
    HDBSCAN_MIN_CLUSTER_SIZE: int = Field(default=5, ge=2)
    PCA_COMPONENTS: int = Field(default=50, ge=2)
    NARRATIVE_ASSIGN_THRESHOLD: float = Field(default=0.86, ge=0.0, le=1.0)

    # Audio Intake & Transcription (Voice Notes)
    MAX_AUDIO_MB: int = Field(default=25, gt=0)
    MAX_AUDIO_SECONDS: int = Field(default=180, gt=0)
    WHISPER_MODEL: str = Field(default="small")
    WHISPER_DEVICE: str = Field(default="cpu")
    WHISPER_COMPUTE_TYPE: str = Field(default="int8")
    PREFER_HINDI_OVER_URDU: bool = Field(default=True)
    LID_CONFIDENCE: float = Field(default=0.70, ge=0.0, le=1.0)
    USE_INDIC_CONFORMER: bool = Field(default=True)
    INDIC_CONFORMER_MODEL: str = Field(default="ai4bharat/indic-conformer-600m-multilingual")
    INDIC_DECODING: str = Field(default="ctc")
    INDIC_CHUNK_SEC: float = Field(default=15.0, gt=0.0)
    WHISPER_WEAK_LANGS: list[str] = Field(default_factory=lambda: ["kn", "te", "ml", "bn", "gu"])

    @field_validator("OCR_LANGUAGES", "GEMINI_FALLBACK_MODELS", mode="before")
    @classmethod
    def _parse_languages(cls, value: Any) -> Any:
        """Accept either a JSON list (``["hi","en"]``) or a CSV string (``hi,en``)."""
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                return json.loads(text)
            return [part.strip() for part in text.split(",") if part.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
