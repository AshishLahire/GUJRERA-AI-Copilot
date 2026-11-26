"""Warm the assistant at startup, so no visitor waits for a model to load.

In the background, once the app is up:
1. load the AI model into GPU memory;
2. load the legal index and its embedding model;
3. answer the questions the home page suggests, in Gujarati, Hindi and English, which fills the
   name index and the answer cache (a suggested legal question is then answered at once);
then ping the model every few minutes so it stays loaded while the app runs.

Nothing is written: the answers run in a transaction that is rolled back, with no audit entries.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from sqlalchemy import Engine

from gujrera.config import get_gujrera_settings

log = logging.getLogger("gujrera.warmup")

# The examples on the home page, and a common question of each kind.
QUESTIONS = (
    "Can a builder take 20% before the agreement?",
    "પઝેશનમાં વિલંબ થાય તો શું મને વ્યાજ મળે?",
    "कब्जे में देरी होने पर क्या मुझे ब्याज मिलेगा?",
    "शिकायत कैसे दर्ज करें?",
    "When will I get possession of Mangal Square?",
    "મંગલ સ્ક્વેર નું પઝેશન ક્યારે મળશે?",
    "Approved projects in Ahmedabad",
)

STATUS: dict[str, Any] = {"state": "not started", "steps": {}}
_STARTED = False
_LOCK = threading.Lock()


def _step(name: str, fn) -> None:  # noqa: ANN001
    t = time.perf_counter()
    try:
        fn()
        STATUS["steps"][name] = round(time.perf_counter() - t, 2)
    except Exception as exc:  # noqa: BLE001 - warming is best effort; the app works without it
        STATUS["steps"][name] = f"failed: {exc.__class__.__name__}"
        log.warning("warm-up step %s failed: %s", name, exc)


def warm(engine: Engine) -> dict[str, Any]:
    from gujrera.chat.llm import load_model
    from gujrera.db.session import session_factory

    cfg = get_gujrera_settings()
    STATUS["state"] = "warming"
    started = time.perf_counter()
    _step("ai_model", lambda: load_model())
    if cfg.GUJRERA_SQL_MODEL != cfg.GUJRERA_LLM_MODEL and cfg.GUJRERA_ANALYTICS_LLM:
        _step("sql_model", lambda: load_model(cfg.GUJRERA_SQL_MODEL))

    def _legal() -> None:
        from gujrera.legal.search import default_index

        index = default_index()
        if index is not None:
            index.search("possession delay interest", k=1)  # loads the embedding model

    _step("legal_index", _legal)

    def _questions() -> None:
        from gujrera.chat.orchestrator import ChatState, respond
        from gujrera.db.repository import Principal, Repository

        with session_factory(engine)() as s:
            repo = Repository(s, Principal.anonymous(), audit_sink=lambda _row: None)
            try:
                for q in QUESTIONS:
                    respond(q, ChatState(), repo)
            finally:
                s.rollback()

    _step("suggested_questions", _questions)
    STATUS["state"] = "ready"
    STATUS["seconds"] = round(time.perf_counter() - started, 1)
    log.info("warm-up done in %.1f s: %s", STATUS["seconds"], STATUS["steps"])
    return STATUS


def _keep_warm(minutes: float) -> None:
    from gujrera.chat.llm import load_model

    cfg = get_gujrera_settings()
    while True:
        time.sleep(minutes * 60)
        load_model()
        if cfg.GUJRERA_SQL_MODEL != cfg.GUJRERA_LLM_MODEL and cfg.GUJRERA_ANALYTICS_LLM:
            load_model(cfg.GUJRERA_SQL_MODEL)


def start(engine_factory) -> bool:  # noqa: ANN001
    """Start warming in the background (once per process). Returns False when disabled."""
    global _STARTED
    cfg = get_gujrera_settings()
    if not cfg.GUJRERA_WARMUP:
        return False
    with _LOCK:
        if _STARTED:
            return True
        _STARTED = True

    def _run() -> None:
        try:
            warm(engine_factory())
        except Exception as exc:  # noqa: BLE001
            STATUS["state"] = f"failed: {exc.__class__.__name__}"
            log.warning("warm-up failed: %s", exc)
        if cfg.GUJRERA_KEEP_WARM_MINUTES > 0:
            _keep_warm(cfg.GUJRERA_KEEP_WARM_MINUTES)

    threading.Thread(target=_run, name="gujrera-warmup", daemon=True).start()
    return True
