"""OCR engine implementations: Ollama VLM (main), Gemini (fallback), and optional PaddleOCR."""

from __future__ import annotations

import base64
import io
import logging
import re
import time
from pathlib import Path

import httpx
from PIL import Image

from factcheck.config import Settings
from factcheck.extract.ocr.prompts import VLM_OCR_PROMPT

logger = logging.getLogger(__name__)


def resize_image_bytes(image_path: Path, max_long_side: int) -> bytes:
    """Load an image, resize if its longest side exceeds ``max_long_side``, and return PNG bytes."""
    with Image.open(image_path) as im:
        im = im.convert("RGB")
        w, h = im.size
        long_side = max(w, h)
        if long_side > max_long_side and max_long_side > 0:
            scale = max_long_side / float(long_side)
            new_size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
            im = im.resize(new_size, Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()


def check_ollama_running(base_url: str, timeout: float = 2.0) -> tuple[bool, str | None]:
    """Check whether the Ollama HTTP server is reachable before sending an OCR request."""
    # Avoid Windows dual-stack localhost (::1 + 127.0.0.1) doubling the connect timeout
    probe_base = base_url.replace("://localhost", "://127.0.0.1").rstrip("/")
    url = f"{probe_base}/api/tags"
    try:
        resp = httpx.get(url, timeout=httpx.Timeout(timeout, connect=timeout))
        if resp.status_code == 200:
            return True, None
        return False, f"Ollama server at {base_url} returned HTTP {resp.status_code}"
    except Exception as exc:
        return (
            False,
            f"Ollama is not running or unreachable at {base_url}: {exc}",
        )


def run_ollama_vlm(
    image_path: Path,
    settings: Settings,
    *,
    prompt: str = VLM_OCR_PROMPT,
    timeout: float | None = None,
    max_image_long_side: int | None = None,
) -> tuple[str, str, str | None]:
    """Run OCR using local VLM via Ollama HTTP API.

    Returns ``(text, engine_name, error_or_none)``.
    """
    engine_name = f"ollama:{settings.VLM_MODEL}"
    ok, err = check_ollama_running(settings.OLLAMA_BASE_URL)
    if not ok:
        return "", engine_name, err

    try:
        t_prep0 = time.perf_counter()
        effective_max_side = max_image_long_side or (1200 if settings.OFFLINE_MODE else settings.MAX_IMAGE_LONG_SIDE)
        effective_timeout = timeout if timeout is not None else (90.0 if settings.OFFLINE_MODE else 120.0)
        resized_bytes = resize_image_bytes(image_path, effective_max_side)
        b64_image = base64.b64encode(resized_bytes).decode("ascii")
        prep_ms = (time.perf_counter() - t_prep0) * 1000.0

        probe_base = settings.OLLAMA_BASE_URL.replace("://localhost", "://127.0.0.1").rstrip("/")
        # Fast path: try /api/chat with assistant prefill '</think>' to bypass chain-of-thought bloat on reasoning models
        chat_url = f"{probe_base}/api/chat"
        chat_payload = {
            "model": settings.VLM_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [b64_image],
                },
                {
                    "role": "assistant",
                    "content": "</think>",
                },
            ],
            "stream": False,
        }
        t_req0 = time.perf_counter()
        text = ""
        try:
            resp = httpx.post(chat_url, json=chat_payload, timeout=effective_timeout)
            if resp.status_code == 200:
                data = resp.json()
                text = str(data.get("message", {}).get("content", "")).strip()
            else:
                resp = None
        except Exception:
            resp = None

        if resp is None or not text:
            # Fall back to /api/generate
            gen_url = f"{probe_base}/api/generate"
            gen_payload = {
                "model": settings.VLM_MODEL,
                "prompt": prompt,
                "images": [b64_image],
                "stream": False,
            }
            resp = httpx.post(gen_url, json=gen_payload, timeout=effective_timeout)
            if resp.status_code != 200:
                return (
                    "",
                    engine_name,
                    f"Ollama returned HTTP {resp.status_code}: {resp.text[:200]}",
                )
            data = resp.json()
            text = str(data.get("response", "")).strip()

        req_ms = (time.perf_counter() - t_req0) * 1000.0
        # Clean repetitive [unclear] tokens if present
        text = re.sub(r"(\[unclear\]\s*){2,}", "[unclear] ", text).strip()
        logger.info(
            "Ollama (%s) timing split: image_prep=%.2fms, req=%.2fms",
            settings.VLM_MODEL,
            prep_ms,
            req_ms,
        )
        return text, engine_name, None
    except Exception as exc:
        return "", engine_name, f"Ollama VLM request failed: {exc}"


