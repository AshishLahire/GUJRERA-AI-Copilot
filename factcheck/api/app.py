"""FastAPI backend serving the Pramaan verification console."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image
from pydantic import BaseModel

from factcheck.claims import extract_claim
from factcheck.config import get_settings
from factcheck.decide import decide_verdict
from factcheck.extract.ocr import OCRCache, render_pdf_first_page_to_png, run_ocr
from factcheck.extract.ocr.fields import extract_fields, strip_synthetic_watermark
from factcheck.forensics import run_forensics
from factcheck.forensics.checks import filter_pib_overlay_lines
from factcheck.forensics.visual import run_visual_forensics
from factcheck.ingest.audio import (
    is_speech_model_loaded,
    language_options,
    transcribe_audio,
)
from factcheck.narratives.assign import assign_document_narrative, load_narratives_index
from factcheck.pipeline import DocumentRun, decide_without_archive, run_document_pipeline
from factcheck.retrieval import match_sources
from factcheck.retrieval.matcher import get_default_retriever
from factcheck.schemas import (
    ClaimResult,
    ExtractedFields,
    ForensicResult,
    NarrativeMatchResult,
    OCRResult,
    RetrievalResult,
    VerdictResult,
)
from gujrera.api.routes import router as gujrera_router

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_SET_PATH = REPO_ROOT / "data" / "demo" / "demo_set.json"
UPLOADS_DIR = REPO_ROOT / "data" / "raw" / "uploads"
AUDIO_UPLOADS_DIR = REPO_ROOT / "data" / "raw" / "audio_jobs"

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB for documents
MAX_TEXT_CHARS = 5000  # pasted messages
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}
AUDIO_ALLOWED_EXTS = {".mp3", ".ogg", ".opus", ".wav", ".m4a"}

AUDIO_MEDIA_TYPES = {
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".opus": "audio/opus",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
}
SAFE_JOB_ID_RE = re.compile(r"^[a-f0-9]{32}$")


class TextCheckRequest(BaseModel):
    """Body of POST /api/check/text."""

    text: str
    allow_fallback: bool = False


def _find_audio_file(job_id: str) -> Path | None:
    if not SAFE_JOB_ID_RE.match(job_id):
        return None
    for ext in AUDIO_ALLOWED_EXTS:
        candidate = AUDIO_UPLOADS_DIR / f"{job_id}{ext}"
        if candidate.exists():
            return candidate
    return None


def _match_decide_narrate(
    claim: ClaimResult,
    forensics: ForensicResult,
    cleaned_text: str,
    removed_overlay_text: str,
    fields: ExtractedFields,
    input_type: str = "DOCUMENT",
) -> tuple[RetrievalResult, VerdictResult, NarrativeMatchResult]:
    """Stages 4-6 shared by document, audio and pasted-text intake."""
    matches = match_sources(
        canonical_claim_en=claim.canonical_claim_en,
        original_text=cleaned_text,
        fields=fields,
        claimed_issuer_id=claim.claimed_issuer_id,
    )
    verdict = decide_verdict(
        forensics,
        matches,
        cleaned_body_text=cleaned_text,
        removed_overlay_text=removed_overlay_text,
        input_type=input_type,
        claimed_issuer_id=claim.claimed_issuer_id,
    )

    retriever = get_default_retriever()
    doc_emb = None
    if retriever.model is not None and cleaned_text:
        try:
            doc_emb = retriever.model.encode(
                [f"query: {cleaned_text}"], normalize_embeddings=True
            )[0]
        except Exception:
            doc_emb = None

    if verdict.verdict_key == "matches_official":
        narrative = NarrativeMatchResult(
            assigned=False,
            summary_text="No known scam narrative",
        )
    else:
        narrative = assign_document_narrative(
            cleaned_text,
            doc_embedding=doc_emb,
            exclude_doc_id=None,
        )
    return matches, verdict, narrative


def _run_text_pipeline(text: str, allow_fallback: bool = False) -> dict[str, Any]:
    """Verify pasted message text (e.g. a WhatsApp forward). Same stages as an upload, minus OCR."""
    raw_text = text.strip()
    cleaned_text, overlay_spans, _ = filter_pib_overlay_lines(raw_text)
    removed_overlay_text = "\n".join(
        raw_text[s.char_start : s.char_end] for s in overlay_spans
    )
    fields = extract_fields(cleaned_text, strip_watermark=False)
    from factcheck.lang import detect_language
    det_text = detect_language(raw_text)
    text_doc = OCRResult(
        image_hash=hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        final_text=raw_text,
        engine_used="pasted_text",
        valid=True,
        fields=fields,
        language=det_text.language,
        script=det_text.script,
        language_confidence=det_text.confidence,
        language_name=det_text.language_name,
        text_direction=det_text.direction,
        primary_language=det_text.primary_language,
        languages_present=[
            {"language": s.language, "share": s.share, "language_name": s.language_name, "script": s.script}
            for s in det_text.languages_present
        ],
        language_badge=det_text.display_badge,
        is_language_uncertain=det_text.is_uncertain,
    )
    forensics = run_forensics(text_doc)
    claim = extract_claim(cleaned_text, allow_cloud=allow_fallback, use_cache=True)
    matches, verdict, narrative = _match_decide_narrate(
        claim, forensics, cleaned_text, removed_overlay_text, fields, input_type="MESSAGE"
    )
    payload = text_doc.model_dump()
    payload["is_text"] = True
    return {
        **payload,
        "ocr": dict(payload),
        "forensics": forensics.model_dump(),
        "claim": claim.model_dump(),
        "matches": matches.model_dump(),
        "verdict": verdict.model_dump(),
        "narrative_result": narrative.model_dump(),
    }


def _run_audio_pipeline(
    audio_path: Path,
    job_id: str,
    orig_name: str,
    language: str | None = None,
    allow_fallback: bool = False,
) -> dict[str, Any]:
    trans_res = transcribe_audio(audio_path, language=language)
    raw_text = trans_res.get("text", "")
    cleaned_text, overlay_spans, _ = filter_pib_overlay_lines(raw_text)
    removed_overlay_text = "\n".join(
        raw_text[s.char_start : s.char_end] for s in overlay_spans
    )
    extracted_fields = extract_fields(cleaned_text, strip_watermark=False)

    cfg = get_settings()
    detected_lang = trans_res.get("language", "en")
    lang_full = trans_res.get("language_name") or detected_lang
    engine_used = trans_res.get("engine", "whisper")
    # Only weak if running on Whisper (or IndicConformer disabled/fell back)
    is_weak_lang = (
        detected_lang in cfg.WHISPER_WEAK_LANGS
        and (not cfg.USE_INDIC_CONFORMER or engine_used == "whisper")
    )

    if is_weak_lang:
        trans_res["weak_language_warning"] = (
            f"Transcription quality for {lang_full} is low with the current engine. "
            "Enable IndicConformer for better accuracy."
        )

    from factcheck.lang import detect_language, get_language_info
    audio_det = detect_language(cleaned_text)
    audio_lang_code = detected_lang if detected_lang else audio_det.language
    lang_info = get_language_info(audio_lang_code)

    expected_script = lang_info.script_code if lang_info else "Latn"
    actual_script = audio_det.script
    is_transliterated = False
    translit_note = None
    if expected_script and actual_script and actual_script != "Unknown":
        if expected_script != actual_script and not (expected_script == "Latn" and audio_lang_code == "hi-Latn"):
            is_transliterated = True
            translit_note = (
                "Transcript is in a different script than the spoken language: "
                "checks may miss warning signs. Enable IndicConformer for this language."
            )
            trans_res["transcript_transliterated"] = True
            trans_res["transliteration_note"] = translit_note

    ocr_for_forensics = OCRResult(
        image_hash=job_id,
        final_text=cleaned_text,
        engine_used=f"whisper_{trans_res.get('engine', 'whisper')}",
        valid=True,
        fields=extracted_fields,
        from_cache=bool(trans_res.get("from_cache", False)),
        markdown_stripped=False,
        time_ms=int(trans_res.get("duration_seconds", 0) * 1000),
        note=trans_res.get("notes") or None,
        error=None,
        language=audio_lang_code,
        script=lang_info.script_code if lang_info else audio_det.script,
        language_confidence=audio_det.confidence,
        language_name=lang_info.name if lang_info else lang_full,
        text_direction=lang_info.direction if lang_info else audio_det.direction,
        primary_language=audio_det.primary_language,
        languages_present=[
            {"language": s.language, "share": s.share, "language_name": s.language_name, "script": s.script}
            for s in audio_det.languages_present
        ],
        language_badge=audio_det.display_badge,
        is_language_uncertain=audio_det.is_uncertain,
        transcript_transliterated=is_transliterated,
        transliteration_note=translit_note,
    )
    forensics = run_forensics(ocr_for_forensics, is_audio=True, transcript_transliterated=is_transliterated)

    if allow_fallback:
        claim = extract_claim(cleaned_text, allow_cloud=True, use_cache=True)
        if is_weak_lang or is_transliterated:
            claim.confidence = round(min(claim.confidence, 0.35), 2)
            note_str = translit_note if is_transliterated else f"Speech recognition quality for {lang_full} is low"
            if claim.status_note:
                claim.status_note += f"; {note_str}"
            else:
                claim.status_note = note_str
    else:
        claim = ClaimResult(
            canonical_claim_en=None,
            claim_language=trans_res.get("language", "en"),
            confidence=0.0,
            status_note="Claim extraction skipped (cloud fallback disabled)",
        )

    matches, verdict, narrative = _match_decide_narrate(
        claim, forensics, cleaned_text, removed_overlay_text, extracted_fields, input_type="VOICE NOTE"
    )
    if is_weak_lang:
        verdict.reason += (
            f" (Note: Speech recognition quality for {lang_full} is low with the current engine; "
            "claim extraction confidence lowered.)"
        )

    payload = ocr_for_forensics.model_dump()
    payload["is_audio"] = True
    payload["job_id"] = job_id
    payload["filename"] = orig_name
    payload["audio_url"] = f"/api/transcribe/{job_id}/audio"
    payload["transcription"] = trans_res
    payload["transcript_transliterated"] = is_transliterated
    payload["transliteration_note"] = translit_note
    payload["forensics"] = forensics.model_dump()
    payload["claim"] = claim.model_dump()
    payload["matches"] = matches.model_dump()
    payload["verdict"] = verdict.model_dump()
    payload["narrative_result"] = narrative.model_dump()
    payload["ocr"] = dict(payload)
    return payload

SAFE_UPLOAD_FILENAME_RE = re.compile(r"^[a-f0-9]{32}(?:\.page1)?\.(?:png|jpg|jpeg)$")
WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:\\[^\s\"']+|/[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+){2,}")


def _map_group(item: dict[str, Any]) -> str:
    source = str(item.get("source_dataset", ""))
    label = str(item.get("label", "")).lower()
    if "01_fake" in source or label == "fake":
        return "fake"
    if "05_whatsapp" in source or label == "genuine":
        return "genuine"
    return "synthetic"


def _load_demo_items() -> list[dict[str, Any]]:
    if not DEMO_SET_PATH.exists():
        return []
    data = json.loads(DEMO_SET_PATH.read_text(encoding="utf-8"))
    return list(data.get("items", []))


def _find_sample_item(sample_id: str) -> dict[str, Any] | None:
    items = _load_demo_items()
    match = next((it for it in items if it["id"] == sample_id), None)
    if match is not None:
        return match
    notices_path = (
        REPO_ROOT / "data" / "dataset" / "01_fake_notice_benchmark" / "notices.jsonl"
    )
    if notices_path.exists():
        for line in notices_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("notice_id") == sample_id:
                return {
                    "id": sample_id,
                    "source_dataset": "01_fake_notice_benchmark",
                    "label": "fake",
                    "language": row.get("language", "en"),
                    "narrative": row.get("narrative_id"),
                    "note": row.get("note"),
                    "expected_issuer": row.get("claimed_issuer")
                    or row.get("claimed_issuer_id"),
                    "expected_issuer_id": row.get("claimed_issuer_id"),
                    "expected_reference_no": row.get("reference_seen"),
                    "image": f"data/dataset/01_fake_notice_benchmark/{row.get('image', '')}",
                }
    fallback_img = (
        REPO_ROOT
        / "data"
        / "dataset"
        / "01_fake_notice_benchmark"
        / "images"
        / f"{sample_id}.jpg"
    )
    if fallback_img.exists() and re.fullmatch(r"FN-[A-Z0-9\-]+", sample_id):
        return {
            "id": sample_id,
            "source_dataset": "01_fake_notice_benchmark",
            "label": "fake",
            "language": "en",
            "narrative": "NAR-POLICY-ORDER",
            "note": None,
            "expected_issuer": "Ministry of Home Affairs",
            "expected_issuer_id": "MHA",
            "expected_reference_no": None,
            "image": f"data/dataset/01_fake_notice_benchmark/images/{sample_id}.jpg",
        }
    return None


def _get_image_dimensions(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as im:
            return im.size
    except Exception:
        return (0, 0)


def _sanitize_error_message(err: str | None) -> str | None:
    if not err:
        return None
    low = err.lower()
    if "503" in err or "unavailable" in low or "gemini busy" in low:
        return "Gemini busy, try again"
    if "image file does not exist" in low:
        return "Requested document image could not be found."
    # Strip any accidental filesystem paths
    cleaned = WINDOWS_PATH_RE.sub("[redacted-path]", err)
    return cleaned


def _is_503_error(err: str | None) -> bool:
    if not err:
        return False
    low = err.lower()
    return "503" in err or "unavailable" in low or "gemini busy" in low


TESTSET_DIR = REPO_ROOT / "data" / "testset"



@lru_cache(maxsize=1)
def _load_heldout_manifest_map() -> dict[str, bool]:
    manifest_p = REPO_ROOT / "data" / "heldout" / "manifest.json"
    if manifest_p.exists():
        try:
            items = json.loads(manifest_p.read_text(encoding="utf-8"))
            return {it["file"]: bool(it.get("in_index", False)) for it in items}
        except Exception:
            pass
    return {}

def _load_testset_items() -> list[dict[str, Any]]:
    manifest = TESTSET_DIR / "manifest.json"
    if not manifest.exists():
        return []
    return json.loads(manifest.read_text(encoding="utf-8")).get("items", [])


def _find_testset_item(item_id: str) -> dict[str, Any] | None:
    return next((it for it in _load_testset_items() if it["id"] == item_id), None)


def _testset_public(item: dict[str, Any]) -> dict[str, Any]:
    ho_map = _load_heldout_manifest_map()
    rel_src = (item.get("source") or "").replace("data/heldout/", "")
    in_idx = bool(
        item.get("in_official_index", False)
        or item.get("in_index", False)
        or ho_map.get(rel_src, False)
        or ho_map.get(item.get("file", ""), False)
    )
    return {
        "id": item["id"],
        "label": item["label"],
        "title": item.get("title"),
        "claimed_issuer_id": item.get("claimed_issuer_id"),
        "language": item.get("language"),
        "in_official_index": in_idx,
        "in_index": in_idx,
        "cleaning": item.get("cleaning"),
        "variant_of": item.get("variant_of"),
        "note": item.get("note") or item.get("index_note"),
        "has_original": bool(item.get("original")),
        "thumbnail_url": f"/api/testset/{item['id']}/image",
    }


def _run_payload(payload: dict[str, Any], run: DocumentRun) -> dict[str, Any]:
    return {
        **payload,
        "ocr": dict(payload),
        "forensics": run.forensics.model_dump(),
        "visual": run.visual.model_dump(),
        "claim": run.claim.model_dump(),
        "matches": run.matches.model_dump(),
        "verdict": run.verdict.model_dump(),
        "narrative_result": run.narrative.model_dump(),
    }


def create_app() -> FastAPI:
    app = FastAPI(
        title="Pramaan API",
        description="Multilingual document & claim verification backend",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def get_health() -> dict[str, Any]:
        cfg = get_settings()
        cache = OCRCache(REPO_ROOT / cfg.CACHE_DB_PATH)
        daily_used = cache.get_daily_api_calls()
        gemini_configured = bool(
            cfg.GEMINI_API_KEY and cfg.GEMINI_API_KEY.get_secret_value().strip()
        )
        ollama_reachable = False
        if cfg.OLLAMA_ENABLED:
            from factcheck.extract.ocr.engines import check_ollama_running
            ok, _ = check_ollama_running(cfg.OLLAMA_BASE_URL, timeout=1.0)
            ollama_reachable = ok

        return {
            "status": "ok",
            "offline_mode": bool(cfg.OFFLINE_MODE),
            "local_llm_model": cfg.LOCAL_LLM_MODEL,
            "ollama_enabled": bool(cfg.OLLAMA_ENABLED),
            "ollama_reachable": ollama_reachable,
            "vlm_model": cfg.VLM_MODEL,
            "gemini_configured": gemini_configured,
            "gemini_model": cfg.GEMINI_MODEL,
            "daily_api_calls_used": daily_used,
            "daily_api_call_limit": cfg.API_DAILY_CALL_LIMIT,
            "speech_model_loaded": is_speech_model_loaded(),
        }

    @app.get("/api/samples")
    def list_samples() -> dict[str, Any]:
        items = _load_demo_items()
        items.sort(key=lambda it: (it.get("demo_order") is None, it.get("demo_order", 9999)))
        samples: list[dict[str, Any]] = []
        for item in items:
            sample_id = item["id"]
            rel_img = item.get("image", "")
            img_path = REPO_ROOT / rel_img
            width, height = _get_image_dimensions(img_path) if img_path.exists() else (0, 0)
            samples.append(
                {
                    "id": sample_id,
                    "demo_order": item.get("demo_order"),
                    "talking_point": item.get("talking_point"),
                    "group": _map_group(item),
                    "label": item.get("label"),
                    "language": item.get("language", "en"),
                    "narrative": item.get("narrative"),
                    "note": item.get("note"),
                    "expected_issuer": item.get("expected_issuer"),
                    "expected_issuer_id": item.get("expected_issuer_id"),
                    "expected_reference_no": item.get("expected_reference_no"),
                    "thumbnail_url": f"/api/samples/{sample_id}/image",
                    "filename": Path(rel_img).name,
                    "width": width,
                    "height": height,
                }
            )
        return {"count": len(samples), "items": samples}

    @app.get("/api/samples/{sample_id}/image")
    def get_sample_image(sample_id: str) -> FileResponse:
        match = _find_sample_item(sample_id)
        if match is None:
            raise HTTPException(status_code=404, detail="Sample not found")
        img_path = (REPO_ROOT / match["image"]).resolve()
        if not img_path.exists():
            raise HTTPException(status_code=404, detail="Sample image missing")
        media_type = "image/png" if img_path.suffix.lower() == ".png" else "image/jpeg"
        return FileResponse(img_path, media_type=media_type, filename=img_path.name)

    @app.get("/api/uploads/{filename}")
    def get_uploaded_image(filename: str) -> FileResponse:
        if not SAFE_UPLOAD_FILENAME_RE.match(filename):
            raise HTTPException(status_code=400, detail="Invalid image identifier")
        img_path = (UPLOADS_DIR / filename).resolve()
        if not img_path.exists() or img_path.parent != UPLOADS_DIR.resolve():
            raise HTTPException(status_code=404, detail="Uploaded image not found")
        media_type = "image/png" if img_path.suffix.lower() == ".png" else "image/jpeg"
        return FileResponse(img_path, media_type=media_type, filename=img_path.name)

    @app.post("/api/ocr/sample/{sample_id}")
    def run_ocr_on_sample(
        sample_id: str,
        allow_fallback: bool = Query(default=False),
        simulate_unseen: bool = Query(default=False),
    ) -> Any:
        match = _find_sample_item(sample_id)
        if match is None:
            return JSONResponse(status_code=404, content={"error": "Sample not found"})

        img_path = (REPO_ROOT / match["image"]).resolve()
        if not img_path.exists():
            return JSONResponse(
                status_code=404, content={"error": "Sample image missing"}
            )

        group = _map_group(match)
        unseen_id = sample_id if (simulate_unseen and group == "fake") else None
        run = run_document_pipeline(
            img_path,
            allow_fallback=allow_fallback,
            synthetic=group == "synthetic",
            known_genuine=group == "genuine",
            exclude_debunk_id=unseen_id,
        )
        if not run.raw.valid and _is_503_error(run.raw.error):
            return JSONResponse(
                status_code=503,
                content={"error": "Gemini busy, try again"},
            )
        if run.ocr.older_ocr_settings:
            logging.getLogger("factcheck.api").warning(
                "Sample %s served from fallback OCR cache: %s (engine=%s)",
                sample_id,
                run.ocr.cache_source,
                run.ocr.engine_used,
            )

        width, height = _get_image_dimensions(img_path)
        payload = run.ocr.model_dump()
        payload["error"] = _sanitize_error_message(run.raw.error)
        payload["sample_id"] = sample_id
        payload["simulate_unseen"] = unseen_id is not None
        payload["demo_order"] = match.get("demo_order")
        payload["talking_point"] = match.get("talking_point")
        payload["group"] = group
        payload["language"] = match.get("language", "en")
        payload["narrative"] = match.get("narrative")
        payload["sample_note"] = match.get("note")
        payload["expected_issuer"] = match.get("expected_issuer")
        payload["expected_issuer_id"] = match.get("expected_issuer_id")
        payload["expected_reference_no"] = match.get("expected_reference_no")
        payload["filename"] = img_path.name
        payload["width"] = width
        payload["height"] = height
        payload["image_url"] = f"/api/samples/{sample_id}/image"
        return _run_payload(payload, run)

    @app.get("/api/testset")
    def list_testset() -> Any:
        items = _load_testset_items()
        pub_items = [_testset_public(it) for it in items]
        in_idx_count = sum(1 for it in pub_items if it["in_index"])
        fresh_count = len(pub_items) - in_idx_count
        return {
            "count": len(items),
            "fresh_count": fresh_count,
            "in_index_count": in_idx_count,
            "description": "Not used to tune thresholds. Items marked 'In index' also appear in the official corpus.",
            "items": pub_items,
        }

    @app.get("/api/testset/{item_id}/image")
    def get_testset_image(item_id: str, original: bool = Query(default=False)) -> Any:
        item = _find_testset_item(item_id)
        if item is None:
            return JSONResponse(status_code=404, content={"error": "Test item not found"})
        rel = item.get("original") if original and item.get("original") else item["file"]
        path = (TESTSET_DIR / rel).resolve()
        if not path.exists() or TESTSET_DIR.resolve() not in path.parents:
            return JSONResponse(status_code=404, content={"error": "Test image missing"})
        media = {".png": "image/png", ".pdf": "application/pdf", ".webp": "image/webp"}.get(
            path.suffix.lower(), "image/jpeg"
        )
        return FileResponse(path, media_type=media, filename=path.name)

    @app.post("/api/testset/{item_id}/run")
    def run_testset_item(
        item_id: str,
        allow_fallback: bool = Query(default=False),
        simulate_unseen: bool = Query(default=False),
    ) -> Any:
        item = _find_testset_item(item_id)
        if item is None:
            return JSONResponse(status_code=404, content={"error": "Test item not found"})
        image_path = (TESTSET_DIR / item["file"]).resolve()
        source = item.get("original") if item["label"] == "real" else item["file"]
        input_path = (TESTSET_DIR / source).resolve()
        run = run_document_pipeline(
            input_path,
            allow_fallback=allow_fallback,
            synthetic=item["label"].startswith("synthetic"),
            image_for_visual=image_path,
        )
        if not run.raw.valid and _is_503_error(run.raw.error):
            return JSONResponse(status_code=503, content={"error": "Gemini busy, try again"})
        if simulate_unseen:
            run.verdict = decide_without_archive(run)
        width, height = _get_image_dimensions(image_path)
        payload = run.ocr.model_dump()
        payload["error"] = _sanitize_error_message(run.raw.error)
        payload["test_item"] = _testset_public(item)
        payload["simulate_unseen"] = simulate_unseen
        payload["filename"] = image_path.name
        payload["width"] = width
        payload["height"] = height
        payload["image_url"] = f"/api/testset/{item_id}/image"
        return _run_payload(payload, run)

    @app.post("/api/ocr/upload")
    async def run_ocr_on_upload(
        file: UploadFile = File(...),
        allow_fallback: bool = Form(default=False),
    ) -> Any:
        orig_name = Path(file.filename or "upload").name
        ext = Path(orig_name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Unsupported file type. Allowed formats: PNG, JPG, JPEG, PDF."
                },
            )

        raw_bytes = await file.read()
        if not raw_bytes:
            return JSONResponse(
                status_code=400,
                content={"error": "Uploaded file is empty."},
            )
        if len(raw_bytes) > MAX_UPLOAD_BYTES:
            return JSONResponse(
                status_code=400,
                content={"error": "File exceeds the 10 MB size limit."},
            )

        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        random_stem = uuid.uuid4().hex
        saved_path = (UPLOADS_DIR / f"{random_stem}{ext}").resolve()
        saved_path.write_bytes(raw_bytes)

        ocr_target_path = saved_path
        pdf_note: str | None = None
        if ext == ".pdf":
            try:
                ocr_target_path = render_pdf_first_page_to_png(saved_path, dpi=200)
                pdf_note = "Only page 1 of the PDF was read."
            except Exception:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Could not render PDF page 1. Please upload a valid PDF."},
                )

        res = run_ocr(
            ocr_target_path,
            allow_gemini_fallback=allow_fallback,
            use_cache=True,
        )
        if not res.valid and _is_503_error(res.error):
            return JSONResponse(
                status_code=503,
                content={"error": "Gemini busy, try again"},
            )

        width, height = _get_image_dimensions(ocr_target_path)
        forensics = run_forensics(res)
        cleaned_text, overlay_spans, _ = filter_pib_overlay_lines(res.final_text)
        removed_overlay_text = "\n".join(
            res.final_text[s.char_start : s.char_end] for s in overlay_spans
        )
        cleaned_fields = (
            extract_fields(cleaned_text, strip_watermark=False)
            if overlay_spans
            else res.fields
        )
        claim = extract_claim(
            cleaned_text,
            allow_cloud=allow_fallback,
            use_cache=True,
        )
        matches, verdict, narrative = _match_decide_narrate(
            claim, forensics, cleaned_text, removed_overlay_text, cleaned_fields
        )

        payload = res.model_dump()
        if pdf_note and not payload.get("note"):
            payload["note"] = pdf_note
        payload["error"] = _sanitize_error_message(res.error)
        payload["filename"] = orig_name
        payload["width"] = width
        payload["height"] = height
        payload["image_url"] = f"/api/uploads/{ocr_target_path.name}"
        forensics_dict = forensics.model_dump()
        claim_dict = claim.model_dump()
        matches_dict = matches.model_dump()
        verdict_dict = verdict.model_dump()
        narrative_dict = narrative.model_dump()
        return {
            **payload,
            "ocr": dict(payload),
            "forensics": forensics_dict,
            "visual": run_visual_forensics(ocr_target_path).model_dump(),
            "claim": claim_dict,
            "matches": matches_dict,
            "verdict": verdict_dict,
            "narrative_result": narrative_dict,
        }

    @app.post("/api/check/text")
    def check_text(body: TextCheckRequest) -> Any:
        text = (body.text or "").strip()
        if not text:
            return JSONResponse(status_code=400, content={"error": "Please paste some text first."})
        if len(text) > MAX_TEXT_CHARS:
            return JSONResponse(
                status_code=400,
                content={"error": f"Text exceeds the {MAX_TEXT_CHARS:,}-character limit."},
            )
        result = _run_text_pipeline(text, allow_fallback=body.allow_fallback)
        claim_error = result["claim"].get("error")
        if _is_503_error(claim_error):
            result["claim"]["error"] = "Gemini busy, try again"
        else:
            result["claim"]["error"] = _sanitize_error_message(claim_error)
        return result

    @app.get("/api/narratives")
    def list_narratives(
        sort: str = Query(default="size", pattern="^(size|recent)$"),
        search: str | None = Query(default=None),
        issuer: str | None = Query(default=None),
    ) -> Any:
        narratives_data, _ = load_narratives_index()
        if not narratives_data:
            return {"count": 0, "items": []}

        items = list(narratives_data.get("clusters", []))
        if search:
            q = search.lower().strip()
            items = [
                it
                for it in items
                if q in it.get("name", "").lower()
                or any(q in iss.get("issuer", "").lower() for iss in it.get("claimed_issuers", []))
            ]
        if issuer:
            iss_q = issuer.lower().strip()
            items = [
                it
                for it in items
                if any(iss_q == iss.get("issuer", "").lower() for iss in it.get("claimed_issuers", []))
            ]

        if sort == "recent":
            items.sort(key=lambda x: x.get("last_date") or "", reverse=True)
        else:
            items.sort(key=lambda x: x.get("size", 0), reverse=True)

        return {"count": len(items), "items": items}

    @app.get("/api/narratives/{cluster_id}")
    def get_narrative_detail(cluster_id: str) -> Any:
        narratives_data, _ = load_narratives_index()
        if not narratives_data:
            raise HTTPException(status_code=404, detail="Narrative index not found")

        cluster = next(
            (c for c in narratives_data.get("clusters", []) if c["id"] == cluster_id),
            None,
        )
        if cluster is None:
            raise HTTPException(status_code=404, detail=f"Narrative {cluster_id} not found")

        return cluster
    @app.get("/api/languages")
    def list_supported_languages() -> dict[str, Any]:
        return {"languages": language_options()}

    @app.post("/api/transcribe/upload")
    async def run_transcribe_upload(
        file: UploadFile = File(...),
        language: str | None = Form(default=None),
        allow_fallback: bool = Form(default=False),
    ) -> Any:
        orig_name = Path(file.filename or "audio").name
        ext = Path(orig_name).suffix.lower()
        if ext not in AUDIO_ALLOWED_EXTS:
            allowed_str = ", ".join(sorted(AUDIO_ALLOWED_EXTS))
            return JSONResponse(
                status_code=400,
                content={
                    "error": f"Unsupported audio format '{ext}'. Allowed: {allowed_str}"
                },
            )

        raw_bytes = await file.read()
        if not raw_bytes:
            return JSONResponse(
                status_code=400,
                content={"error": "Uploaded audio file is empty."},
            )

        cfg = get_settings()
        max_audio_bytes = cfg.MAX_AUDIO_MB * 1024 * 1024
        if len(raw_bytes) > max_audio_bytes:
            return JSONResponse(
                status_code=400,
                content={
                    "error": f"Audio file exceeds the {cfg.MAX_AUDIO_MB} MB size limit."
                },
            )

        AUDIO_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        job_id = uuid.uuid4().hex
        saved_path = (AUDIO_UPLOADS_DIR / f"{job_id}{ext}").resolve()
        saved_path.write_bytes(raw_bytes)

        try:
            return _run_audio_pipeline(
                audio_path=saved_path,
                job_id=job_id,
                orig_name=orig_name,
                language=language or None,
                allow_fallback=allow_fallback,
            )
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})
        except Exception as exc:
            return JSONResponse(
                status_code=500, content={"error": f"Audio processing failed: {exc}"}
            )

    @app.get("/api/transcribe/{job_id}/audio")
    def get_audio_clip(job_id: str) -> FileResponse:
        p = _find_audio_file(job_id)
        if not p:
            raise HTTPException(status_code=404, detail="Audio file not found")
        media_type = AUDIO_MEDIA_TYPES.get(p.suffix.lower(), "audio/mpeg")
        return FileResponse(p, media_type=media_type, filename=p.name)

    @app.post("/api/transcribe/{job_id}/language")
    def retranscribe_audio_language(
        job_id: str,
        language: str = Form(...),
        allow_fallback: bool = Form(default=False),
    ) -> Any:
        p = _find_audio_file(job_id)
        if not p:
            raise HTTPException(status_code=404, detail="Audio file not found")
        try:
            return _run_audio_pipeline(
                audio_path=p,
                job_id=job_id,
                orig_name=p.name,
                language=language,
                allow_fallback=allow_fallback,
            )
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})
        except Exception as exc:
            return JSONResponse(
                status_code=500, content={"error": f"Audio processing failed: {exc}"}
            )

    # GUJRERA copilot endpoints (/api/gujrera/*)
    app.include_router(gujrera_router)

    return app


app = create_app()

logger = logging.getLogger('factcheck.api')
