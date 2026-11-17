"""Streamlit UI (Stage 7: presentation) with file uploader, demo selector, and real OCR runner."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from factcheck.extract.ocr.runner import run_ocr as execute_ocr
from factcheck.schemas import OCRResult

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_MANIFEST_PATH = PROJECT_ROOT / "data" / "demo" / "demo_set.json"


def load_demo_manifest(manifest_path: Path = DEMO_MANIFEST_PATH) -> list[dict[str, Any]]:
    """Return the list of demo items from ``data/demo/demo_set.json``."""
    if not manifest_path.exists():
        return []
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return list(data.get("items", []))
    return list(data)


def run_ocr(
    image_path: str | Path,
    *,
    allow_gemini_fallback: bool = False,
) -> OCRResult:
    """OCR entry point called by both upload and demo-sample flows."""
    return execute_ocr(image_path, allow_gemini_fallback=allow_gemini_fallback)


def reference_matches(expected_ref: str | None, extracted_refs: list[str]) -> bool:
    """Return True if ``expected_ref`` matches any extracted reference number."""
    if not expected_ref or not extracted_refs:
        return False
    expected_parts = [
        p.strip() for p in expected_ref.split(";") if p.strip()
    ]
    extracted_norm = {r.strip() for r in extracted_refs if r.strip()}
    for part in expected_parts:
        if part in extracted_norm:
            return True
        # Also allow prefix-stripped match (e.g. "Reg. No: PMKY7010346HW" vs "PMKY7010346HW")
        if ":" in part and part.split(":", 1)[1].strip() in extracted_norm:
            return True
    return False


def main() -> None:
    import streamlit as st

    st.set_page_config(
        page_title="FactCheck Pipeline — OCR & Demo",
        layout="wide",
    )
    st.title("Indian-Language Misinformation Verification Pipeline")
    st.caption("Stage 7: presentation — Document Upload, Demo Sample Selector & Stage 2a OCR")

    demo_items = load_demo_manifest()
    demo_lookup: dict[str, dict[str, Any]] = {
        f"{item['id']} — {item['note']}": item for item in demo_items
    }

    col_upload, col_sample, col_opts = st.columns([2, 2, 1])
    with col_upload:
        uploaded_file = st.file_uploader(
            "Upload a notice image",
            type=["png", "jpg", "jpeg", "webp"],
        )
    with col_sample:
        sample_options = ["(None — use uploaded file)"] + list(demo_lookup.keys())
        selected_label = st.selectbox("Load sample", options=sample_options)
    with col_opts:
        allow_gemini = st.checkbox("Allow Gemini fallback", value=False)

    active_image_path: Path | None = None
    selected_item: dict[str, Any] | None = None

    if selected_label != "(None — use uploaded file)":
        selected_item = demo_lookup[selected_label]
        active_image_path = (PROJECT_ROOT / selected_item["image"]).resolve()
    elif uploaded_file is not None:
        suffix = Path(uploaded_file.name).suffix or ".png"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded_file.getvalue())
            active_image_path = Path(tmp.name)

    if active_image_path is None:
        st.info("Upload an image or choose an entry from **Load sample** to run OCR.")
        return

    img_col, res_col = st.columns([1, 1])
    with img_col:
        st.subheader("Document Image")
        if active_image_path.exists():
            st.image(str(active_image_path), use_container_width=True)
        else:
            st.error(f"Image file not found: {active_image_path}")

    with res_col:
        st.subheader("OCR Output & Reference Comparison")
        with st.spinner("Running OCR..."):
            result = run_ocr(
                active_image_path,
                allow_gemini_fallback=allow_gemini,
            )

        if result.error:
            if "503" in result.error or "UNAVAILABLE" in result.error.upper():
                st.error("Gemini busy, try again")
            else:
                st.error(f"OCR Error: {result.error}")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Engine Used", result.engine_used)
        m2.metric("Cache Hit", "Yes" if result.from_cache else "No")
        m3.metric("Time Taken", f"{result.time_ms:.1f} ms")
        m4.metric("Valid Text", "Yes" if result.valid else "No")

        extracted_refs = result.fields.reference_numbers
        extracted_ref_display = (
            ", ".join(extracted_refs) if extracted_refs else "None extracted"
        )
        st.markdown("### Extracted Reference Number(s)")
        st.code(extracted_ref_display, language=None)

        if selected_item is not None:
            exp_issuer = selected_item.get("expected_issuer") or "Unknown"
            exp_ref = selected_item.get("expected_reference_no")
            st.markdown("#### Demo Sample Comparison")
            st.markdown(
                f"- **Sample ID:** `{selected_item['id']}` (`{selected_item['source_dataset']}`, label=`{selected_item['label']}`, lang=`{selected_item['language']}`)"
            )
            st.markdown(f"- **Expected Issuer:** `{exp_issuer}`")
            if exp_ref:
                matched = reference_matches(exp_ref, extracted_refs)
                tick = " ✅" if matched else " ❌"
                st.markdown(
                    f"- **Reference Number Check:** Expected `{exp_ref}` | Extracted `{extracted_ref_display}`{tick}"
                )
            else:
                st.markdown(
                    f"- **Reference Number Check:** No reference number expected | Extracted `{extracted_ref_display}`"
                )
            st.markdown(f"- **What this demonstrates:** {selected_item['note']}")

        st.markdown("### Transcribed Text")
        st.text_area(
            "OCR Text",
            value=result.final_text,
            height=240,
            label_visibility="collapsed",
        )

        st.markdown("### Extracted Structured Fields")
        st.json(result.fields.model_dump())


if __name__ == "__main__":
    main()
