"""Audio transcription for voice notes: 22 scheduled Indian languages + English/Hinglish.

Adapts teammate's Whisper + IndicConformer logic with:
1. Lazy loading & global status check (`is_speech_model_loaded()`).
2. Duration enforcement against `MAX_AUDIO_SECONDS` (180s default).
3. SQLite persistent transcript caching by SHA-256(audio_bytes + engine + model + language).
4. Auto-detection, confidence scoring, Urdu->Hindi mapping, and needs_confirmation handling.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from faster_whisper import WhisperModel, decode_audio

from factcheck.config import get_settings
from factcheck.ingest.audio.indic_asr import indic_available, transcribe_indic
from factcheck.ingest.audio.languages import (
    LANGUAGES,
    WHISPER_SUPPORTED,
    choose_engine,
    language_name,
)

# Prompts only in matching language/script to avoid Devanagari bias on other scripts
PROMPTS = {
    "hi": "भारत सरकार, परिपत्र, सूचना, रिज़र्व बैंक, सीबीएसई, एनटीए, पीआईबी फैक्ट चेक, RBI, CBSE, NTA, PIB Fact Check.",
    "en": "Government notice, circular, RBI, CBSE, NTA, PIB Fact Check.",
}
NOT_AUTO_DETECTABLE = ", ".join(language_name(c) for c in LANGUAGES if c not in WHISPER_SUPPORTED)

_model_lock = threading.Lock()
_whisper_model: WhisperModel | None = None


def is_speech_model_loaded() -> bool:
    """Check if either Whisper or IndicConformer speech model is currently loaded in memory."""
    try:
        from factcheck.ingest.audio.indic_asr import is_indic_model_loaded
        indic_loaded = is_indic_model_loaded()
    except Exception:
        indic_loaded = False
    return _whisper_model is not None or indic_loaded


def get_whisper_model() -> WhisperModel:
    """Load Whisper model once and reuse in memory."""
    global _whisper_model
    if _whisper_model is None:
        with _model_lock:
            if _whisper_model is None:
                cfg = get_settings()
                kwargs = dict(device=cfg.WHISPER_DEVICE, compute_type=cfg.WHISPER_COMPUTE_TYPE)
                try:  # cached copy first, so an offline (on-premise) machine never calls the Hub
                    _whisper_model = WhisperModel(cfg.WHISPER_MODEL, local_files_only=True, **kwargs)
                except Exception:  # noqa: BLE001 - not downloaded yet
                    _whisper_model = WhisperModel(cfg.WHISPER_MODEL, **kwargs)
    return _whisper_model


def _init_audio_cache_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audio_transcript_cache (
            cache_key TEXT PRIMARY KEY,
            transcript_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def compute_audio_cache_key(
    audio_bytes: bytes,
    engine: str,
    model_name: str,
    language: str | None,
) -> str:
    """Return SHA-256(audio_bytes + engine + model + language)."""
    h = hashlib.sha256()
    h.update(audio_bytes)
    lang_tag = language or "auto"
    h.update(f"|{engine}|{model_name}|{lang_tag}".encode("utf-8"))
    return h.hexdigest()


def get_cached_transcript(cache_key: str) -> dict[str, Any] | None:
    cfg = get_settings()
    if not cfg.CACHE_DB_PATH.exists():
        return None
    try:
        with sqlite3.connect(cfg.CACHE_DB_PATH) as conn:
            _init_audio_cache_table(conn)
            cur = conn.cursor()
            cur.execute("SELECT transcript_json FROM audio_transcript_cache WHERE cache_key = ?", (cache_key,))
            row = cur.fetchone()
            if row:
                return json.loads(row[0])
    except Exception:
        pass
    return None


def save_cached_transcript(cache_key: str, data: dict[str, Any]) -> None:
    cfg = get_settings()
    try:
        cfg.CACHE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(cfg.CACHE_DB_PATH) as conn:
            _init_audio_cache_table(conn)
            conn.execute(
                "INSERT OR REPLACE INTO audio_transcript_cache (cache_key, transcript_json) VALUES (?, ?)",
                (cache_key, json.dumps(data)),
            )
    except Exception:
        pass


def _whisper(audio, language, task="transcribe"):
    prompt = PROMPTS.get(language) if task == "transcribe" else None
    return get_whisper_model().transcribe(
        audio,
        language=language,
        task=task,
        beam_size=5,
        vad_filter=True,
        initial_prompt=prompt,
    )


def _whisper_text(audio, language, task="transcribe"):
    segs, _ = _whisper(audio, language, task)
    segments = [
        {"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
        for s in segs
    ]
    return " ".join(s["text"] for s in segments).strip(), segments


def _detection(info) -> dict[str, Any]:
    probs = sorted(info.all_language_probs or [], key=lambda x: x[1], reverse=True)[:3]
    return {
        "detected": info.language,
        "confidence": round(info.language_probability, 3),
        "candidates": [
            {"code": c, "name": language_name(c), "prob": round(p, 3)}
            for c, p in probs
        ],
    }


def transcribe_audio(
    path: Path | str,
    language: str | None = None,
    engine: str = "auto",
    translate: bool = False,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Transcribe audio file path (.mp3/.ogg/.opus/.wav/.m4a) to text and timestamped segments."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Audio file not found: {p}")

    cfg = get_settings()
    if language and language not in LANGUAGES:
        raise ValueError(f"Unknown language '{language}'. Use one of: {sorted(LANGUAGES)}")

    audio_bytes = p.read_bytes()

    # 1. Check cache
    effective_model = cfg.INDIC_CONFORMER_MODEL if engine == "indic" else cfg.WHISPER_MODEL
    cache_key = compute_audio_cache_key(audio_bytes, engine, effective_model, language)
    if use_cache:
        cached = get_cached_transcript(cache_key)
        if cached is not None:
            cached["from_cache"] = True
            return cached

    # 2. Decode audio (16 kHz mono)
    audio = decode_audio(str(p), sampling_rate=16000)
    duration_sec = round(len(audio) / 16000, 2)

    # 3. Enforce MAX_AUDIO_SECONDS limit
    if duration_sec > cfg.MAX_AUDIO_SECONDS:
        raise ValueError(
            f"Audio duration ({duration_sec}s) exceeds the maximum allowed limit of {cfg.MAX_AUDIO_SECONDS}s."
        )

    notes: list[str] = []

    # 4. Language detection or manual selection
    if language:
        lang = language
        detection = {
            "mode": "manual",
            "detected": None,
            "confidence": None,
            "candidates": [],
            "needs_confirmation": False,
        }
    else:
        _, info = _whisper(audio, None)
        detection = {"mode": "auto", **_detection(info)}
        lang = info.language
        if lang == "ur" and cfg.PREFER_HINDI_OVER_URDU:
            lang = "hi"
            notes.append(
                "Detected Urdu; transcribed as Hindi (Devanagari). "
                "If the speaker really used Urdu, re-run with language='ur'."
            )
        low_conf = info.language_probability < cfg.LID_CONFIDENCE
        detection["needs_confirmation"] = low_conf or lang not in LANGUAGES
        if detection["needs_confirmation"]:
            detection["message"] = (
                f"Not sure about the language (best guess: {language_name(lang)}). "
                f"Please confirm or choose the correct one. Note: {NOT_AUTO_DETECTABLE} "
                "cannot be auto-detected and must be selected manually."
            )

    # 5. Pick engine
    chosen = choose_engine(lang, engine) if lang in LANGUAGES else "whisper"
    text, segments = "", []

    # 6a. IndicConformer (if chosen), falling back to Whisper if unavailable
    if chosen == "indic":
        ok, reason = indic_available()
        if ok:
            try:
                out = transcribe_indic(audio, lang)
                text, segments = out["text"], out["segments"]
            except Exception as exc:
                ok = False
                reason = f"IndicConformer failed: {str(exc).splitlines()[0][:150]}"
                if "gated" in str(exc).lower():
                    reason += " (log in to Hugging Face: run 'hf auth login')"
        if not ok:
            if lang in WHISPER_SUPPORTED:
                chosen = "whisper"
                notes.append(f"{reason} Used Whisper instead.")
            else:
                err_res = _result(
                    "", [], lang, "none", detection, len(audio),
                    notes + [f"{language_name(lang)} needs IndicConformer. {reason}"],
                    error=True,
                )
                return err_res

    # 6b. Whisper
    if chosen == "whisper":
        text, segments = _whisper_text(audio, lang if lang in WHISPER_SUPPORTED else None)

    result = _result(text, segments, lang, chosen, detection, len(audio), notes)

    # 7. Optional translation
    if translate and text and lang != "en":
        if lang in WHISPER_SUPPORTED:
            result["text_en"], _ = _whisper_text(audio, lang, task="translate")
        else:
            result["notes"].append(
                f"English translation not available for {language_name(lang)}; LLM can translate."
            )

    # 8. Save result to cache
    save_cached_transcript(cache_key, result)
    result["from_cache"] = False
    return result


def _result(
    text: str,
    segments: list[dict[str, Any]],
    lang: str,
    engine: str,
    detection: dict[str, Any],
    n_samples: int,
    notes: list[str],
    error: bool = False,
) -> dict[str, Any]:
    return {
        "text": text,
        "language": lang,
        "language_name": language_name(lang),
        "engine": engine,
        "detection": detection,
        "duration_sec": round(n_samples / 16000, 2),
        "segments": segments,
        "text_en": None,
        "empty": not text,
        "error": error,
        "notes": notes,
    }
