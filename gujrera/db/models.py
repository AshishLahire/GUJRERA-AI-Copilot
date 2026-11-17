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
PROJECT_STATUSES = ("ongoing", "completed", "lapsed", "revoked")
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


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime)
    user_id: Mapped[int | None] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str | None] = mapped_column(Text)
