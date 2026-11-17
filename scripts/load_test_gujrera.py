"""Load test: 100 users at once against a real API server.

    python scripts/load_test_gujrera.py [--users 100] [--requests 5] [--llm-users 10]

Starts the API (uvicorn, one process, default settings: self-hosted LLM routing
and summaries ON) on a temporary copy of the mock registry, then:

1. Routine traffic: N users start together with no pause and each sends a mix
   of requests: gold questions in Gujarati, Hindi and English that the keyword
   rules answer, RERA checks of pasted ads, project/promoter profiles, and a
   promoter login plus "my dues". This is a burst far heavier than real traffic,
   where users pause to read.
2. Questions that need the self-hosted LLM (free-form questions the rules do not
   understand, and law questions with a summary): M users at once, one GPU.

The API answers in one piece (no streaming), so "answer starts" is measured as
the full response time, which is stricter. Writes docs/gujrera_load_test.md.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "gujrera_load_test.md"

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from gujrera.chat.gold import build_gold  # noqa: E402
from gujrera.config import get_gujrera_settings  # noqa: E402
from gujrera.db.models import DueNotice, Project, Promoter, User  # noqa: E402
from gujrera.db.session import init_db, make_engine, session_factory  # noqa: E402
from gujrera.ingest.mock_generator import MockConfig, generate  # noqa: E402
from gujrera.trust.samples import build_cases  # noqa: E402

PASSWORD = get_gujrera_settings().GUJRERA_DEMO_PASSWORD.get_secret_value()
LLM_QUESTIONS = [
    ("en", "my cousin says the people who built {p} are shady, should I worry before booking?"),
    ("en", "Can the builder take more than 10 percent of the cost before signing the agreement?"),
    ("en", "What can I do if the builder changes the approved plan without asking buyers?"),
    ("hi", "अगर बिल्डर समय पर फ्लैट नहीं देता तो मुझे क्या ब्याज मिलेगा?"),
    ("gu", "બિલ્ડર કરાર વગર 10 ટકાથી વધુ રકમ લઈ શકે?"),
]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def pct(values: list[float], p: float) -> float:
    values = sorted(values)
    return values[min(len(values) - 1, int(round(p / 100 * (len(values) - 1))))] if values else float("nan")


def build_db(path: Path):
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    init_db(engine)
    Session = session_factory(engine)
    with Session() as s:
        generate(s, MockConfig())
        s.commit()
        gold = [g for g in build_gold(s)]
        ads = [c.text for c in build_cases(s)]
        projects = s.scalars(select(Project.id)).all()
        promoters = s.scalars(select(Promoter.id)).all()
        devs = [u.username for u in s.scalars(select(User).where(
            User.promoter_id.in_(select(DueNotice.promoter_id)))).all()]
        first_project = s.scalar(select(Project).order_by(Project.id)).name.replace(" (Demo)", "")
    engine.dispose()
    return gold, ads, projects, promoters, devs, first_project


async def timed(client: httpx.AsyncClient, kind: str, method: str, url: str, **kw):
    t0 = time.perf_counter()
    try:
        res = await client.request(method, url, **kw)
        ok = res.status_code == 200
        body = res.json() if ok else {}
    except Exception:  # noqa: BLE001
        ok, body = False, {}
    return kind, time.perf_counter() - t0, ok, body


async def routine_user(client, rng, gold, ads, projects, promoters, devs, n, think=0.0):
    out = []
    for _ in range(n):
        if think:
            await asyncio.sleep(rng.uniform(0.5 * think, 1.5 * think))  # reading the last answer
        r = rng.random()
        if r < 0.55:
            g = rng.choice(gold)
            out.append(await timed(client, "chat question", "POST", "/api/gujrera/chat",
                                   json={"message": g.question, "lang": g.lang}))
        elif r < 0.7 and ads:
            out.append(await timed(client, "RERA check (pasted ad)", "POST", "/api/gujrera/trust/text",
                                   json={"text": rng.choice(ads)}))
        elif r < 0.85:
            if rng.random() < 0.5:
                out.append(await timed(client, "profile", "GET",
                                       f"/api/gujrera/profile/project/{rng.choice(projects)}?lang=gu"))
            else:
                out.append(await timed(client, "profile", "GET",
                                       f"/api/gujrera/profile/promoter/{rng.choice(promoters)}?lang=hi"))
        else:
            k, dt, ok, body = await timed(client, "login", "POST", "/api/gujrera/auth/login",
                                          json={"username": rng.choice(devs), "password": PASSWORD})
            out.append((k, dt, ok, body))
            if ok:
                out.append(await timed(client, "promoter: my dues", "POST", "/api/gujrera/chat",
                                       json={"message": "What are my dues?"},
                                       headers={"Authorization": f"Bearer {body['token']}"}))
    return out


async def run(base: str, users: int, reqs: int, llm_users: int, data) -> dict:
    gold, ads, projects, promoters, devs, first_project = data
    limits = httpx.Limits(max_connections=users + 10, max_keepalive_connections=users + 10)
    async with httpx.AsyncClient(base_url=base, timeout=180, limits=limits) as client:
        # warm-up: load models once, as a deployment would at start-up
        await client.post("/api/gujrera/chat", json={"message": LLM_QUESTIONS[1][1], "lang": "en"})
        await client.post("/api/gujrera/chat", json={"message": gold[0].question, "lang": gold[0].lang})

        phases = {}
        for name, think in (("realistic", 10.0), ("burst", 0.0)):
            t0 = time.perf_counter()
            results = await asyncio.gather(*[routine_user(client, random.Random(i), gold, ads, projects, promoters,
                                                          devs, reqs, think) for i in range(users)])
            phases[name] = ([x for user in results for x in user], time.perf_counter() - t0)

        t0 = time.perf_counter()
        llm = await asyncio.gather(*[timed(client, "needs the LLM", "POST", "/api/gujrera/chat",
                                           json={"message": q.format(p=first_project), "lang": lang})
                                     for lang, q in (LLM_QUESTIONS * (llm_users // len(LLM_QUESTIONS) + 1))[
                                         :llm_users]])
        llm_wall = time.perf_counter() - t0
    return {"phases": phases, "llm": list(llm), "llm_wall": llm_wall}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=100)
    ap.add_argument("--requests", type=int, default=5)
    ap.add_argument("--llm-users", type=int, default=10)
    args = ap.parse_args()

    db = Path(tempfile.mkdtemp()) / "load.sqlite"
    data = build_db(db)
    port = free_port()
    env = {**os.environ, "GUJRERA_DB_URL": f"sqlite:///{db.as_posix()}"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "gujrera.api.dev_app:app", "--port", str(port),
                               "--log-level", "warning"], cwd=ROOT, env=env)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            try:
                if httpx.get(base + "/api/gujrera/health", timeout=2).status_code == 200:
                    break
            except Exception:  # noqa: BLE001
                time.sleep(0.5)
        res = asyncio.run(run(base, args.users, args.requests, args.llm_users, data))
    finally:
        server.terminate()
        server.wait(timeout=20)
    report(res, args)


def summarise(rows):
    lat = [r[1] for r in rows if r[2]]
    return {"n": len(rows), "errors": sum(not r[2] for r in rows), "p50": pct(lat, 50), "p95": pct(lat, 95),
            "max": max(lat) if lat else float("nan"), "under3": sum(x <= 3 for x in lat)}


def _table(rows, kinds):
    out = ["| Request | Count | p50 | p95 | Slowest | Errors |", "|:--|--:|--:|--:|--:|--:|"]
    for k in kinds:
        s = summarise([r for r in rows if r[0] == k])
        out.append(f"| {k} | {s['n']} | {s['p50']:.2f} s | {s['p95']:.2f} s | {s['max']:.2f} s | {s['errors']} |")
    return out


def report(res, args) -> None:
    def is_llm(r):
        return r[0] == "chat question" and r[3].get("understood_by") == "llm"

    lines = [
        "# Load test",
        "",
        f"Real API server (one uvicorn process, default settings, self-hosted LLM on) on this laptop "
        f"({os.cpu_count()} CPU threads, RTX 3070 Ti), mock registry. Reproduce with "
        "`python scripts/load_test_gujrera.py`.",
        "",
        "The API returns each answer in one piece, so the times below run until the **whole** answer has "
        "arrived, which is stricter than the deck's \"answer starts within 3 seconds\". Requests are a mix of "
        "questions in Gujarati, Hindi and English from the gold set, pasted-ad checks, project and promoter "
        "profiles, and promoter login plus \"my dues\". Questions the rules passed to the LLM are reported "
        "in part 3.",
        "",
    ]
    llm_extra = []
    titles = {
        "realistic": (f"1. {args.users} users at once, reading between questions (deck target)",
                      f"{args.users} users each send {args.requests} requests, pausing 5–15 s between them "
                      "to read the answer, as people do."),
        "burst": (f"2. Stress: {args.users} users with no pause",
                  f"The same {args.users} users fire all {args.requests} requests back to back. Far heavier than "
                  "real use; shows where one process saturates."),
    }
    for name, (rows, wall) in res["phases"].items():
        routine = [r for r in rows if not is_llm(r)]
        llm_extra += [r for r in rows if is_llm(r)]
        st = summarise(routine)
        title, desc = titles[name]
        lines += [f"## {title}", "", desc, "",
                  f"- Requests: **{st['n']}** in {wall:.1f} s ({st['n'] / wall:.1f} per second), "
                  f"errors: **{st['errors']}**",
                  f"- Complete answer within 3 s: **{st['under3']}/{st['n'] - st['errors']}** "
                  f"({100 * st['under3'] / max(1, st['n'] - st['errors']):.0f}%; p50 {st['p50']:.2f} s, "
                  f"p95 {st['p95']:.2f} s, slowest {st['max']:.2f} s)", ""]
        lines += _table(routine, sorted({r[0] for r in routine})) + [""]
    llm_s = summarise(res["llm"] + llm_extra)
    lines += [
        "## 3. Questions that need the self-hosted LLM",
        "",
        f"{args.llm_users} free-form and law questions sent at once, plus the {len(llm_extra)} gold questions "
        "in parts 1–2 that the rules passed to the LLM; one laptop GPU, one Ollama model.",
        "",
        f"- Answers: **{llm_s['n']}**, errors **{llm_s['errors']}**; within 3 s: {llm_s['under3']}; "
        f"p50 {llm_s['p50']:.1f} s, p95 {llm_s['p95']:.1f} s, slowest {llm_s['max']:.1f} s",
        "",
        "One GPU answers LLM questions one after another, so they queue when many arrive together. For the "
        "PoC: stream answers so the first words arrive in about a second, serve the model with parallel "
        "batching (e.g. vLLM on a GPU server), and keep the rule-based path for routine questions, as now. "
        "More API processes need the chat state moved to a shared store (Redis or Postgres), as noted in the "
        "plan.",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
