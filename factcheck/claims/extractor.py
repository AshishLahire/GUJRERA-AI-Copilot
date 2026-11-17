"""Stage 3 claim extractor with strict JSON validation, 1 retry, model fallback, and SQLite caching."""

from __future__ import annotations

import json
import re
import time
from datetime import date
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field, ValidationError

from factcheck.claims.authority import normalise_authority
from factcheck.claims.cache import ClaimCache, compute_claim_cache_key
from factcheck.claims.prompts import CLAIM_PROMPT_VERSION, build_claim_prompt
from factcheck.lang import detect_language
from factcheck.config import Settings, get_settings
from factcheck.extract.ocr.cache import OCRCache
from factcheck.schemas import ClaimResult

REPO_ROOT = Path(__file__).resolve().parents[2]
JSON_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)
PRIVATE_NAME_RE = re.compile(
    r"\b(?:Mr\.|Ms\.|Mrs\.|Shri|Smt\.)\s+[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*\b"
)


def mask_private_names(text: str | None) -> str | None:
    """Mask private individual honorifics and names to 'the recipient' for privacy compliance."""
    if not text:
        return text
    return PRIVATE_NAME_RE.sub("the recipient", text)

# Error text that means "the model is busy or timed out, try again / try another model".
TRANSIENT_ERROR_MARKERS = (
    "503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "500", "INTERNAL",
    "overloaded", "high demand", "timed out", "timeout",
)
MAX_TRANSIENT_RETRIES_PER_MODEL = 2
TRANSIENT_BACKOFF_SECONDS = 2.0


class _StrictClaimPayload(BaseModel):
    """Strict schema used to validate the raw JSON returned by the LLM."""

    canonical_claim_en: str | None = None
    claim_language: str = "en"
    claimed_issuer: str | None = None
    action: str | None = None
    effective_date: str | None = None
    effective_date_raw: str | None = None
    amounts: list[str] = Field(default_factory=list)
    audience: str | None = None
    claim_type: str = "other"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


def _call_gemini_claim_llm(prompt: str, settings: Settings) -> str:
    """Invoke Gemini using the same model and settings as OCR fallback."""
    if settings.OFFLINE_MODE:
        import logging
        logging.getLogger("factcheck.claims").error("Attempted Gemini claim extraction while OFFLINE_MODE=True")
        raise RuntimeError("Gemini claim extraction calls are blocked because OFFLINE_MODE=True")
    from google import genai
    from google.genai import types

    api_key = (
        settings.GEMINI_API_KEY.get_secret_value().strip()
        if settings.GEMINI_API_KEY
        else ""
    )
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=settings.GEMINI_TIMEOUT_SECONDS * 1000),
    )
    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=[prompt],
        config=types.GenerateContentConfig(
            temperature=0.0,
            response_mime_type="application/json",
        ),
    )
    return response.text or ""


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "n/a", "not stated"}:
        return None
    return text


def _parse_iso_date(value: str | None) -> str | None:
    """Keep effective_date only if it is a real YYYY-MM-DD date."""
    text = _clean_optional_text(value)
    if text is None:
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


_RELATIVE_DATE_RE = re.compile(
    r"(?i)\b(within|in|after|before|next|upcoming|immediate|forthwith|hours?|days?|weeks?|months?|"
    r"घंटे|घण्टे|दिन|सप्ताह|माह|महीने|भीतर|अंदर|तत्काल|शीघ्र)\b"
)

