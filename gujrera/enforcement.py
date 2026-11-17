"""Unregistered-project watch: citizen ad reports grouped into enforcement cases for GUJRERA.

When a buyer checks an ad and it fails (number not in the registry, no number, lapsed registration, or
details that do not match), they can report it. The server re-runs the check on the ad text (it never
trusts a verdict sent by the browser), pulls out who and where (project and promoter as advertised,
district, phone numbers, websites, "pay to this account"), and files it under a case:

- same claimed registration number -> same case;
- otherwise the same advertised project name (allowing small spelling differences) in the same district.

Officers see cases ranked by how many separate ads were reported and how recently, open the evidence
and move each case through new -> reviewing -> notice issued -> closed. The law each kind points to:

- unregistered: Section 3 (no advertising, booking or sale without registration); penalty Section 59.
- lapsed: selling under a lapsed or revoked registration (Sections 3, 6 and 7).
- misleading: Section 12 (false or incorrect statements in an advertisement), e.g. a different promoter
  or a possession date later than registered; Section 13 for taking more than 10% before an agreement.

The reporter's name and number are never stored; a logged-in reporter is linked by user id only.
Reading and updating cases is for officers; district officers see their own district.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import func, inspect, select
from sqlalchemy.engine import Engine

from gujrera.db.models import AdReport, Base, EnforcementCase
from gujrera.db.repository import AccessDenied, Repository
from gujrera.trust.checks import GUJARAT_DISTRICTS as DISTRICTS, TrustReport

UNREGISTERED, LAPSED, MISLEADING = "unregistered", "lapsed", "misleading"
STATUSES = ("new", "reviewing", "notice_issued", "closed")
OUTCOMES = ("registered", "false_alarm", "penalty", "other")
KIND_FOR_VERDICT = {"not_found": UNREGISTERED, "no_rera_number": UNREGISTERED,
                    "lapsed_or_revoked": LAPSED, "mismatch": MISLEADING}
MISLEADING_CHECKS = ("possession_date", "promoter_match", "booking_over_limit")
LAW = {
    UNREGISTERED: "RERA Act, 2016, Section 3 (registration before advertising or sale); penalty Section 59",
    LAPSED: "RERA Act, 2016, Sections 3, 6 and 7 (sale under a lapsed or revoked registration)",
    MISLEADING: "RERA Act, 2016, Section 12 (false statements in an advertisement); Section 13 (advance above 10%)",
}
NAME_MATCH = 90


def ensure_tables(engine: Engine) -> None:
    """Add tables introduced after a database was seeded (enforcement cases, ad reports, order compliance)."""
    from gujrera.db.models import OrderCompliance

    names = set(inspect(engine).get_table_names())
    missing = [t for t in (EnforcementCase.__table__, AdReport.__table__, OrderCompliance.__table__) if t.name not in names]
    if missing:
        Base.metadata.create_all(engine, tables=missing)


# ------------------------------------------------------------------ extraction
_PHONE = re.compile(r"(?<!\d)(?:\+91[\s-]?|0)?([6-9]\d{4})[\s-]?(\d{5})(?!\d)")
_WEB = re.compile(r"\b((?:https?://)?(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|in|co\.in|net|org|info|online|site)(?:/\S*)?)",
                  re.IGNORECASE)
_TITLE_SPLIT = re.compile(r"^(.+?)\s+(?:by|from|-|–|—|\|)\s+(.+)$", re.IGNORECASE)
_TITLE_NOISE = re.compile(r"^(?:[^\w઀-૿ऀ-ॿ]*(?:new launch|ધમાકા ઓફર|धमाका ऑफर|offer|ઓફર|ऑफर)[!:.\s-]*)+", re.IGNORECASE)


def extract_ad_details(text: str) -> dict[str, Any]:
    """Who and where, as printed on the ad. Best effort: officers see the full excerpt as well."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    title = _TITLE_NOISE.sub("", lines[0]).strip() if lines else ""
    project, promoter = title, None
    m = _TITLE_SPLIT.match(title)
    if m:
        project, promoter = m.group(1).strip(), m.group(2).strip()
    text_lc = (text or "").lower()
    district = next((d for k, d in DISTRICTS.items() if k in text_lc), None)
    phones = sorted({a + b for a, b in _PHONE.findall(text or "")})
    sites = sorted({w.lower().rstrip(".,)") for w in _WEB.findall(text or "") if "@" not in w})
    return {"project": project[:200] or None, "promoter": (promoter or "")[:200] or None, "district": district,
            "phones": phones[:5], "websites": sites[:5]}


