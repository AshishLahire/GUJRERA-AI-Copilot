"""Relational schema for GUJRERA records.

Every source table has ``is_mock``. Rows produced by the mock generator set it
to True and the UI/API must label them; rows imported from public GUJRERA data
set it to False and carry ``source_url``.

Personal data is kept to a minimum: complainants are referenced by a user id
and a salted hash, never by name or phone number.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# --- Controlled vocabularies (stored as plain strings for portability) ---

PROJECT_TYPES = ("residential", "commercial", "mixed", "plotted")
# "unverified": imported public record whose registered completion date has passed, but the source does not
# say whether it was completed. No delay or lapse is claimed for these; users are told to check the portal.
PROJECT_STATUSES = ("ongoing", "completed", "lapsed", "revoked", "unverified")
APPROVAL_KINDS = (
    "layout_plan",
    "building_permission",
    "non_agricultural",
    "fire_noc",
    "environment_clearance",
)
COMPLAINT_FORMS = ("A", "B")  # A: to the Authority (s.31); B: adjudicating officer (s.71). Verify against Gujarat Rules.
COMPLAINT_CATEGORIES = (
    "possession_delay",
    "refund",
    "structural_defect",
    "plan_deviation",
    "false_advertisement",
    "amenities_not_provided",
    "agreement_violation",
    "agent_misconduct",
    "compensation",
)
RELIEFS = ("possession_with_interest", "refund_with_interest", "rectification", "compensation", "other")
COMPLAINT_STATUSES = ("filed", "under_scrutiny", "hearing_scheduled", "order_reserved", "disposed", "withdrawn")
OPEN_COMPLAINT_STATUSES = ("filed", "under_scrutiny", "hearing_scheduled", "order_reserved")
ORDER_TYPES = ("complaint_order", "show_cause", "penalty_order", "extension_order", "revocation_order")
DUE_KINDS = ("annual_fee", "late_qpr_penalty", "penalty", "notice")
DUE_STATUSES = ("pending", "paid", "waived", "responded")
ROLES = ("citizen", "developer", "agent", "officer")


class Base(DeclarativeBase):
    pass


class Promoter(Base):
    __tablename__ = "promoters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    name_gu: Mapped[str | None] = mapped_column(String(200))
    promoter_type: Mapped[str] = mapped_column(String(40), default="company")
    district: Mapped[str] = mapped_column(String(60), index=True)
    address: Mapped[str | None] = mapped_column(String(300))
    source_url: Mapped[str | None] = mapped_column(String(500))
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)

    projects: Mapped[list[Project]] = relationship(back_populates="promoter")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rera_no: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    promoter_id: Mapped[int] = mapped_column(ForeignKey("promoters.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    name_gu: Mapped[str | None] = mapped_column(String(200))
    district: Mapped[str] = mapped_column(String(60), index=True)
    taluka: Mapped[str | None] = mapped_column(String(80))
    planning_authority: Mapped[str | None] = mapped_column(String(40))
    project_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), index=True)
    units: Mapped[int] = mapped_column(Integer, default=0)
    reg_date: Mapped[date] = mapped_column(Date)
    proposed_completion: Mapped[date] = mapped_column(Date)
    revised_completion: Mapped[date | None] = mapped_column(Date)
    actual_completion: Mapped[date | None] = mapped_column(Date)
    reg_valid_until: Mapped[date] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(String(500))
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)

    promoter: Mapped[Promoter] = relationship(back_populates="projects")


class ProjectProgress(Base):
    """Quarterly progress report (QPR) filings."""

    __tablename__ = "project_progress"
    __table_args__ = (UniqueConstraint("project_id", "quarter"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    quarter: Mapped[str] = mapped_column(String(7))  # e.g. "2025-Q3"
    percent_complete: Mapped[float] = mapped_column(Float)
    due_on: Mapped[date] = mapped_column(Date)
    filed_on: Mapped[date | None] = mapped_column(Date)  # None = not filed
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    authority: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20))  # granted | pending | rejected
    ref: Mapped[str | None] = mapped_column(String(80))
    decided_on: Mapped[date | None] = mapped_column(Date)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reg_no: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    name_gu: Mapped[str | None] = mapped_column(String(200))
    district: Mapped[str] = mapped_column(String(60), index=True)
    reg_date: Mapped[date] = mapped_column(Date)
    valid_until: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))  # active | expired | revoked
    source_url: Mapped[str | None] = mapped_column(String(500))
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    role: Mapped[str] = mapped_column(String(20))
    promoter_id: Mapped[int | None] = mapped_column(ForeignKey("promoters.id"))
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"))
    district_scope: Mapped[str | None] = mapped_column(String(60))  # officers; None = statewide
    preferred_lang: Mapped[str] = mapped_column(String(5), default="gu")
    display_name: Mapped[str | None] = mapped_column(String(200))
    password_hash: Mapped[str | None] = mapped_column(String(200))  # PBKDF2; see gujrera/auth.py
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)


class Complaint(Base):
    __tablename__ = "complaints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_no: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), index=True)
    promoter_id: Mapped[int | None] = mapped_column(ForeignKey("promoters.id"), index=True)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"))
    complainant_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    complainant_hash: Mapped[str | None] = mapped_column(String(64))
    form: Mapped[str] = mapped_column(String(1))
    category: Mapped[str] = mapped_column(String(40), index=True)
    summary: Mapped[str] = mapped_column(Text)
    district: Mapped[str] = mapped_column(String(60), index=True)
    filed_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), index=True)
    closed_on: Mapped[date | None] = mapped_column(Date)
    outcome: Mapped[str | None] = mapped_column(String(40))  # allowed | partly_allowed | dismissed | settled
    relief: Mapped[str | None] = mapped_column(String(40))
    channel: Mapped[str] = mapped_column(String(20), default="portal")  # portal | copilot
    # Complaints filed through the copilot are tracked with ref_no + a 6-digit code; only a hash is kept.
    tracking_code_hash: Mapped[str | None] = mapped_column(String(64))
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)

    events: Mapped[list[ComplaintEvent]] = relationship(
        back_populates="complaint", order_by="ComplaintEvent.at"
    )


class ComplaintEvent(Base):
    __tablename__ = "complaint_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), index=True)
    at: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(String(300))

    complaint: Mapped[Complaint] = relationship(back_populates="events")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_no: Mapped[str] = mapped_column(String(60), unique=True)
    order_type: Mapped[str] = mapped_column(String(30), index=True)
    complaint_id: Mapped[int | None] = mapped_column(ForeignKey("complaints.id"))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), index=True)
    promoter_id: Mapped[int | None] = mapped_column(ForeignKey("promoters.id"), index=True)
    issued_on: Mapped[date] = mapped_column(Date)
    summary: Mapped[str] = mapped_column(Text)
    doc_path: Mapped[str | None] = mapped_column(String(300))
    source_url: Mapped[str | None] = mapped_column(String(500))
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)


class DueNotice(Base):
    """Fees, penalties and notices addressed to a promoter. Private to that promoter and officers."""

    __tablename__ = "dues_notices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    promoter_id: Mapped[int] = mapped_column(ForeignKey("promoters.id"), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"))
    kind: Mapped[str] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(String(300))
    amount: Mapped[float | None] = mapped_column(Float)  # INR; None for notices without a sum
    issued_on: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)


class MockPortalSubmission(Base):
    """Stands in for GUJRERA's existing complaint workflow until its API is available.

    Holds the full submission (including contact details) the way the real
    portal would. The copilot's own tables keep only a hash of the complainant.
    """

    __tablename__ = "mock_portal_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_no: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime)
    payload_json: Mapped[str] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime)
    user_id: Mapped[int | None] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str | None] = mapped_column(Text)


class EnforcementCase(Base):
    """Citizen ad reports about one advertised project, grouped for GUJRERA's enforcement team.

    kind: unregistered (Section 3: advertised or sold without registration; penalty Section 59),
          lapsed (sold under a lapsed or revoked registration), misleading (Section 12: details that do
          not match the registration, e.g. another promoter or a later possession date).
    """

    __tablename__ = "enforcement_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_no: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(String(200))  # project name as advertised
    advertised_promoter: Mapped[str | None] = mapped_column(String(200))
    district: Mapped[str | None] = mapped_column(String(60), index=True)
    claimed_rera: Mapped[str | None] = mapped_column(String(120), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"))  # registered project it names, if any
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)  # new | reviewing | notice_issued | closed
    outcome: Mapped[str | None] = mapped_column(String(40))  # registered | false_alarm | penalty | other
    notes: Mapped[str | None] = mapped_column(Text)
    opened_on: Mapped[date] = mapped_column(Date)
    updated_on: Mapped[date] = mapped_column(Date)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)


class AdReport(Base):
    """One ad a citizen reported after the RERA check. Holds the ad's content and the check result,
    never the reporter's name or number (a logged-in reporter is linked by user id only)."""

    __tablename__ = "ad_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("enforcement_cases.id"), index=True)
    reported_on: Mapped[date] = mapped_column(Date, index=True)
    channel: Mapped[str] = mapped_column(String(20))  # text | upload | chat
    verdict: Mapped[str] = mapped_column(String(40))
    claimed_rera: Mapped[str | None] = mapped_column(String(120))
    advertised_project: Mapped[str | None] = mapped_column(String(200))
    advertised_promoter: Mapped[str | None] = mapped_column(String(200))
    district: Mapped[str | None] = mapped_column(String(60))
    contact_phones: Mapped[str | None] = mapped_column(String(200))  # numbers printed on the ad
    websites: Mapped[str | None] = mapped_column(String(300))
    asks_payment_to_account: Mapped[bool] = mapped_column(Boolean, default=False)
    problems: Mapped[str | None] = mapped_column(Text)  # failed checks, one per line
    excerpt: Mapped[str] = mapped_column(Text)  # the ad text (first 1,500 characters)
    text_hash: Mapped[str] = mapped_column(String(64), index=True)  # same ad reported twice is one report
    reporter_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)


