"""AI4Bharat IndicConformer engine: all 22 scheduled Indian languages."""

from __future__ import annotations

from functools import lru_cache
from typing import Any
import numpy as np

from factcheck.config import get_settings

SR = 16000  # audio samples per second


def indic_available() -> tuple[bool, str]:
    cfg = get_settings()
    if not cfg.USE_INDIC_CONFORMER:
        return False, "IndicConformer disabled (USE_INDIC_CONFORMER=false)."
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError:
        return False, "IndicConformer not installed. Run: pip install torch torchaudio transformers onnx onnxruntime"
    return True, ""


import threading

_indic_lock = threading.Lock()
_indic_model: Any = None


def is_indic_model_loaded() -> bool:
    """Check if the IndicConformer model is currently loaded in memory."""
    return _indic_model is not None


def get_indic_model() -> Any:
    """Load IndicConformer model once lazily and keep in memory."""
    global _indic_model
    if _indic_model is None:
        with _indic_lock:
            if _indic_model is None:
                cfg = get_settings()
                from transformers import AutoModel
                _indic_model = AutoModel.from_pretrained(cfg.INDIC_CONFORMER_MODEL, trust_remote_code=True)
    return _indic_model


def speech_chunks(audio: np.ndarray, max_sec: float | None = None) -> list[tuple[int, int]]:
    """Split audio at pauses into pieces of at most max_sec seconds."""
    cfg = get_settings()
    chunk_sec = max_sec if max_sec is not None else cfg.INDIC_CHUNK_SEC
    max_len = int(chunk_sec * SR)
    try:
        from faster_whisper.vad import get_speech_timestamps
        spans = [(s["start"], s["end"]) for s in get_speech_timestamps(audio)]
    except Exception:
        spans = [(0, len(audio))]
    if not spans:
        if len(audio) == 0:
            return []
        spans = [(0, len(audio))]

    chunks, cur_start, cur_end = [], spans[0][0], spans[0][1]
    for start, end in spans[1:]:
        if end - cur_start <= max_len:
            cur_end = end
        else:
            chunks.append((cur_start, cur_end))
            cur_start, cur_end = start, end
    chunks.append((cur_start, cur_end))

    final = []
    for start, end in chunks:
        for s in range(start, end, max_len):
            final.append((s, min(s + max_len, end)))
    return final


def transcribe_indic(audio: np.ndarray, lang: str) -> dict[str, Any]:
    cfg = get_settings()
    import torch
    model = get_indic_model()
    segments = []
    with torch.inference_mode():
        for start, end in speech_chunks(audio):
            wav = torch.from_numpy(audio[start:end].astype(np.float32)).unsqueeze(0)
            out = model(wav, lang, cfg.INDIC_DECODING)
            text = (" ".join(out) if isinstance(out, (list, tuple)) else str(out)).strip()
            if text:
                segments.append({
                    "start": round(start / SR, 2),
                    "end": round(end / SR, 2),
                    "text": text,
                })
    return {
        "text": " ".join(s["text"] for s in segments).strip(),
        "segments": segments,
    }