def kind_of(report: TrustReport) -> str | None:
    """Which enforcement kind a checked ad belongs to, or None if there is nothing to report."""
    if report.verdict in KIND_FOR_VERDICT:
        return KIND_FOR_VERDICT[report.verdict]
    if report.verdict == "registered_with_warnings" and any(
            c.id in MISLEADING_CHECKS and c.severity == "critical" and c.status in ("fail", "warn")
            for c in report.checks):
        return MISLEADING
    return None


def _norm(name: str | None) -> str:
    return re.sub(r"[^\w઀-૿ऀ-ॿ]+", " ", (name or "").lower()).strip()


# ---------------------------------------------------------------------- filing
def file_report(repo: Repository, text: str, report: TrustReport, *, channel: str,
                today: date | None = None) -> tuple[AdReport, EnforcementCase, bool]:
    """Store a citizen's report and attach it to a case. Returns (report, case, is_new_report).
    Raises ValueError when the ad passed the check (nothing to report)."""
    kind = kind_of(report)
    if kind is None:
        raise ValueError("This ad matches the registry, so there is nothing to report.")
    s = repo.s
    today = today or date.today()
    clean = (text or "").strip()
    digest = hashlib.sha256(re.sub(r"\s+", " ", clean.lower()).encode("utf-8")).hexdigest()
    existing = s.scalar(select(AdReport).where(AdReport.text_hash == digest))
    if existing is not None:  # the same ad reported again: one report, no double counting
        return existing, s.get(EnforcementCase, existing.case_id), False

    details = extract_ad_details(clean)
    claimed = report.claim.get("project_numbers") or []
    claimed_rera = (claimed[0].get("normalised") if isinstance(claimed[0], dict) else str(claimed[0])) if claimed else None
    project_id = report.records[0].get("id") if report.records else None
    problems = [f"{c.title}: {c.detail}" for c in report.checks if c.status == "fail"]
    pays_account = any(c.id == "forensic_payment_to_account" for c in report.checks)

    case = _find_case(repo, kind, claimed_rera, details["project"], details["district"])
    if case is None:
        seq = (s.scalar(select(func.count()).select_from(EnforcementCase)) or 0) + 1
        case = EnforcementCase(ref_no=f"ENF-{today.year}-{seq:04d}", kind=kind,
                               title=details["project"] or claimed_rera or "Unnamed project",
                               advertised_promoter=details["promoter"], district=details["district"],
                               claimed_rera=claimed_rera, project_id=project_id, status="new",
                               opened_on=today, updated_on=today, is_mock=bool(report.is_mock))
        s.add(case)
        s.flush()
    else:
        case.updated_on = today
        if case.status == "closed":  # new evidence reopens a closed case
            case.status = "reviewing"
            case.notes = (case.notes or "") + f"\n{today.isoformat()}: reopened by a new citizen report."
    row = AdReport(case_id=case.id, reported_on=today, channel=channel, verdict=report.verdict,
                   claimed_rera=claimed_rera, advertised_project=details["project"],
                   advertised_promoter=details["promoter"], district=details["district"],
                   contact_phones=", ".join(details["phones"]) or None, websites=", ".join(details["websites"]) or None,
                   asks_payment_to_account=pays_account, problems="\n".join(problems) or None,
                   excerpt=clean[:1500], text_hash=digest, reporter_user_id=repo.p.user_id,
                   is_mock=bool(report.is_mock))
    s.add(row)
    s.flush()
    repo._audit("ad_reported", {"case": case.ref_no, "kind": kind, "verdict": report.verdict})
    return row, case, True


def _find_case(repo: Repository, kind: str, claimed_rera: str | None, name: str | None,
               district: str | None) -> EnforcementCase | None:
    stmt = select(EnforcementCase).where(EnforcementCase.kind == kind)
    if claimed_rera:
        hit = repo.s.scalar(stmt.where(EnforcementCase.claimed_rera == claimed_rera))
        if hit:
            return hit
    target = _norm(name)
    if not target:
        return None
    for case in repo.s.scalars(stmt.where(EnforcementCase.district == district) if district else stmt):
        if fuzz.ratio(target, _norm(case.title)) >= NAME_MATCH:
            return case
    return None


