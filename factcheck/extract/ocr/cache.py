"""SQLite OCR result cache and daily API call counter.

Cache keys are SHA-256 of ``(image_bytes + engine + model_name + prompt_version)``.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

from factcheck.extract.ocr.prompts import PROMPT_VERSION


def compute_cache_key(
    image_bytes: bytes,
    engine: str,
    model_name: str,
    prompt_version: str = PROMPT_VERSION,
) -> str:
    """Return the hex SHA-256 digest of (image bytes + engine + model name + prompt version)."""
    h = hashlib.sha256()
    h.update(image_bytes)
    h.update(f"|{engine}|{model_name}|{prompt_version}".encode("utf-8"))
    return h.hexdigest()


def compute_image_hash(
    image_bytes: bytes,
    engine: str = "ollama",
    model_name: str = "qwen3-vl:8b",
    prompt_version: str = PROMPT_VERSION,
) -> str:
    """Return the cache key SHA-256 of (image bytes + engine + model name + prompt version)."""
    return compute_cache_key(image_bytes, engine, model_name, prompt_version)


class OCRCache:
    """SQLite-backed cache for OCR outputs and daily hosted-API call counter."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ocr_cache (
                    image_hash TEXT PRIMARY KEY,
                    final_text TEXT NOT NULL,
                    engine_used TEXT NOT NULL,
                    valid INTEGER NOT NULL,
                    fields_json TEXT NOT NULL,
                    time_ms REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(ocr_cache)").fetchall()
            }
            if "time_ms" not in cols:
                conn.execute("ALTER TABLE ocr_cache ADD COLUMN time_ms REAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_call_counter (
                    call_date TEXT PRIMARY KEY,
                    call_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.commit()

    def get(self, image_hash: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT final_text, engine_used, valid, fields_json, time_ms FROM ocr_cache WHERE image_hash = ?",
                (image_hash,),
            ).fetchone()
        if row is None:
            return None
        final_text, engine_used, valid_int, fields_json, time_ms = row
        return {
            "image_hash": image_hash,
            "final_text": final_text,
            "engine_used": engine_used,
            "valid": bool(valid_int),
            "fields": json.loads(fields_json) if fields_json else {},
            "time_ms": float(time_ms) if time_ms is not None else None,
        }

    def set(
        self,
        *,
        image_hash: str,
        final_text: str,
        engine_used: str,
        valid: bool,
        fields: dict[str, Any],
        time_ms: float | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ocr_cache (image_hash, final_text, engine_used, valid, fields_json, time_ms)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(image_hash) DO UPDATE SET
                    final_text = excluded.final_text,
                    engine_used = excluded.engine_used,
                    valid = excluded.valid,
                    fields_json = excluded.fields_json,
                    time_ms = excluded.time_ms,
                    created_at = CURRENT_TIMESTAMP
                """,
                (
                    image_hash,
                    final_text,
                    engine_used,
                    1 if valid else 0,
                    json.dumps(fields, ensure_ascii=False),
                    time_ms,
                ),
            )
            conn.commit()

    def get_daily_api_calls(self, day: str | None = None) -> int:
        day_str = day or date.today().isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT call_count FROM api_call_counter WHERE call_date = ?",
                (day_str,),
            ).fetchone()
        return int(row[0]) if row else 0

    def reset_daily_api_calls(self, day: str | None = None) -> None:
        day_str = day or date.today().isoformat()
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM api_call_counter WHERE call_date = ?",
                (day_str,),
            )
            conn.commit()

    def increment_daily_api_calls(self, day: str | None = None) -> int:
        day_str = day or date.today().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO api_call_counter (call_date, call_count)
                VALUES (?, 1)
                ON CONFLICT(call_date) DO UPDATE SET
                    call_count = call_count + 1
                """,
                (day_str,),
            )
            conn.commit()
            row = conn.execute(
                "SELECT call_count FROM api_call_counter WHERE call_date = ?",
                (day_str,),
            ).fetchone()
        return int(row[0]) if row else 1
