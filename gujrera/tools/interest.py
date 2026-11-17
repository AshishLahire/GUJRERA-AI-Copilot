"""Delay interest and refund calculator.

Law (texts in data/gujrera/legal, also searchable in the chat):
- RERA Act 2016, Section 18(1): if the promoter cannot give possession by the agreed date, a buyer who
  stays gets interest for every month of delay until possession (proviso); a buyer who withdraws gets
  the amount paid back with interest, plus compensation (clause (b)).
- Gujarat RERA General Rules 2017, Rule 16: the rate is the one agreed in the agreement for sale; if none
  is agreed, SBI's Marginal Cost of Lending Rate (MCLR) plus two per cent. Interest runs from the date
  the promoter received each amount until it is refunded (sub-rule 3).
- Rule 17: a refund with interest is payable within 45 days of becoming due.

The calculation is simple interest by days (amount x rate x days / 365). It is an estimate to help a
buyer know what to ask for; the Authority decides the amount. Compensation (Sections 71-72) is decided
by the adjudicating officer and is not calculated here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from factcheck.lang.normalize import normalize_digits
from gujrera.config import get_gujrera_settings
from gujrera.i18n import fmt_date
from gujrera.profile.summarise import Sentence

STAY, WITHDRAW = "stay", "withdraw"
REFUND_DAYS = 45  # Rule 17
SECTION_18 = {"type": "legal_act", "id": "RERA Act, 2016, Section 18", "is_mock": False}
RULE_16 = {"type": "legal_rules", "id": "Gujarat RERA General Rules, 2017, Rule 16", "is_mock": False}
RULE_17 = {"type": "legal_rules", "id": "Gujarat RERA General Rules, 2017, Rule 17", "is_mock": False}


@dataclass
class Payment:
    amount: float
    paid_on: date | None = None  # needed for a refund; for delay interest only payments after the promised date matter


@dataclass
class Row:
    amount: float
    start: date
    end: date
    days: int
    interest: float


@dataclass
class Calculation:
    mode: str
    rate_pct: float
    rate_source: str  # "agreement" | "sbi_mclr"
    promised: date
    until: date
    rows: list[Row] = field(default_factory=list)
    principal: float = 0.0
    interest: float = 0.0
    delay_days: int = 0
    refund_due_by: date | None = None

    @property
    def total(self) -> float:
        return self.principal + self.interest if self.mode == WITHDRAW else self.interest

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode, "rate_pct": self.rate_pct, "rate_source": self.rate_source,
            "promised": self.promised.isoformat(), "until": self.until.isoformat(),
            "delay_days": self.delay_days, "principal": round(self.principal), "interest": round(self.interest),
            "total": round(self.total),
            "refund_due_by": self.refund_due_by.isoformat() if self.refund_due_by else None,
            "rows": [{"amount": round(r.amount), "from": r.start.isoformat(), "to": r.end.isoformat(),
                      "days": r.days, "interest": round(r.interest)} for r in self.rows],
        }


def default_rate() -> dict[str, Any]:
    """Rule 16(2) rate: SBI MCLR + 2%. The MCLR and its date are settings, so they can be updated."""
    cfg = get_gujrera_settings()
    return {"mclr": cfg.GUJRERA_SBI_MCLR, "mclr_as_of": cfg.GUJRERA_SBI_MCLR_AS_OF,
            "rate": round(cfg.GUJRERA_SBI_MCLR + 2, 2)}


def calculate(payments: list[Payment], promised: date, *, mode: str = STAY, until: date | None = None,
              rate_pct: float | None = None) -> Calculation:
    if mode not in (STAY, WITHDRAW):
        raise ValueError("mode must be 'stay' or 'withdraw'")
    payments = [p for p in payments if p.amount and p.amount > 0]
    if not payments:
        raise ValueError("Enter at least one amount paid.")
    if mode == WITHDRAW and any(p.paid_on is None for p in payments):
        raise ValueError("For a refund, enter the date of each payment: interest runs from that date (Rule 16(3)).")
    until = until or date.today()
    source = "agreement" if rate_pct is not None else "sbi_mclr"
    rate = rate_pct if rate_pct is not None else default_rate()["rate"]
    if not 0 < rate <= 30:
        raise ValueError("The interest rate should be between 0 and 30% a year.")

    calc = Calculation(mode, rate, source, promised, until, delay_days=max(0, (until - promised).days))
    for p in payments:
        if mode == STAY:  # interest for the delay: from the promised date (or a later payment) to possession
            start = max(promised, p.paid_on or promised)
        else:  # refund: from the day the promoter received the money (Rule 16(3))
            start = p.paid_on  # type: ignore[assignment]
        days = max(0, (until - start).days)
        interest = p.amount * rate / 100 * days / 365
        calc.rows.append(Row(p.amount, start, until, days, interest))
        calc.principal += p.amount
        calc.interest += interest
    if mode == WITHDRAW:
        calc.refund_due_by = until + timedelta(days=REFUND_DAYS)
    return calc


# ---------------------------------------------------------------- amounts in text
_UNITS = {
    "crore": 1e7, "crores": 1e7, "cr": 1e7, "કરોડ": 1e7, "करोड़": 1e7, "करोड": 1e7,
    "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "l": 1e5, "લાખ": 1e5, "लाख": 1e5,
    "thousand": 1e3, "હજાર": 1e3, "हज़ार": 1e3, "हजार": 1e3,
}
_AMOUNT_RE = re.compile(
    r"(?:₹|rs\.?|inr|રૂ\.?|रु\.?)?\s*(\d[\d,]*(?:\.\d+)?)\s*(crores?|cr|lakhs?|lacs?|l\b|thousand|કરોડ|લાખ|હજાર|करोड़|करोड|लाख|हज़ार|हजार)?",
    re.IGNORECASE,
)


def parse_amount(text: str) -> float | None:
    """The largest money amount in a message: "40 lakh", "₹40,00,000", "1.2 કરોડ", "35 लाख"."""
    best = None
    for m in _AMOUNT_RE.finditer(normalize_digits(text or "")):
        number, unit = m.group(1).replace(",", ""), (m.group(2) or "").lower()
        try:
            value = float(number)
        except ValueError:
            continue
        has_currency = bool(re.match(r"\s*(₹|rs|inr|રૂ|रु)", m.group(0), re.IGNORECASE))
        if unit:
            value *= _UNITS.get(unit, 1)
        elif not has_currency and value < 10000:
            continue  # a year, a day count or a flat number, not money
        if 1900 <= value <= 2100 and not unit and not has_currency:
            continue
        best = value if best is None or value > best else best
    return best


# -------------------------------------------------------------------- answer text
def fmt_inr(amount: float) -> str:
    n = int(round(amount))
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        s = ",".join([head, *groups, tail]) if head else ",".join([*groups, tail])
    return ("-" if n < 0 else "") + s


T = {
    "promised": {
        "en": "As per the RERA registration of {project}, the promised completion date was {date}.",
        "gu": "{project} ની RERA નોંધણી મુજબ પૂર્ણતાની વચન આપેલી તારીખ {date} હતી.",
        "hi": "{project} के RERA पंजीकरण के अनुसार पूरा होने की वादा की गई तारीख {date} थी।",
    },
    "late": {
        "en": "As of {until}, possession is {days} days late.",
        "gu": "{until} સુધીમાં પઝેશન {days} દિવસ મોડું છે.",
        "hi": "{until} तक पज़ेशन {days} दिन देर से है।",
    },
    "not_late": {
        "en": "As of {until}, the promised date has not passed, so no delay interest is due yet.",
        "gu": "{until} સુધીમાં વચન આપેલી તારીખ વીતી નથી, તેથી હજી વિલંબનું વ્યાજ બનતું નથી.",
        "hi": "{until} तक वादा की गई तारीख नहीं निकली है, इसलिए अभी देरी का ब्याज नहीं बनता।",
    },
    "stay": {
        "en": "If you stay in the project, interest for the delay on ₹{principal} paid comes to about ₹{interest} so far (Section 18(1)).",
        "gu": "જો તમે પ્રોજેક્ટમાં ચાલુ રહો, તો ચૂકવેલા ₹{principal} પર અત્યાર સુધીના વિલંબનું વ્યાજ આશરે ₹{interest} થાય છે (કલમ 18(1)).",
        "hi": "अगर आप प्रोजेक्ट में बने रहते हैं, तो चुकाए गए ₹{principal} पर अब तक की देरी का ब्याज लगभग ₹{interest} बनता है (धारा 18(1))।",
    },
    "per_lakh": {
        "en": "That is about ₹{per_lakh} for every ₹1 lakh you have paid; it keeps adding up each month until possession.",
        "gu": "એટલે કે ચૂકવેલા દરેક ₹1 લાખ પર આશરે ₹{per_lakh}; પઝેશન મળે ત્યાં સુધી દર મહિને વધતું રહે છે.",
        "hi": "यानी चुकाए गए हर ₹1 लाख पर लगभग ₹{per_lakh}; पज़ेशन मिलने तक हर महीने बढ़ता रहता है।",
    },
    "withdraw": {
        "en": "If you withdraw, the promoter must refund ₹{principal} with about ₹{interest} interest, ₹{total} in all (Section 18(1)), within 45 days, i.e. by {due} (Rule 17).",
        "gu": "જો તમે પ્રોજેક્ટમાંથી નીકળી જાઓ, તો પ્રમોટરે ₹{principal} અને આશરે ₹{interest} વ્યાજ, કુલ ₹{total} પરત કરવા પડે (કલમ 18(1)), 45 દિવસમાં એટલે કે {due} સુધીમાં (નિયમ 17).",
        "hi": "अगर आप प्रोजेक्ट छोड़ते हैं, तो प्रमोटर को ₹{principal} और लगभग ₹{interest} ब्याज, कुल ₹{total} लौटाने होंगे (धारा 18(1)), 45 दिनों में यानी {due} तक (नियम 17)।",
    },
    "rate_sbi": {
        "en": "Rate used: {rate}% a year, which is SBI's MCLR of {mclr}% (from {as_of}) plus 2%, the rate Rule 16 sets when the agreement names none.",
        "gu": "વપરાયેલો દર: વર્ષે {rate}%, એટલે SBI નો MCLR {mclr}% ({as_of} થી) વત્તા 2%; કરારમાં દર ન હોય ત્યારે નિયમ 16 મુજબ આ દર લાગે.",
        "hi": "इस्तेमाल दर: सालाना {rate}%, यानी SBI का MCLR {mclr}% ({as_of} से) जोड़ 2%; अनुबंध में दर न हो तो नियम 16 के अनुसार यही दर लगती है।",
    },
    "rate_agreement": {
        "en": "Rate used: {rate}% a year, as agreed in your agreement for sale (Rule 16(1)).",
        "gu": "વપરાયેલો દર: વર્ષે {rate}%, તમારા વેચાણ કરારમાં નક્કી થયા મુજબ (નિયમ 16(1)).",
        "hi": "इस्तेमाल दर: सालाना {rate}%, आपके बिक्री अनुबंध में तय के अनुसार (नियम 16(1))।",
    },
    "need_dates": {
        "en": "For a refund, interest runs from the date of each payment (Rule 16(3)), so the amount depends on when you paid. Open the calculator and enter your payments with their dates.",
        "gu": "રિફંડમાં વ્યાજ દરેક ચુકવણીની તારીખથી ગણાય છે (નિયમ 16(3)), એટલે રકમ તમે ક્યારે ચૂકવ્યા તેના પર આધાર રાખે છે. કેલ્ક્યુલેટર ખોલો અને ચુકવણીઓ તારીખ સાથે દાખલ કરો.",
        "hi": "रिफंड में ब्याज हर भुगतान की तारीख से गिना जाता है (नियम 16(3)), इसलिए राशि इस पर निर्भर है कि आपने कब भुगतान किया। कैलकुलेटर खोलें और भुगतान तारीख के साथ डालें।",
    },
    "note": {
        "en": "This is an estimate (simple interest, using the registered date; use your agreement's possession date if it differs). The Authority decides the final amount; compensation is decided separately. Not legal advice.",
        "gu": "આ અંદાજ છે (સાદું વ્યાજ, નોંધાયેલી તારીખ પરથી; તમારા કરારની પઝેશન તારીખ જુદી હોય તો તે વાપરો). અંતિમ રકમ ઓથોરિટી નક્કી કરે છે; વળતર અલગથી નક્કી થાય છે. આ કાનૂની સલાહ નથી.",
        "hi": "यह अनुमान है (साधारण ब्याज, पंजीकृत तारीख से; आपके अनुबंध की पज़ेशन तारीख अलग हो तो वह इस्तेमाल करें)। अंतिम राशि प्राधिकरण तय करता है; मुआवज़ा अलग से तय होता है। यह कानूनी सलाह नहीं है।",
    },
}


def _t(key: str, lang: str, **values: Any) -> str:
    return T[key].get(lang, T[key]["en"]).format(**values)


def explain(calc: Calculation, project: dict[str, Any], lang: str, *, amount_known: bool = True) -> list[Sentence]:
    """Cited sentences for a calculation. ``project`` is a repository project dict."""
    rec = {"type": "project", "id": project["rera_no"], "is_mock": bool(project.get("is_mock"))}
    name = project.get("name_gu") if lang == "gu" and project.get("name_gu") else project["name"]
    name = re.sub(r"\s*\((?:Demo|ડેમો)\)\s*$", "", name)
    out = [Sentence(_t("promised", lang, project=name, date=fmt_date(calc.promised, lang)), [rec], "calc_promised")]
    until = fmt_date(calc.until, lang)
    if calc.mode == STAY:
        if calc.delay_days <= 0:
            out.append(Sentence(_t("not_late", lang, until=until), [rec, SECTION_18], "calc_not_late"))
        else:
            out.append(Sentence(_t("late", lang, until=until, days=calc.delay_days), [rec], "calc_late"))
            if amount_known:
                out.append(Sentence(_t("stay", lang, principal=fmt_inr(calc.principal), interest=fmt_inr(calc.interest)),
                                    [SECTION_18, RULE_16], "calc_stay"))
            per_lakh = 1e5 * calc.rate_pct / 100 * calc.delay_days / 365
            out.append(Sentence(_t("per_lakh", lang, per_lakh=fmt_inr(per_lakh)), [SECTION_18, RULE_16], "calc_per_lakh"))
    else:
        out.append(Sentence(_t("withdraw", lang, principal=fmt_inr(calc.principal), interest=fmt_inr(calc.interest),
                               total=fmt_inr(calc.total), due=fmt_date(calc.refund_due_by, lang)),
                            [SECTION_18, RULE_16, RULE_17], "calc_withdraw"))
    if calc.rate_source == "sbi_mclr":
        r = default_rate()
        as_of = fmt_date(date.fromisoformat(r["mclr_as_of"]), lang)
        out.append(Sentence(_t("rate_sbi", lang, rate=calc.rate_pct, mclr=r["mclr"], as_of=as_of), [RULE_16], "calc_rate"))
    else:
        out.append(Sentence(_t("rate_agreement", lang, rate=calc.rate_pct), [RULE_16], "calc_rate"))
    out.append(Sentence(_t("note", lang), [], "calc_note"))
    return out


def promised_date(project: dict[str, Any]) -> date:
    """The original completion date in the registration: the date buyers were promised."""
    d = project["proposed_completion"]
    return d if isinstance(d, date) else date.fromisoformat(str(d))


# ------------------------------------------------------------------------ chat
INTEREST_WORDS = ("interest", "refund", "money back", "વ્યાજ", "રિફંડ", "પૈસા પાછા", "ब्याज", "रिफंड", "पैसे वापस")
WITHDRAW_WORDS = ("refund", "withdraw", "cancel", "money back", "રિફંડ", "પૈસા પાછા", "રદ", "रिफंड", "पैसे वापस",
                  "रद्द", "वापस")


def wants_calculation(text_lc: str) -> bool:
    return any(w in text_lc for w in INTEREST_WORDS)


def possession_end(project: dict[str, Any]) -> date:
    """Interest for delay runs until possession: the actual completion date if there is one, else today."""
    actual = project.get("actual_completion")
    if actual:
        actual = actual if isinstance(actual, date) else date.fromisoformat(str(actual))
        return min(actual, date.today())
    return date.today()


def chat_estimate(message: str, project: dict[str, Any], lang: str) -> tuple[list[Sentence], dict[str, Any]]:
    """Sentences and a card for "how much interest will I get for the delay in X (I paid 40 lakh)?"."""
    text_lc = (message or "").lower()
    amount = parse_amount(message)
    withdraw = any(w in text_lc for w in WITHDRAW_WORDS)
    calc = calculate([Payment(amount or 1e5)], promised_date(project), until=possession_end(project))
    if withdraw:
        full = explain(calc, project, lang)
        rec = full[0]
        sentences = [rec, Sentence(_t("need_dates", lang), [RULE_16], "calc_need_dates"),
                     *[x for x in full if x.key in ("calc_rate", "calc_note")]]
    else:
        sentences = explain(calc, project, lang, amount_known=amount is not None)
    card = {"type": "interest", "project_id": project["id"], "project": project["name"], "rera_no": project["rera_no"],
            "mode": WITHDRAW if withdraw else STAY, "amount": round(amount) if amount else None,
            "promised": calc.promised.isoformat(), "delay_days": calc.delay_days, "rate_pct": calc.rate_pct,
            "interest": round(calc.interest) if amount and not withdraw else None, "is_mock": bool(project.get("is_mock"))}
    return sentences, card
