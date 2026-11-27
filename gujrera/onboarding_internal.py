"""The department's internal records, loaded through the data onboarding console.

The authority assistant answers the officials' questions from five kinds of internal record: complaints,
orders (with penalty amounts), notices to promoters, applications under scrutiny, and recorded defaults.
Each kind is loaded the same way as projects (upload, match columns, check on a copy, load) and is matched
to its project by RERA registration number, so the promoter and district come from the registry.

The department's own words are mapped to the values the reports use ("Show Cause Notice" -> show_cause,
"QPR not submitted" -> qpr_not_filed); a value that cannot be mapped rejects the row with the reason, so
the officer can fix the file and load it again. Loaded rows are real data (is_mock = False).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from gujrera.db.models import (
    AuthorityNotice,
    Complaint,
    ComplaintEvent,
    ComplianceEvent,
    Order,
    OrderPenalty,
    Project,
    ProjectScrutiny,
)
from gujrera.ingest.public_import import PROJECT_COLUMNS, _s, parse_date
from gujrera.trust.rera_number import parse_rera_number

RERA = PROJECT_COLUMNS["rera_no"]

SPECS: dict[str, dict[str, tuple[str, ...]]] = {
    "complaint": {
        "ref_no": ("complaint no", "complaint number", "complaint ref", "ref no", "reference no", "complaint id", "case no"),
        "rera_no": RERA,
        "filed_on": ("filed on", "date of filing", "filing date", "complaint date", "received on", "date"),
        "category": ("category", "complaint type", "type of complaint", "nature of complaint", "subject"),
        "status": ("status", "complaint status", "current status", "stage"),
        "summary": ("summary", "description", "details", "complaint details", "grievance"),
        "relief": ("relief", "relief sought", "prayer"),
        "form": ("form", "form type"),
        "closed_on": ("closed on", "disposed on", "date of disposal", "order date"),
        "outcome": ("outcome", "result", "decision"),
        "hearing_on": ("hearing date", "next hearing", "next hearing date", "hearing on"),
    },
    "order": {
        "order_no": ("order no", "order number", "order ref", "order id"),
        "order_type": ("order type", "type", "type of order", "nature of order"),
        "issued_on": ("issued on", "order date", "date of order", "date"),
        "rera_no": RERA,
        "complaint_ref": ("complaint no", "complaint number", "complaint ref", "case no"),
        "summary": ("summary", "description", "details", "direction", "subject"),
        "penalty_amount": ("penalty", "penalty amount", "amount", "penalty (rs)", "penalty rs", "fine"),
        "penalty_paid": ("paid", "penalty paid", "payment status", "recovered"),
    },
    "notice": {
        "ref_no": ("notice no", "notice number", "notice ref", "ref no", "reference no", "notice id"),
        "rera_no": RERA,
        "notice_type": ("notice type", "type", "type of notice", "subject"),
        "issued_on": ("issued on", "notice date", "date of notice", "date"),
        "status": ("status", "notice status", "reply status"),
    },
    "scrutiny": {
        "rera_no": RERA,
        "subject": ("application type", "subject", "type", "application for", "application"),
        "stage": ("stage", "status", "current stage", "scrutiny status"),
        "opened_on": ("opened on", "application date", "date of application", "received on", "submitted on", "date"),
        "closed_on": ("closed on", "decided on", "approved on", "date of decision"),
        "officer_note": ("note", "remarks", "officer note", "query"),
    },
    "default": {
        "rera_no": RERA,
        "event_type": ("default type", "type", "non compliance", "non-compliance", "default", "subject"),
        "period": ("period", "quarter", "financial year", "fy"),
        "event_date": ("date", "default date", "due date", "date of default", "recorded on"),
        "resolved_on": ("resolved on", "complied on", "filed on", "paid on", "date of compliance"),
    },
}
REQUIRED: dict[str, tuple[str, ...]] = {
    "complaint": ("ref_no", "rera_no", "filed_on"),
    "order": ("order_no", "issued_on"),
    "notice": ("ref_no", "rera_no", "issued_on"),
    "scrutiny": ("rera_no", "opened_on"),
    "default": ("rera_no", "event_date"),
}
KIND_LABELS = {
    "complaint": "Complaints (department records)",
    "order": "Orders, with penalty amounts",
    "notice": "Notices to promoters",
    "scrutiny": "Applications under scrutiny",
    "default": "Recorded defaults (missed filings or fees)",
}
KIND_I18N = {
    "complaint": ("ફરિયાદો (વિભાગના રેકોર્ડ)", "शिकायतें (विभाग के रिकॉर्ड)"),
    "order": ("આદેશો, દંડની રકમ સાથે", "आदेश, दंड की राशि के साथ"),
    "notice": ("પ્રમોટરોને નોટિસ", "प्रमोटरों को नोटिस"),
    "scrutiny": ("ચકાસણી હેઠળની અરજીઓ", "जाँच के अधीन आवेदन"),
    "default": ("નોંધાયેલા ડિફોલ્ટ (ચૂકી ગયેલી ફાઇલિંગ કે ફી)", "दर्ज डिफ़ॉल्ट (छूटी फ़ाइलिंग या शुल्क)"),
}
LABELS = {
    "ref_no": "Reference number", "filed_on": "Filed on", "category": "Category", "summary": "Summary",
    "relief": "Relief sought", "form": "Form (A or B)", "closed_on": "Closed on", "outcome": "Outcome",
    "hearing_on": "Hearing date", "order_no": "Order number", "order_type": "Order type", "issued_on": "Issued on",
    "complaint_ref": "Complaint number", "penalty_amount": "Penalty amount (Rs)", "penalty_paid": "Penalty paid",
    "notice_type": "Notice type", "subject": "Application type", "stage": "Stage", "opened_on": "Opened on",
    "officer_note": "Note", "event_type": "Default type", "period": "Period", "event_date": "Date of default",
    "resolved_on": "Resolved on",
}
LABEL_I18N = {
    "ref_no": ("સંદર્ભ નંબર", "संदर्भ संख्या"), "filed_on": ("નોંધણી તારીખ", "दर्ज करने की तिथि"),
    "category": ("શ્રેણી", "श्रेणी"), "summary": ("સાર", "सार"), "relief": ("માંગેલી રાહત", "माँगी गई राहत"),
    "form": ("ફોર્મ (A કે B)", "फ़ॉर्म (A या B)"), "closed_on": ("બંધ થયાની તારીખ", "बंद होने की तिथि"),
    "outcome": ("પરિણામ", "परिणाम"), "hearing_on": ("સુનાવણી તારીખ", "सुनवाई की तिथि"),
    "order_no": ("આદેશ નંબર", "आदेश संख्या"), "order_type": ("આદેશનો પ્રકાર", "आदेश का प्रकार"),
    "issued_on": ("જારી તારીખ", "जारी करने की तिथि"), "complaint_ref": ("ફરિયાદ નંબર", "शिकायत संख्या"),
    "penalty_amount": ("દંડની રકમ (રૂ.)", "दंड की राशि (रु.)"), "penalty_paid": ("દંડ ભર્યો", "दंड चुकाया"),
    "notice_type": ("નોટિસનો પ્રકાર", "नोटिस का प्रकार"), "subject": ("અરજીનો પ્રકાર", "आवेदन का प्रकार"),
    "stage": ("તબક્કો", "चरण"), "opened_on": ("શરૂ થયાની તારીખ", "शुरू होने की तिथि"),
    "officer_note": ("નોંધ", "टिप्पणी"), "event_type": ("ડિફોલ્ટનો પ્રકાર", "डिफ़ॉल्ट का प्रकार"),
    "period": ("સમયગાળો", "अवधि"), "event_date": ("ડિફોલ્ટની તારીખ", "डिफ़ॉल्ट की तिथि"),
    "resolved_on": ("ઉકેલ્યાની તારીખ", "समाधान की तिथि"),
}


# ------------------------------------------------------------------ the department's words -> report values
def _pick(value: Any, choices: list[tuple[tuple[str, ...], str]], default: str | None, what: str) -> str:
    text = _s(value).lower().replace("-", " ").replace("_", " ")
    if not text:
        if default is None:
            raise ValueError(f"{what} is empty")
        return default
    for words, out in choices:
        if any(w in text for w in words):
            return out
    if default is None:
        raise ValueError(f"unknown {what} {_s(value)!r}")
    return default


COMPLAINT_STATUS = [(("dispos", "decided", "allowed", "dismiss", "closed", "final order"), "disposed"),
                    (("withdraw",), "withdrawn"), (("reserved",), "order_reserved"),
                    (("hearing", "listed", "adjourn"), "hearing_scheduled"),
                    (("scrutin", "admitted", "under process", "pending"), "under_scrutiny"),
                    (("filed", "registered", "new", "received"), "filed")]
OUTCOMES = [(("partly", "partially"), "partly_allowed"), (("allow",), "allowed"), (("dismiss", "reject"), "dismissed"),
            (("settle", "compromise", "withdraw"), "settled")]
RELIEFS = [(("refund",), "refund_with_interest"), (("interest",), "possession_with_interest"),
           (("compensat",), "compensation"), (("rectif", "repair", "defect"), "rectification")]
ORDER_TYPES = [(("penal", "fine"), "penalty_order"), (("revoc", "cancel"), "revocation_order"),
               (("show cause",), "show_cause"), (("extens",), "extension_order"),
               (("complaint", "final", "judg", "disposal"), "complaint_order")]
NOTICE_TYPES = [(("show cause",), "show_cause"), (("hearing",), "hearing"), (("penal", "demand"), "penalty_demand"),
                (("non compliance", "noncompliance", "qpr", "compliance", "default"), "non_compliance")]
NOTICE_STATUS = [(("close",), "closed"), (("repl", "respond", "answer"), "replied"), (("issu", "sent", "open", "pending"), "issued")]
SUBJECTS = [(("exten",), "extension"), (("alter", "modif", "change"), "alteration"), (("regist", "new"), "registration")]
STAGES = [(("query", "clarif", "deficien"), "query_raised"), (("clear", "approv", "grant"), "cleared"),
          (("reject", "refus"), "rejected"), (("scrutin", "pending", "process", "review", "submitted"), "under_scrutiny")]
EVENT_TYPES = [(("annual", "form 5", "form5"), "form5_annual_report_not_filed"),
               (("quarter end", "return"), "quarter_end_return_not_filed"),
               (("qpr", "quarterly", "progress"), "qpr_not_filed"), (("fee", "payment", "dues"), "fee_not_paid")]


def _project(s: Session, raw: Any, required: bool = True) -> Project | None:
    text = _s(raw)
    if not text:
        if required:
            raise ValueError("RERA registration number is empty")
        return None
    parsed = parse_rera_number(text)
    if parsed is None or parsed.kind != "project":
        raise ValueError(f"unrecognised project registration number {text!r}")
    project = s.scalar(select(Project).where(Project.rera_no == parsed.normalised))
    if project is None:
        raise ValueError(f"{parsed.normalised} is not in the registry: load the project record first")
    return project


def _date(value: Any, what: str, required: bool = True) -> date | None:
    d = parse_date(value)
    if d is None and required:
        raise ValueError(f"{what} is missing or not a date: {_s(value)!r}")
    return d


def _snap(obj: Any) -> dict[str, Any]:
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def _upsert(s: Session, existing: Any, make, fill) -> str:  # noqa: ANN001
    if existing is None:
        obj = make()
        fill(obj)
        s.add(obj)
        s.flush()
        return "inserted"
    before = _snap(existing)
    fill(existing)
    s.flush()
    return "unchanged" if _snap(existing) == before else "updated"


# ------------------------------------------------------------------ one row of each kind
def apply_complaint(s: Session, row: dict[str, Any]) -> str:
    from gujrera.complaints.rules import classify

    ref = _s(row.get("ref_no"))[:40]
    if not ref:
        raise ValueError("complaint reference number is empty")
    project = _project(s, row.get("rera_no"))
    filed = _date(row.get("filed_on"), "filing date")
    summary = _s(row.get("summary"))
    category = (classify(f"{_s(row.get('category'))} {summary}") or ["other"])[0]
    status = _pick(row.get("status"), COMPLAINT_STATUS, "filed", "complaint status")
    closed = _date(row.get("closed_on"), "closing date", required=False)
    outcome = _pick(row.get("outcome"), OUTCOMES, None, "outcome") if _s(row.get("outcome")) else None
    relief = _pick(row.get("relief"), RELIEFS, "refund_with_interest", "relief") if _s(row.get("relief")) else None
    form = (_s(row.get("form")).upper()[:1] or ("B" if relief == "compensation" else "A"))
    if form not in ("A", "B"):
        raise ValueError(f"form must be A or B, not {_s(row.get('form'))!r}")
    hearing = _date(row.get("hearing_on"), "hearing date", required=False)

    def fill(c: Complaint) -> None:
        c.project_id, c.promoter_id, c.district = project.id, project.promoter_id, project.district
        c.filed_on, c.category, c.status, c.form = filed, category, status, form
        c.summary = (summary or _s(row.get("category")) or "Complaint")[:2000]
        c.closed_on = closed if status in ("disposed", "withdrawn") else None
        c.outcome = outcome if status == "disposed" else None
        c.relief, c.channel, c.is_mock = relief, "portal", False
        if hearing:
            c.hearing_on = hearing

    existing = s.scalar(select(Complaint).where(Complaint.ref_no == ref))
    result = _upsert(s, existing, lambda: Complaint(ref_no=ref), fill)
    complaint = existing or s.scalar(select(Complaint).where(Complaint.ref_no == ref))
    if result == "inserted":  # the buyer-facing timeline starts with the filing
        s.add(ComplaintEvent(complaint_id=complaint.id, at=filed, status="filed", note="Loaded from department records"))
        if status != "filed":
            s.add(ComplaintEvent(complaint_id=complaint.id, at=closed or filed, status=status, note=None))
        s.flush()
    return result


def apply_order(s: Session, row: dict[str, Any]) -> str:
    number = _s(row.get("order_no"))[:60]
    if not number:
        raise ValueError("order number is empty")
    kind = _pick(row.get("order_type"), ORDER_TYPES, "complaint_order", "order type")
    issued = _date(row.get("issued_on"), "order date")
    complaint = None
    if _s(row.get("complaint_ref")):
        complaint = s.scalar(select(Complaint).where(Complaint.ref_no == _s(row.get("complaint_ref"))[:40]))
        if complaint is None:
            raise ValueError(f"complaint {_s(row.get('complaint_ref'))!r} is not loaded: load complaints first")
    project = _project(s, row.get("rera_no"), required=False)
    if project is None and complaint is not None and complaint.project_id:
        project = s.get(Project, complaint.project_id)
    if project is None and complaint is None:
        raise ValueError("give the project's RERA number or the complaint number")
    amount_text = _s(row.get("penalty_amount")).replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "").strip()
    amount = None
    if amount_text:
        try:
            amount = float(amount_text)
        except ValueError:
            raise ValueError(f"penalty amount is not a number: {_s(row.get('penalty_amount'))!r}") from None
    paid = _s(row.get("penalty_paid")).lower() in ("yes", "y", "paid", "true", "1", "recovered", "હા", "हाँ", "हां")

    def fill(o: Order) -> None:
        o.order_type, o.issued_on, o.is_mock = kind, issued, False
        o.complaint_id = complaint.id if complaint else None
        o.project_id = project.id if project else None
        o.promoter_id = project.promoter_id if project else (complaint.promoter_id if complaint else None)
        o.summary = (_s(row.get("summary")) or kind.replace("_", " ").capitalize())[:4000]

    existing = s.scalar(select(Order).where(Order.order_no == number))
    result = _upsert(s, existing, lambda: Order(order_no=number), fill)
    order = existing or s.scalar(select(Order).where(Order.order_no == number))
    if amount is not None:
        pen = s.get(OrderPenalty, order.id)
        if pen is None:
            s.add(OrderPenalty(order_id=order.id, amount=amount, paid=paid, is_mock=False))
            result = "inserted" if result == "inserted" else "updated"
        elif (pen.amount, pen.paid) != (amount, paid):
            pen.amount, pen.paid = amount, paid
            result = "updated" if result == "unchanged" else result
        s.flush()
    return result


def apply_notice(s: Session, row: dict[str, Any]) -> str:
    ref = _s(row.get("ref_no"))[:40]
    if not ref:
        raise ValueError("notice reference number is empty")
    project = _project(s, row.get("rera_no"))
    kind = _pick(row.get("notice_type"), NOTICE_TYPES, "non_compliance", "notice type")
    issued = _date(row.get("issued_on"), "notice date")
    status = _pick(row.get("status"), NOTICE_STATUS, "issued", "notice status")

    def fill(n: AuthorityNotice) -> None:
        n.promoter_id, n.project_id = project.promoter_id, project.id
        n.notice_type, n.issued_on, n.status, n.is_mock = kind, issued, status, False

    existing = s.scalar(select(AuthorityNotice).where(AuthorityNotice.ref_no == ref))
    return _upsert(s, existing, lambda: AuthorityNotice(ref_no=ref), fill)


def apply_scrutiny(s: Session, row: dict[str, Any]) -> str:
    project = _project(s, row.get("rera_no"))
    subject = _pick(row.get("subject"), SUBJECTS, "registration", "application type")
    stage = _pick(row.get("stage"), STAGES, "under_scrutiny", "stage")
    opened = _date(row.get("opened_on"), "application date")
    closed = _date(row.get("closed_on"), "decision date", required=False)

    def fill(x: ProjectScrutiny) -> None:
        x.stage, x.is_mock = stage, False
        x.closed_on = closed if stage in ("cleared", "rejected") else None
        note = _s(row.get("officer_note"))
        if note:
            x.officer_note = note[:300]

    existing = s.scalar(select(ProjectScrutiny).where(ProjectScrutiny.project_id == project.id,
                                                      ProjectScrutiny.subject == subject,
                                                      ProjectScrutiny.opened_on == opened))
    return _upsert(s, existing, lambda: ProjectScrutiny(project_id=project.id, subject=subject, opened_on=opened), fill)


def apply_default(s: Session, row: dict[str, Any]) -> str:
    project = _project(s, row.get("rera_no"))
    kind = _pick(row.get("event_type"), EVENT_TYPES, None, "default type")
    when = _date(row.get("event_date"), "date of default")
    period = _s(row.get("period"))[:10] or None
    resolved = _date(row.get("resolved_on"), "resolved date", required=False)

    def fill(e: ComplianceEvent) -> None:
        e.promoter_id, e.resolved_on, e.period, e.is_mock = project.promoter_id, resolved, period, False

    existing = s.scalar(select(ComplianceEvent).where(ComplianceEvent.project_id == project.id,
                                                      ComplianceEvent.event_type == kind,
                                                      ComplianceEvent.event_date == when))
    return _upsert(s, existing, lambda: ComplianceEvent(project_id=project.id, event_type=kind, event_date=when), fill)


APPLY = {"complaint": apply_complaint, "order": apply_order, "notice": apply_notice,
         "scrutiny": apply_scrutiny, "default": apply_default}