# --------------------------------------------------------------------- officers
def _officer(repo: Repository) -> None:
    if repo.p.role != "officer":
        raise AccessDenied("Ad enforcement cases are for GUJRERA officers.")


def _scoped(repo: Repository, stmt):
    if repo.p.district_scope:
        stmt = stmt.where(EnforcementCase.district == repo.p.district_scope)
    return stmt


def case_dict(case: EnforcementCase, reports: list[AdReport], *, full: bool = False) -> dict[str, Any]:
    phones = sorted({p.strip() for r in reports for p in (r.contact_phones or "").split(",") if p.strip()})
    sites = sorted({w.strip() for r in reports for w in (r.websites or "").split(",") if w.strip()})
    d = {
        "id": case.id, "ref_no": case.ref_no, "kind": case.kind, "law": LAW[case.kind], "title": case.title,
        "advertised_promoter": case.advertised_promoter, "district": case.district, "claimed_rera": case.claimed_rera,
        "project_id": case.project_id, "status": case.status, "outcome": case.outcome,
        "opened_on": case.opened_on.isoformat(), "updated_on": case.updated_on.isoformat(),
        "reports": len(reports), "last_reported": max((r.reported_on for r in reports), default=case.opened_on).isoformat(),
        "phones": phones, "websites": sites, "asks_payment_to_account": any(r.asks_payment_to_account for r in reports),
        "is_mock": case.is_mock,
    }
    if full:
        d["notes"] = case.notes
        d["evidence"] = [{"id": r.id, "reported_on": r.reported_on.isoformat(), "channel": r.channel, "verdict": r.verdict,
                          "claimed_rera": r.claimed_rera, "advertised_project": r.advertised_project,
                          "advertised_promoter": r.advertised_promoter, "problems": (r.problems or "").splitlines(),
                          "excerpt": r.excerpt} for r in sorted(reports, key=lambda r: r.reported_on, reverse=True)]
    return d


def list_cases(repo: Repository, *, status: str | None = None, kind: str | None = None,
               district: str | None = None) -> dict[str, Any]:
    _officer(repo)
    stmt = _scoped(repo, select(EnforcementCase))
    if district and not repo.p.district_scope:
        stmt = stmt.where(EnforcementCase.district == district)
    cases = repo.s.scalars(stmt).all()
    reports: dict[int, list[AdReport]] = {}
    if cases:
        for r in repo.s.scalars(select(AdReport).where(AdReport.case_id.in_([c.id for c in cases]))):
            reports.setdefault(r.case_id, []).append(r)
    rows = [case_dict(c, reports.get(c.id, [])) for c in cases]
    counts = {
        "open": sum(r["status"] != "closed" for r in rows),
        "new": sum(r["status"] == "new" for r in rows),
        "by_kind": {k: sum(r["kind"] == k and r["status"] != "closed" for r in rows) for k in (UNREGISTERED, LAPSED, MISLEADING)},
        "reports": sum(r["reports"] for r in rows),
    }
    if status:
        rows = [r for r in rows if (r["status"] != "closed" if status == "open" else r["status"] == status)]
    if kind:
        rows = [r for r in rows if r["kind"] == kind]
    rows.sort(key=lambda r: (r["status"] == "closed", -r["reports"], -date.fromisoformat(r["last_reported"]).toordinal()))
    repo._audit("enforcement_list", {"status": status, "kind": kind, "n": len(rows)})
    return {"counts": counts, "items": rows, "district_scope": repo.p.district_scope}


def get_case(repo: Repository, case_id: int) -> dict[str, Any] | None:
    _officer(repo)
    case = repo.s.scalar(_scoped(repo, select(EnforcementCase).where(EnforcementCase.id == case_id)))
    if case is None:
        return None
    reports = list(repo.s.scalars(select(AdReport).where(AdReport.case_id == case.id)))
    repo._audit("enforcement_case_viewed", {"case": case.ref_no})
    return case_dict(case, reports, full=True)