_MONTH_NAME_TO_INT = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "june": 6, "jun": 6,
    "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def _parse_calendar_date(text: str | None) -> date | None:
    """Extract a calendar date from a string (ISO, DD.MM.YYYY, DD/MM/YYYY, or Month DD, YYYY)."""
    if not text:
        return None
    # 1. ISO YYYY-MM-DD
    m_iso = re.search(r"\b(20\d\d|19\d\d)-(0?[1-9]|1[0-2])-(0?[1-9]|[12]\d|3[01])\b", text)
    if m_iso:
        try:
            return date(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)))
        except ValueError:
            pass
    # 2. DD.MM.YYYY, DD/MM/YYYY, DD-MM-YYYY
    m_dmy = re.search(r"\b(0?[1-9]|[12]\d|3[01])[./-](0?[1-9]|1[0-2])[./-](20\d\d|19\d\d)\b", text)
    if m_dmy:
        try:
            return date(int(m_dmy.group(3)), int(m_dmy.group(2)), int(m_dmy.group(1)))
        except ValueError:
            pass
    # 3. DD Month YYYY (e.g. 13 October 2026 or 13th October 2026)
    m_dmy_name = re.search(
        r"\b(0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d\d|19\d\d)\b", text
    )
    if m_dmy_name:
        mon = _MONTH_NAME_TO_INT.get(m_dmy_name.group(2).lower())
        if mon:
            try:
                return date(int(m_dmy_name.group(3)), mon, int(m_dmy_name.group(1)))
            except ValueError:
                pass
    # 4. Month DD, YYYY (e.g. October 13, 2026)
    m_mdy_name = re.search(
        r"\b([A-Za-z]+)\s+(0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?,?\s+(20\d\d|19\d\d)\b", text
    )
    if m_mdy_name:
        mon = _MONTH_NAME_TO_INT.get(m_mdy_name.group(1).lower())
        if mon:
            try:
                return date(int(m_mdy_name.group(3)), mon, int(m_mdy_name.group(2)))
            except ValueError:
                pass
    return None


def _is_date_derivable_from_text(iso_date_str: str, text: str) -> bool:
    """Check if an ISO YYYY-MM-DD date has its year and day/month present in the source text."""
    if not iso_date_str or not text:
        return False
    try:
        d = date.fromisoformat(iso_date_str)
    except ValueError:
        return False

    y_str = str(d.year)
    if y_str not in text:
        return False

    day_str = f"{d.day:02d}"
    day_short = str(d.day)
    mon_str = f"{d.month:02d}"
    mon_short = str(d.month)

    patterns = [
        rf"\b{day_str}[./-]{mon_str}\b",
        rf"\b{day_short}[./-]{mon_short}\b",
        rf"\b{mon_str}[./-]{day_str}\b",
        rf"\b{y_str}-{mon_str}-{day_str}\b",
    ]
    for m_name, m_num in _MONTH_NAME_TO_INT.items():
        if m_num == d.month and len(m_name) >= 3:
            patterns.append(rf"(?i)\b{day_short}(?:st|nd|rd|th)?\s+{m_name}\b")
            patterns.append(rf"(?i)\b{m_name}\s+{day_short}(?:st|nd|rd|th)?\b")

    return any(re.search(pat, text) for pat in patterns)


def _validate_effective_date(
    model_effective_date: str | None,
    raw_date: str | None,
    source_text: str = "",
) -> tuple[str | None, str | None]:
    """Validate and derive effective_date and effective_date_raw.

    - If raw_date is relative (e.g. 'within 24 hours') or absent, effective_date is set to None.
    - If raw_date contains a calendar date, derives effective_date from it.
    - If model_effective_date is not derivable from raw_date or source_text, sets it to None.
    - Never keeps today's or hallucinated nearby dates.
    """
    cleaned_raw = _clean_optional_text(raw_date)
    cleaned_eff = _clean_optional_text(model_effective_date)

    # If the model placed a relative deadline in effective_date, move it to raw
    if cleaned_eff and _RELATIVE_DATE_RE.search(cleaned_eff) and not re.search(r"\b(20\d\d|19\d\d)\b", cleaned_eff):
        if not cleaned_raw:
            cleaned_raw = cleaned_eff
        cleaned_eff = None

    # Check if raw value is relative without a calendar date
    if cleaned_raw and _RELATIVE_DATE_RE.search(cleaned_raw) and not re.search(r"\b(20\d\d|19\d\d)\b", cleaned_raw):
        return None, cleaned_raw

    # If raw value is absent entirely
    if not cleaned_raw:
        # Check if model_effective_date is in source_text as a real date
        if cleaned_eff and _is_date_derivable_from_text(cleaned_eff, source_text):
            return _parse_iso_date(cleaned_eff), None
        return None, None

    # If raw value contains a parseable calendar date, derive ISO date from it
    parsed_from_raw = _parse_calendar_date(cleaned_raw)
    if parsed_from_raw:
        return parsed_from_raw.isoformat(), cleaned_raw

    # Raw value did not parse directly into a date; check if model_effective_date is derivable
    if cleaned_eff:
        iso_val = _parse_iso_date(cleaned_eff)
        if iso_val and (
            _is_date_derivable_from_text(iso_val, cleaned_raw)
            or _is_date_derivable_from_text(iso_val, source_text)
        ):
            return iso_val, cleaned_raw

    return None, cleaned_raw


