"""Agreement-for-sale checker: compare a buyer's draft agreement with the model agreement for sale in
the Gujarat RERA General Rules 2017 (Annexure A) and the RERA Act 2016.

The yardsticks (read from the indexed Annexure A and Act):
- recital and 1(a): the carpet area of the apartment in sq. m. / sq. ft. (net usable floor area);
- 1(g): final carpet area confirmed after the occupancy certificate, variation capped at three per cent;
- 1(e): the total price is escalation-free, except development charges and levies of the competent authority;
- 4.1: interest on the promoter's delay and on the allottee's delayed payments at the same rate (also Rule 16);
- 4 (proviso): the promoter may terminate only on three defaults of payment, after fifteen days' written notice,
  and then refunds within thirty days;
- 6: possession on or before a stated date; extension only for (i) war, civil commotion or act of God or
  (ii) an order of the Government, an authority or a court; otherwise refund with interest at the 4.1 rate;
- 7.4: defects notified within five years of possession are rectified by the promoter at his own cost
  (Section 14(3): within thirty days);
- 1 (proviso) and Section 14(2): no change to the sanctioned plans affecting the apartment without the allottee's
  prior written consent;
- Section 13(1): no more than ten per cent of the cost before a registered agreement for sale;
- Section 4(2)(l)(D): seventy per cent of collections in the separate project account;
- Section 31: any aggrieved person may complain to the Authority, whatever the agreement says.

Checks are rules over the text (English wording; Gujarati agreements need the same rules in Gujarati, a PoC
item). Each finding quotes the sentence it is based on and cites the clause or section. It points out what
to ask the promoter to change; it is not legal advice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from gujrera.db.repository import Repository
from gujrera.trust.rera_number import find_rera_numbers

FAIL, WARN, PASS = "fail", "warn", "pass"
ANNEX = "Gujarat RERA General Rules, 2017, Annexure A (model agreement for sale), clause "


def _annex(clause: str) -> dict[str, Any]:
    return {"type": "legal_annexure", "id": ANNEX + clause, "is_mock": False}


def _act(sec: str) -> dict[str, Any]:
    return {"type": "legal_act", "id": f"RERA Act, 2016, Section {sec}", "is_mock": False}


RULE16 = {"type": "legal_rules", "id": "Gujarat RERA General Rules, 2017, Rule 16", "is_mock": False}

TITLES: dict[str, dict[str, str]] = {
    "rera_number": {"en": "Project registration number", "gu": "પ્રોજેક્ટ નોંધણી નંબર", "hi": "प्रोजेक्ट पंजीकरण संख्या"},
    "carpet_area": {"en": "Carpet area stated", "gu": "કાર્પેટ એરિયા લખેલો છે", "hi": "कारपेट एरिया लिखा है"},
    "area_variation": {"en": "Area variation within 3%", "gu": "ક્ષેત્રફળમાં ફેરફાર 3% સુધી", "hi": "क्षेत्रफल में बदलाव 3% तक"},
    "escalation": {"en": "Price free of escalation", "gu": "કિંમતમાં વધારો નહીં", "hi": "कीमत में बढ़ोतरी नहीं"},
    "interest_delay": {"en": "Interest for delay in possession", "gu": "પઝેશનમાં વિલંબનું વ્યાજ", "hi": "पज़ेशन में देरी का ब्याज"},
    "interest_equal": {"en": "Same interest rate both ways", "gu": "બંને પક્ષે સરખો વ્યાજ દર", "hi": "दोनों तरफ़ बराबर ब्याज दर"},
    "possession_date": {"en": "Firm possession date", "gu": "ચોક્કસ પઝેશન તારીખ", "hi": "पक्की पज़ेशन तारीख"},
    "delay_excuses": {"en": "Allowed reasons for delay", "gu": "વિલંબ માટે માન્ય કારણો", "hi": "देरी के मान्य कारण"},
    "refund_on_default": {"en": "Refund with interest if the promoter fails", "gu": "પ્રમોટર નિષ્ફળ જાય તો વ્યાજ સાથે રિફંડ",
                          "hi": "प्रमोटर विफल हो तो ब्याज सहित रिफंड"},
    "termination": {"en": "Termination only after 3 defaults and notice", "gu": "3 ડિફોલ્ટ અને નોટિસ પછી જ કરાર રદ",
                    "hi": "3 चूक और नोटिस के बाद ही समाप्ति"},
    "plan_changes": {"en": "No plan changes without consent", "gu": "સંમતિ વગર પ્લાનમાં ફેરફાર નહીં", "hi": "सहमति के बिना नक्शे में बदलाव नहीं"},
    "defect_liability": {"en": "5-year defect liability", "gu": "5 વર્ષની ખામી જવાબદારી", "hi": "5 साल की खामी ज़िम्मेदारी"},
    "advance_limit": {"en": "At most 10% before the registered agreement", "gu": "નોંધાયેલા કરાર પહેલાં વધુમાં વધુ 10%",
                      "hi": "पंजीकृत अनुबंध से पहले अधिकतम 10%"},
    "project_account": {"en": "Payments into the project account", "gu": "પ્રોજેક્ટ ખાતામાં ચુકવણી", "hi": "प्रोजेक्ट खाते में भुगतान"},
    "complaint_right": {"en": "Right to complain to GUJRERA", "gu": "GUJRERA માં ફરિયાદનો અધિકાર", "hi": "GUJRERA में शिकायत का अधिकार"},
}


@dataclass
class Finding:
    id: str
    status: str
    detail: str
    excerpt: str | None = None
    ask: str | None = None
    citations: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self, lang: str) -> dict[str, Any]:
        return {"id": self.id, "status": self.status, "title": TITLES[self.id].get(lang, TITLES[self.id]["en"]),
                "title_en": TITLES[self.id]["en"], "detail": self.detail, "excerpt": self.excerpt, "ask": self.ask,
                "citations": self.citations}


def sentences(text: str) -> list[str]:
    flat = re.sub(r"[ \t]+", " ", text or "")
    # not after abbreviations common in Indian agreements ("Rs. 62,00,000", "No. 1234", "sq. ft.", "Pvt. Ltd.")
    parts = re.split(r"(?<!Rs\.)(?<!No\.)(?<!sq\.)(?<!ft\.)(?<!mt\.)(?<!Ltd\.)(?<!Pvt\.)(?<!Dr\.)(?<!Mr\.)(?<!Ms\.)(?<!Smt\.)"
                     r"(?<!Shri\.)(?<!viz\.)(?<!i\.e\.)(?<!e\.g\.)(?<=[.;:])\s+(?=[A-Z0-9(])|\n{1,}", flat)
    return [p.strip() for p in parts if len(p.strip()) > 3]


def _find(sents: list[str], *patterns: str) -> list[str]:
    rx = [re.compile(p, re.IGNORECASE) for p in patterns]
    return [s for s in sents if all(r.search(s) for r in rx)]


def _clip(s: str | None, n: int = 260) -> str | None:
    return None if s is None else (s if len(s) <= n else s[: n - 1] + "…")


def _percents(s: str) -> list[float]:
    return [float(x) for x in re.findall(r"(\d{1,2}(?:\.\d+)?)\s*(?:%|per\s*cent|percent)", s, re.IGNORECASE)]


BUYER = r"\b(allottee|purchaser|buyer|vendee|flat\s*owner)s?\b"
PROMOTER = r"\b(promoter|developer|builder|company|vendor)s?\b"
DELAY_PAY = r"(delay(ed)?\s+(in\s+)?payment|late\s+payment|overdue|default\s+in\s+payment|unpaid|outstanding\s+(amount|instal))"
DELAY_POSS = r"(delay\w*|fail\w*|unable)\s.{0,60}(possession|handing\s+over|deliver\w*)|possession.{0,60}(delay\w*|late)"
BAD_EXCUSES = (r"shortage of (labour|labor|material|cement|steel|water|power|electricity)", r"non[- ]availability",
               r"market conditions?", r"financial (reasons|difficult|constraint)", r"economic", r"slow ?down",
               r"any (other )?(reason|cause) (whatsoever|beyond)", r"strike", r"funding", r"bank (loan|finance)")


def check(text: str, repo: Repository | None = None) -> dict[str, Any]:
    sents = sentences(text)
    low = (text or "").lower()
    out: list[Finding] = []

    # 0. registration number of the project, checked in the registry
    nums = [n for n in find_rera_numbers(text or "") if n.kind == "project"]
    project = None
    if not nums:
        out.append(Finding("rera_number", FAIL, "The agreement does not state the project's GUJRERA registration number.",
                           ask="Ask for the registration number to be written into the agreement.", citations=[_act("13"), _act("11")]))
    elif repo is not None:
        project = repo.get_project(nums[0].normalised)
        if project is None:
            out.append(Finding("rera_number", FAIL, f"{nums[0].normalised} is not in the GUJRERA registry.",
                               excerpt=nums[0].normalised, ask="Do not sign until the registration is confirmed on the GUJRERA portal.",
                               citations=[_act("3")]))
        else:
            ok = project["status"] in ("ongoing", "completed")
            out.append(Finding("rera_number", PASS if ok else FAIL,
                               f"Registered: {project['name']} by {project['promoter_name'].replace(' (Demo)', '')}, status {project['status']}.",
                               excerpt=nums[0].normalised, citations=[project["source"]]))

    # 1. carpet area
    carpet = _find(sents, r"carpet\s+area", r"(sq\.?\s*(m|ft|mt|metre|meter|feet)|square\s+(met|feet|foot))")
    if carpet:
        out.append(Finding("carpet_area", PASS, "The carpet area is stated.", excerpt=_clip(carpet[0]), citations=[_annex("1(a)")]))
    else:
        sba = _find(sents, r"(super\s*built[- ]?up|saleable|super\s+area|built[- ]?up\s+area)")
        out.append(Finding("carpet_area", FAIL, "The apartment's carpet area (net usable floor area) is not stated"
                           + (" — only super built-up / saleable area is given." if sba else "."),
                           excerpt=_clip(sba[0]) if sba else None,
                           ask="Ask for the carpet area in sq. m. or sq. ft., as the model agreement requires.",
                           citations=[_annex("1(a)")]))

    # 2. variation of area
    var = _find(sents, r"(variation|vary|increase|decrease|change)", r"area", r"\d")
    var_pcts = [p for s in var for p in _percents(s)]
    if var_pcts and max(var_pcts) > 3:
        s_ = next(s for s in var if any(p > 3 for p in _percents(s)))
        out.append(Finding("area_variation", FAIL, f"The area may vary by up to {max(var_pcts):g}%; the model agreement caps the variation at 3%.",
                           excerpt=_clip(s_), ask="Ask for the variation to be capped at 3%, with a refund (with interest) for any reduction.",
                           citations=[_annex("1(g)")]))
    elif var_pcts:
        out.append(Finding("area_variation", PASS, "Area variation is within 3%.", excerpt=_clip(var[0]), citations=[_annex("1(g)")]))

    # 3. escalation
    esc = _find(sents, r"(escalat|increase in (the )?(price|cost|consideration)|price (rise|revision|hike))")
    esc_bad = [s for s in esc if re.search(r"(material|labour|labor|steel|cement|construction cost|input cost|market)", s, re.I)
               and not re.search(r"escalation[- ]free", s, re.I)]
    if esc_bad:
        out.append(Finding("escalation", FAIL, "The price can be increased for costs like materials or labour; the model price is escalation-free "
                           "except development charges and levies of the authorities.", excerpt=_clip(esc_bad[0]),
                           ask="Ask for the price to be fixed, with only government charges passed on.", citations=[_annex("1(e)")]))
    elif re.search(r"escalation[- ]free", low):
        out.append(Finding("escalation", PASS, "The price is stated to be escalation-free.", citations=[_annex("1(e)")]))

    # 4. interest: promoter's delay vs buyer's late payment
    int_sents = _find(sents, r"interest")
    buyer_rates = [p for s in int_sents if re.search(DELAY_PAY, s, re.I) or (re.search(BUYER, s, re.I) and re.search(r"(pay|default)", s, re.I)
                   and not re.search(DELAY_POSS, s, re.I)) for p in _percents(s)]
    promoter_sents = [s for s in int_sents if re.search(DELAY_POSS, s, re.I)]
    promoter_rates = [p for s in promoter_sents for p in _percents(s)]
    if not promoter_sents:
        out.append(Finding("interest_delay", FAIL, "No interest is promised to the buyer if possession is late.",
                           ask="Ask for interest for every month of delay until possession, as the model agreement provides.",
                           citations=[_annex("4.1"), _act("18")]))
    else:
        nothing = [s for s in promoter_sents if re.search(r"(no|without|not\s+(be\s+)?(liable|entitled)\s+to\s+(pay\s+)?(any\s+)?)\s*interest", s, re.I)]
        if nothing:
            out.append(Finding("interest_delay", FAIL, "The agreement says no interest is payable to the buyer for delay.",
                               excerpt=_clip(nothing[0]), ask="Interest for delay is a right under Section 18; ask for this to be removed.",
                               citations=[_annex("4.1"), _act("18")]))
        else:
            out.append(Finding("interest_delay", PASS, "Interest for delay in possession is provided.", excerpt=_clip(promoter_sents[0]),
                               citations=[_annex("4.1"), _act("18")]))
    if buyer_rates and promoter_rates and max(buyer_rates) != max(promoter_rates):
        out.append(Finding("interest_equal", FAIL, f"The buyer pays {max(buyer_rates):g}% on late payments but the promoter pays "
                           f"{max(promoter_rates):g}% for delay. The rates must be the same.",
                           ask="Ask for one interest rate both ways (SBI MCLR + 2% if none is agreed).",
                           citations=[_annex("4.1"), RULE16]))
    elif buyer_rates and promoter_rates:
        out.append(Finding("interest_equal", PASS, f"The same rate ({max(buyer_rates):g}%) applies both ways.", citations=[_annex("4.1"), RULE16]))

    # 5. possession date
    poss = _find(sents, r"possession")
    dated = [s for s in poss if re.search(r"(on or before|by|not later than|latest by)\s.{0,25}(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\b(19|20)\d{2}\b|"
                                         r"(january|february|march|april|may|june|july|august|september|october|november|december))", s, re.I)]
    vague = [s for s in poss if re.search(r"(tentative|approximate|likely|expected|endeavour|endeavor|as soon as|reasonable time|subject to)", s, re.I)]
    if dated and not [s for s in dated if s in vague]:
        out.append(Finding("possession_date", PASS, "A possession date is stated.", excerpt=_clip(dated[0]), citations=[_annex("6")]))
    else:
        out.append(Finding("possession_date", FAIL if not dated else WARN,
                           "No firm possession date." if not dated else "The possession date is qualified as tentative or expected.",
                           excerpt=_clip((vague or poss or [None])[0]),
                           ask="Ask for possession 'on or before' a specific date.", citations=[_annex("6"), _act("18")]))

    # 6. excuses for delay
    bad = [s for s in sents if re.search(r"(delay|extension of time|force majeure|beyond (the )?control)", s, re.I)
           and any(re.search(b, s, re.I) for b in BAD_EXCUSES)]
    if bad:
        out.append(Finding("delay_excuses", FAIL, "Delay may be excused for reasons outside the model list, which allows only war, civil "
                           "commotion or act of God, and orders of the Government, an authority or a court.", excerpt=_clip(bad[0]),
                           ask="Ask for the excuses to be limited to those in the model agreement.", citations=[_annex("6")]))
    elif re.search(r"(force majeure|act of god)", low):
        out.append(Finding("delay_excuses", PASS, "Delay excuses stay within the model list.", citations=[_annex("6")]))

    # 7. refund if the promoter fails
    fail_ref = [s for s in sents if re.search(PROMOTER, s, re.I) and re.search(r"(fail|unable|cancel|terminat|withdraw)", s, re.I)
                and re.search(r"refund", s, re.I)]
    no_int = [s for s in fail_ref if re.search(r"without (any )?interest", s, re.I) and not re.search(DELAY_PAY, s, re.I)]
    if no_int:
        out.append(Finding("refund_on_default", FAIL, "If the promoter fails, money is to be refunded without interest; the model agreement "
                           "refunds it with interest at the clause 4.1 rate from the date it was paid.", excerpt=_clip(no_int[0]),
                           ask="Ask for refund with interest (Section 18).", citations=[_annex("6"), _act("18")]))
    elif fail_ref:
        out.append(Finding("refund_on_default", PASS, "Refund on the promoter's failure is provided.", excerpt=_clip(fail_ref[0]),
                           citations=[_annex("6"), _act("18")]))

    # 8. termination by the promoter
    term = _find(sents, PROMOTER, r"(terminat|cancel)")
    harsh = [s for s in term if re.search(r"(any (single )?default|one default|first default|without (any )?notice|sole (and absolute )?discretion|forthwith)", s, re.I)]
    forfeit = [s for s in sents if re.search(r"forfeit", s, re.I)]
    forfeit_pct = [p for s in forfeit for p in _percents(s)]
    if harsh:
        out.append(Finding("termination", FAIL, "The promoter can cancel on a single default, without notice or at its discretion; the model "
                           "agreement allows it only after three defaults and fifteen days' written notice, with a refund within thirty days.",
                           excerpt=_clip(harsh[0]), ask="Ask for the model termination clause.", citations=[_annex("4")]))
    elif forfeit_pct and max(forfeit_pct) > 10:
        s_ = next(s for s in forfeit if any(p > 10 for p in _percents(s)))
        out.append(Finding("termination", WARN, f"Up to {max(forfeit_pct):g}% can be forfeited on cancellation, more than the 10% advance the Act "
                           "allows before an agreement.", excerpt=_clip(s_), ask="Ask for forfeiture to be limited to the booking amount.",
                           citations=[_annex("4"), _act("13")]))
    elif re.search(r"three defaults|3 defaults", low):
        out.append(Finding("termination", PASS, "Termination follows the three-defaults-and-notice rule.", citations=[_annex("4")]))

    # 9. changes to plans
    changes = [s for s in sents if re.search(r"(alter|modif|change|revis|vary)", s, re.I)
               and re.search(r"(plan|layout|specification|design|elevation)", s, re.I)
               and re.search(r"(without (the )?(prior )?(written )?consent|sole (and absolute )?discretion|at (its|their) option|deemed (to have )?consent|"
                             r"shall not object|no objection)", s, re.I)]
    if changes:
        out.append(Finding("plan_changes", FAIL, "The promoter can change plans or specifications without the buyer's consent; changes that "
                           "affect the apartment need the buyer's prior written consent, and two-thirds of buyers for common areas.",
                           excerpt=_clip(changes[0]), ask="Ask for this clause to be removed.", citations=[_annex("1"), _act("14")]))

    # 10. defect liability
    defect = _find(sents, r"defect")
    short = [s for s in defect if re.search(r"(\b(one|two|three|four|1|2|3|4)\s*(year|yr)s?\b|\b\d{1,2}\s*months?\b)", s, re.I)
             and not re.search(r"\b(five|5)\s*years?\b", s, re.I)]
    if short:
        out.append(Finding("defect_liability", FAIL, "The defect liability period is shorter than five years from possession.",
                           excerpt=_clip(short[0]), ask="Ask for five years, with repairs within thirty days at the promoter's cost.",
                           citations=[_annex("7.4"), _act("14")]))
    elif [s for s in defect if re.search(r"\b(five|5)\s*years?\b", s, re.I)]:
        out.append(Finding("defect_liability", PASS, "Five-year defect liability is provided.", citations=[_annex("7.4"), _act("14")]))
    else:
        out.append(Finding("defect_liability", WARN, "No defect liability clause found.", ask="Ask for the model five-year defect clause.",
                           citations=[_annex("7.4"), _act("14")]))

    # 11. advance before agreement
    adv = [s for s in sents if re.search(r"(booking|application money|advance|on (signing|allotment)|token)", s, re.I)]
    adv_pcts = [(p, s) for s in adv for p in _percents(s)]
    over = [(p, s) for p, s in adv_pcts if p > 10 and not re.search(r"interest", s, re.I)]
    if over:
        p, s_ = max(over)
        out.append(Finding("advance_limit", FAIL, f"{p:g}% is asked at booking or allotment; no more than 10% may be taken before a registered "
                           "agreement for sale.", excerpt=_clip(s_), ask="Pay no more than 10% until the agreement is registered.",
                           citations=[_act("13")]))
    elif adv_pcts:
        out.append(Finding("advance_limit", PASS, "The booking amount is within 10%.", citations=[_act("13")]))

    # 12. project account
    acct = [s for s in sents if re.search(r"(separate|designated|escrow|RERA)\s+(bank\s+)?account", s, re.I)]
    any_acct = [s for s in sents if re.search(r"(any|such)\s+(other\s+)?(bank\s+)?account\s+(as\s+)?(directed|nominated|specified|intimated)", s, re.I)]
    if any_acct and not acct:
        out.append(Finding("project_account", WARN, "Payments may go to any account the promoter names, rather than the project's separate account.",
                           excerpt=_clip(any_acct[0]), ask="Ask for the project's separate account to be named in the agreement.",
                           citations=[_act("4")]))
    elif acct:
        out.append(Finding("project_account", PASS, "Payments go to the project's separate account.", excerpt=_clip(acct[0]), citations=[_act("4")]))

    # 13. right to complain
    bar = [s for s in sents if re.search(r"(shall not|will not|cannot|waive\w*|give\w* up|relinquish\w*)\s.{0,40}(approach|complain|file|move)\w*\s.{0,40}(authority|RERA|forum|court|commission)", s, re.I)
           or (re.search(r"arbitrat", s, re.I) and re.search(r"(exclusive|sole remedy|only remedy|final and binding)", s, re.I))]
    if bar:
        out.append(Finding("complaint_right", FAIL, "The agreement tries to stop the buyer from complaining to GUJRERA or limits the buyer to "
                           "arbitration; any aggrieved person may complain to the Authority whatever the agreement says.",
                           excerpt=_clip(bar[0]), ask="Ask for this clause to be removed.", citations=[_act("31")]))

    counts = {k: sum(f.status == k for f in out) for k in (FAIL, WARN, PASS)}
    return {"findings": out, "counts": counts, "project": project, "sentences": len(sents)}


def report(text: str, repo: Repository | None, lang: str = "en") -> dict[str, Any]:
    res = check(text, repo)
    order = {FAIL: 0, WARN: 1, PASS: 2}
    res["findings"] = [f.to_dict(lang) for f in sorted(res["findings"], key=lambda f: order[f.status])]
    p = res["project"]
    res["project"] = None if p is None else {"id": p["id"], "name": p["name"], "rera_no": p["rera_no"], "status": p["status"]}
    if repo is not None:
        repo._audit("agreement_checked", {"fail": res["counts"][FAIL], "warn": res["counts"][WARN]})
    return res


# ---------------------------------------------------------------- files
MAX_PDF_PAGES, MAX_OCR_PAGES = 60, 15


def extract_text(path) -> tuple[str, str]:
    """Text of an agreement file: every page of a PDF (OCR for scanned pages), a photo, or a text file.
    Returns (text, how it was read)."""
    from pathlib import Path

    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".txt":
        return path.read_text(encoding="utf-8", errors="replace"), "text"
    if ext == ".pdf":
        import pypdfium2 as pdfium

        doc = pdfium.PdfDocument(str(path))
        try:  # close the document so the uploaded file can be deleted (Windows keeps open files locked)
            parts, ocr_pages, n_pages = [], 0, len(doc)
            for i in range(min(n_pages, MAX_PDF_PAGES)):
                page = doc[i]
                textpage = page.get_textpage()
                layer = textpage.get_text_range().strip()
                textpage.close()
                if len(layer) >= 40:
                    parts.append(layer)
                elif ocr_pages < MAX_OCR_PAGES:
                    from gujrera.trust.ocr import _ocr_pil, tesseract_available

                    if tesseract_available():
                        parts.append(_ocr_pil(page.render(scale=300 / 72).to_pil())[0])
                        ocr_pages += 1
                page.close()
        finally:
            doc.close()
        how = "pdf-text" if not ocr_pages else f"pdf with {ocr_pages} scanned page(s) read by OCR"
        if n_pages > MAX_PDF_PAGES:
            how += f"; first {MAX_PDF_PAGES} of {n_pages} pages"
        return "\n".join(parts), how
    from gujrera.trust.ocr import ocr_file

    out = ocr_file(path)
    return out.text, "photo read by OCR"


# ------------------------------------------------------------------------ chat
CHECK_WORDS = ("check my agreement", "check the agreement", "agreement checker", "review my agreement",
               "is my agreement", "કરાર તપાસો", "કરાર ચકાસો", "अनुबंध जाँचें", "अनुबंध जांचें", "एग्रीमेंट")
_SUM = {
    "found": {"en": "Agreement check against the model agreement in the Gujarat RERA Rules: {fail} problem(s), {warn} point(s) to check, {ok} in order.",
              "gu": "ગુજરાત RERA નિયમોના મોડેલ કરાર સામે ચકાસણી: {fail} સમસ્યા, {warn} તપાસવાની બાબત, {ok} બરાબર.",
              "hi": "गुजरात RERA नियमों के मॉडल अनुबंध से जाँच: {fail} समस्याएँ, {warn} जाँचने की बातें, {ok} ठीक।"},
    "open": {"en": "Paste your draft agreement for sale here, or upload it on the Agreement checker page; it is compared clause by clause with the model agreement in the Gujarat RERA Rules.",
             "gu": "તમારો વેચાણ કરારનો મુસદ્દો અહીં પેસ્ટ કરો, અથવા 'કરાર ચકાસણી' પાને અપલોડ કરો; તેને ગુજરાત RERA નિયમોના મોડેલ કરાર સાથે કલમવાર સરખાવાય છે.",
             "hi": "अपना बिक्री अनुबंध का मसौदा यहाँ पेस्ट करें, या 'अनुबंध जाँच' पेज पर अपलोड करें; इसे गुजरात RERA नियमों के मॉडल अनुबंध से धारा-दर-धारा मिलाया जाता है।"},
}


def looks_like_agreement(text: str) -> bool:
    low = (text or "").lower()
    return len(low) > 400 and ("agreement for sale" in low or ("agreement" in low and
            bool(re.search(r"\b(allottee|purchaser|vendee)\b", low)) and bool(re.search(r"\b(promoter|developer|builder)\b", low))))


def wants_check(text_lc: str) -> bool:
    return any(w in text_lc for w in CHECK_WORDS)


def chat_reply(text: str, repo: Repository, lang: str, *, run: bool):
    from gujrera.profile.summarise import Sentence

    if not run:
        return [Sentence(_SUM["open"].get(lang, _SUM["open"]["en"]), [], "agreement_open")], {"type": "agreement", "counts": None}
    res = report(text, repo, lang)
    c = res["counts"]
    out = [Sentence(_SUM["found"].get(lang, _SUM["found"]["en"]).format(fail=c[FAIL], warn=c[WARN], ok=c[PASS]),
                    [{"type": "legal_annexure", "id": ANNEX.removesuffix(", clause "), "is_mock": False}], "agreement_found")]
    for f in [f for f in res["findings"] if f["status"] == FAIL][:4]:
        out.append(Sentence(f"{f['title']}: {f['detail']}", f["citations"], "agreement_issue"))
    return out, {"type": "agreement", "counts": c, "findings": res["findings"][:8]}
