"""Prompt constants for Vision-Language Model (VLM) OCR."""

PROMPT_VERSION = "v3"

VLM_OCR_PROMPT = (
    "Transcribe all text in this image exactly as written. Keep the "
    "original script (Hindi, Marathi, Tamil, English or mixed). Preserve "
    "spelling mistakes, punctuation, line breaks, reference numbers, dates, "
    "phone numbers, email addresses and amounts exactly as printed. Do not "
    "translate, correct, summarise or add commentary. If text is unreadable, "
    "write [unclear]. Output only the transcribed text. Output plain text only. "
    "Do not use markdown, headings, bold, bullet symbols or code blocks."
)