class OrderCompliance(Base):
    """Whether the promoter has done what an order directs (refund, interest, repairs ...), by when.

    status: pending (deadline not passed, or passed and nothing recorded: shown as overdue), complied,
    partly_complied, not_complied (reported by the buyer or found by the officer), recovery (recovery as
    arrears of land revenue started, Section 40).
    """

    __tablename__ = "order_compliance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True, index=True)
    direction: Mapped[str] = mapped_column(String(40))  # see gujrera.orders.DIRECTIONS
    due_on: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    complied_on: Mapped[date | None] = mapped_column(Date)
    updated_on: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(300))
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)


class QprSubmission(Base):
    """A quarterly progress report prepared and filed through the assistant: the Section 11(1) details and
    the project-account figures behind the Section 4(2)(l)(D) checks. In the PoC this is handed to the
    GUJRERA portal; here it also marks the registry's progress row as filed."""

    __tablename__ = "qpr_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    quarter: Mapped[str] = mapped_column(String(7))
    filed_on: Mapped[date] = mapped_column(Date)
    filed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    payload_json: Mapped[str] = mapped_column(Text)
    warnings: Mapped[str | None] = mapped_column(Text)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)


class ProjectWatch(Base):
    """A logged-in buyer following a project. Alerts are built from the registry's dated records since
    `created_on`; `last_seen_on` marks what the buyer has read. No phone number is stored: SMS or WhatsApp
    delivery is a portal-side hand-off in the PoC (gujrera.watch.Notifier)."""

    __tablename__ = "project_watches"
    __table_args__ = (UniqueConstraint("user_id", "project_id", name="uq_watch_user_project"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    created_on: Mapped[date] = mapped_column(Date)
    last_seen_on: Mapped[date] = mapped_column(Date)
