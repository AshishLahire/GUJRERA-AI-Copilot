"""Lightweight backend serving only the GUJRERA endpoints.

Useful for demos and frontend work when the full Pramaan stack (retrieval
indexes, Whisper) is not installed:

    python -m uvicorn gujrera.api.dev_app:app --port 8000

The full backend (factcheck.api.app) also mounts these routes.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gujrera.api.routes import lifespan, router

app = FastAPI(title="GujRERA Saathi API (dev)", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/api/health")
def health() -> dict:
    # Minimal stand-in so the console's health banner stays quiet.
    return {"status": "ok", "offline_mode": True, "ollama_enabled": False, "vlm_model": "",
            "gemini_configured": False, "gemini_model": "", "daily_api_calls_used": 0,
            "daily_api_call_limit": 0, "mode": "gujrera-dev"}
