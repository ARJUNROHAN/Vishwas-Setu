"""Post-approval obligations and document validity.

The Council does not grant conditional approvals (Grant of Approval Regs 2024-27 cl. 6.10). What the
APH and Regulations do attach to an approval are **time-bound requirements**, tracked here as
undertakings — each created only where its provision applies:
  * security deposit proof + Affidavit 3 within 15 days of intimation (APH cl. 2.25(f)), for
    self-financing institutions in the categories where the deposit provisions apply (Regs 6.2(f), 6.3(l));
  * appointment of Principal and faculty before commencement (Regs 6.2(i)) — new institutions;
  * deficiencies observed by EVC/SHC fulfilled before the next EoA (Regs 6.3(c));
  * accreditation of 60% of eligible courses within three years (Regs 4.3).
Documents: land lease (cl. 2.1(e)), fire safety certificate, structural stability certificate for
buildings older than 30 years (Annexure 2; Ch. VI). Warnings are flags for officials, never denials.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import audit, clock, obligations as obl, rules
from .errors import Forbidden, Invalid, WorkflowError
from .models import Application, Institution, StageInstance, TrackedDocument, Undertaking, User

UNDERTAKING_TEMPLATES = {
    "SECURITY_DEPOSIT": {
        "title": "Proof of security deposit with Affidavit 3",
        "text": "Submit proof of creation of the security deposit along with Affidavit 3 within 15 days of intimation. "
                "Consequences of delay are assessed by the competent authority under the applicable clause.",
        "ref": "APH cl. 2.25(f) (printed p. 31); Regs 6.2(f) / 6.3(l)"},
    "DEFICIENCY_COMPLIANCE": {
        "title": "Fulfil deficiencies observed by the EVC / SHC before the next EoA",
        "text": "Deficiencies observed by the Expert Visit Committee / Standing Hearing Committee shall be fulfilled and "
                "evidence submitted before the issue of EoA for the next Academic Year.",
        "ref": "Grant of Approval Regs 2024-27 cl. 6.3(c)"},
    "FACULTY_APPOINTMENT": {
        "title": "Appoint Principal / Director and faculty; update on portal",
        "text": "Appoint the Principal/Director and faculty as per Council policy before commencement of classes and "
                "upload appointment details on the portal.",
        "ref": "Grant of Approval Regs 2024-27 cl. 6.2(i)"},
    "ACCREDITATION": {
        "title": "Accreditation of at least 60% of eligible courses",
        "text": "At least 60% of eligible courses to be accredited within three years; otherwise EoA shall not be issued.",
        "ref": "Grant of Approval Regs 2024-27 cl. 4.3"},
}

DOC_TYPES = {
    "LAND_LEASE": "Registered land lease deed",
    "FIRE_NOC": "Fire safety certificate",
    "STABILITY_CERT": "Structural stability certificate",
    "BUILDING_LEASE": "Registered building lease",
}


# --------------------------------------------------------------------------- undertakings
def create_undertaking(db: Session, institution: Institution, kind: str, actor: User | None, due_on: date,
                       application: Application | None = None, condition_text: str | None = None,
                       source_document: str = "") -> Undertaking:
    tpl = UNDERTAKING_TEMPLATES[kind]
    u = Undertaking(institution_id=institution.id, application_id=application.id if application else None, kind=kind,
                    title=tpl["title"], condition_text=condition_text or tpl["text"], aph_reference=tpl["ref"],
                    source_document=source_document, due_on=due_on, status="OPEN", created_at=clock.now())
    db.add(u)
    db.flush()
    audit.record(db, actor=actor, action="UNDERTAKING_CREATED", entity_type="undertaking", entity_id=u.id,
                 application_id=u.application_id, institution_id=institution.id,
                 detail={"kind": kind, "due_on": due_on.isoformat(), "source_clause": tpl["ref"],
                         "source_document": source_document})
    _open_undertaking_ob(db, u, institution, due_on)
    return u


def _open_undertaking_ob(db, u: Undertaking, inst: Institution, due_on: date):
    obl.open_obligation(db, kind="UNDERTAKING", title=f"{u.title} — {inst.name}", subject_type="undertaking",
                        subject_id=u.id, due_at=clock.ist_close_of(due_on), owner_role="INSTITUTION",
                        application_id=u.application_id, institution_id=inst.id, region_id=inst.region_id,
                        source_reference=u.aph_reference)


def next_eoa_deadline(today: date) -> date:
    return date(today.year, 12, 31) if today.month <= 10 else date(today.year + 1, 12, 31)


def security_deposit_applies(db: Session, app: Application) -> bool:
    kinds = {k.strip() for k in rules.setting(db, "security_deposit_applies_to").split(",") if k.strip()}
    return app.application_type in kinds and app.institution.self_financing


def create_undertakings_for_approval(db: Session, app: Application, actor: User) -> list[Undertaking]:
    inst = app.institution
    src = f"Order {app.decision_ref}" if app.decision_ref else ""
    made: list[Undertaking] = []
    if security_deposit_applies(db, app):
        days = rules.setting_int(db, "security_deposit_days", 15)
        made.append(create_undertaking(db, inst, "SECURITY_DEPOSIT", actor, due_on=clock.today() + timedelta(days=days),
                                       application=app, source_document=src))
    if app.application_type == "NEW_INSTITUTION":
        start_year = int(app.academic_year[:4]) if app.academic_year[:4].isdigit() else clock.today().year
        made.append(create_undertaking(db, inst, "FACULTY_APPOINTMENT", actor, due_on=date(start_year, 7, 31),
                                       application=app, source_document=src))
    noted = [si for si in app.stages if si.outcome == "DEFICIENCY" and si.stage_code in ("EVC", "SHC") and si.remarks]
    if noted:
        text = UNDERTAKING_TEMPLATES["DEFICIENCY_COMPLIANCE"]["text"] + " Observed: " + "; ".join(
            f"{si.stage_name}: {si.remarks}" for si in noted)
        made.append(create_undertaking(db, inst, "DEFICIENCY_COMPLIANCE", actor, due_on=next_eoa_deadline(clock.today()),
                                       application=app, condition_text=text, source_document=src))
    return made


def submit_evidence(db: Session, u: Undertaking, actor: User, remarks: str, file_ids: list[int]) -> None:
    if actor.role != "INSTITUTION" or actor.institution_id != u.institution_id:
        raise Forbidden("Only the institution can submit evidence")
    if u.status not in ("OPEN", "REJECTED", "LAPSED"):
        raise WorkflowError("Evidence already submitted")
    if not file_ids:
        raise Invalid("Attach at least one evidence document")
    u.was_late = u.was_late or clock.today() > u.due_on
    u.status, u.remarks = "SUBMITTED", remarks
    u.evidence_file_ids = list(u.evidence_file_ids or []) + file_ids
    for ob in obl.open_for(db, "undertaking", u.id, ["UNDERTAKING"]):
        obl.close_obligation(db, ob, "Evidence submitted", actor)
    audit.record(db, actor=actor, action="EVIDENCE_SUBMITTED", entity_type="undertaking", entity_id=u.id,
                 application_id=u.application_id, institution_id=u.institution_id,
                 detail={"files": file_ids, "late": u.was_late}, reason=remarks)
    inst = u.institution
    obl.open_obligation(db, kind="UNDERTAKING_VERIFY", title=f"Verify evidence: {u.title} — {inst.name}",
                        subject_type="undertaking", subject_id=u.id,
                        due_at=clock.due_after_days(clock.now(), rules.setting_int(db, "verify_days", 7)),
                        owner_role="SCRUTINY_OFFICER", application_id=u.application_id, institution_id=inst.id,
                        region_id=inst.region_id, source_reference="Verification time limit: DESIGN")


def verify_undertaking(db: Session, u: Undertaking, actor: User, accept: bool, remarks: str) -> None:
    if actor.role != "SCRUTINY_OFFICER" or actor.region_id != u.institution.region_id:
        raise Forbidden("Only a scrutiny officer of this Region can verify")
    if u.status != "SUBMITTED":
        raise WorkflowError("Nothing to verify")
    if not remarks.strip():
        raise Invalid("Remarks are mandatory")
    for ob in obl.open_for(db, "undertaking", u.id, ["UNDERTAKING_VERIFY"]):
        obl.close_obligation(db, ob, "Verified" if accept else "Returned for correction", actor)
    u.status, u.remarks = ("VERIFIED" if accept else "REJECTED"), remarks
    audit.record(db, actor=actor, action="UNDERTAKING_VERIFIED" if accept else "UNDERTAKING_REJECTED",
                 entity_type="undertaking", entity_id=u.id, application_id=u.application_id,
                 institution_id=u.institution_id, reason=remarks)
    users = obl.users_for_role(db, "INSTITUTION", None, u.institution_id)
    if accept:
        obl.notify(db, recipients=users, category="INFO", subject=f"Compliance verified: {u.title}", body=remarks,
                   dedupe_key=f"und{u.id}:verified", link="/compliance?tab=undertakings")
    else:
        new_due = max(u.due_on, clock.today() + timedelta(days=rules.setting_int(db, "resubmit_days", 7)))
        u.due_on = new_due
        obl.notify(db, recipients=users, category="INFO", subject=f"Correction requested: {u.title}",
                   body=f"{remarks}. Resubmit by {new_due:%d %b %Y}.",
                   dedupe_key=f"und{u.id}:rejected:{clock.now():%Y%m%d%H%M%S}", link="/compliance?tab=undertakings")
        _open_undertaking_ob(db, u, u.institution, new_due)


# --------------------------------------------------------------------------- documents
def lease_critical_date(doc: TrackedDocument, inst: Institution) -> date:
    """APH cl. 2.1(e): EoA is not issued from the year the live lease equals the longest course duration."""
    try:
        return doc.valid_until.replace(year=doc.valid_until.year - inst.max_course_years)
    except ValueError:
        return doc.valid_until.replace(year=doc.valid_until.year - inst.max_course_years, day=28)


def expiry_due(doc: TrackedDocument) -> date:
    return lease_critical_date(doc, doc.institution) if doc.doc_type == "LAND_LEASE" else doc.valid_until


DOC_SOURCE = {"LAND_LEASE": "APH cl. 2.1(e); Ch. VI", "FIRE_NOC": "APH Annexure 2 (valid fire safety certificate)",
              "STABILITY_CERT": "APH Annexure 2; Ch. VI p. 57 (5-year validity — verify)", "BUILDING_LEASE": "APH Annexure 1"}


def required_doc_types(db: Session, inst: Institution) -> list[str]:
    req = ["FIRE_NOC"]
    if inst.land_tenure == "LEASED":
        req.append("LAND_LEASE")
    age = rules.building_age_years(inst, clock.today())
    if age is not None and age > rules.setting_int(db, "stability_building_age_years", 30):
        req.append("STABILITY_CERT")
    return req


def track_document(db: Session, doc: TrackedDocument, actor: User | None) -> None:
    inst = doc.institution
    due = expiry_due(doc)
    what = (f"Land lease review: live lease reaches {inst.max_course_years} yrs on {due:%d %b %Y}"
            if doc.doc_type == "LAND_LEASE" else f"Renew {doc.title} (expires {doc.valid_until:%d %b %Y})")
    obl.open_obligation(db, kind="DOC_EXPIRY", title=f"{what} — {inst.name}", subject_type="document",
                        subject_id=doc.id, due_at=clock.ist_close_of(due), owner_role="INSTITUTION",
                        institution_id=inst.id, region_id=inst.region_id, actor=actor,
                        source_reference=DOC_SOURCE.get(doc.doc_type, ""))


def lease_checks(valid_from: date, valid_until: date, today: date, max_course_years: int, db: Session) -> list[dict]:
    term = (valid_until - valid_from).days / 365.25
    live = (valid_until - today).days / 365.25
    min_term = rules.setting_int(db, "lease_min_term_years", 30)
    min_live = rules.setting_int(db, "lease_min_live_years_on_renewal", 25)
    return [
        {"check": f"Lease term of at least {min_term} years", "value": f"{term:.1f} years", "ok": term >= min_term - 0.1,
         "source": "APH Ch. VI; Annexure 1"},
        {"check": f"Live lease of at least {min_live} years on renewal", "value": f"{live:.1f} years", "ok": live >= min_live,
         "source": "AICTE FAQ on cl. 2.1(e)"},
        {"check": f"Live lease exceeds the longest course duration ({max_course_years} yrs)", "value": f"{live:.1f} years",
         "ok": live > max_course_years, "source": "APH cl. 2.1(e)"},
    ]


def stability_checks(valid_from: date, valid_until: date, db: Session) -> list[dict]:
    years = rules.setting_int(db, "stability_validity_years", 5)
    limit = valid_from.replace(year=valid_from.year + years) if not (valid_from.month == 2 and valid_from.day == 29) else \
        valid_from.replace(year=valid_from.year + years, day=28)
    return [{"check": f"Validity not beyond {years} years from issue", "value": f"valid until {valid_until:%d %b %Y}",
             "ok": valid_until <= limit, "source": "APH Ch. VI p. 57 — verify"}]


def _validate_dates(valid_from: date, valid_until: date):
    if valid_until <= valid_from:
        raise Invalid("Expiry date must be after the issue / start date")


def submit_new_document(db: Session, inst: Institution, actor: User, doc_type: str, valid_from: date, valid_until: date,
                        file_id: int, issuer_name: str = "", reference_no: str = "") -> TrackedDocument:
    """Upload a required document that is missing (e.g. a stability certificate)."""
    if actor.role != "INSTITUTION" or actor.institution_id != inst.id:
        raise Forbidden("Only the institution can upload its documents")
    if doc_type not in DOC_TYPES:
        raise Invalid("Unknown document type")
    _validate_dates(valid_from, valid_until)
    existing = db.scalars(select(TrackedDocument).where(TrackedDocument.institution_id == inst.id,
                                                        TrackedDocument.doc_type == doc_type,
                                                        TrackedDocument.superseded_by_id.is_(None),
                                                        TrackedDocument.verification_status != "REJECTED")).first()
    if existing:
        raise WorkflowError("This document already exists; submit a renewal instead")
    doc = TrackedDocument(institution_id=inst.id, doc_type=doc_type, title=DOC_TYPES[doc_type], version=1,
                          issuer_name=issuer_name, reference_no=reference_no, valid_from=valid_from,
                          valid_until=valid_until, file_id=file_id, verification_status="PENDING")
    db.add(doc)
    db.flush()
    audit.record(db, actor=actor, action="DOCUMENT_SUBMITTED", entity_type="document", entity_id=doc.id,
                 institution_id=inst.id, detail={"type": doc_type, "valid_until": valid_until.isoformat()})
    _open_verify(db, doc, inst)
    return doc


def _open_verify(db, doc, inst):
    obl.open_obligation(db, kind="DOC_VERIFY", title=f"Verify {doc.title} (v{doc.version}) — {inst.name}",
                        subject_type="document", subject_id=doc.id,
                        due_at=clock.due_after_days(clock.now(), rules.setting_int(db, "verify_days", 7)),
                        owner_role="SCRUTINY_OFFICER", institution_id=inst.id, region_id=inst.region_id,
                        source_reference="Verification time limit: DESIGN")


def submit_renewal(db: Session, doc: TrackedDocument, actor: User, valid_from: date, valid_until: date, file_id: int,
                   remarks: str = "", issuer_name: str = "", reference_no: str = "") -> TrackedDocument:
    if actor.role != "INSTITUTION" or actor.institution_id != doc.institution_id:
        raise Forbidden("Only the institution can submit a renewal")
    if doc.superseded_by_id:
        raise WorkflowError("A newer version already exists")
    _validate_dates(valid_from, valid_until)
    if valid_until <= doc.valid_until:
        raise Invalid("The renewed document must be valid beyond the current one")
    pending = db.scalars(select(TrackedDocument).where(
        TrackedDocument.institution_id == doc.institution_id, TrackedDocument.doc_type == doc.doc_type,
        TrackedDocument.verification_status == "PENDING")).first()
    if pending:
        raise WorkflowError("A renewal is already awaiting verification")
    new = TrackedDocument(institution_id=doc.institution_id, doc_type=doc.doc_type, title=doc.title,
                          version=doc.version + 1, issuer_name=issuer_name, reference_no=reference_no,
                          valid_from=valid_from, valid_until=valid_until, file_id=file_id,
                          verification_status="PENDING", remarks=remarks)
    db.add(new)
    db.flush()
    for ob in obl.open_for(db, "document", doc.id, ["DOC_EXPIRY"]):
        obl.close_obligation(db, ob, "Renewal submitted for verification", actor)
    audit.record(db, actor=actor, action="DOCUMENT_RENEWAL_SUBMITTED", entity_type="document", entity_id=new.id,
                 institution_id=doc.institution_id,
                 detail={"replaces": doc.id, "version": new.version, "valid_from": valid_from.isoformat(),
                         "valid_until": valid_until.isoformat(), "file_id": file_id}, reason=remarks or None)
    _open_verify(db, new, doc.institution)
    return new


def previous_version(db: Session, new: TrackedDocument) -> TrackedDocument | None:
    return db.scalars(select(TrackedDocument).where(
        TrackedDocument.institution_id == new.institution_id, TrackedDocument.doc_type == new.doc_type,
        TrackedDocument.version == new.version - 1)).first()


def verify_document(db: Session, new: TrackedDocument, actor: User, accept: bool, remarks: str) -> None:
    if actor.role != "SCRUTINY_OFFICER" or actor.region_id != new.institution.region_id:
        raise Forbidden("Only a scrutiny officer of this Region can verify")
    if new.verification_status != "PENDING":
        raise WorkflowError("Nothing to verify")
    if not remarks.strip():
        raise Invalid("Remarks are mandatory")
    old = previous_version(db, new) if new.version > 1 else None
    for ob in obl.open_for(db, "document", new.id, ["DOC_VERIFY"]):
        obl.close_obligation(db, ob, "Verified" if accept else "Rejected", actor)
    new.verification_status, new.remarks = ("VERIFIED" if accept else "REJECTED"), remarks
    audit.record(db, actor=actor, action="DOCUMENT_VERIFIED" if accept else "DOCUMENT_REJECTED", entity_type="document",
                 entity_id=new.id, institution_id=new.institution_id,
                 detail={"version": new.version, "previous_version_kept": bool(old)}, reason=remarks)
    users = obl.users_for_role(db, "INSTITUTION", None, new.institution_id)
    if accept:
        if old:
            old.superseded_by_id = new.id
        track_document(db, new, actor)
        obl.notify(db, recipients=users, category="INFO", subject=f"{new.title} (v{new.version}) verified", body=remarks,
                   dedupe_key=f"doc{new.id}:verified", link="/compliance?tab=documents")
    else:
        if old:
            due = max(expiry_due(old), clock.today() + timedelta(days=rules.setting_int(db, "resubmit_days", 7)))
            inst = old.institution
            obl.open_obligation(db, kind="DOC_EXPIRY", title=f"Resubmit renewed {old.title} — {inst.name}",
                                subject_type="document", subject_id=old.id, due_at=clock.ist_close_of(due),
                                owner_role="INSTITUTION", institution_id=inst.id, region_id=inst.region_id, actor=actor,
                                source_reference=DOC_SOURCE.get(old.doc_type, ""))
        obl.notify(db, recipients=users, category="INFO", subject=f"{new.title} (v{new.version}) not accepted",
                   body=remarks, dedupe_key=f"doc{new.id}:rejected", link="/compliance?tab=documents")


def doc_status(doc: TrackedDocument, today: date) -> str:
    if doc.verification_status == "PENDING":
        return "AWAITING_VERIFICATION"
    if doc.verification_status == "REJECTED":
        return "REJECTED"
    if doc.superseded_by_id:
        return "SUPERSEDED"
    if doc.valid_until < today:
        return "EXPIRED"
    if doc.doc_type == "LAND_LEASE" and expiry_due(doc) < today:
        return "LEASE_REVIEW_REQUIRED"
    if (expiry_due(doc) - today).days <= 90:
        return "EXPIRING_SOON"
    return "VALID"


def sync_statuses(db: Session) -> int:
    changed = 0
    for u in db.scalars(select(Undertaking).where(Undertaking.status.in_(["OPEN", "REJECTED"]))):
        for ob in obl.open_for(db, "undertaking", u.id, ["UNDERTAKING"]):
            if ob.state == "OVERDUE" and ob.escalation_level >= 2 and u.status != "LAPSED":
                u.status = "LAPSED"
                audit.record(db, actor=None, action="UNDERTAKING_LAPSED", entity_type="undertaking", entity_id=u.id,
                             application_id=u.application_id, institution_id=u.institution_id,
                             reason="Unfulfilled beyond the final escalation level; flagged for the competent authority")
                changed += 1
    return changed
