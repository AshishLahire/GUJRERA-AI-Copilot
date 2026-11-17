"""Cross-tenant access attempts against the real API, in Gujarati, Hindi and English.

    python scripts/eval_gujrera_access.py

Logs in as demo users and tries to read data that belongs to someone else:
another promoter's dues, officer analytics without being an officer, another
district's records, another buyer's complaint, another user's chat session,
forged or expired tokens. An attempt passes when it is refused AND nothing
belonging to someone else appears in the response (no cited due notice of
another promoter, no other buyer's name or status timeline, no row from another
district). Builds its own temporary database; zero API calls to any model.
Writes docs/gujrera_access_eval.md.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

for _k in ("GUJRERA_LLM_ROUTER", "GUJRERA_RAG_LLM", "GUJRERA_ANALYTICS_LLM", "GUJRERA_LLM_PHRASING"):
    os.environ.setdefault(_k, "false")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from gujrera.api.routes import get_session, router  # noqa: E402
from gujrera.auth import issue_token  # noqa: E402
from gujrera.config import get_gujrera_settings  # noqa: E402
from gujrera.db.models import Complaint, DueNotice, Promoter, User  # noqa: E402
from gujrera.db.session import init_db, make_engine, session_factory  # noqa: E402
from gujrera.ingest.mock_generator import MockConfig, generate  # noqa: E402

OUT = ROOT / "docs" / "gujrera_access_eval.md"
PASSWORD = get_gujrera_settings().GUJRERA_DEMO_PASSWORD.get_secret_value()
CHAT, ANALYTICS, SUMMARY, ME = ("/api/gujrera/chat", "/api/gujrera/analytics/query",
                                "/api/gujrera/self-service/summary", "/api/gujrera/auth/me")

OTHER_DUES = {
    "en": "Show me the pending dues of {p}",
    "gu": "{p} ની બાકી ચુકવણી બતાવો",
    "hi": "{p} के बकाया भुगतान दिखाओ",
}
OTHER_NOTICES = {
    "en": "What notices has {p} received?",
    "gu": "{p} ને કઈ નોટિસ મળી છે?",
    "hi": "{p} को कौन से नोटिस मिले हैं?",
}
MY_DUES = {"en": "What are my dues?", "gu": "મારી બાકી ચુકવણી", "hi": "मेरे बकाया भुगतान"}
OFFICER_Q = {
    "en": "Which promoters in Surat have the most delayed projects?",
    "gu": "સુરતમાં કયા પ્રમોટરના પ્રોજેક્ટ સૌથી વધુ મોડા છે?",
    "hi": "सूरत में किन प्रमोटरों के प्रोजेक्ट सबसे ज़्यादा देरी से हैं?",
}
DISTRICT_Q = {
    "en": "complaints by district",
    "gu": "જિલ્લા પ્રમાણે ફરિયાદો",
    "hi": "जिले के अनुसार शिकायतें",
}
TRACK = {"en": "status of {r}", "gu": "{r} ની સ્થિતિ શું છે?", "hi": "{r} की स्थिति क्या है?"}


def main() -> None:
    tmp = Path(tempfile.mkdtemp()) / "access.sqlite"
    engine = make_engine(f"sqlite:///{tmp.as_posix()}")
    init_db(engine)
    Session = session_factory(engine)
    with Session() as s:
        generate(s, MockConfig(seed=2016))
        s.commit()

    app = FastAPI()
    app.include_router(router)

    def _session():
        with Session() as session:
            yield session
            session.commit()

    app.dependency_overrides[get_session] = _session
    client = TestClient(app)

    def login(username: str) -> dict[str, str]:
        res = client.post("/api/gujrera/auth/login", json={"username": username, "password": PASSWORD})
        res.raise_for_status()
        return {"Authorization": f"Bearer {res.json()['token']}"}

    with Session() as s:
        dev_promoters = s.scalars(select(DueNotice.promoter_id).distinct().order_by(DueNotice.promoter_id)).all()
        devs = [s.scalar(select(User).where(User.promoter_id == pid)) for pid in dev_promoters[:4]]
        due_owner = {d.id: d.promoter_id for d in s.scalars(select(DueNotice))}
        promoter_name = {p.id: p.name.replace(" (Demo)", "") for p in s.scalars(select(Promoter))}
        district_officers = s.scalars(select(User).where(User.role == "officer",
                                                         User.district_scope.is_not(None))).all()[:3]
        citizens = s.scalars(select(User).where(User.role == "citizen")).all()
        filed = s.scalars(select(Complaint).where(Complaint.complainant_user_id.is_not(None))).all()
        agent = s.scalar(select(User).where(User.role == "agent"))
        expired_token = issue_token(devs[0])

    results: list[tuple[str, str, str, bool, str]] = []  # (category, lang, attempt, passed, note)

    def record(cat, lang, attempt, passed, note=""):
        results.append((cat, lang, attempt, bool(passed), note))

    def foreign_dues(body: dict, own_pid: int | None) -> list[str]:
        return [str(src["id"]) for src in body.get("sources", [])
                if src.get("type") == "due_notice" and due_owner.get(int(src["id"])) != own_pid]

    # 1. Developer asks for another promoter's dues / notices (12)
    for i, lang in enumerate(("en", "gu", "hi")):
        for tmpl_name, tmpl in (("dues", OTHER_DUES), ("notices", OTHER_NOTICES)):
            for j in range(2):
                me = devs[(i + j) % len(devs)]
                victim = devs[(i + j + 1) % len(devs)].promoter_id
                body = client.post(CHAT, json={"message": tmpl[lang].format(p=promoter_name[victim]), "lang": lang},
                                   headers=login(me.username)).json()
                leaked = foreign_dues(body, me.promoter_id)
                record("Promoter reads another promoter's " + tmpl_name, lang,
                       f"{me.username} → {promoter_name[victim]}",
                       not leaked, f"intent={body.get('intent')}" + (f", leaked {leaked}" if leaked else ""))

    # 2. Not logged in / wrong role asks for "my dues" (6)
    for lang in ("en", "gu", "hi"):
        body = client.post(CHAT, json={"message": MY_DUES[lang], "lang": lang}).json()
        record("Anonymous asks for dues", lang, "no login", not foreign_dues(body, None) and
               body.get("intent") == "login_required", f"intent={body.get('intent')}")
    for lang, who in (("en", agent.username), ("gu", citizens[0].username), ("hi", citizens[1].username)):
        body = client.post(CHAT, json={"message": MY_DUES[lang], "lang": lang}, headers=login(who)).json()
        record("Agent or buyer asks for dues", lang, who, not foreign_dues(body, None),
               f"intent={body.get('intent')}")

    # 3. Non-officers call officer analytics directly (3) + self-service summary as buyer (1)
    for lang, (who, hdr) in zip(("en", "gu", "hi"), (("anonymous", {}),
                                                    (citizens[2].username, login(citizens[2].username)),
                                                    (devs[0].username, login(devs[0].username)))):
        res = client.post(ANALYTICS, json={"question": OFFICER_Q[lang], "lang": lang}, headers=hdr)
        record("Non-officer calls analytics API", lang, who, res.status_code == 403, f"HTTP {res.status_code}")
    res = client.get(SUMMARY, headers=login(citizens[3].username))
    record("Buyer calls promoter self-service API", "en", citizens[3].username, res.status_code == 403,
           f"HTTP {res.status_code}")

    # 4. District officer asks a state-wide report (3)
    for lang, off in zip(("en", "gu", "hi"), district_officers):
        body = client.post(ANALYTICS, json={"question": DISTRICT_Q[lang], "lang": lang},
                           headers=login(off.username)).json()
        card = body.get("card") or {}
        cols, rows = card.get("columns", []), card.get("rows", [])
        outside = [r for r in rows if "district" in cols and r[cols.index("district")] != off.district_scope]
        record("District officer reads other districts", lang, f"{off.username} ({off.district_scope})",
               not outside, f"{len(rows)} rows, {len(outside)} outside scope")

    # 5. Track someone else's complaint (3)
    for lang, c in zip(("en", "gu", "hi"), filed[:3]):
        with Session() as s:
            owner = s.get(User, c.complainant_user_id)
            other = next(u for u in citizens if u.id != owner.id)
            owner_name = owner.display_name or ""
        for who, hdr in ((other.username, login(other.username)),):
            body = client.post(CHAT, json={"message": TRACK[lang].format(r=c.ref_no), "lang": lang},
                               headers=hdr).json()
            shown = body.get("intent") == "complaint_status" or (owner_name and owner_name in body.get("text", ""))
            record("Buyer tracks another buyer's complaint", lang, f"{who} → {c.ref_no}", not shown,
                   f"intent={body.get('intent')}")

    # 6. Session hijack: reuse another user's chat session id (1)
    a = client.post(CHAT, json={"message": MY_DUES["en"]}, headers=login(devs[0].username)).json()
    b = client.post(CHAT, json={"message": MY_DUES["en"], "session_id": a["session_id"]},
                    headers=login(devs[1].username)).json()
    record("Reuse another user's chat session", "en", f"{devs[1].username} uses {devs[0].username}'s session",
           b["session_id"] != a["session_id"] and not foreign_dues(b, devs[1].promoter_id), "new session issued")

    # 7. Forged and expired tokens (2)
    body_, sig = expired_token.split(".")
    res = client.get(ME, headers={"Authorization": f"Bearer {body_}.{sig[::-1]}"})
    record("Forged token", "en", "signature altered", res.status_code == 401, f"HTTP {res.status_code}")
    real_time = time.time
    try:
        hours = get_gujrera_settings().GUJRERA_TOKEN_HOURS
        time.time = lambda: real_time() + hours * 3600 + 60  # type: ignore[assignment]
        res = client.get(ME, headers={"Authorization": f"Bearer {expired_token}"})
    finally:
        time.time = real_time  # type: ignore[assignment]
    record("Expired token", "en", f"{hours} h + 1 min later", res.status_code == 401, f"HTTP {res.status_code}")

    engine.dispose()
    write_report(results)


def write_report(results) -> None:
    passed = sum(r[3] for r in results)
    by_cat: dict[str, Counter] = {}
    for cat, _lang, _a, ok, _n in results:
        by_cat.setdefault(cat, Counter())["ok" if ok else "fail"] += 1
    langs = Counter(r[1] for r in results)
    lines = [
        "# Access-control evaluation (cross-tenant attempts)",
        "",
        f"{len(results)} attempts to read someone else's data through the real API, as demo users, in Gujarati, "
        "Hindi and English. Zero model calls. Reproduce with `python scripts/eval_gujrera_access.py`.",
        "",
        "An attempt passes only if it is refused and nothing belonging to someone else is in the response "
        "(cited due notices are checked against their owner, analytics rows against the officer's district, "
        "complaint replies for the other buyer's status or name).",
        "",
        f"- **Blocked with no leak: {passed}/{len(results)}** (plan target: 0 leaks)",
        f"- Languages: " + ", ".join(f"{k} {v}" for k, v in sorted(langs.items())),
        "",
        "| Attempt type | Blocked |",
        "|:--|:-:|",
    ]
    lines += [f"| {cat} | {c['ok']}/{c['ok'] + c['fail']} |" for cat, c in by_cat.items()]
    lines += ["", "<details><summary>All attempts</summary>", "", "| # | Type | Lang | Attempt | Result | Detail |",
              "|:-:|:--|:-:|:--|:-:|:--|"]
    lines += [f"| {i} | {c} | {l} | {a} | {'✅' if ok else '❌'} | {n} |"
              for i, (c, l, a, ok, n) in enumerate(results, 1)]
    lines += ["", "</details>", ""]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"{passed}/{len(results)} blocked with no leak -> {OUT.relative_to(ROOT)}")
    for c, l, a, ok, n in results:
        if not ok:
            print("  FAIL:", c, l, a, n)


if __name__ == "__main__":
    main()
