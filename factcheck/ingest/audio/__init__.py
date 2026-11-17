"""Audio intake and transcription package (Voice notes)."""

from factcheck.ingest.audio.languages import (
    LANGUAGES,
    WHISPER_SUPPORTED,
    WHISPER_STRONG,
    choose_engine,
    language_name,
    language_options,
)
from factcheck.ingest.audio.transcribe import (
    transcribe_audio,
    get_whisper_model,
    is_speech_model_loaded,
)

__all__ = [
    "LANGUAGES",
    "WHISPER_SUPPORTED",
    "WHISPER_STRONG",
    "choose_engine",
    "language_name",
    "language_options",
    "transcribe_audio",
    "get_whisper_model",
    "is_speech_model_loaded",
]