def update_case(repo: Repository, case_id: int, *, status: str | None = None, outcome: str | None = None,
                note: str | None = None, today: date | None = None) -> dict[str, Any] | None:
    _officer(repo)
    case = repo.s.scalar(_scoped(repo, select(EnforcementCase).where(EnforcementCase.id == case_id)))
    if case is None:
        return None
    if status is not None and status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    if outcome is not None and outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {', '.join(OUTCOMES)}")
    if status == "closed" and not (outcome or case.outcome):
        raise ValueError("Choose an outcome to close the case.")
    today = today or date.today()
    changes = []
    if status and status != case.status:
        changes.append(f"status {case.status} -> {status}")
        case.status = status
    if outcome and outcome != case.outcome:
        changes.append(f"outcome {outcome}")
        case.outcome = outcome
    if note and note.strip():
        changes.append(f"note: {note.strip()[:1000]}")
    if changes:
        case.notes = ((case.notes or "") + f"\n{today.isoformat()} (officer {repo.p.user_id}): " + "; ".join(changes)).strip()
        case.updated_on = today
    repo._audit("enforcement_case_updated", {"case": case.ref_no, "changes": changes})
    reports = list(repo.s.scalars(select(AdReport).where(AdReport.case_id == case.id)))
    return case_dict(case, reports, full=True)


# ------------------------------------------------------------------ starting set
def seed_reports(session, *, as_of: date | None = None, seed: int = 2016) -> dict[str, int]:
    """A starting set of reported ads, built from the trust-check evaluation's problem ads: a few
    projects reported several times (different phone numbers and wording), others once, over the last
    four months, with some cases already being worked on. Marked is_mock like the rest of the seed."""
    import random
    from datetime import timedelta

    from gujrera.db.repository import Principal
    from gujrera.trust.checks import check_text
    from gujrera.trust.samples import build_cases

    rng = random.Random(seed)
    as_of = as_of or date.today()
    repo = Repository(session, Principal.anonymous(), audit_sink=lambda _row: None)
    plan = {"not_found": 6, "no_number": 5, "lapsed_or_revoked": 3, "promoter_mismatch": 4, "possession_late": 3,
            "booking_over_limit": 2}
    extras = ["Limited units left! Call {p}", "Site visit this Sunday. WhatsApp {p}", "Festive offer. Contact {p}",
              "Book today, price rises next week. {p}", "Visit www.{w}.in for floor plans"]
    filed = 0
    by_kind: dict[str, int] = {}
    for case in build_cases(session, as_of=as_of):
        if plan.get(case.kind, 0) <= 0:
            continue
        plan[case.kind] -= 1
        repeats = rng.choice([1, 1, 2, 3, 5]) if case.kind in ("not_found", "no_number") else rng.choice([1, 1, 2])
        word = re.sub(r"[^a-z]", "", case.text.splitlines()[0].lower())[:14] or "homes"
        for i in range(repeats):
            phone = f"9{rng.randint(100000000, 999999999)}"
            text = case.text if i == 0 else case.text + "\n" + rng.choice(extras).format(p=phone, w=word)
            when = as_of - timedelta(days=rng.randint(1, 120))
            report = check_text(text, repo, as_of=as_of)
            if kind_of(report) is None:
                continue
            report.is_mock = True
            _, c, new = file_report(repo, text, report, channel=rng.choice(["text", "upload", "chat"]), today=when)
            if new:
                filed += 1
                c.opened_on = min(c.opened_on, when)
                c.updated_on = max(c.updated_on, when)
                by_kind[c.kind] = by_kind.get(c.kind, 0) + 1
    cases = session.scalars(select(EnforcementCase).order_by(EnforcementCase.id)).all()
    for c, (status, outcome, note) in zip(cases[1::3], [
            ("reviewing", None, "Asked the planning authority whether a layout is approved."),
            ("notice_issued", None, "Show-cause notice issued under Section 3; reply due in 15 days."),
            ("closed", "registered", "Promoter applied for registration; ads withdrawn."),
            ("reviewing", None, "Site inspection scheduled."),
            ("closed", "false_alarm", "Old brochure of a registered project with an outdated number.")]):
        c.status, c.outcome = status, outcome
        c.notes = f"{c.updated_on.isoformat()}: {note}"
    session.commit()
    return {"ad_reports": filed, "enforcement_cases": len(cases)}


