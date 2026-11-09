"""Workflow engine.

Applications are routed by their category under the ruleset pinned at submission (Table 2.3 for
Chapter II, Chapter I for new institutions, the Regulations for Council-initiated cases, manual
review for unmapped categories). Every transition is an authorised human action, except moving a
case into the next prescribed queue once its owner has completed a stage. Nothing here grants
or rejects an approval on its own.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import audit, clock, obligations as obl, rules
from .errors import Forbidden, Invalid, WorkflowError
from .models import (
    Application, ApplicationDocument, Deficiency, EvcVisit, Institution, Obligation, StageDefinition,
    StageInstance, User,
)

GLOBAL_ROLES = ("BUREAU", "COMPETENT_AUTHORITY", "RULE_ADMIN", "SAC_MEMBER", "ADMIN")
ITEMISED_STAGES = ("SCRUTINY", "SELF_DISCLOSURE")


# --------------------------------------------------------------------------- helpers
def stage_def(app: Application, code: str) -> StageDefinition:
    for s in app.route.stages:
        if s.code == code:
            return s
    raise WorkflowError(f"Stage {code} is not part of route {app.route.name}")


def current_instance(app: Application) -> StageInstance | None:
    for si in reversed(app.stages):
        if si.completed_at is None:
            return si
    return None


def _next_regular_stage(app: Application, after: StageDefinition) -> StageDefinition | None:
    for s in app.route.stages:
        if s.order > after.order and not s.conditional:
            return s
    return None


def _least_loaded(db: Session, role: str, region_id: int) -> User | None:
    q = select(User).where(User.role == role, User.active.is_(True))
    candidates = list(db.scalars(q.where(User.region_id == region_id))) or list(db.scalars(q.where(User.region_id.is_(None))))
    if not candidates:
        return None
    load = dict(db.execute(select(StageInstance.assignee_id, func.count()).where(StageInstance.completed_at.is_(None))
                           .group_by(StageInstance.assignee_id)).all())
    return min(candidates, key=lambda u: (load.get(u.id, 0), u.id))


def _region(app: Application) -> int:
    return app.institution.region_id


def _require(cond: bool, msg: str, err=WorkflowError):
    if not cond:
        raise err(msg)


def open_deficiencies(db: Session, app: Application) -> list[Deficiency]:
    return list(db.scalars(select(Deficiency).where(Deficiency.application_id == app.id,
                                                    Deficiency.status.in_(["OPEN", "RESPONDED"]))
                           .order_by(Deficiency.seq)))


# --------------------------------------------------------------------------- submission
def submit_application(db: Session, *, institution: Institution, application_type: str, academic_year: str,
                       actor: User | None, programme: str = "", intake_requested: int | None = None,
                       parent_application_id: int | None = None, documents: dict[str, int] | None = None,
                       enforce_checklist: bool = True, initiated_by: str = "INSTITUTION") -> Application:
    rs = rules.active_ruleset(db)
    t = rules.type_def(db, rs, application_type)
    _require(t.initiated_by == initiated_by,
             f"'{t.label}' is initiated by {t.initiated_by.lower()}, not by {initiated_by.lower()}", Forbidden)
    processing_year = rules.assign_academic_year(db, t, academic_year, clock.today())
    checklist = rules.checklist_for(db, rs.id, t, institution, clock.today())
    documents = documents or {}
    missing = [c["label"] for c in checklist if c["mandatory"] and not documents.get(c["doc_code"])]
    if enforce_checklist and missing:
        raise Invalid("Mandatory documents missing: " + "; ".join(missing))
    route = rules.route(db, rs.id, t.route_code)
    seq = (db.scalar(select(func.count(Application.id))) or 0) + 1
    app = Application(application_no=f"1-{46300000000 + seq * 7919}", institution_id=institution.id,
                      application_type=application_type, academic_year=academic_year,
                      processing_academic_year=processing_year, ruleset_id=rs.id, route_id=route.id,
                      status="IN_PROGRESS", submitted_at=clock.now(), programme=programme,
                      intake_requested=intake_requested, parent_application_id=parent_application_id)
    db.add(app)
    db.flush()
    db.refresh(app)
    for c in checklist:
        fid = documents.get(c["doc_code"])
        db.add(ApplicationDocument(application_id=app.id, doc_code=c["doc_code"], label=c["label"],
                                   mandatory=c["mandatory"], source=c["source"], file_id=fid or None,
                                   status="UPLOADED" if (fid or not enforce_checklist) else "MISSING"))
    audit.record(db, actor=actor, action="APPLICATION_SUBMITTED", entity_type="application", entity_id=app.id,
                 application_id=app.id, institution_id=institution.id,
                 detail={"type": application_type, "table_2_3_row": t.table_row, "chapter": t.chapter,
                         "route": route.name, "route_source": route.aph_reference,
                         "ruleset": f"{rs.code} v{rs.version}", "academic_year": academic_year,
                         "processing_academic_year": processing_year, "notice_category": t.notice_category,
                         "checklist_items": len(checklist)})
    audit.record(db, actor=None, action="ROUTED", entity_type="application", entity_id=app.id,
                 application_id=app.id, institution_id=institution.id,
                 detail={"route_code": route.code, "stages": [s.code for s in route.stages],
                         "source": route.aph_reference, "ruleset": f"{rs.code} v{rs.version}"},
                 reason=f"Category '{t.label}' resolves to '{route.name}' under the pinned ruleset")
    first = next((s for s in route.stages if not s.conditional), None)
    start_stage(db, app, first, actor=None)
    return app


def start_stage(db: Session, app: Application, sd: StageDefinition, actor: User | None) -> StageInstance:
    assignee = _least_loaded(db, sd.assignee_role, _region(app))
    si = StageInstance(application_id=app.id, stage_code=sd.code, stage_name=sd.name,
                       assignee_id=assignee.id if assignee else None, started_at=clock.now())
    db.add(si)
    app.current_stage_code = sd.code
    app.status = "IN_PROGRESS"
    db.flush()
    audit.record(db, actor=actor, action="STAGE_STARTED", entity_type="stage", entity_id=si.id,
                 application_id=app.id, institution_id=app.institution_id,
                 detail={"stage": sd.code, "assignee": assignee.full_name if assignee else None,
                         "time_limit_days": sd.sla_days})
    if sd.managed_by == "evc":
        _queue_evc(db, app, si, sd)
    else:
        obl.open_obligation(db, kind="RULE_REVIEW" if sd.managed_by == "rule_review" else "STAGE_SLA",
                            title=f"{sd.name}: {app.application_no} ({app.institution.name})",
                            subject_type="stage", subject_id=si.id,
                            due_at=clock.due_after_days(si.started_at, sd.sla_days), owner_role=sd.assignee_role,
                            owner_user_id=si.assignee_id, application_id=app.id, institution_id=app.institution_id,
                            region_id=_region(app), source_reference="Time limit: prototype default (DESIGN)")
    return si


def _queue_evc(db: Session, app: Application, si: StageInstance, sd: StageDefinition) -> None:
    is_new = app.institution.is_new or app.application_type == "NEW_INSTITUTION"
    visit = EvcVisit(application_id=app.id, stage_instance_id=si.id, queued_at=clock.now(), status="QUEUED",
                     priority_new_institution=is_new)
    db.add(visit)
    db.flush()
    days = rules.setting_int(db, "evc_schedule_days_new", 10) if is_new else sd.sla_days
    audit.record(db, actor=None, action="EVC_QUEUED", entity_type="evc_visit", entity_id=visit.id,
                 application_id=app.id, institution_id=app.institution_id,
                 detail={"priority_new_institution": is_new, "schedule_within_days": days})
    obl.open_obligation(db, kind="EVC_SCHEDULE", title=f"Schedule EVC: {app.application_no} ({app.institution.name})",
                        subject_type="evc_visit", subject_id=visit.id, due_at=clock.due_after_days(clock.now(), days),
                        owner_role="EVC_COORDINATOR", owner_user_id=si.assignee_id, application_id=app.id,
                        institution_id=app.institution_id, region_id=_region(app),
                        source_reference="Time limit: prototype default (DESIGN); APH sets no single EVC SLA")


# --------------------------------------------------------------------------- permissions
def _in_scope(user: User, app: Application) -> bool:
    return user.role in GLOBAL_ROLES or user.region_id == app.institution.region_id


def can_act(user: User, app: Application, managed_by: tuple[str, ...] = ("officer",)) -> bool:
    si = current_instance(app)
    if not si or app.status != "IN_PROGRESS":
        return False
    sd = stage_def(app, si.stage_code)
    if sd.managed_by not in managed_by or user.role != sd.assignee_role or not _in_scope(user, app):
        return False
    return si.assignee_id in (None, user.id)


def allowed_actions(user: User, app: Application) -> list[str]:
    acts: list[str] = []
    if can_act(user, app):
        acts += ["record_nil_deficiency", "record_deficiency", "return_for_clarification"]
    if can_act(user, app, ("deficiency_review",)):
        acts.append("verify_deficiencies")
    if can_act(user, app, ("rule_review",)):
        acts.append("assign_route")
    si = current_instance(app)
    if si and app.status in ("IN_PROGRESS", "RETURNED") and user.role in ("REGIONAL_HEAD", "BUREAU") and _in_scope(user, app):
        acts += ["revert", "reassign"]
    if app.status == "RETURNED" and user.role == "INSTITUTION" and user.institution_id == app.institution_id:
        acts.append("respond")
    if app.status == "READY_FOR_DECISION" and user.role == "COMPETENT_AUTHORITY":
        acts += ["approve", "reject"]
    if (app.status == "REJECTED" and user.role == "INSTITUTION" and user.institution_id == app.institution_id
            and app.application_type != "APPEAL"):
        acts.append("appeal")
    return acts


# --------------------------------------------------------------------------- stage outcomes
def record_outcome(db: Session, app: Application, actor: User, outcome: str, remarks: str,
                   deficiencies: list[dict] | None = None, via_evc: bool = False) -> None:
    _require(outcome in ("NIL_DEFICIENCY", "DEFICIENCY"), "Outcome must be NIL_DEFICIENCY or DEFICIENCY", Invalid)
    _require(via_evc or can_act(actor, app), "Only the officer assigned to this stage can record its outcome", Forbidden)
    _require(bool(remarks and remarks.strip()), "Remarks are mandatory", Invalid)
    si = current_instance(app)
    sd = stage_def(app, si.stage_code)
    items = [d for d in (deficiencies or []) if (d.get("finding") or "").strip()]
    if outcome == "DEFICIENCY" and sd.code in ITEMISED_STAGES:
        _require(bool(items), "Record each deficiency as a separate item (finding, reference, correction requested)", Invalid)
    _close_stage(db, app, si, actor, outcome, remarks)
    if outcome == "DEFICIENCY" and items:
        for n, d in enumerate(items, start=1):
            db.add(Deficiency(application_id=app.id, stage_instance_id=si.id, seq=n, finding=d["finding"].strip(),
                              reference=(d.get("reference") or "").strip(),
                              correction_requested=(d.get("correction") or "").strip(), status="OPEN",
                              created_at=clock.now()))
        audit.record(db, actor=actor, action="DEFICIENCIES_RECORDED", entity_type="stage", entity_id=si.id,
                     application_id=app.id, institution_id=app.institution_id,
                     detail={"count": len(items), "findings": [d["finding"][:80] for d in items]}, reason=remarks)
        db.flush()
    _route_after(db, app, sd, outcome, remarks, actor)


def _close_stage(db, app, si, actor, outcome, remarks):
    si.completed_at, si.outcome, si.remarks = clock.now(), outcome, remarks
    for ob in obl.open_for(db, "stage", si.id):
        obl.close_obligation(db, ob, f"Stage outcome recorded: {outcome}", actor)
    audit.record(db, actor=actor, action="STAGE_COMPLETED", entity_type="stage", entity_id=si.id,
                 application_id=app.id, institution_id=app.institution_id,
                 detail={"stage": si.stage_code, "outcome": outcome}, reason=remarks)


def _route_after(db, app, sd, outcome, remarks, actor):
    if outcome == "NIL_DEFICIENCY":
        nxt = _next_regular_stage(app, sd)
        if nxt:
            _auto_advance(db, app, nxt, sd)
        else:
            _ready_for_decision(db, app, "RECOMMENDED")
        return
    rule = sd.on_deficiency or "RETURN"
    if rule == "RETURN":
        _return(db, app, actor, remarks, then_stage=sd.code)
    elif rule.startswith("RETURN_THEN:"):
        _return(db, app, actor, remarks, then_stage=rule.split(":", 1)[1])
    elif rule.startswith("GOTO:"):
        _auto_advance(db, app, stage_def(app, rule.split(":", 1)[1]), sd)
    elif rule == "TO_DECISION":
        _ready_for_decision(db, app, "NOT_RECOMMENDED")
    else:
        raise WorkflowError(f"Unknown deficiency rule {rule}")


def _auto_advance(db, app, nxt, frm):
    audit.record(db, actor=None, action="AUTO_ADVANCED", entity_type="application", entity_id=app.id,
                 application_id=app.id, institution_id=app.institution_id, detail={"from": frm.code, "to": nxt.code},
                 reason="Preceding stage completed by its owner; moved to the next prescribed queue")
    start_stage(db, app, nxt, actor=None)


def _ready_for_decision(db, app, recommendation):
    app.status, app.current_stage_code, app.recommendation = "READY_FOR_DECISION", "DECISION", recommendation
    app.summary = build_case_summary(db, app)
    audit.record(db, actor=None, action="READY_FOR_DECISION", entity_type="application", entity_id=app.id,
                 application_id=app.id, institution_id=app.institution_id, detail={"recommendation": recommendation})
    obl.open_obligation(db, kind="DECISION", title=f"Decision pending: {app.application_no} ({app.institution.name})",
                        subject_type="application", subject_id=app.id,
                        due_at=clock.due_after_days(clock.now(), rules.setting_int(db, "decision_days", 7)),
                        owner_role="COMPETENT_AUTHORITY", application_id=app.id, institution_id=app.institution_id,
                        region_id=_region(app), source_reference="Time limit: prototype default (DESIGN)")


def _return(db, app, actor, reason, then_stage):
    app.status, app.pending_next_stage = "RETURNED", then_stage
    days = rules.setting_int(db, "institution_compliance_days", 7)
    audit.record(db, actor=actor, action="RETURNED_TO_INSTITUTION", entity_type="application", entity_id=app.id,
                 application_id=app.id, institution_id=app.institution_id,
                 detail={"resume_at_stage": then_stage, "reply_within_days": days}, reason=reason)
    obl.open_obligation(db, kind="INSTITUTION_COMPLIANCE", title=f"Reply to deficiencies on {app.application_no}",
                        subject_type="application", subject_id=app.id, due_at=clock.due_after_days(clock.now(), days),
                        owner_role="INSTITUTION", application_id=app.id, institution_id=app.institution_id,
                        region_id=_region(app), source_reference="APH cl. 1.8 (deficiency communication); time limit DESIGN")


def return_for_clarification(db: Session, app: Application, actor: User, reason: str) -> None:
    _require(can_act(actor, app), "Only the officer assigned to this stage can return it", Forbidden)
    _require(bool(reason and reason.strip()), "A reason is mandatory", Invalid)
    si = current_instance(app)
    for ob in obl.open_for(db, "stage", si.id):
        obl.pause(db, ob, "Returned to institution for clarification", actor)
    app.status, app.pending_next_stage = "RETURNED", None
    days = rules.setting_int(db, "institution_compliance_days", 7)
    audit.record(db, actor=actor, action="RETURNED_FOR_CLARIFICATION", entity_type="application", entity_id=app.id,
                 application_id=app.id, institution_id=app.institution_id, detail={"stage": si.stage_code}, reason=reason)
    obl.open_obligation(db, kind="INSTITUTION_COMPLIANCE", title=f"Reply to clarification on {app.application_no}",
                        subject_type="application", subject_id=app.id, due_at=clock.due_after_days(clock.now(), days),
                        owner_role="INSTITUTION", application_id=app.id, institution_id=app.institution_id,
                        region_id=_region(app), source_reference="Time limit: prototype default (DESIGN)")


def institution_respond(db: Session, app: Application, actor: User, remarks: str, file_ids: list[int] | None = None,
                        item_responses: dict | None = None) -> None:
    _require(app.status == "RETURNED", "Application is not awaiting the institution")
    _require(actor.role == "INSTITUTION" and actor.institution_id == app.institution_id,
             "Only the applicant institution can respond", Forbidden)
    _require(bool(remarks and remarks.strip()), "Please describe the compliance submitted", Invalid)
    items = [d for d in open_deficiencies(db, app) if d.status == "OPEN"]
    item_responses = {int(k): v for k, v in (item_responses or {}).items()}
    if items:
        missing = [d.seq for d in items if not (item_responses.get(d.id, {}).get("response") or "").strip()]
        _require(not missing, f"Respond to every recorded deficiency (missing item(s) {missing})", Invalid)
        for d in items:
            r = item_responses[d.id]
            d.status, d.response_text = "RESPONDED", r["response"].strip()
            d.response_file_ids, d.responded_at = list(r.get("file_ids") or []), clock.now()
    for ob in obl.open_for(db, "application", app.id, ["INSTITUTION_COMPLIANCE"]):
        obl.close_obligation(db, ob, "Institution submitted compliance", actor)
    audit.record(db, actor=actor, action="INSTITUTION_RESPONDED", entity_type="application", entity_id=app.id,
                 application_id=app.id, institution_id=app.institution_id,
                 detail={"files": file_ids or [], "items_answered": [d.seq for d in items]}, reason=remarks)
    if app.pending_next_stage:
        target = stage_def(app, app.pending_next_stage)
        app.pending_next_stage = None
        start_stage(db, app, target, actor=None)
    else:
        si = current_instance(app)
        app.status = "IN_PROGRESS"
        for ob in obl.open_for(db, "stage", si.id):
            si.paused_days += obl.resume(db, ob, actor)


def verify_deficiencies(db: Session, app: Application, actor: User, verdicts: dict, remarks: str) -> None:
    """Re-scrutiny: verify ONLY the deficiencies recorded by scrutiny (APH cl. 1.8)."""
    _require(can_act(actor, app, ("deficiency_review",)), "Only the assigned re-scrutiny officer can verify", Forbidden)
    _require(bool(remarks and remarks.strip()), "Remarks are mandatory", Invalid)
    items = [d for d in open_deficiencies(db, app) if d.status == "RESPONDED"]
    _require(bool(items), "There are no responded deficiencies to verify")
    verdicts = {int(k): v for k, v in (verdicts or {}).items()}
    extra = set(verdicts) - {d.id for d in items}
    _require(not extra, "Re-scrutiny may verify only the deficiencies recorded by scrutiny", Invalid)
    missing = [d.seq for d in items if d.id not in verdicts]
    _require(not missing, f"Give a verdict on every recorded deficiency (missing item(s) {missing})", Invalid)
    for d in items:
        v = verdicts[d.id]
        d.status = "RESOLVED" if v.get("resolved") else "NOT_RESOLVED"
        d.verified_by, d.verified_at, d.verify_remarks = actor.id, clock.now(), (v.get("remarks") or "").strip()
    unresolved = [d.seq for d in items if d.status == "NOT_RESOLVED"]
    si = current_instance(app)
    sd = stage_def(app, si.stage_code)
    outcome = "DEFICIENCY" if unresolved else "NIL_DEFICIENCY"
    audit.record(db, actor=actor, action="DEFICIENCIES_VERIFIED", entity_type="stage", entity_id=si.id,
                 application_id=app.id, institution_id=app.institution_id,
                 detail={"resolved": [d.seq for d in items if d.status == "RESOLVED"], "not_resolved": unresolved},
                 reason=remarks)
    _close_stage(db, app, si, actor, outcome, remarks)
    _route_after(db, app, sd, outcome, remarks, actor)


def assign_route(db: Session, app: Application, actor: User, route_code: str, reason: str) -> None:
    """Manual rule review: the rule administrator assigns the route for an unmapped category."""
    _require(can_act(actor, app, ("rule_review",)), "Only the assigned rule administrator can assign a route", Forbidden)
    _require(bool(reason and reason.strip()), "Cite the clause / notification relied on", Invalid)
    _require(route_code not in ("MANUAL_RULE_REVIEW", "APPEAL_SAC"), "Choose a processing route", Invalid)
    new_route = rules.route(db, app.ruleset_id, route_code)
    si = current_instance(app)
    _close_stage(db, app, si, actor, "ROUTE_ASSIGNED", reason)
    app.route_id = new_route.id
    db.flush()
    db.refresh(app)
    audit.record(db, actor=actor, action="ROUTE_ASSIGNED", entity_type="application", entity_id=app.id,
                 application_id=app.id, institution_id=app.institution_id,
                 detail={"route": new_route.name, "source": new_route.aph_reference}, reason=reason)
    start_stage(db, app, next(s for s in new_route.stages if not s.conditional), actor)


def revert(db: Session, app: Application, actor: User, target_code: str, reason: str) -> None:
    _require("revert" in allowed_actions(actor, app), "You are not authorised to revert this application", Forbidden)
    _require(bool(reason and reason.strip()), "A reason is mandatory", Invalid)
    si = current_instance(app)
    cur, target = stage_def(app, si.stage_code), stage_def(app, target_code)
    _require(target.order < cur.order, "Can only revert to an earlier stage")
    si.completed_at, si.outcome, si.remarks = clock.now(), "REVERTED", reason
    for ob in obl.open_for(db, "stage", si.id) + obl.open_for(db, "application", app.id, ["INSTITUTION_COMPLIANCE"]):
        obl.close_obligation(db, ob, "Reverted to earlier stage", actor)
    for v in db.scalars(select(EvcVisit).where(EvcVisit.stage_instance_id == si.id)):
        for ob in obl.open_for(db, "evc_visit", v.id):
            obl.close_obligation(db, ob, "Reverted to earlier stage", actor)
    audit.record(db, actor=actor, action="REVERTED", entity_type="application", entity_id=app.id,
                 application_id=app.id, institution_id=app.institution_id,
                 detail={"from": cur.code, "to": target.code}, reason=reason)
    app.pending_next_stage = None
    start_stage(db, app, target, actor)


def reassign(db: Session, app: Application, actor: User, user_id: int, reason: str) -> None:
    _require("reassign" in allowed_actions(actor, app), "You are not authorised to reassign", Forbidden)
    _require(bool(reason and reason.strip()), "A reason is mandatory", Invalid)
    si = current_instance(app)
    new = db.get(User, user_id)
    sd = stage_def(app, si.stage_code)
    _require(new is not None and new.role == sd.assignee_role and (new.region_id in (None, app.institution.region_id)),
             "Assignee must hold the stage role for this Region", Invalid)
    old = si.assignee.full_name if si.assignee else None
    si.assignee_id = new.id
    for ob in db.scalars(select(Obligation).where(Obligation.state != "CLOSED", Obligation.application_id == app.id,
                                                  Obligation.subject_type.in_(["stage", "evc_visit"]))):
        ob.owner_user_id = new.id
    audit.record(db, actor=actor, action="REASSIGNED", entity_type="stage", entity_id=si.id, application_id=app.id,
                 institution_id=app.institution_id, detail={"from": old, "to": new.full_name}, reason=reason)


# --------------------------------------------------------------------------- decision & appeal
def decide(db: Session, app: Application, actor: User, decision: str, reason: str,
           decision_ref: str = "", file_id: int | None = None) -> None:
    """Recorded by the competent authority only. The system recommendation is shown, never applied."""
    from . import compliance

    _require(app.status == "READY_FOR_DECISION", "Application is not ready for a decision")
    _require(actor.role == "COMPETENT_AUTHORITY", "Only the competent authority can record a decision", Forbidden)
    _require(decision in ("APPROVED", "REJECTED"), "Decision must be APPROVED or REJECTED", Invalid)
    _require(bool(reason and reason.strip()), "Reasons are mandatory for every decision", Invalid)
    _require(bool(decision_ref and decision_ref.strip()), "Enter the order / letter reference number", Invalid)
    app.status, app.decision, app.decision_reason = decision, decision, reason
    app.decision_ref, app.decision_file_id = decision_ref.strip(), file_id
    app.decided_at, app.current_stage_code = clock.now(), None
    for ob in obl.open_for(db, "application", app.id, ["DECISION"]):
        obl.close_obligation(db, ob, f"Decision recorded: {decision}", actor)
    chapter_i = app.application_type == "NEW_INSTITUTION"
    letter = ("Letter of Approval (LoA)" if decision == "APPROVED" else "Letter of Denial (LoD)") if chapter_i else \
        ("Approval order" if decision == "APPROVED" else "EC decision (not approved)")
    audit.record(db, actor=actor, action="DECISION_RECORDED", entity_type="application", entity_id=app.id,
                 application_id=app.id, institution_id=app.institution_id,
                 detail={"decision": decision, "letter": letter, "decision_ref": app.decision_ref,
                         "order_file_id": file_id, "committee_recommendation": app.recommendation}, reason=reason)
    inst_users = obl.users_for_role(db, "INSTITUTION", None, app.institution_id)
    if decision == "APPROVED":
        obl.notify(db, recipients=inst_users, category="INFO", subject=f"{letter} issued for {app.application_no}",
                   body=f"Ref {app.decision_ref}. Reasons: {reason}", dedupe_key=f"app{app.id}:decision",
                   link=f"/applications/{app.id}")
        compliance.create_undertakings_for_approval(db, app, actor)
    else:
        days = rules.setting_int(db, "appeal_window_days", 7)
        src = ("APH cl. 1.11(a): within 7 days from issue of the LoD" if chapter_i
               else "APH cl. 2.24(a): within 7 days after upload of the EC decision")
        obl.notify(db, recipients=inst_users, category="INFO", subject=f"{letter}: {app.application_no}",
                   body=f"Ref {app.decision_ref}. Reasons: {reason}. One appeal may be filed within {days} days ({src}).",
                   dedupe_key=f"app{app.id}:decision", link=f"/applications/{app.id}")
        if app.application_type != "APPEAL":
            obl.open_obligation(db, kind="APPEAL_WINDOW", title=f"Appeal window for {app.application_no}",
                                subject_type="application", subject_id=app.id,
                                due_at=app.decided_at + timedelta(days=days), owner_role="INSTITUTION",
                                application_id=app.id, institution_id=app.institution_id, region_id=_region(app),
                                source_reference=src)


def file_appeal(db: Session, app: Application, actor: User, grounds: str) -> Application:
    _require("appeal" in allowed_actions(actor, app), "Appeal not available for this application", Forbidden)
    window = obl.open_for(db, "application", app.id, ["APPEAL_WINDOW"])
    _require(bool(window) and clock.now() <= window[0].due_at, "The appeal window has closed")
    _require(bool(grounds and grounds.strip()), "Grounds of appeal are mandatory", Invalid)
    prior = db.scalars(select(Application).where(Application.parent_application_id == app.id)).first()
    _require(prior is None, "Only one appeal is permitted")
    for ob in window:
        obl.close_obligation(db, ob, "Appeal filed", actor)
    appeal = submit_application(db, institution=app.institution, application_type="APPEAL",
                                academic_year=app.academic_year, actor=actor, programme=app.programme,
                                parent_application_id=app.id, enforce_checklist=False, initiated_by="APPEAL")
    appeal.summary = f"Appeal against {app.application_no}. Grounds: {grounds}"
    app.status = "UNDER_APPEAL"
    audit.record(db, actor=actor, action="APPEAL_FILED", entity_type="application", entity_id=app.id,
                 application_id=app.id, institution_id=app.institution_id,
                 detail={"appeal_application_id": appeal.id}, reason=grounds)
    return appeal


def build_case_summary(db: Session, app: Application) -> str:
    labels = rules.type_labels(db)
    lines = [f"Application {app.application_no} — {labels.get(app.application_type, app.application_type)}",
             f"Institution: {app.institution.name} ({app.institution.region.name} Region)",
             f"Route: {app.route.name} — {app.route.aph_reference} ({app.route.aph_version})",
             f"Processing academic year: {app.processing_academic_year}"]
    if app.programme:
        lines.append(f"Programme: {app.programme}" + (f", intake sought {app.intake_requested}" if app.intake_requested else ""))
    for si in app.stages:
        if si.completed_at:
            lines.append(f"• {si.stage_name}: {si.outcome or '-'} on {clock.to_ist(si.completed_at):%d %b %Y}"
                         + (f" — {si.remarks}" if si.remarks else ""))
    defs = list(db.scalars(select(Deficiency).where(Deficiency.application_id == app.id).order_by(Deficiency.id)))
    if defs:
        lines.append(f"Deficiencies recorded: {len(defs)}; resolved: {sum(d.status == 'RESOLVED' for d in defs)}")
    lines.append("System-generated and advisory; it does not replace the competent authority's examination.")
    return "\n".join(lines)


def ageing_days(app: Application, now: datetime) -> int:
    return max(0, (now - app.submitted_at).days)
