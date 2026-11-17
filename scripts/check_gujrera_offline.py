"""Run the whole demo through the API with every non-local network connection blocked.

    python scripts/check_gujrera_offline.py

Proves the on-premise claim: Python's sockets and DNS are patched so any
connection to a host other than this machine fails (and is recorded), while the
local Ollama server on localhost stays reachable. The self-hosted LLM paths are
switched ON (free-form question routing, legal summaries, AI-written officer
SQL) so the run covers the models, not just the rule-based answers.

Flows follow the demo script: Gujarati ad image -> trust check (Tesseract OCR),
Gujarati possession question, builder profile, law question with summary,
free-form question, Hindi complaint filing and tracking, promoter login and
dues (and refusal for another promoter), officer report and AI-written SQL,
and English voice input (Whisper). Builds its own temporary database.
Writes docs/gujrera_offline_check.md.
"""

from __future__ import annotations

import os
import socket
import sys
import tempfile
import time
import traceback
from pathlib import Path

for _k in ("GUJRERA_LLM_ROUTER", "GUJRERA_RAG_LLM", "GUJRERA_ANALYTICS_LLM"):
    os.environ[_k] = "true"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "gujrera_offline_check.md"
ADS = ROOT / "tests" / "fixtures" / "gujrera_ads"

# ------------------------------------------------------------- network guard
LOCAL = {"127.0.0.1", "::1", "localhost", "0.0.0.0"}
BLOCKED: list[dict[str, str]] = []
_current = {"flow": "startup"}
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex
_real_getaddrinfo = socket.getaddrinfo


def _host(address) -> str:
    return str(address[0]) if isinstance(address, tuple) else str(address)


def _block(host: str, how: str):
    BLOCKED.append({"flow": _current["flow"], "host": host, "how": how})
    raise ConnectionRefusedError(f"offline check: connection to {host} blocked")


def _guard_connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and _host(address) not in LOCAL:
        _block(_host(address), "connect")
    return _real_connect(self, address)