# ------------------------------------------------------------------------ chat
ENFORCEMENT_WORDS = ("unregistered", "without registration", "enforcement", "reported ad", "ads reported",
                     "fake ad", "illegal ad", "નોંધણી વગર", "અનરજિસ્ટર્ડ", "ખોટી જાહેરાત", "બનાવટી જાહેરાત",
                     "बिना पंजीकरण", "अपंजीकृत", "नकली विज्ञापन", "फर्जी विज्ञापन")
_CHAT = {
    "overview": {
        "en": "{open} open enforcement cases{where} from {reports} citizen reports: {unreg} unregistered, {lapsed} lapsed registration, {mis} misleading ads; {new} not yet reviewed.",
        "gu": "{where}{reports} નાગરિક રિપોર્ટ પરથી {open} ખુલ્લા કેસ: {unreg} નોંધણી વગર, {lapsed} નોંધણીની મુદત પૂરી, {mis} ગેરમાર્ગે દોરતી જાહેરાત; {new} ની હજી સમીક્ષા બાકી.",
        "hi": "{where}{reports} नागरिक रिपोर्टों से {open} खुले मामले: {unreg} बिना पंजीकरण, {lapsed} पंजीकरण समाप्त, {mis} भ्रामक विज्ञापन; {new} की समीक्षा बाकी।",
    },
    "top": {"en": "Most reported: {items}.", "gu": "સૌથી વધુ રિપોર્ટ: {items}.", "hi": "सबसे अधिक रिपोर्ट: {items}।"},
    "citizen": {
        "en": "To check a project ad, paste it or upload a photo in \"Check an ad\". If it fails, you can report it to GUJRERA from there; the list of reported projects is for GUJRERA officers.",
        "gu": "જાહેરાત તપાસવા \"જાહેરાત તપાસો\" માં લખાણ મૂકો કે ફોટો અપલોડ કરો. ચકાસણીમાં નિષ્ફળ જાય તો ત્યાંથી GUJRERA ને રિપોર્ટ કરી શકો છો; રિપોર્ટ થયેલા પ્રોજેક્ટની યાદી GUJRERA અધિકારીઓ માટે છે.",
        "hi": "विज्ञापन जाँचने के लिए \"विज्ञापन जाँचें\" में टेक्स्ट डालें या फोटो अपलोड करें। जाँच में असफल हो तो वहीं से GUJRERA को रिपोर्ट कर सकते हैं; रिपोर्ट किए गए प्रोजेक्ट की सूची GUJRERA अधिकारियों के लिए है।",
    },
    "none": {"en": "No ad reports yet{where}.", "gu": "{where}હજી કોઈ જાહેરાત રિપોર્ટ નથી.", "hi": "{where}अभी कोई विज्ञापन रिपोर्ट नहीं।"},
}


def wants_enforcement(text_lc: str) -> bool:
    return any(w in text_lc for w in ENFORCEMENT_WORDS)


def chat_reply(repo: Repository, lang: str, *, district: str | None = None):
    from gujrera.profile.summarise import Sentence

    data = list_cases(repo, status="open", district=district)
    shown = repo.p.district_scope or district
    where = {"en": f" in {shown}" if shown else "", "gu": f"{shown} માં " if shown else "",
             "hi": f"{shown} में " if shown else ""}[lang]

    def c(key: str, **v: Any) -> str:
        return _CHAT[key].get(lang, _CHAT[key]["en"]).format(**v)

    items = data["items"]
    if not items:
        return [Sentence(c("none", where=where), [], "enf_none")], None
    k = data["counts"]["by_kind"]
    reports = sum(i["reports"] for i in items)
    out = [Sentence(c("overview", open=len(items), where=where, reports=reports, unreg=k[UNREGISTERED],
                      lapsed=k[LAPSED], mis=k[MISLEADING], new=sum(i["status"] == "new" for i in items)),
                    [], "enf_overview")]
    top = items[:3]
    out.append(Sentence(c("top", items="; ".join(f"{i['title']}, {i['district'] or '?'} ({i['reports']})" for i in top)),
                        [{"type": "enforcement_case", "id": i["ref_no"], "is_mock": i["is_mock"]} for i in top], "enf_top"))
    return out, {"type": "enforcement", "items": items[:5], "counts": data["counts"]}


def citizen_reply(lang: str):
    from gujrera.profile.summarise import Sentence

    return [Sentence(_CHAT["citizen"].get(lang, _CHAT["citizen"]["en"]), [], "enf_citizen")]