def _post_validate_claim(claim: ClaimResult, source_text: str = "") -> ClaimResult:
    """Post-validate effective_date and claim_language on any ClaimResult."""
    eff_date, eff_raw = _validate_effective_date(
        claim.effective_date,
        claim.effective_date_raw,
        source_text=source_text,
    )
    claim_lang = (
        detect_language(source_text).language
        if source_text and source_text.strip()
        else (claim.claim_language or "en")
    )
    return claim.model_copy(
        update={
            "effective_date": eff_date,
            "effective_date_raw": eff_raw,
            "claim_language": claim_lang,
        }
    )


def _parse_and_validate_claim_json(raw_text: str, source_text: str = "") -> ClaimResult:
    """Parse raw LLM output as strict JSON and validate into ClaimResult."""
    cleaned = JSON_FENCE_RE.sub("", (raw_text or "").strip()).strip()
    if not cleaned:
        raise ValueError("Empty response from claim LLM")
    parsed = json.loads(cleaned)
    if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
        parsed = parsed[0]
    if not isinstance(parsed, dict):
        raise ValueError("Claim LLM response is not a JSON object")

    strict_obj = _StrictClaimPayload.model_validate(parsed)
    claim_type = strict_obj.claim_type
    if claim_type not in ("forged_document", "rumour", "official_notice", "other"):
        claim_type = "other"

    # Keep the issuer as written (minus generic types like "bank"); resolve it to a registry id.
    raw_issuer = _clean_optional_text(strict_obj.claimed_issuer)
    display_issuer, issuer_id = normalise_authority(raw_issuer)
    claimed_issuer = raw_issuer if display_issuer is not None else None

    # Post-validate effective_date and claim_language
    effective_date, effective_date_raw = _validate_effective_date(
        strict_obj.effective_date,
        strict_obj.effective_date_raw,
        source_text=source_text,
    )

    claim_lang = (
        detect_language(source_text).language
        if source_text and source_text.strip()
        else (strict_obj.claim_language or "en")
    )

    return ClaimResult(
        canonical_claim_en=_clean_optional_text(strict_obj.canonical_claim_en),
        claim_language=claim_lang,
        claimed_issuer=claimed_issuer,
        claimed_issuer_id=issuer_id,
        action=_clean_optional_text(strict_obj.action),
        effective_date=effective_date,
        effective_date_raw=effective_date_raw,
        amounts=[str(a) for a in (strict_obj.amounts or [])],
        audience=_clean_optional_text(strict_obj.audience),
        claim_type=claim_type,  # type: ignore[arg-type]
        confidence=float(strict_obj.confidence),
        from_cache=False,
    )


def _is_transient(err: str) -> bool:
    low = err.lower()
    return any(m.lower() in low for m in TRANSIENT_ERROR_MARKERS)


def _is_model_missing(err: str) -> bool:
    return "404" in err or "NOT_FOUND" in err


def _is_daily_quota(err: str) -> bool:
    return "RESOURCE_EXHAUSTED" in err and "per day" in err.lower()