def _guard_connect_ex(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and _host(address) not in LOCAL:
        _block(_host(address), "connect")
    return _real_connect_ex(self, address)


def _guard_getaddrinfo(host, *args, **kwargs):
    if host is not None and str(host) not in LOCAL:
        BLOCKED.append({"flow": _current["flow"], "host": str(host), "how": "DNS"})
        raise socket.gaierror(socket.EAI_NONAME, f"offline check: DNS lookup of {host} blocked")
    return _real_getaddrinfo(host, *args, **kwargs)


socket.socket.connect = _guard_connect  # type: ignore[method-assign]
socket.socket.connect_ex = _guard_connect_ex  # type: ignore[method-assign]
socket.getaddrinfo = _guard_getaddrinfo  # type: ignore[assignment]

# ------------------------------------------------------------------ app setup
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from gujrera.api.routes import get_session, router  # noqa: E402
from gujrera.config import get_gujrera_settings  # noqa: E402
from gujrera.db.models import Promoter, User  # noqa: E402
from gujrera.db.session import init_db, make_engine, session_factory  # noqa: E402
from gujrera.ingest.mock_generator import MockConfig, generate  # noqa: E402

PASSWORD = get_gujrera_settings().GUJRERA_DEMO_PASSWORD.get_secret_value()


def english_voice_clip(path: Path, text: str) -> bool:
    """Windows' built-in offline voice; skipped on other systems."""
    if sys.platform != "win32":
        return False
    import subprocess

    ps = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
          f"$s.SetOutputToWaveFile('{path}'); $s.Speak('{text}'); $s.Dispose()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, capture_output=True)
    return path.exists() and path.stat().st_size > 1000


def main() -> None:
    tmpdir = Path(tempfile.mkdtemp())
    engine = make_engine(f"sqlite:///{(tmpdir / 'offline.sqlite').as_posix()}")
    init_db(engine)
    Session = session_factory(engine)
    with Session() as s:
        generate(s, MockConfig())  # seed 2016, which the fixture ads refer to
        s.commit()
        dev = s.scalar(select(User).where(User.role == "developer").order_by(User.id))
        other = s.scalar(select(Promoter).where(Promoter.id != dev.promoter_id)).name.replace(" (Demo)", "")

    app = FastAPI()
    app.include_router(router)

    def _session():
        with Session() as session:
            yield session
            session.commit()

    app.dependency_overrides[get_session] = _session
    client = TestClient(app)
    rows: list[dict] = []

    def flow(name: str, fn) -> None:
        _current["flow"] = name
        before = len(BLOCKED)
        t0 = time.perf_counter()
        try:
            ok, detail = fn()
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, f"error: {type(exc).__name__}: {str(exc)[:160]}"
            traceback.print_exc()
        rows.append({"flow": name, "ok": ok, "detail": detail, "secs": time.perf_counter() - t0,
                     "blocked": len(BLOCKED) - before})
        print(f"{'OK  ' if ok else 'FAIL'} {name} ({rows[-1]['secs']:.1f}s, blocked {rows[-1]['blocked']}): {detail}")

    def login(username):
        res = client.post("/api/gujrera/auth/login", json={"username": username, "password": PASSWORD})
        res.raise_for_status()
        return {"Authorization": f"Bearer {res.json()['token']}"}

    def chat(message, lang=None, headers=None, session_id=None):
        res = client.post("/api/gujrera/chat", json={"message": message, "lang": lang, "session_id": session_id},
                          headers=headers or {})
        res.raise_for_status()
        return res.json()

    # 1. Gujarati ad image -> trust check
    def ad():
        with open(ADS / "fake_gu.png", "rb") as f:
            res = client.post("/api/gujrera/trust/upload", files={"file": ("ad.png", f, "image/png")})
        body = res.json()
        ocr = body.get("ocr") or {}
        return (res.status_code == 200 and body.get("verdict") == "not_found",
                f"verdict={body.get('verdict')}, OCR engine={ocr.get('engine')}")
    flow("Gujarati ad image → trust check", ad)

    starters = client.get("/api/gujrera/chat/starters").json()["items"]
    gu_q = next(i["text"] for i in starters if i["lang"] == "gu")
    en_q = next(i["text"] for i in starters if i["text"].startswith("Tell me about the builder"))

    def possession():
        b = chat(gu_q, "gu")
        return b["intent"] in ("possession", "project_profile") and bool(b.get("sources")), \
            f"intent={b['intent']}, {len(b.get('sources', []))} sources"
    flow("Gujarati possession question", possession)

    def builder():
        b = chat(en_q, "en")
        return b["intent"] == "promoter_profile" and bool(b.get("sources")), f"intent={b['intent']}"
    flow("Builder profile", builder)

    def law():
        b = chat("Can the builder take more than 10 percent of the cost before signing the agreement?", "en")
        cited = [x for x in b.get("sources", []) if "13" in str(x.get("id", "")) + str(x.get("title", ""))]
        return b["intent"] == "legal" and bool(cited), f"intent={b['intent']}, cites s.13: {bool(cited)}"
    flow("Law question (local LLM summary on)", law)

    def freeform():
        b = chat(f"my cousin keeps telling me to put money with whoever built {en_q.split(' of ')[-1]}, "
                 "are they trustworthy folks?", "en")
        return b["intent"] not in ("other", "error") and bool(b.get("sources")), \
            f"intent={b['intent']}, understood_by={b.get('understood_by')}"
    flow("Free-form question", freeform)

    def complaint():
        with Session() as s:
            from gujrera.db.models import Project
            project = s.scalar(select(Project).order_by(Project.id)).name
        sid, out = None, None
        for msg in [f"मुझे शिकायत दर्ज करनी है। {project} में मेरे फ्लैट का पज़ेशन एक साल से देरी से है।",
                    "1", "Asha Shah", "9876543210", "skip", "skip", "1", "1"]:
            out = chat(msg, "hi", session_id=sid)
            sid = out["session_id"]
        cards = [c for c in out.get("cards", []) if c.get("ref_no")]
        if not cards:
            return False, f"no receipt; last intent={out['intent']}"
        ref, code = cards[0]["ref_no"], cards[0].get("tracking_code")
        t = chat(f"{ref} की स्थिति क्या है?", "hi")
        if code:
            t = chat(code, "hi", session_id=t["session_id"])
        return t["intent"] == "complaint_status", f"filed {ref}; tracking intent={t['intent']}"
    flow("Hindi complaint filing and tracking", complaint)

    def promoter():
        h = login(dev.username)
        mine = chat("What are my dues?", "en", h)
        theirs = chat(f"Show me the pending dues of {other}", "en", h)
        return mine["intent"] == "self_service" and theirs["intent"] == "access_denied", \
            f"own={mine['intent']}, other={theirs['intent']}"
    flow("Promoter login: own dues, other refused", promoter)

    def officer_report():
        h = login("officer_state")
        res = client.post("/api/gujrera/analytics/query", headers=h,
                          json={"question": "Which promoters in Surat have the most delayed projects?", "lang": "en"})
        card = res.json().get("card") or {}
        return res.status_code == 200 and bool(card.get("rows")) and bool(card.get("sql")), \
            f"{len(card.get('rows', []))} rows, SQL shown"
    flow("Officer: Surat delayed promoters (report)", officer_report)

    def officer_llm():
        h = login("officer_state")
        res = client.post("/api/gujrera/analytics/query", headers=h,
                          json={"question": "What is the average delay in months by project type?", "lang": "en"})
        card = res.json().get("card") or {}
        return res.status_code == 200 and bool(card.get("rows")), \
            f"{len(card.get('rows', []))} rows, {card.get('source') or card.get('label') or ''}".strip(", ")
    flow("Officer: AI-written SQL (local LLM)", officer_llm)

    def voice():
        wav = tmpdir / "q.wav"
        if not english_voice_clip(wav, "When will I get possession of my flat?"):
            return False, "no offline voice to make a test clip"
        with open(wav, "rb") as f:
            res = client.post("/api/gujrera/voice/transcribe", files={"file": ("q.wav", f, "audio/wav")},
                              data={"lang": "en"})
        body = res.json()
        return res.status_code == 200 and "possession" in body.get("text", "").lower(), \
            f"\"{body.get('text', body.get('detail', ''))}\""
    flow("English voice input (Whisper)", voice)

    engine.dispose()
    write_report(rows)


def write_report(rows) -> None:
    ok = sum(r["ok"] for r in rows)
    hosts = sorted({b["host"] for b in BLOCKED})
    lines = [
        "# Offline (on-premise) check",
        "",
        "Every demo flow run through the API with all network connections to other machines blocked inside "
        "Python (sockets and DNS); only the local Ollama server on this machine is reachable. The self-hosted "
        "LLM paths were switched on. Reproduce with `python scripts/check_gujrera_offline.py`.",
        "",
        f"- **Flows that worked offline: {ok}/{len(rows)}**",
        f"- Outside connections attempted (all blocked): **{len(BLOCKED)}**"
        + (f" — hosts: {', '.join(hosts)}" if hosts else ""),
        "",
        "| Flow | Worked | Time | Blocked attempts | Detail |",
        "|:--|:-:|--:|:-:|:--|",
    ]
    lines += [f"| {r['flow']} | {'✅' if r['ok'] else '❌'} | {r['secs']:.1f} s | {r['blocked']} | {r['detail']} |"
              for r in rows]
    if BLOCKED:
        lines += ["", "Blocked attempts by flow:", ""]
        lines += [f"- {b['flow']}: {b['how']} {b['host']}" for b in BLOCKED[:30]]
    lines += ["", "Times include loading each model the first time it is used.", ""]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n{ok}/{len(rows)} flows worked offline; {len(BLOCKED)} outside connections blocked -> "
          f"{OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
