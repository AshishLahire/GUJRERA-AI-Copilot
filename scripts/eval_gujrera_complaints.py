"""Simulated complaint-filing conversations in Gujarati, Hindi and English.

    python scripts/eval_gujrera_complaints.py

A scripted buyer starts with a one-message story naming the project, then
answers whatever the copilot asks. Measures whether the complaint is submitted
complete, whether the category guessed from the story is right, whether the
form (A/B) is right, and how many turns it takes. Builds its own temporary
database; zero API calls. Writes docs/gujrera_complaints_eval.md.

The stories are templates, so this checks the flow and the rules, not how
well free-form real complaints are understood.
"""

from __future__ import annotations

import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from gujrera.chat.orchestrator import ChatState, respond  # noqa: E402
from gujrera.complaints.rules import form_for  # noqa: E402
from gujrera.db.models import Complaint, Project  # noqa: E402
from gujrera.db.repository import Principal, Repository  # noqa: E402
from gujrera.db.session import init_db, make_engine, session_factory  # noqa: E402
from gujrera.ingest.mock_generator import MockConfig, generate  # noqa: E402

OUT = ROOT / "docs" / "gujrera_complaints_eval.md"
PREFIX = {"en": "I want to file a complaint. ", "gu": "મારે ફરિયાદ નોંધાવવી છે. ", "hi": "मुझे शिकायत दर्ज करनी है। "}
STORIES = {
    "possession_delay": ("possession_with_interest", {
        "en": "Possession of my flat in {p} was promised for March 2025 but it is still not ready.",
        "gu": "{p} માં મારા ફ્લેટનું પઝેશન માર્ચ 2025 માં આપવાનું હતું પણ હજુ મળ્યું નથી.",
        "hi": "{p} में मेरे फ्लैट का पज़ेशन मार्च 2025 में मिलना था लेकिन अभी तक नहीं मिला।"}),
    "refund": ("refund_with_interest", {
        "en": "I cancelled my booking in {p} six months ago and want my money back but the builder is not paying.",
        "gu": "મેં {p} માં બુકિંગ રદ કર્યું છે અને મને મારા પૈસા પાછા જોઈએ છે પણ બિલ્ડર આપતા નથી.",
        "hi": "मैंने {p} में बुकिंग रद्द की है और मुझे पैसे वापस चाहिए लेकिन बिल्डर नहीं दे रहा।"}),
    "structural_defect": ("rectification", {
        "en": "There are big cracks in the walls and water leakage from the ceiling of my flat in {p}.",
        "gu": "{p} માં મારા ફ્લેટની દીવાલોમાં તિરાડ છે અને છત પરથી પાણી લીકેજ થાય છે.",
        "hi": "{p} में मेरे फ्लैट की दीवारों में दरार है और छत से पानी का रिसाव होता है।"}),
    "amenities_not_provided": ("rectification", {
        "en": "The club house and covered parking promised in {p} have not been provided.",
        "gu": "{p} માં વચન આપેલ ક્લબ હાઉસ અને પાર્કિંગની સુવિધા આપી નથી.",
        "hi": "{p} में वादा किया गया क्लब हाउस और पार्किंग की सुविधा नहीं दी गई।"}),
    "agreement_violation": ("other", {
        "en": "The developer of {p} is demanding extra charges that are not in my agreement.",
        "gu": "{p} ના ડેવલપર કરારમાં ન હોય તેવા વધારાના પૈસા માંગે છે.",
        "hi": "{p} का डेवलपर अनुबंध में नहीं लिखे अतिरिक्त शुल्क माँग रहा है।"}),
    "false_advertisement": ("compensation", {
        "en": "The brochure for {p} showed a swimming pool and garden that do not exist, and I want compensation.",
        "gu": "{p} ની જાહેરાતમાં બતાવેલ સ્વિમિંગ પૂલ અને ગાર્ડન અસ્તિત્વમાં નથી, મને વળતર જોઈએ છે.",
        "hi": "{p} के विज्ञापन में दिखाया गया स्विमिंग पूल और गार्डन मौजूद नहीं है, मुझे मुआवजा चाहिए।"}),
}
ANSWERS = {
    "name": {"en": "Ramesh Patel", "gu": "રમેશ પટેલ", "hi": "रमेश पटेल"},
    "mobile": "98765 43210", "email": "skip", "unit": "A-101", "consent": "1", "review": "1",
}