def try_run_paddleocr(
    image_path: Path,
    settings: Settings,
) -> tuple[str, float, str] | None:
    """Run PaddleOCR if already importable; return None silently otherwise."""
    try:
        from paddleocr import PaddleOCR  # type: ignore[import-not-found]
    except ImportError:
        return None

    try:
        lang = "hi" if "hi" in settings.OCR_LANGUAGES else "en"
        ocr = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)
        result = ocr.ocr(str(image_path), cls=True)
        lines: list[str] = []
        confidences: list[float] = []
        for page in result or []:
            for item in page or []:
                if len(item) >= 2 and isinstance(item[1], (list, tuple)):
                    txt, conf = item[1][0], float(item[1][1])
                    lines.append(str(txt))
                    confidences.append(conf)
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        return "\n".join(lines).strip(), avg_conf, f"paddleocr:{lang}"
    except Exception as exc:
        logger.debug("PaddleOCR execution skipped due to error: %s", exc)
        return None


def run_gemini_fallback(
    image_path: Path,
    settings: Settings,
    *,
    prompt: str = VLM_OCR_PROMPT,
    model_override: str | None = None,
    media_resolution_override: str | None = None,
) -> tuple[str, str, str | None]:
    """Run Gemini fallback via ``google-genai`` with configured thinking, timeout, and media resolution."""
    model_name = model_override or settings.GEMINI_MODEL
    engine_name = f"gemini:{model_name}"
    if settings.OFFLINE_MODE:
        logger.error("Attempted Gemini OCR call while OFFLINE_MODE=True on %s", image_path)
        raise RuntimeError("Gemini OCR calls are blocked because OFFLINE_MODE=True")
    api_key = (
        settings.GEMINI_API_KEY.get_secret_value()
        if settings.GEMINI_API_KEY is not None
        else ""
    )
    if not api_key:
        return "", engine_name, "GEMINI_API_KEY is not configured"

    try:
        from google import genai
        from google.genai import types

        t_prep0 = time.perf_counter()
        resized_bytes = resize_image_bytes(image_path, settings.MAX_IMAGE_LONG_SIDE)
        image_part = types.Part.from_bytes(data=resized_bytes, mime_type="image/png")
        thinking_level = (
            types.ThinkingLevel.MINIMAL
            if "lite" in model_name.lower()
            else types.ThinkingLevel.LOW
        )
        res_mode = (media_resolution_override or settings.GEMINI_MEDIA_RESOLUTION or "low").strip().lower()
        media_res = (
            types.MediaResolution.MEDIA_RESOLUTION_LOW
            if res_mode == "low"
            else None
        )
        gen_config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(
                thinking_level=thinking_level,
            ),
            media_resolution=media_res,
        )
        http_options = types.HttpOptions(
            timeout=int(settings.GEMINI_TIMEOUT_SECONDS * 1000),
            retry_options=types.HttpRetryOptions(
                attempts=2,
                initial_delay=1.0,
                max_delay=5.0,
            ),
        )
        prep_ms = (time.perf_counter() - t_prep0) * 1000.0

        t_req0 = time.perf_counter()
        client = genai.Client(api_key=api_key, http_options=http_options)
        response = client.models.generate_content(
            model=model_name,
            contents=[image_part, prompt],
            config=gen_config,
        )
        req_ms = (time.perf_counter() - t_req0) * 1000.0

        t_res0 = time.perf_counter()
        text = (response.text or "").strip()
        res_ms = (time.perf_counter() - t_res0) * 1000.0

        logger.info(
            "Gemini (%s) timing split: image_prep=%.2fms, upload_request=%.2fms, response=%.2fms",
            model_name,
            prep_ms,
            req_ms,
            res_ms,
        )
        return text, engine_name, None
    except Exception as exc:
        return "", engine_name, f"Gemini API error: {exc}"


_CONFIG_ERROR_CODE_RE = re.compile(
    r"\b(?:400|401|403|404)\b|INVALID_ARGUMENT|UNAUTHENTICATED|PERMISSION_DENIED|NOT_FOUND"
)
_QUOTA_ERROR_CODE_RE = re.compile(r"\b429\b|RESOURCE_EXHAUSTED")


def is_gemini_config_error(error: str | None) -> bool:
    """Return True if ``error`` is a Gemini 400/401/403/404 configuration error."""
    if not error or "gemini" not in error.lower():
        return False
    return bool(_CONFIG_ERROR_CODE_RE.search(error))


def should_count_gemini_call(error: str | None) -> bool:
    """Only count calls that return a successful response (error is None) or a 429 quota error."""
    if error is None:
        return True
    if is_gemini_config_error(error):
        return False
    return bool(_QUOTA_ERROR_CODE_RE.search(error))
