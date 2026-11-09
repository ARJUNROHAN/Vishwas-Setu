"""API serializers. Timestamps are stored UTC and emitted as IST ISO strings (+05:30)."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import clock, compliance, rules, workflow
from .models import (
    Application, ApplicationDocument, AuditEvent, Deficiency, Escalation, EvcVisit, Notification, Obligation,
    StageInstance, TrackedDocument, Undertaking, User,
)


def iso(v):
    if isinstance(v, datetime):
        return clock.to_ist(v).replace(microsecond=0).isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return v


def user_brief(u: User | None):
    if not u:
        return None
    return {"id": u.id, "name": u.full_name, "role": u.role, "designation": u.designation,
            "region_id": u.region_id, "institution_id": u.institution_id}


def institution(i):
    return {"id": i.id, "permanent_id": i.permanent_id, "name": i.name, "city": i.city, "state": i.state,
            "region": i.region.name, "region_id": i.region_id, "type": i.institution_type, "is_new": i.is_new,
            "max_course_years": i.max_course_years, "land_tenure": i.land_tenure,
            "building_completion_date": iso(i.building_completion_date), "self_financing": i.self_financing}


def obligation(ob: Obligation, now: datetime | None = None):
    now = now or clock.now()
    return {"id": ob.id, "kind": ob.kind, "title": ob.title, "state": ob.state, "due_at": iso(ob.due_at),
            "opened_at": iso(ob.opened_at), "closed_at": iso(ob.closed_at), "close_reason": ob.close_reason,
            "days_left": round((ob.due_at - now).total_seconds() / 86400, 1), "escalation_level": ob.escalation_level,
            "owner_role": ob.owner_role, "owner": ob.owner_user.full_name if ob.owner_user else None,
            "application_id": ob.application_id, "institution_id": ob.institution_id,
            "institution": ob.institution.name if ob.institution else None, "region_id": ob.region_id,
            "subject_type": ob.subject_type, "subject_id": ob.subject_id, "source_reference": ob.source_reference,
            "was_overdue": ob.was_overdue}


def escalation(e: Escalation, now: datetime):
    return {"id": e.id, "level": e.level, "target_role": e.target_role, "created_at": iso(e.created_at),
            "acknowledged_at": iso(e.acknowledged_at), "ack_note": e.ack_note, "resolved_at": iso(e.resolved_at),
            "obligation": obligation(e.obligation, now)}


def stage(si: StageInstance):
    return {"id": si.id, "code": si.stage_code, "name": si.stage_name, "started_at": iso(si.started_at),
            "completed_at": iso(si.completed_at), "outcome": si.outcome, "remarks": si.remarks,
            "assignee": user_brief(si.assignee), "paused_days": si.paused_days}


def deficiency(d: Deficiency, users: dict):
    return {"id": d.id, "seq": d.seq, "stage_instance_id": d.stage_instance_id, "finding": d.finding,
            "reference": d.reference, "correction_requested": d.correction_requested, "status": d.status,
            "response_text": d.response_text, "response_file_ids": [f for f in (d.response_file_ids or []) if f],
            "responded_at": iso(d.responded_at), "verified_by": users.get(d.verified_by),
            "verified_at": iso(d.verified_at), "verify_remarks": d.verify_remarks, "created_at": iso(d.created_at)}


def application_row(app: Application, now: datetime, open_obs: list[Obligation] | None, labels: dict):
    si = workflow.current_instance(app)
    obs = open_obs or []
    worst = min(obs, key=lambda o: o.due_at, default=None)
    return {
        "id": app.id, "application_no": app.application_no, "type": app.application_type,
        "type_label": labels.get(app.application_type, app.application_type), "institution": app.institution.name,
        "institution_id": app.institution_id, "region": app.institution.region.name,
        "region_id": app.institution.region_id, "route": app.route.name, "route_code": app.route.code,
        "status": app.status, "stage": app.current_stage_code,
        "stage_name": si.stage_name if si else ("Decision" if app.status == "READY_FOR_DECISION" else None),
        "assignee": si.assignee.full_name if si and si.assignee else None,
        "assignee_id": si.assignee_id if si else None,
        "submitted_at": iso(app.submitted_at), "age_days": workflow.ageing_days(app, now),
        "stage_age_days": (now - si.started_at).days if si else None,
        "next_due_at": iso(worst.due_at) if worst else None, "next_due_state": worst.state if worst else None,
        "escalation_level": max((o.escalation_level for o in obs), default=0),
        "academic_year": app.academic_year, "processing_academic_year": app.processing_academic_year,
        "programme": app.programme, "recommendation": app.recommendation, "decision": app.decision,
        "ruleset": app.route.aph_version, "version": app.version,
    }


def application_detail(db: Session, app: Application, user: User, now: datetime):
    labels = rules.type_labels(db)
    obs = list(db.scalars(select(Obligation).where(Obligation.application_id == app.id).order_by(Obligation.opened_at)))
    open_obs = [o for o in obs if o.state != "CLOSED"]
    events = list(db.scalars(select(AuditEvent).where(AuditEvent.application_id == app.id).order_by(AuditEvent.seq)))
    visits = list(db.scalars(select(EvcVisit).where(EvcVisit.application_id == app.id).order_by(EvcVisit.id)))
    unds = list(db.scalars(select(Undertaking).where(Undertaking.application_id == app.id)))
    defs = list(db.scalars(select(Deficiency).where(Deficiency.application_id == app.id).order_by(Deficiency.id)))
    docs = list(db.scalars(select(ApplicationDocument).where(ApplicationDocument.application_id == app.id)
                           .order_by(ApplicationDocument.id)))
    users = {u.id: u.full_name for u in db.scalars(select(User))}
    t = rules.type_def(db, app.ruleset, app.application_type)
    si = workflow.current_instance(app)
    route_stages = [{"code": s.code, "name": s.name, "order": s.order, "sla_days": s.sla_days,
                     "conditional": s.conditional, "assignee_role": s.assignee_role, "on_deficiency": s.on_deficiency,
                     "managed_by": s.managed_by} for s in app.route.stages]
    revert_targets = []
    if si:
        cur = workflow.stage_def(app, si.stage_code)
        revert_targets = [s["code"] for s in route_stages if s["order"] < cur.order]
    assignable = []
    if si and workflow.stage_def(app, si.stage_code).managed_by == "rule_review":
        assignable = [{"code": r.code, "name": r.name, "source": r.aph_reference}
                      for r in rules_routes(db, app.ruleset_id)]
    return {
        **application_row(app, now, open_obs, labels),
        "institution_detail": institution(app.institution),
        "rule_trace": {"ruleset": f"{app.ruleset.code} v{app.ruleset.version}", "ruleset_status": app.ruleset.status,
                       "aph_edition": app.ruleset.aph_edition, "source_url": app.ruleset.source_url,
                       "chapter": t.chapter, "table_row": t.table_row, "category": t.label,
                       "notice_category": t.notice_category, "notice_verified": t.notice_verified, "note": t.note,
                       "route_source_type": app.route.source_type},
        "route_detail": {"name": app.route.name, "code": app.route.code, "aph_reference": app.route.aph_reference,
                         "aph_version": app.route.aph_version, "description": app.route.description,
                         "stages": route_stages},
        "stages": [stage(s) for s in app.stages],
        "deficiencies": [deficiency(d, users) for d in defs],
        "checklist": [{"id": d.id, "doc_code": d.doc_code, "label": d.label, "mandatory": d.mandatory,
                       "source": d.source, "file_id": d.file_id, "status": d.status} for d in docs],
        "obligations": [obligation(o, now) for o in obs],
        "audit": [audit_event(e) for e in events],
        "evc_visits": [evc_visit(v, users) for v in visits],
        "undertakings": [undertaking(u, now) for u in unds],
        "allowed_actions": workflow.allowed_actions(user, app),
        "revert_targets": revert_targets, "assignable_routes": assignable,
        "pending_next_stage": app.pending_next_stage,
        "summary": app.summary or workflow.build_case_summary(db, app),
        "decision_reason": app.decision_reason, "decision_ref": app.decision_ref,
        "decision_file_id": app.decision_file_id, "decided_at": iso(app.decided_at),
        "intake_requested": app.intake_requested, "parent_application_id": app.parent_application_id,
    }


def rules_routes(db, ruleset_id):
    from .models import RouteTemplate
    return [r for r in db.scalars(select(RouteTemplate).where(RouteTemplate.ruleset_id == ruleset_id))
            if r.code not in ("MANUAL_RULE_REVIEW", "APPEAL_SAC")]


def audit_event(e: AuditEvent):
    return {"seq": e.seq, "ts": iso(e.ts), "actor": e.actor_label, "action": e.action, "entity_type": e.entity_type,
            "entity_id": e.entity_id, "application_id": e.application_id, "institution_id": e.institution_id,
            "detail": e.detail, "reason": e.reason, "request_id": e.request_id, "hash": e.hash, "prev_hash": e.prev_hash}


def evc_visit(v: EvcVisit, users: dict | None = None):
    app = v.application
    return {"id": v.id, "application_id": app.id, "application_no": app.application_no,
            "institution": app.institution.name, "institution_state": app.institution.state,
            "region": app.institution.region.name, "type": app.application_type,
            "type_label": app.application_type.replace("_", " ").capitalize(), "status": v.status, "mode": v.mode,
            "panel": v.panel, "queued_at": iso(v.queued_at), "scheduled_on": iso(v.scheduled_on),
            "report_outcome": v.report_outcome, "report_remarks": v.report_remarks, "report_file_id": v.report_file_id,
            "report_submitted_by": (users or {}).get(v.report_submitted_by), "video_url": v.video_url,
            "video_minutes": v.video_minutes, "priority_new_institution": v.priority_new_institution}


def undertaking(u: Undertaking, now: datetime, open_obs: list[Obligation] | None = None):
    return {"id": u.id, "institution": u.institution.name, "institution_id": u.institution_id,
            "region": u.institution.region.name, "application_id": u.application_id, "kind": u.kind, "title": u.title,
            "condition_text": u.condition_text, "aph_reference": u.aph_reference, "source_document": u.source_document,
            "due_on": iso(u.due_on), "days_left": (u.due_on - clock.to_ist(now).date()).days, "status": u.status,
            "evidence_file_ids": [f for f in (u.evidence_file_ids or []) if f], "remarks": u.remarks,
            "created_at": iso(u.created_at), "was_late": u.was_late,
            "escalation_level": max((o.escalation_level for o in (open_obs or [])), default=0)}


def document(db: Session, d: TrackedDocument, today: date, open_obs: list[Obligation] | None = None):
    due = compliance.expiry_due(d)
    out = {"id": d.id, "institution": d.institution.name, "institution_id": d.institution_id,
           "region": d.institution.region.name, "doc_type": d.doc_type, "title": d.title, "version": d.version,
           "issuer_name": d.issuer_name, "reference_no": d.reference_no, "valid_from": iso(d.valid_from),
           "valid_until": iso(d.valid_until), "renew_by": iso(due), "days_to_renew_by": (due - today).days,
           "verification_status": d.verification_status, "status": compliance.doc_status(d, today),
           "file_id": d.file_id, "remarks": d.remarks, "superseded_by_id": d.superseded_by_id,
           "source": compliance.DOC_SOURCE.get(d.doc_type, ""),
           "escalation_level": max((o.escalation_level for o in (open_obs or [])), default=0)}
    if d.doc_type == "LAND_LEASE":
        out["checks"] = compliance.lease_checks(d.valid_from, d.valid_until, today, d.institution.max_course_years, db)
    elif d.doc_type == "STABILITY_CERT":
        out["checks"] = compliance.stability_checks(d.valid_from, d.valid_until, db)
    return out


def notification(n: Notification):
    return {"id": n.id, "category": n.category, "subject": n.subject, "body": n.body, "created_at": iso(n.created_at),
            "read": n.read_at is not None, "link": n.link, "channel": n.channel, "status": n.status,
            "dedupe_key": n.dedupe_key}
