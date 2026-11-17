"""Voice evaluation: word error rate (WER) and whether the spoken question still gets the right answer.

    python scripts/eval_gujrera_voice.py --make-sheet      # write the prompts and the recording sheet
    python scripts/eval_gujrera_voice.py --synthetic-en    # make English clips with Windows' offline voices
    python scripts/eval_gujrera_voice.py                   # transcribe every clip found and score it

30 prompts (10 each in Gujarati, Hindi and English) about the demo registry:
possession dates, builders, projects, complaints and the law. People read them
aloud and save each recording as data/eval/gujrera_voice/clips/<id>.<ext>
(wav, mp3, m4a, ogg, opus or webm; a phone voice note is fine). Each clip is
transcribed with the same self-hosted Whisper the app uses, with the language
the user picked in the app, and scored two ways:

- WER and CER against the prompt text (after the same normalisation as Pramaan's
  ASR benchmark: punctuation, nukta, digits);
- task success: the transcript is sent to the chat as a user would and passes
  if the reply has the expected intent and cites the expected project, promoter
  or section.

Prompts whose clips are missing are skipped and counted. Clips made by
--synthetic-en are computer voices and are reported separately, since they are
much easier than real speakers. Writes docs/gujrera_voice_eval.md.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import os
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

for _k in ("GUJRERA_LLM_ROUTER", "GUJRERA_RAG_LLM", "GUJRERA_ANALYTICS_LLM", "GUJRERA_LLM_PHRASING"):
    os.environ.setdefault(_k, "false")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import select  # noqa: E402

from gujrera.chat.orchestrator import ChatState, respond  # noqa: E402
from gujrera.db.models import Project, Promoter  # noqa: E402
from gujrera.db.repository import Principal, Repository  # noqa: E402
from gujrera.db.session import init_db, make_engine, session_factory  # noqa: E402
from gujrera.ingest.mock_generator import MockConfig, generate  # noqa: E402

VOICE_DIR = ROOT / "data" / "eval" / "gujrera_voice"
CLIPS = VOICE_DIR / "clips"
PROMPTS = VOICE_DIR / "prompts.csv"
SHEET = ROOT / "docs" / "gujrera_voice_recording_sheet.md"
OUT = ROOT / "docs" / "gujrera_voice_eval.md"
EXTS = (".wav", ".mp3", ".m4a", ".ogg", ".opus", ".webm")

Q = {
    "possession": {"en": "When will I get possession of my flat in {p}?",
                   "gu": "{p} માં મારા ફ્લેટનું પઝેશન ક્યારે મળશે?",
                   "hi": "{p} में मेरे फ्लैट का पज़ेशन कब मिलेगा?"},
    "promoter": {"en": "Tell me about the builder {b}",
                 "gu": "બિલ્ડર {b} વિશે જણાવો",
                 "hi": "बिल्डर {b} के बारे में बताइए"},
    "project": {"en": "Give me the details of {p}",
                "gu": "{p} ની માહિતી આપો",
                "hi": "{p} की जानकारी दीजिए"},
    "complaints": {"en": "How many complaints are there against {p}?",
                   "gu": "{p} સામે કેટલી ફરિયાદો છે?",
                   "hi": "{p} के खिलाफ कितनी शिकायतें हैं?"},
}
LEGAL = {"en": ("What does section eighteen of the RERA Act say about refunds?", "Section 18"),
         "gu": ("રેરા કાયદાની કલમ 18 શું કહે છે?", "Section 18"),
         "hi": ("रेरा कानून की धारा 18 क्या कहती है?", "Section 18")}
INTENTS = {"possession": ("possession",), "promoter": ("promoter_profile",),
           "project": ("project_profile", "possession"), "complaints": ("complaints", "project_profile"),
           "legal": ("legal",)}
PLAN = ["possession", "possession", "possession", "promoter", "promoter", "project", "project",
        "complaints", "complaints", "legal"]


def _clean(name: str) -> str:
    return name.replace(" (Demo)", "").replace(" (ડેમો)", "")


def demo_db():
    engine = make_engine(f"sqlite:///{(Path(tempfile.mkdtemp()) / 'voice.sqlite').as_posix()}")
    init_db(engine)
    Session = session_factory(engine)
    with Session() as s:
        generate(s, MockConfig())  # seed 2016: the demo registry
        s.commit()
    return engine, Session


def make_prompts(Session) -> list[dict]:
    rows = []
    with Session() as s:
        projects = s.scalars(select(Project).where(Project.status == "ongoing").order_by(Project.id)).all()
        promoters = s.scalars(select(Promoter).order_by(Promoter.id)).all()
        for li, lang in enumerate(("gu", "hi", "en")):
            pi = bi = 0
            for n, kind in enumerate(PLAN, 1):
                if kind == "legal":
                    text, expect_id = LEGAL[lang]
                    expect_type = "legal_act"
                elif kind == "promoter":
                    b = promoters[(li * 2 + bi) % len(promoters)]
                    bi += 1
                    name = b.name_gu if lang == "gu" and b.name_gu else b.name
                    text, expect_type, expect_id = Q[kind][lang].format(b=_clean(name)), "promoter", f"{b.id}|promoter:{b.id}"
                else:
                    p = projects[(li * 7 + pi) % len(projects)]
                    pi += 1
                    name = p.name_gu if lang == "gu" and p.name_gu else p.name
                    text, expect_type, expect_id = (Q[kind][lang].format(p=_clean(name)), "project",
                                                    f"{p.rera_no}|project:{p.id}|{p.id}")
                rows.append({"id": f"{lang}_{n:02d}", "lang": lang, "kind": kind, "text": text,
                             "expect_intent": "|".join(INTENTS[kind]), "expect_type": expect_type,
                             "expect_id": expect_id})
    return rows


def write_sheet(rows: list[dict]) -> None:
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    CLIPS.mkdir(parents=True, exist_ok=True)
    with PROMPTS.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    lines = [
        "# Voice recording sheet (30 clips)",
        "",
        "Read each line aloud once, naturally, as you would ask a helpline. Record on a phone (a WhatsApp "
        "voice note is fine) or a laptop, in a normal room. Save each recording with its ID as the file name, "
        "e.g. `gu_01.m4a`, in `data/eval/gujrera_voice/clips/`, then run "
        "`python scripts/eval_gujrera_voice.py`.",
        "",
        "Different speakers for different languages are better than one person reading everything. Small "
        "slips are fine: the evaluation compares against the text below, so read it as written.",
        "",
        "| ID | Language | Read this |",
        "|:--|:--|:--|",
    ]
    names = {"gu": "Gujarati", "hi": "Hindi", "en": "English"}
    lines += [f"| {r['id']} | {names[r['lang']]} | {r['text']} |" for r in rows]
    lines.append("")
    SHEET.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {PROMPTS.relative_to(ROOT)} and {SHEET.relative_to(ROOT)} ({len(rows)} prompts)")


def read_prompts() -> list[dict]:
    with PROMPTS.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def synthetic_en(rows: list[dict]) -> None:
    """English clips from Windows' built-in offline voices, alternating speakers."""
    CLIPS.mkdir(parents=True, exist_ok=True)
    for i, r in enumerate(x for x in rows if x["lang"] == "en"):
        path = CLIPS / f"{r['id']}.syn.wav"
        voice = ("Microsoft David Desktop", "Microsoft Zira Desktop")[i % 2]
        text = r["text"].replace("'", "''")
        ps = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              f"$s.SelectVoice('{voice}'); $s.Rate = 0; $s.SetOutputToWaveFile('{path}'); $s.Speak('{text}'); "
              "$s.Dispose()")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, capture_output=True)
    print(f"Wrote synthetic English clips to {CLIPS.relative_to(ROOT)} (*.syn.wav)")