def _call_ollama_claim_llm(prompt: str, settings: Settings) -> str:
    """Invoke local LLM via Ollama HTTP API with thinking turned off and JSON output format."""
    import httpx
    probe_base = settings.OLLAMA_BASE_URL.replace("://localhost", "://127.0.0.1").rstrip("/")
    chat_url = f"{probe_base}/api/chat"
    chat_payload = {
        "model": settings.LOCAL_LLM_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            },
            {
                "role": "assistant",
                "content": "</think>",
            },
        ],
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.0,
            "num_predict": 2048,
        },
    }
    resp = httpx.post(chat_url, json=chat_payload, timeout=90.0)
    if resp.status_code == 200:
        data = resp.json()
        content = data.get("message", {}).get("content", "").strip()
        if content:
            return content

    gen_url = f"{probe_base}/api/generate"
    gen_payload = {
        "model": settings.LOCAL_LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.0,
            "num_predict": 2048,
        },
    }
    resp = httpx.post(gen_url, json=gen_payload, timeout=90.0)
    if resp.status_code != 200:
        raise RuntimeError(f"Ollama returned HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    return data.get("response", "").strip()


def extract_claim(
    cleaned_text: str,
    *,
    allow_cloud: bool = False,
    use_cache: bool = True,
    settings: Settings | None = None,
    llm_fn: Callable[[str, Settings], str] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> ClaimResult:
    """Extract a canonical claim from overlay-filtered OCR text (or pasted / transcribed text).

    - Checks `ClaimCache` first (keyed by SHA-256(text + model + CLAIM_PROMPT_VERSION)).
    - Only calls the cloud LLM when `allow_cloud=True`; otherwise returns a status note
      `'Claim extraction needs cloud access'`.
    - Counts each live call against the shared daily API counter in `ocr_cache.sqlite`.
    - Validates JSON with pydantic; on invalid JSON, retries once, then fails gracefully.
    - If the model is busy (503/429/timeout) it retries with backoff, then moves to
      `GEMINI_FALLBACK_MODELS`; a missing model (404) moves on immediately.
    """
    cfg = settings or get_settings()
    norm_text = (cleaned_text or "").strip()
    if not norm_text:
        return ClaimResult(
            canonical_claim_en=None,
            status_note="No document text to extract claim from",
        )

    db_path = (
        cfg.CACHE_DB_PATH
        if cfg.CACHE_DB_PATH.is_absolute()
        else REPO_ROOT / cfg.CACHE_DB_PATH
    )
    claim_cache = ClaimCache(db_path)
    is_offline = cfg.OFFLINE_MODE
    engine_name = "ollama" if is_offline else "gemini"
    active_model = cfg.LOCAL_LLM_MODEL if is_offline else cfg.GEMINI_MODEL
    cache_key = compute_claim_cache_key(norm_text, active_model, CLAIM_PROMPT_VERSION, engine=engine_name)

    if use_cache:
        cached = claim_cache.get(cache_key)
        if cached is not None:
            res = ClaimResult.model_validate(cached)
            res.from_cache = True
            res = _post_validate_claim(res, source_text=norm_text)
            if res.canonical_claim_en:
                res.canonical_claim_en = mask_private_names(res.canonical_claim_en)
            return res
        if not is_offline:
            # Fallback to compatible earlier prompt versions (e.g. v2) for cloud Gemini
            for older_pv in ("v2", "v1"):
                older_key = compute_claim_cache_key(norm_text, cfg.GEMINI_MODEL, older_pv, engine="gemini")
                older_cached = claim_cache.get(older_key)
                if older_cached is not None:
                    res = ClaimResult.model_validate(older_cached)
                    res.from_cache = True
                    res.status_note = "Cached (older claim settings)"
                    res = _post_validate_claim(res, source_text=norm_text)
                    if res.canonical_claim_en:
                        res.canonical_claim_en = mask_private_names(res.canonical_claim_en)
                    return res

    if is_offline:
        # Route to local model via Ollama
        call_fn = llm_fn or _call_ollama_claim_llm
        full_prompt = build_claim_prompt(norm_text, date.today().isoformat())
        try:
            raw_output = call_fn(full_prompt, cfg)
            result = _parse_and_validate_claim_json(raw_output, source_text=norm_text)
            if use_cache:
                claim_cache.set(
                    cache_key,
                    model=f"ollama:{cfg.LOCAL_LLM_MODEL}",
                    prompt_version=CLAIM_PROMPT_VERSION,
                    claim_data=result.model_dump(),
                )
            if result.canonical_claim_en:
                result.canonical_claim_en = mask_private_names(result.canonical_claim_en)
            return result
        except Exception as exc:
            return ClaimResult(
                canonical_claim_en=None,
                status_note="Offline claim extraction failed",
                error=str(exc),
            )

    if not allow_cloud:
        return ClaimResult(
            canonical_claim_en=None,
            status_note="Claim extraction needs cloud access",
        )

    ocr_cache = OCRCache(db_path)
    call_fn = llm_fn or _call_gemini_claim_llm
    full_prompt = build_claim_prompt(norm_text, date.today().isoformat())
    models = [cfg.GEMINI_MODEL] + [m for m in cfg.GEMINI_FALLBACK_MODELS if m != cfg.GEMINI_MODEL]

    last_error: str | None = None
    invalid_json_attempts = 0
    for model_name in models:
        model_cfg = cfg if model_name == cfg.GEMINI_MODEL else cfg.model_copy(update={"GEMINI_MODEL": model_name})
        transient_failures = 0
        while True:
            used_today = ocr_cache.get_daily_api_calls()
            if used_today >= cfg.API_DAILY_CALL_LIMIT:
                return ClaimResult(
                    canonical_claim_en=None,
                    status_note="Daily cloud API limit reached",
                    error=f"Daily API call limit ({cfg.API_DAILY_CALL_LIMIT}) reached",
                )
            try:
                ocr_cache.increment_daily_api_calls()
                raw_output = call_fn(full_prompt, model_cfg)
            except Exception as exc:
                msg = str(exc)
                last_error = f"{model_name}: {msg}"
                if _is_daily_quota(msg):
                    return ClaimResult(
                        canonical_claim_en=None,
                        status_note="Gemini daily quota exhausted",
                        error=last_error,
                    )
                if _is_model_missing(msg):
                    break  # try the next model
                if _is_transient(msg):
                    transient_failures += 1
                    if transient_failures > MAX_TRANSIENT_RETRIES_PER_MODEL:
                        break  # this model stays busy, try the next one
                    sleep_fn(TRANSIENT_BACKOFF_SECONDS * transient_failures)
                    continue
                return ClaimResult(
                    canonical_claim_en=None,
                    status_note="Claim extraction unavailable",
                    error=msg,
                )

            try:
                result = _parse_and_validate_claim_json(raw_output, source_text=norm_text)
            except (json.JSONDecodeError, ValidationError, ValueError) as val_exc:
                invalid_json_attempts += 1
                last_error = f"Invalid claim JSON (attempt {invalid_json_attempts}): {val_exc}"
                if invalid_json_attempts >= 2:  # Initial try + 1 retry on invalid JSON
                    return ClaimResult(
                        canonical_claim_en=None,
                        status_note="Claim extraction failed after retry",
                        error=last_error,
                    )
                continue

            if use_cache:
                claim_cache.set(
                    cache_key,
                    model=model_name,
                    prompt_version=CLAIM_PROMPT_VERSION,
                    claim_data=result.model_dump(),
                )
            if result.canonical_claim_en:
                result.canonical_claim_en = mask_private_names(result.canonical_claim_en)
            return result

    return ClaimResult(
        canonical_claim_en=None,
        status_note="Claim extraction unavailable (all models busy or missing)",
        error=last_error,
    )
