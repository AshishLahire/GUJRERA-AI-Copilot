"""Synthetic ads built from registry records, for the demo console and the evaluation.

Each case states the verdict(s) the trust check should return. Cases are built
from (mock) registry rows, so the expected answer is known exactly.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from gujrera.db.models import Project, Promoter

SAFE_VERDICTS = ("verified", "registered_with_warnings")


@dataclass
class TrustCase:
    id: str
    kind: str
    lang: str
    text: str
    expected: tuple[str, ...]
    note: str


def _core(name: str) -> str:
    return name.replace(" (Demo)", "").replace(" (ડેમો)", "")


def _en_ad(p: Project, promoter_name: str, rera_no: str | None, possession_year: int, extra: str = "") -> str:
    lines = [f"{p.name} by {promoter_name}",
             f"Spacious 2 & 3 BHK flats in {p.taluka}, {p.district}."]
    if rera_no:
        lines.append(f"GujRERA Reg. No: {rera_no}")
    lines.append(f"Possession Dec {possession_year}. Price 45 Lakh onwards.")
    if extra:
        lines.append(extra)
    lines.append("Site visit: call our sales office.")
    return "\n".join(lines)


def _gu_ad(p: Project, promoter_gu: str, rera_no: str, possession_year: int) -> str:
    return "\n".join([
        f"{p.name_gu} - {promoter_gu}",
        f"2 અને 3 BHK ફ્લેટ, {p.district}",
        f"RERA નંબર: {rera_no}",
        f"પઝેશન ડિસેમ્બર {possession_year}. કિંમત 45 લાખથી શરૂ.",
    ])


def build_cases(session: Session, *, as_of: date | None = None, per_kind: int = 10,
                seed: int = 11) -> list[TrustCase]:
    as_of = as_of or date.today()
    rng = random.Random(seed)
    projects = session.scalars(select(Project).order_by(Project.id)).all()
    promoters = {p.id: p for p in session.scalars(select(Promoter))}
    valid = [p for p in projects if p.status == "ongoing" and p.reg_valid_until >= as_of]
    dead = [p for p in projects if p.status in ("lapsed", "revoked")
            or (p.status == "ongoing" and p.reg_valid_until < as_of)]
    cases: list[TrustCase] = []

    def pick(pool: list[Project], n: int) -> list[Project]:
        return rng.sample(pool, min(n, len(pool)))

    for i, p in enumerate(pick(valid, per_kind)):
        pr = promoters[p.promoter_id]
        year = rng.randint(p.reg_date.year + 1, p.reg_valid_until.year) if p.reg_valid_until.month == 12 \
            else rng.randint(p.reg_date.year + 1, max(p.reg_date.year + 1, p.reg_valid_until.year - 1))
        cases.append(TrustCase(f"genuine-en-{i:02d}", "genuine", "en",
                               _en_ad(p, _core(pr.name), p.rera_no, year),
                               SAFE_VERDICTS, "Correct number, promoter, project and possession date"))
    for i, p in enumerate(pick(valid, per_kind)):
        pr = promoters[p.promoter_id]
        cases.append(TrustCase(f"genuine-gu-{i:02d}", "genuine", "gu",
                               _gu_ad(p, _core(pr.name_gu or pr.name), p.rera_no,
                                      max(p.reg_date.year + 1, p.reg_valid_until.year - 1)),
                               SAFE_VERDICTS, "Gujarati ad with correct details"))
    for i, p in enumerate(pick(valid, per_kind)):
        pr = promoters[p.promoter_id]
        fake = p.rera_no.rsplit("/", 2)
        fake_no = f"{fake[0]}/RAA{rng.randint(10000, 99999)}/{fake[2]}"
        cases.append(TrustCase(f"notfound-{i:02d}", "not_found", "en",
                               _en_ad(p, _core(pr.name), fake_no, p.reg_valid_until.year - 1),
                               ("not_found",), "Registration number does not exist"))
    for i, p in enumerate(pick(dead, per_kind)):
        pr = promoters[p.promoter_id]
        cases.append(TrustCase(f"lapsed-{i:02d}", "lapsed_or_revoked", "en",
                               _en_ad(p, _core(pr.name), p.rera_no, as_of.year + 1),
                               ("lapsed_or_revoked",), f"Registration status {p.status}"))
    for i, p in enumerate(pick(valid, per_kind)):
        others = [o for o in promoters.values() if o.id != p.promoter_id
                  and _core(o.name).split()[0] != _core(promoters[p.promoter_id].name).split()[0]]
        if not others:  # only one promoter on record: no mismatch example can be made
            continue
        other = rng.choice(others)
        cases.append(TrustCase(f"promoter-{i:02d}", "promoter_mismatch", "en",
                               _en_ad(p, _core(other.name), p.rera_no, p.reg_valid_until.year - 1),
                               ("mismatch",), f"Ad names {_core(other.name)} instead of the registered promoter"))
    for i, p in enumerate(pick(valid, per_kind)):
        pr = promoters[p.promoter_id]
        cases.append(TrustCase(f"possession-{i:02d}", "possession_late", "en",
                               _en_ad(p, _core(pr.name), p.rera_no, p.reg_valid_until.year + 2),
                               ("mismatch",), "Advertised possession after registered completion"))
    for i, p in enumerate(pick(valid, per_kind)):
        pr = promoters[p.promoter_id]
        cases.append(TrustCase(f"nonumber-{i:02d}", "no_number", "en",
                               _en_ad(p, _core(pr.name), None, p.reg_valid_until.year - 1,
                                      "Book now with Rs 51,000 only. Pay to A/c No 123456789012 IFSC SBIN0001234."),
                               ("no_rera_number",), "No RERA number; payment to an account"))
    for i, p in enumerate(pick(valid, per_kind)):
        pr = promoters[p.promoter_id]
        cases.append(TrustCase(f"booking-{i:02d}", "booking_over_limit", "en",
                               _en_ad(p, _core(pr.name), p.rera_no, p.reg_valid_until.year - 1,
                                      "Book with just 25% and get a free modular kitchen."),
                               ("registered_with_warnings",), "Booking above 10% must raise a warning"))
    return cases


def demo_samples(session: Session, *, as_of: date | None = None) -> list[TrustCase]:
    """One case per kind, for the console's sample picker. Only on demo data: sample ads with made-up
    claims are never built around real projects or builders (imported public records)."""
    if not session.scalar(select(Project.id).where(Project.is_mock.is_(True)).limit(1)):
        return []
    seen: dict[str, TrustCase] = {}
    for case in build_cases(session, as_of=as_of, per_kind=1, seed=5):
        key = f"{case.kind}-{case.lang}"
        seen.setdefault(key, case)
    return list(seen.values())
