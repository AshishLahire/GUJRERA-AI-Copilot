"""SQLite cache for Stage 3 claim extraction (stored in the same DB file, separate table)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def compute_claim_cache_key(
    text: str,
    model: str,
    prompt_version: str,
    engine: str = "gemini",
) -> str:
    """Return SHA-256 hex digest of (text + engine + model + prompt_version)."""
    h = hashlib.sha256()
    h.update(text.encode("utf-8"))
    eff_model = (
        model
        if engine == "gemini" and not model.startswith("gemini:")
        else (f"{engine}:{model}" if not model.startswith(f"{engine}:") else model)
    )
    h.update(f"|{eff_model}|{prompt_version}".encode("utf-8"))
    return h.hexdigest()


class ClaimCache:
    """Separate SQLite table `claim_cache` in `ocr_cache.sqlite`."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS claim_cache (
                    cache_key TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    claim_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def get(self, cache_key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT claim_json FROM claim_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["claim_json"])

    def set(
        self,
        cache_key: str,
        *,
        model: str,
        prompt_version: str,
        claim_data: dict[str, Any],
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO claim_cache (cache_key, model, prompt_version, claim_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    model = excluded.model,
                    prompt_version = excluded.prompt_version,
                    claim_json = excluded.claim_json,
                    created_at = excluded.created_at
                """,
                (
                    cache_key,
                    model,
                    prompt_version,
                    json.dumps(claim_data, ensure_ascii=False),
                    now,
                ),
            )
            conn.commit()