def _normaliser():
    spec = importlib.util.spec_from_file_location("eval_asr", ROOT / "scripts" / "eval_asr.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.normalize_text_for_asr


def find_clips(r: dict) -> list[tuple[Path, bool]]:
    out = []
    for ext in EXTS:
        if (CLIPS / f"{r['id']}{ext}").exists():
            out.append((CLIPS / f"{r['id']}{ext}", False))
    if (CLIPS / f"{r['id']}.syn.wav").exists():
        out.append((CLIPS / f"{r['id']}.syn.wav", True))
    return out


def evaluate() -> None:
    import jiwer

    from factcheck.ingest.audio.transcribe import transcribe_audio

    norm = _normaliser()
    rows = read_prompts()
    engine, Session = demo_db()
    results = []
    for r in rows:
        for path, synthetic in find_clips(r):
            t0 = time.perf_counter()
            tr = transcribe_audio(path, language=r["lang"], engine="whisper", use_cache=False)
            secs = time.perf_counter() - t0
            hyp = (tr.get("text") or "").strip()
            ref_n, hyp_n = norm(r["text"]), norm(hyp)
            wer = jiwer.wer(ref_n, hyp_n) if ref_n else 0.0
            cer = jiwer.cer(ref_n, hyp_n) if ref_n else 0.0
            with Session() as s:
                reply = respond(hyp or "-", ChatState(), Repository(s, Principal.anonymous()), lang=r["lang"]).to_dict()
                s.rollback()
            ok_intent = reply["intent"] in r["expect_intent"].split("|")
            want = set(r["expect_id"].split("|"))
            ok_entity = any(str(src.get("id")) in want or (r["expect_type"] == "legal_act" and
                                                           any(w in str(src.get("id")) for w in want))
                            for src in reply.get("sources", []))
            offered = reply["intent"] == "did_you_mean" and any(
                o.get("kind") == r["expect_type"] and str(o.get("id")) in want for o in reply.get("options", []))
            results.append({**r, "file": path.name, "synthetic": synthetic, "hyp": hyp, "wer": wer, "cer": cer,
                            "task_ok": ok_intent and ok_entity, "offered": offered, "intent": reply["intent"], "secs": secs})
            print(f"{r['id']} {'SYN' if synthetic else 'REAL'} WER {wer:.2f} task {'ok' if ok_intent and ok_entity else 'FAIL'}"
                  f" | {hyp}")
    engine.dispose()
    report(rows, results)


def report(rows, results) -> None:
    names = {"gu": "Gujarati", "hi": "Hindi", "en": "English"}
    lines = [
        "# Voice evaluation",
        "",
        "Spoken questions about the demo registry, transcribed with the self-hosted Whisper small the app uses "
        "(language as picked in the app), then sent to the chat. Reproduce with "
        "`python scripts/eval_gujrera_voice.py`; the prompts and how to record them are in "
        "`docs/gujrera_voice_recording_sheet.md`.",
        "",
        "- **WER / CER**: word / character error rate against the prompt text (lower is better).",
        "- **Task success**: the transcript, sent to the chat, gets the expected answer type and cites the "
        "expected project, builder or section. This is what matters to a user: a transcript with errors can "
        "still be answered correctly.",
        "- **Right name offered**: the heard name was close but not exact, and the chat asked \"Did you mean "
        "…?\" with the right project or builder, so the user gets the answer with one tap (☝️ below).",
        "",
    ]
    for synthetic, title in ((False, "Real speakers"), (True, "Computer voices (Windows, offline; much easier "
                                                                "than real speech)")):
        group = [x for x in results if x["synthetic"] == synthetic]
        lines += [f"## {title}", ""]
        if not group:
            lines += ["No clips yet." + (" Record them with the sheet above." if not synthetic else ""), ""]
            continue
        lines += ["| Language | Clips | WER | CER | Answered right | Right name offered (one tap) | "
                  "Avg. transcription time |", "|:--|:-:|:-:|:-:|:-:|:-:|:-:|"]
        by = defaultdict(list)
        for x in group:
            by[x["lang"]].append(x)
        for lang in ("gu", "hi", "en"):
            g = by.get(lang)
            if not g:
                lines.append(f"| {names[lang]} | 0 of 10 | – | – | – | – | – |")
                continue
            lines.append(f"| {names[lang]} | {len(g)} of 10 | {sum(x['wer'] for x in g) / len(g):.0%} | "
                         f"{sum(x['cer'] for x in g) / len(g):.0%} | {sum(x['task_ok'] for x in g)}/{len(g)} | {sum(x['offered'] for x in g)}/{len(g)} | "
                         f"{sum(x['secs'] for x in g) / len(g):.1f} s |")
        lines += ["", "<details><summary>Every clip</summary>", "",
                  "| ID | Said | Heard | WER | Task |", "|:--|:--|:--|:-:|:-:|"]
        lines += [f"| {x['id']} | {x['text']} | {x['hyp']} | {x['wer']:.0%} | {'✅' if x['task_ok'] else ('☝️' if x['offered'] else '❌')} "
                  f"({x['intent']}) |" for x in group]
        lines += ["", "</details>", ""]
    lines += [
        "Gujarati is the known weak spot of Whisper small (the deck cites about 64% WER). The app therefore "
        "puts the transcript in the text box for the user to check before sending, and warns for Gujarati. "
        "The PoC plan replaces it with IndicConformer for Gujarati and Hindi.",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"-> {OUT.relative_to(ROOT)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--make-sheet", action="store_true")
    ap.add_argument("--synthetic-en", action="store_true")
    args = ap.parse_args()
    if args.make_sheet or not PROMPTS.exists():
        engine, Session = demo_db()
        write_sheet(make_prompts(Session))
        engine.dispose()
    if args.synthetic_en:
        synthetic_en(read_prompts())
    if not (args.make_sheet or args.synthetic_en):
        evaluate()


if __name__ == "__main__":
    main()
