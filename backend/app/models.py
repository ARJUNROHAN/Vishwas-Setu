"""ORM models.

Timestamps are stored as naive UTC; dates (due dates, validity) are Indian calendar dates.
Groups: rules (versioned), people, domain, cross-cutting (deadlines, alerts, audit, files).
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


# --------------------------------------------------------------------------- rules (versioned)
class Ruleset(Base):
    """An immutable, versioned set of routing rules. Applications pin the version they were submitted under."""
    __tablename__ = "rulesets"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40))
    version: Mapped[int] = mapped_column(Integer)
    aph_edition: Mapped[str] = mapped_column(String(80))
    source_url: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE")  # ACTIVE | RETIRED
    effective_from: Mapped[datetime] = mapped_column(DateTime)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_by: Mapped[str] = mapped_column(String(120), default="System seed")
    notes: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (UniqueConstraint("code", "version"),)


class Region(Base):
    __tablename__ = "regions"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    office_city: Mapped[str] = mapped_column(String(80))


class RouteTemplate(Base):
    __tablename__ = "route_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    ruleset_id: Mapped[int] = mapped_column(ForeignKey("rulesets.id"))
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    source_type: Mapped[str] = mapped_column(String(12), default="APH")
    aph_reference: Mapped[str] = mapped_column(String(200), default="")
    ruleset: Mapped[Ruleset] = relationship()
    stages: Mapped[list["StageDefinition"]] = relationship(
        back_populates="route", order_by="StageDefinition.order", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("ruleset_id", "code"),)

    @property
    def aph_version(self) -> str:
        return f"{self.ruleset.code} v{self.ruleset.version}"


class StageDefinition(Base):
    __tablename__ = "stage_definitions"
    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("route_templates.id"))
    code: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(80))
    order: Mapped[int] = mapped_column(Integer)
    sla_days: Mapped[int] = mapped_column(Integer)
    assignee_role: Mapped[str] = mapped_column(String(30))
    conditional: Mapped[bool] = mapped_column(Boolean, default=False)
    on_deficiency: Mapped[str] = mapped_column(String(40), default="RETURN")
    managed_by: Mapped[str] = mapped_column(String(20), default="officer")
    route: Mapped[RouteTemplate] = relationship(back_populates="stages")
    __table_args__ = (UniqueConstraint("route_id", "code"),)


class ApplicationTypeDef(Base):
    """Category → route mapping (Table 2.3 row / Chapter I / Regulations), per ruleset."""
    __tablename__ = "application_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    ruleset_id: Mapped[int] = mapped_column(ForeignKey("rulesets.id"))
    code: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(160))
    chapter: Mapped[str] = mapped_column(String(6))
    table_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    route_code: Mapped[str] = mapped_column(String(40))
    notice_category: Mapped[str] = mapped_column(String(20))  # PUBLIC_NOTICE | YEAR_ROUND | ODL_CYCLE
    notice_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    checklist_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    initiated_by: Mapped[str] = mapped_column(String(12), default="INSTITUTION")
    note: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (UniqueConstraint("ruleset_id", "code"),)


class DocumentRequirement(Base):
    __tablename__ = "document_requirements"
    id: Mapped[int] = mapped_column(primary_key=True)
    ruleset_id: Mapped[int] = mapped_column(ForeignKey("rulesets.id"))
    checklist_code: Mapped[str] = mapped_column(String(30))
    doc_code: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(200))
    condition: Mapped[str] = mapped_column(String(30))  # always | optional | building_over_30 | land_leased
    source: Mapped[str] = mapped_column(String(200))


class AcademicCalendar(Base):
    __tablename__ = "academic_calendars"
    id: Mapped[int] = mapped_column(primary_key=True)
    academic_year: Mapped[str] = mapped_column(String(10), unique=True)
    notice_ref: Mapped[str] = mapped_column(String(200))
    application_open: Mapped[date] = mapped_column(Date)
    application_close: Mapped[date] = mapped_column(Date)
    odl_cycles: Mapped[list] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)


class EscalationPolicy(Base):
    __tablename__ = "escalation_policies"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    reminder_offsets_days: Mapped[list] = mapped_column(JSON, default=list)
    escalation_steps: Mapped[list] = mapped_column(JSON, default=list)  # [{level, after_days, to_role}]


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(20), default="")
    source_type: Mapped[str] = mapped_column(String(12), default="DESIGN")
    source: Mapped[str] = mapped_column(Text, default="")


# --------------------------------------------------------------------------- people
class Expert(Base):
    __tablename__ = "experts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    expertise: Mapped[str] = mapped_column(String(80))
    organisation: Mapped[str] = mapped_column(String(160))
    home_state: Mapped[str] = mapped_column(String(80))


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(30))
    designation: Mapped[str] = mapped_column(String(160), default="")
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"), nullable=True)
    institution_id: Mapped[int | None] = mapped_column(ForeignKey("institutions.id"), nullable=True)
    expert_id: Mapped[int | None] = mapped_column(ForeignKey("experts.id"), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    region: Mapped[Region | None] = relationship()


# --------------------------------------------------------------------------- domain
class Institution(Base):
    __tablename__ = "institutions"
    id: Mapped[int] = mapped_column(primary_key=True)
    permanent_id: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(80))
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"))
    institution_type: Mapped[str] = mapped_column(String(60))
    max_course_years: Mapped[int] = mapped_column(Integer, default=4)
    is_new: Mapped[bool] = mapped_column(Boolean, default=False)
    land_tenure: Mapped[str] = mapped_column(String(10), default="OWNED")  # OWNED | LEASED
    building_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    region: Mapped[Region] = relationship()

    @property
    def self_financing(self) -> bool:
        return self.institution_type.startswith("Private")


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_no: Mapped[str] = mapped_column(String(30), unique=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"))
    application_type: Mapped[str] = mapped_column(String(40))
    academic_year: Mapped[str] = mapped_column(String(10))
    processing_academic_year: Mapped[str] = mapped_column(String(40))
    ruleset_id: Mapped[int] = mapped_column(ForeignKey("rulesets.id"))
    route_id: Mapped[int] = mapped_column(ForeignKey("route_templates.id"))
    status: Mapped[str] = mapped_column(String(30), default="IN_PROGRESS")
    current_stage_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    decision_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)
    decision_file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id"), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(String(30), nullable=True)
    pending_next_stage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    parent_application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id"), nullable=True)
    intake_requested: Mapped[int | None] = mapped_column(Integer, nullable=True)
    programme: Mapped[str] = mapped_column(String(120), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)  # optimistic locking
    institution: Mapped[Institution] = relationship()
    route: Mapped[RouteTemplate] = relationship()
    ruleset: Mapped[Ruleset] = relationship()
    stages: Mapped[list["StageInstance"]] = relationship(
        back_populates="application", order_by="StageInstance.id", cascade="all, delete-orphan")


class ApplicationDocument(Base):
    """Checklist item for one application (evaluated from Annexure checklists at submission)."""
    __tablename__ = "application_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"))
    doc_code: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(200))
    mandatory: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(200), default="")
    file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="MISSING")  # MISSING | UPLOADED | NOT_REQUIRED


class StageInstance(Base):
    __tablename__ = "stage_instances"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"))
    stage_code: Mapped[str] = mapped_column(String(30))
    stage_name: Mapped[str] = mapped_column(String(80))
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(30), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    paused_days: Mapped[float] = mapped_column(default=0.0)
    application: Mapped[Application] = relationship(back_populates="stages")
    assignee: Mapped[User | None] = relationship()


class Deficiency(Base):
    """One recorded deficiency. Re-scrutiny verifies only these items (APH cl. 1.8)."""
    __tablename__ = "deficiencies"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"))
    stage_instance_id: Mapped[int] = mapped_column(ForeignKey("stage_instances.id"))
    seq: Mapped[int] = mapped_column(Integer)
    finding: Mapped[str] = mapped_column(Text)
    reference: Mapped[str] = mapped_column(String(200), default="")  # document / standard
    correction_requested: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="OPEN")  # OPEN | RESPONDED | RESOLVED | NOT_RESOLVED
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_file_ids: Mapped[list] = mapped_column(JSON, default=list)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verify_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class EvcVisit(Base):
    __tablename__ = "evc_visits"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"))
    stage_instance_id: Mapped[int] = mapped_column(ForeignKey("stage_instances.id"))
    mode: Mapped[str] = mapped_column(String(10), default="PHYSICAL")
    panel: Mapped[list] = mapped_column(JSON, default=list)  # [{id(expert), name, ...}]
    queued_at: Mapped[datetime] = mapped_column(DateTime)
    scheduled_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="QUEUED")  # QUEUED | SCHEDULED | REPORT_SUBMITTED
    report_file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id"), nullable=True)
    report_outcome: Mapped[str | None] = mapped_column(String(30), nullable=True)
    report_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_submitted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    video_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority_new_institution: Mapped[bool] = mapped_column(Boolean, default=False)
    application: Mapped[Application] = relationship()


class Undertaking(Base):
    __tablename__ = "undertakings"
    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"))
    application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    condition_text: Mapped[str] = mapped_column(Text)
    aph_reference: Mapped[str] = mapped_column(String(200), default="")
    source_document: Mapped[str] = mapped_column(String(200), default="")
    due_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    evidence_file_ids: Mapped[list] = mapped_column(JSON, default=list)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    was_late: Mapped[bool] = mapped_column(Boolean, default=False)
    institution: Mapped[Institution] = relationship()


class TrackedDocument(Base):
    __tablename__ = "tracked_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"))
    doc_type: Mapped[str] = mapped_column(String(40))  # LAND_LEASE | FIRE_NOC | STABILITY_CERT | BUILDING_LEASE
    title: Mapped[str] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer, default=1)
    issuer_name: Mapped[str] = mapped_column(String(160), default="")
    reference_no: Mapped[str] = mapped_column(String(80), default="")
    valid_from: Mapped[date] = mapped_column(Date)
    valid_until: Mapped[date] = mapped_column(Date)
    file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id"), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(20), default="VERIFIED")
    superseded_by_id: Mapped[int | None] = mapped_column(ForeignKey("tracked_documents.id"), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    institution: Mapped[Institution] = relationship()


# --------------------------------------------------------------------------- cross-cutting
class Obligation(Base):
    __tablename__ = "obligations"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(240))
    subject_type: Mapped[str] = mapped_column(String(30))
    subject_id: Mapped[int] = mapped_column(Integer)
    application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id"), nullable=True)
    institution_id: Mapped[int | None] = mapped_column(ForeignKey("institutions.id"), nullable=True)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"), nullable=True)
    owner_role: Mapped[str] = mapped_column(String(30))
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    source_reference: Mapped[str] = mapped_column(String(200), default="")
    opened_at: Mapped[datetime] = mapped_column(DateTime)
    due_at: Mapped[datetime] = mapped_column(DateTime)
    state: Mapped[str] = mapped_column(String(20), default="UPCOMING")
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)
    paused_since: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    close_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    was_overdue: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_user: Mapped[User | None] = relationship()
    institution: Mapped[Institution | None] = relationship()


class Escalation(Base):
    __tablename__ = "escalations"
    id: Mapped[int] = mapped_column(primary_key=True)
    obligation_id: Mapped[int] = mapped_column(ForeignKey("obligations.id"))
    level: Mapped[int] = mapped_column(Integer)
    target_role: Mapped[str] = mapped_column(String(30))
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ack_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    obligation: Mapped[Obligation] = relationship()
    __table_args__ = (UniqueConstraint("obligation_id", "level"),)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    obligation_id: Mapped[int | None] = mapped_column(ForeignKey("obligations.id"), nullable=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    channel: Mapped[str] = mapped_column(String(10))  # IN_APP | EMAIL
    category: Mapped[str] = mapped_column(String(20))
    subject: Mapped[str] = mapped_column(String(240))
    body: Mapped[str] = mapped_column(Text)
    dedupe_key: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(20), default="DELIVERED")  # DELIVERED (in-app) | SIMULATED (email)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    link: Mapped[str | None] = mapped_column(String(200), nullable=True)
    __table_args__ = (UniqueConstraint("dedupe_key", "recipient_id", "channel"),)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    seq: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_label: Mapped[str] = mapped_column(String(160))
    action: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int] = mapped_column(Integer)
    application_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    institution_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100))
    user_id: Mapped[int] = mapped_column(Integer)
    method_path: Mapped[str] = mapped_column(String(200))
    status_code: Mapped[int] = mapped_column(Integer)
    response_body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    __table_args__ = (UniqueConstraint("key", "user_id"),)


class FileObject(Base):
    __tablename__ = "files"
    id: Mapped[int] = mapped_column(primary_key=True)
    storage_key: Mapped[str] = mapped_column(String(200))
    original_name: Mapped[str] = mapped_column(String(200))
    sha256: Mapped[str] = mapped_column(String(64))
    mime: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    institution_id: Mapped[int | None] = mapped_column(ForeignKey("institutions.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime)
    scan_status: Mapped[str] = mapped_column(String(20), default="CLEAN")