def simulate(repo: Repository, lang: str, story: str, relief: str) -> dict:
    state = ChatState()
    out = respond(PREFIX[lang] + story, state, repo).to_dict()
    turns, guessed = 1, None
    while state.complaint is not None and turns < 20:
        flow = state.complaint
        if guessed is None and flow.draft.category:
            guessed = flow.draft.category
        step = flow.awaiting
        if step == "relief":
            answer = str(next(o["n"] for o in flow.options if o["id"] == relief))
        elif step == "category":
            answer = "1"  # buyer accepts the first suggestion if asked
        elif step == "name":
            answer = ANSWERS["name"][lang]
        else:
            answer = ANSWERS.get(step, "skip")
        out = respond(answer, state, repo).to_dict()
        turns += 1
    card = next((c for c in out["cards"] if c["type"] == "complaint_submitted"), None)
    return {"submitted": card is not None, "turns": turns, "guessed": guessed, "lang_kept": out["lang"] == lang,
            "ref": card["ref_no"] if card else None}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        engine = make_engine(f"sqlite:///{(Path(tmp) / 'eval.sqlite').as_posix()}")
        init_db(engine)
        Session = session_factory(engine)
        with Session() as s:
            generate(s, MockConfig())
        rows = []
        with Session() as s:
            repo = Repository(s, Principal.anonymous())
            projects = s.scalars(select(Project).where(Project.status == "ongoing").order_by(Project.id).limit(5)).all()
            for category, (relief, by_lang) in STORIES.items():
                for lang, template in by_lang.items():
                    for p in projects:
                        name = p.name_gu if lang == "gu" and p.name_gu else p.name
                        r = simulate(repo, lang, template.format(p=name), relief)
                        c = s.scalar(select(Complaint).where(Complaint.ref_no == r["ref"])) if r["ref"] else None
                        complete = bool(c and c.project_id == p.id and c.summary and c.category and c.relief
                                        and c.complainant_hash and c.tracking_code_hash)
                        rows.append({**r, "lang": lang, "category": category, "complete": complete,
                                     "category_ok": r["guessed"] == category,
                                     "form_ok": bool(c and c.form == form_for(relief)),
                                     "project_ok": bool(c and c.project_id == p.id)})
        engine.dispose()

    n = len(rows)

    def pct(key: str, subset=None) -> str:
        subset = rows if subset is None else subset
        k = sum(1 for r in subset if r[key])
        return f"{k}/{len(subset)}"

    by_lang = defaultdict(list)
    by_cat = defaultdict(list)
    for r in rows:
        by_lang[r["lang"]].append(r)
        by_cat[r["category"]].append(r)
    avg_turns = sum(r["turns"] for r in rows) / n
    lines = [
        "# Complaint filing evaluation (simulated conversations)",
        "",
        f"{n} scripted conversations: 6 complaint types × 3 languages × 5 projects, on the mock registry. "
        "Zero API calls. Reproduce with `python scripts/eval_gujrera_complaints.py`.",
        "",
        "Stories come from templates, so this checks the flow and rules, not understanding of free-form "
        "real complaints.",
        "",
        f"- Submitted and complete on first submission: **{pct('complete')}** (deck target: 80%+)",
        f"- Right project picked from the story: **{pct('project_ok')}**",
        f"- Category guessed correctly from the story: **{pct('category_ok')}**",
        f"- Right form (A, or B for compensation): **{pct('form_ok')}**",
        f"- Stayed in the buyer's language throughout: **{pct('lang_kept')}**",
        f"- Average turns per complaint: **{avg_turns:.1f}**",
        "",
        "| Language | Complete | Category right |",
        "|:--|:-:|:-:|",
        *[f"| {k} | {pct('complete', v)} | {pct('category_ok', v)} |" for k, v in by_lang.items()],
        "",
        "| Complaint type | Complete | Category right | Form right |",
        "|:--|:-:|:-:|:-:|",
        *[f"| {k} | {pct('complete', v)} | {pct('category_ok', v)} | {pct('form_ok', v)} |"
          for k, v in by_cat.items()],
    ]
    misses = [r for r in rows if not (r["complete"] and r["category_ok"] and r["form_ok"] and r["lang_kept"])]
    if misses:
        lines += ["", "## Misses", ""]
        lines += [f"- {r['lang']} {r['category']}: guessed {r['guessed']}, complete {r['complete']}, "
                  f"form ok {r['form_ok']}, language kept {r['lang_kept']}" for r in misses[:40]]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
