"""REST API (blueprint §13). Illegal transition → 409, missing permission → 403, invalid input → 422."""
from __future__ import annotations

import csv
import hashlib
import io
import os
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from . import audit, clock, compliance, evc, obligations as obl, rules, serializers as ser, workflow
from .auth import OFFICIAL_ROLES, ROLES, check_password, current_user, issue_token, require
from .db import get_db
from .errors import WorkflowError
from .models import (
    AcademicCalendar, Application, ApplicationDocument, ApplicationTypeDef, AuditEvent, DocumentRequirement,
    Escalation, EscalationPolicy, EvcVisit, FileObject, Institution, Notification, Obligation, Region, RouteTemplate,
    Ruleset, Setting, StageDefinition, TrackedDocument, Undertaking, User,
)

router = APIRouter()
STORAGE = Path(os.environ.get("STORAGE_DIR", Path(__file__).resolve().parent.parent / "storage"))
ALLOWED_EXT = {".pdf", ".jpg", ".jpeg", ".png"}
MAX_UPLOAD = 10 * 1024 * 1024
DEMO_MODE = os.environ.get("DEMO_MODE", "1") == "1"
GLOBAL = ("BUREAU", "ADMIN", "COMPETENT_AUTHORITY", "RULE_ADMIN", "SAC_MEMBER")


def _fail(e: WorkflowError):
    raise HTTPException(e.status, str(e))


def run(db: Session, fn, *a, **kw):
    try:
        out = fn(*a, **kw)
    except WorkflowError as e:
        db.rollback()
        _fail(e)
    db.commit()
    return out


# --------------------------------------------------------------------------- scoping
def scoped_apps(user: User):
    q = select(Application).join(Institution)
    if user.role == "INSTITUTION":
        q = q.where(Application.institution_id == user.institution_id)
    elif user.role == "EVC_MEMBER":
        ids = select(EvcVisit.application_id)
        q = q.where(Application.id.in_(ids))
    elif user.role not in GLOBAL:
        q = q.where(Institution.region_id == user.region_id)
    return q


def get_app_for(db: Session, user: User, app_id: int) -> Application:
    app = db.scalars(scoped_apps(user).where(Application.id == app_id)).first()
    if user.role == "EVC_MEMBER" and app:
        if not any(user.expert_id in {p["id"] for p in (v.panel or [])}
                   for v in db.scalars(select(EvcVisit).where(EvcVisit.application_id == app.id))):
            app = None
    if not app:
        raise HTTPException(404, "Application not found")
    return app


def _open_obs_by(db: Session, subject_type: str) -> dict[int, list[Obligation]]:
    out: dict[int, list[Obligation]] = defaultdict(list)
    for ob in db.scalars(select(Obligation).where(Obligation.state != "CLOSED", Obligation.subject_type == subject_type)):
        out[ob.subject_id].append(ob)
    return out


def _inst_scope(user: User, model):
    if user.role == "INSTITUTION":
        return [model.institution_id == user.institution_id]
    if user.role in GLOBAL:
        return []
    return [model.institution_id.in_(select(Institution.id).where(Institution.region_id == user.region_id))]


# --------------------------------------------------------------------------- auth & meta
class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalars(select(User).where(User.username == body.username)).first()
    if not user or not check_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid username or password")
    audit.record(db, actor=user, action="LOGIN", entity_type="user", entity_id=user.id)
    db.commit()
    return {"token": issue_token(user), "user": me_payload(db, user)}


def me_payload(db: Session, user: User):
    inst = db.get(Institution, user.institution_id) if user.institution_id else None
    region = db.get(Region, user.region_id) if user.region_id else None
    return {**ser.user_brief(user), "username": user.username, "email": user.email, "role_label": ROLES.get(user.role),
            "region": region.name if region else None, "institution": inst.name if inst else None,
            "expert_id": user.expert_id}


@router.get("/auth/me")
@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return me_payload(db, user)


@router.get("/demo/users")
def demo_users(db: Session = Depends(get_db)):
    if not DEMO_MODE:
        raise HTTPException(404)
    order = list(ROLES)
    users = list(db.scalars(select(User).where(User.role.notin_(["INSTITUTION", "EVC_MEMBER"]))))
    users += list(db.scalars(select(User).where(User.role == "EVC_MEMBER").limit(3)))
    demo = list(db.scalars(select(User).join(Institution, User.institution_id == Institution.id)
                           .where(Institution.name.like("%Demo%"))))
    users += demo + list(db.scalars(select(User).where(User.role == "INSTITUTION").limit(2)))
    users.sort(key=lambda u: (order.index(u.role), u.region_id or 0, u.id))
    return [{"username": u.username, "name": u.full_name, "role": u.role, "role_label": ROLES[u.role],
             "designation": u.designation, "region": u.region.name if u.region else "All India"} for u in users]


@router.get("/meta")
def meta(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return {"application_types": rules.type_labels(db), "roles": ROLES,
            "regions": [{"id": r.id, "name": r.name, "office_city": r.office_city} for r in db.scalars(select(Region))],
            "doc_types": compliance.DOC_TYPES}


@router.get("/application-types")
def application_types(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rs = rules.active_ruleset(db)
    inst = db.get(Institution, user.institution_id) if user.institution_id else None
    out = []
    for t in db.scalars(select(ApplicationTypeDef).where(ApplicationTypeDef.ruleset_id == rs.id).order_by(ApplicationTypeDef.id)):
        r = rules.route(db, rs.id, t.route_code)
        row = {"code": t.code, "label": t.label, "chapter": t.chapter, "table_row": t.table_row,
               "initiated_by": t.initiated_by, "notice_category": t.notice_category, "notice_verified": t.notice_verified,
               "note": t.note, "route": {"code": r.code, "name": r.name, "source": r.aph_reference,
                                         "stages": [{"code": s.code, "name": s.name, "conditional": s.conditional}
                                                    for s in r.stages]}}
        if inst:
            row["checklist"] = rules.checklist_for(db, rs.id, t, inst, clock.today())
        out.append(row)
    return {"ruleset": f"{rs.code} v{rs.version}", "types": out}


# --------------------------------------------------------------------------- clock / demo
@router.get("/clock")
def get_clock(db: Session = Depends(get_db)):
    now = clock.now(db)
    return {"now": ser.iso(now), "offset_days": clock.load_offset(db), "demo_mode": DEMO_MODE}


class AdvanceIn(BaseModel):
    days: int = Field(ge=1, le=120)


@router.post("/clock/advance")
def advance_clock(body: AdvanceIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not DEMO_MODE:
        raise HTTPException(403, "Clock control is disabled outside demo mode")
    clock.advance(db, body.days)
    audit.record(db, actor=user, action="DEMO_CLOCK_ADVANCED", entity_type="system", entity_id=0,
                 detail={"days": body.days, "now": ser.iso(clock.now())})
    stats = obl.tick(db)
    stats["lapsed_undertakings"] = compliance.sync_statuses(db)
    db.commit()
    return {"now": ser.iso(clock.now()), "tick": stats}


@router.post("/demo/reset")
def demo_reset(user: User = Depends(require("ADMIN", "BUREAU"))):
    if not DEMO_MODE:
        raise HTTPException(403)
    from . import seed
    return seed.run()


@router.post("/tick")
def run_tick(db: Session = Depends(get_db), user: User = Depends(require("ADMIN", "BUREAU"))):
    stats = obl.tick(db)
    stats["lapsed_undertakings"] = compliance.sync_statuses(db)
    db.commit()
    return stats


# --------------------------------------------------------------------------- dashboard
def _bucket(days: int) -> str:
    return "0-7" if days <= 7 else "8-15" if days <= 15 else "16-30" if days <= 30 else "30+"


@router.get("/dashboard")
@router.get("/dashboard/summary")
def dashboard(region_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    now = clock.now(db)
    today = clock.today()
    q = scoped_apps(user)
    allin = user.role in GLOBAL
    if region_id and allin:
        q = q.where(Institution.region_id == region_id)
    apps = list(db.scalars(q))
    active = [a for a in apps if a.status in ("IN_PROGRESS", "RETURNED", "READY_FOR_DECISION")]
    oq = select(Obligation).where(obl.visible_filter(user), Obligation.state != "CLOSED")
    if region_id and allin:
        oq = oq.where(Obligation.region_id == region_id)
    open_obs = list(db.scalars(oq))
    obs_by_app = defaultdict(list)
    for o in open_obs:
        if o.application_id:
            obs_by_app[o.application_id].append(o)

    pend = {s: {"stage": s, "count": 0, "overdue": 0, "due_soon": 0}
            for s in ["SELF_DISCLOSURE", "SCRUTINY", "RE_SCRUTINY", "EVC", "SHC", "SAC", "RULE_REVIEW", "RETURNED", "DECISION"]}
    for a in active:
        key = "RETURNED" if a.status == "RETURNED" else (a.current_stage_code or "DECISION")
        p = pend.setdefault(key, {"stage": key, "count": 0, "overdue": 0, "due_soon": 0})
        p["count"] += 1
        states = {o.state for o in obs_by_app[a.id]}
        if "OVERDUE" in states:
            p["overdue"] += 1
        elif "DUE_SOON" in states:
            p["due_soon"] += 1
    ageing = Counter(_bucket(workflow.ageing_days(a, now)) for a in active)

    by_region = []
    if allin:
        for r in db.scalars(select(Region)):
            ra = [a for a in active if a.institution.region_id == r.id]
            ro = [o for o in open_obs if o.region_id == r.id]
            by_region.append({
                "region": r.name, "region_id": r.id, "active": len(ra),
                "overdue": sum(1 for o in ro if o.state == "OVERDUE" and o.owner_role != "INSTITUTION"),
                "escalated": sum(1 for o in ro if o.escalation_level > 0),
                "avg_age_days": round(sum(workflow.ageing_days(a, now) for a in ra) / len(ra), 1) if ra else 0,
                "evc_pending": sum(1 for o in ro if o.kind in ("EVC_SCHEDULE", "EVC_REPORT")),
                "compliance_overdue": sum(1 for o in ro if o.kind in ("UNDERTAKING", "DOC_EXPIRY") and o.state == "OVERDUE")})

    workload = []
    if user.role != "INSTITUTION":
        wq = select(User).where(User.role.in_(["SCRUTINY_OFFICER", "RESCRUTINY_OFFICER", "EVC_COORDINATOR", "SHC_MEMBER"]))
        if not allin:
            wq = wq.where(User.region_id == user.region_id)
        elif region_id:
            wq = wq.where(User.region_id == region_id)
        for o in db.scalars(wq):
            mine = [ob for ob in open_obs if ob.owner_user_id == o.id]
            workload.append({"officer": o.full_name, "role": o.role, "region": o.region.name if o.region else "",
                             "open": len(mine), "overdue": sum(1 for m in mine if m.state == "OVERDUE"),
                             "due_soon": sum(1 for m in mine if m.state == "DUE_SOON")})
        workload.sort(key=lambda w: (-w["overdue"], -w["open"]))

    def count(kinds, state=None):
        return sum(1 for o in open_obs if o.kind in kinds and (state is None or o.state == state))

    apps_overdue = {o.application_id for o in open_obs if o.application_id and o.state == "OVERDUE"}
    unds = list(db.scalars(select(Undertaking).where(*_inst_scope(user, Undertaking))))
    docs = list(db.scalars(select(TrackedDocument).where(*_inst_scope(user, TrackedDocument),
                                                         TrackedDocument.superseded_by_id.is_(None),
                                                         TrackedDocument.verification_status == "VERIFIED")))
    if region_id and allin:
        ids = {i.id for i in db.scalars(select(Institution).where(Institution.region_id == region_id))}
        unds = [u for u in unds if u.institution_id in ids]
        docs = [d for d in docs if d.institution_id in ids]
    docs_valid = sum(1 for d in docs if compliance.doc_status(d, today) in ("VALID", "EXPIRING_SOON"))
    esc_q = select(Escalation).join(Obligation).where(Escalation.resolved_at.is_(None), obl.visible_filter(user))
    escs = list(db.scalars(esc_q))
    start = (now - timedelta(days=clock.to_ist(now).weekday())).replace(hour=0, minute=0, second=0)
    weeks = []
    for i in range(9, -1, -1):
        ws = start - timedelta(weeks=i)
        we = ws + timedelta(weeks=1)
        weeks.append({"week": clock.to_ist(ws).date().isoformat(),
                      "submitted": sum(1 for a in apps if ws <= a.submitted_at < we),
                      "decided": sum(1 for a in apps if a.decided_at and ws <= a.decided_at < we)})
    watch = sorted([o for o in open_obs if o.state in ("OVERDUE", "DUE_SOON")],
                   key=lambda o: (-o.escalation_level, o.due_at))[:8]
    return {
        "now": ser.iso(now),
        "kpis": {"active": len(active), "in_processing": sum(1 for a in active if a.status == "IN_PROGRESS"),
                 "returned": sum(1 for a in active if a.status == "RETURNED"),
                 "ready_for_decision": sum(1 for a in active if a.status == "READY_FOR_DECISION"),
                 "decided": sum(1 for a in apps if a.status in ("APPROVED", "REJECTED", "UNDER_APPEAL")),
                 "overdue": sum(1 for o in open_obs if o.state == "OVERDUE"),
                 "due_soon": sum(1 for o in open_obs if o.state == "DUE_SOON"),
                 "escalated": sum(1 for o in open_obs if o.escalation_level > 0),
                 "escalations_unacknowledged": sum(1 for e in escs if not e.acknowledged_at),
                 "evc_pending": count(["EVC_SCHEDULE", "EVC_REPORT"]),
                 "undertakings_open": count(["UNDERTAKING", "UNDERTAKING_VERIFY"]),
                 "undertakings_overdue": count(["UNDERTAKING"], "OVERDUE"),
                 "docs_due": count(["DOC_EXPIRY"], "DUE_SOON"), "docs_overdue": count(["DOC_EXPIRY"], "OVERDUE"),
                 "verifications_pending": count(["UNDERTAKING_VERIFY", "DOC_VERIFY"])},
        "pendency_by_stage": [p for p in pend.values() if p["count"] or p["stage"] in ("SCRUTINY", "EVC", "DECISION")],
        "ageing": [{"bucket": b, "count": ageing.get(b, 0)} for b in ["0-7", "8-15", "16-30", "30+"]],
        "by_region": by_region, "workload": workload, "watchlist": [ser.obligation(o, now) for o in watch],
        "headline": {
            "on_track": {"value": len(active) - len(apps_overdue & {a.id for a in active}), "total": len(active)},
            "evc_scheduled": {"value": count(["EVC_REPORT"]), "total": count(["EVC_SCHEDULE", "EVC_REPORT"])},
            "undertakings_verified": {"value": sum(1 for u in unds if u.status == "VERIFIED"), "total": len(unds)},
            "docs_valid": {"value": docs_valid, "total": len(docs)}},
        "weekly": weeks,
    }


# --------------------------------------------------------------------------- applications
@router.get("/applications")
def list_applications(status: str | None = None, stage: str | None = None, region_id: int | None = None,
                      app_type: str | None = None, q: str | None = None, overdue: bool = False, mine: bool = False,
                      db: Session = Depends(get_db), user: User = Depends(current_user)):
    now = clock.now(db)
    query = scoped_apps(user)
    if status == "ACTIVE":
        query = query.where(Application.status.in_(["IN_PROGRESS", "RETURNED", "READY_FOR_DECISION"]))
    elif status:
        query = query.where(Application.status == status)
    if stage:
        query = query.where(Application.current_stage_code == stage)
    if region_id:
        query = query.where(Institution.region_id == region_id)
    if app_type:
        query = query.where(Application.application_type == app_type)
    apps = list(db.scalars(query.order_by(Application.submitted_at)))
    if q:
        ql = q.lower()
        apps = [a for a in apps if ql in a.application_no.lower() or ql in a.institution.name.lower()]
    obs = defaultdict(list)
    for o in db.scalars(select(Obligation).where(Obligation.state != "CLOSED", Obligation.application_id.isnot(None))):
        obs[o.application_id].append(o)
    labels = rules.type_labels(db)
    rows = [ser.application_row(a, now, obs[a.id], labels) for a in apps]
    if overdue:
        rows = [r for r in rows if r["next_due_state"] == "OVERDUE"]
    if mine:
        rows = [r for r in rows if r["assignee_id"] == user.id or (
            user.role == "COMPETENT_AUTHORITY" and r["status"] == "READY_FOR_DECISION")]
    return rows


@router.get("/applications/{app_id}")
def get_application(app_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return ser.application_detail(db, get_app_for(db, user, app_id), user, clock.now(db))


@router.get("/applications/{app_id}/route")
def get_route(app_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    d = ser.application_detail(db, get_app_for(db, user, app_id), user, clock.now(db))
    return {"rule_trace": d["rule_trace"], "route": d["route_detail"]}


class ActionIn(BaseModel):
    action: str
    remarks: str = ""
    expected_version: int | None = None
    target_stage: str | None = None
    route_code: str | None = None
    user_id: int | None = None
    file_ids: list[int] = []
    deficiencies: list[dict] = []
    item_responses: dict = {}
    verdicts: dict = {}
    decision_ref: str = ""
    decision_file_id: int | None = None


@router.post("/applications/{app_id}/actions")
def application_action(app_id: int, body: ActionIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    app = get_app_for(db, user, app_id)
    clock.now(db)
    if body.expected_version is not None and body.expected_version != app.version:
        raise HTTPException(409, "This application was changed by someone else; reload and try again")
    a = body.action
    try:
        if a == "record_nil_deficiency":
            workflow.record_outcome(db, app, user, "NIL_DEFICIENCY", body.remarks)
        elif a == "record_deficiency":
            workflow.record_outcome(db, app, user, "DEFICIENCY", body.remarks, deficiencies=body.deficiencies)
        elif a == "return_for_clarification":
            workflow.return_for_clarification(db, app, user, body.remarks)
        elif a == "respond":
            workflow.institution_respond(db, app, user, body.remarks, body.file_ids, body.item_responses)
        elif a == "verify_deficiencies":
            workflow.verify_deficiencies(db, app, user, body.verdicts, body.remarks)
        elif a == "assign_route":
            workflow.assign_route(db, app, user, body.route_code or "", body.remarks)
        elif a == "revert":
            workflow.revert(db, app, user, body.target_stage or "", body.remarks)
        elif a == "reassign":
            workflow.reassign(db, app, user, body.user_id or 0, body.remarks)
        elif a in ("approve", "reject"):
            workflow.decide(db, app, user, "APPROVED" if a == "approve" else "REJECTED", body.remarks,
                            body.decision_ref, body.decision_file_id)
        elif a == "appeal":
            new = workflow.file_appeal(db, app, user, body.remarks)
            app.version += 1
            db.commit()
            return {"ok": True, "appeal_application_id": new.id}
        else:
            raise HTTPException(422, f"Unknown action {a}")
    except WorkflowError as e:
        db.rollback()
        _fail(e)
    app.version += 1
    db.commit()
    db.refresh(app)
    return ser.application_detail(db, app, user, clock.now(db))


class NewAppIn(BaseModel):
    application_type: str
    academic_year: str = "2027-28"
    programme: str = ""
    intake_requested: int | None = None
    documents: dict[str, int] = {}


@router.post("/applications")
def create_application(body: NewAppIn, db: Session = Depends(get_db), user: User = Depends(require("INSTITUTION"))):
    inst = db.get(Institution, user.institution_id)
    for fid in body.documents.values():
        fo = db.get(FileObject, fid)
        if not fo or fo.institution_id != inst.id:
            raise HTTPException(422, "Every checklist document must be uploaded by your institution")
    app = run(db, workflow.submit_application, db, institution=inst, application_type=body.application_type,
              academic_year=body.academic_year, actor=user, programme=body.programme,
              intake_requested=body.intake_requested, documents=body.documents)
    return {"id": app.id, "application_no": app.application_no, "processing_academic_year": app.processing_academic_year}


@router.get("/officers")
def officers(role: str, region_id: int, db: Session = Depends(get_db), user: User = Depends(require(*OFFICIAL_ROLES))):
    return [ser.user_brief(u) for u in db.scalars(select(User).where(User.role == role,
                                                                      (User.region_id == region_id) | User.region_id.is_(None)))]


# --------------------------------------------------------------------------- EVC
@router.get("/evc")
@router.get("/evc/queue")
def evc_queue(include_done: bool = False, db: Session = Depends(get_db), user: User = Depends(require(*OFFICIAL_ROLES))):
    visits = evc.queue_for(db, user)
    if include_done:
        done = db.scalars(select(EvcVisit).where(EvcVisit.status == "REPORT_SUBMITTED")).all()
        visits += [v for v in done if user.role in GLOBAL or v.application.institution.region_id == user.region_id]
    by_visit = _open_obs_by(db, "evc_visit")
    now = clock.now(db)
    users = {u.id: u.full_name for u in db.scalars(select(User))}
    out = []
    for v in visits:
        row = ser.evc_visit(v, users)
        obs = by_visit.get(v.id, [])
        row["obligation"] = ser.obligation(obs[0], now) if obs else None
        row["can_report"] = user.role == "EVC_MEMBER" and user.expert_id in {p["id"] for p in (v.panel or [])}
        out.append(row)
    return out


@router.get("/evc/{visit_id}/panel")
def evc_panel(visit_id: int, on: date, db: Session = Depends(get_db), user: User = Depends(require("EVC_COORDINATOR"))):
    v = db.get(EvcVisit, visit_id)
    if not v:
        raise HTTPException(404)
    panel = evc.draw_panel(db, v, on, seed=int(datetime.now().timestamp()))
    return {"panel": panel, "warnings": evc.check_panel(db, v, panel, on)}


class ScheduleIn(BaseModel):
    date: date
    panel: list[dict]
    mode: str = "PHYSICAL"


@router.post("/evc/{visit_id}/schedule")
def evc_schedule(visit_id: int, body: ScheduleIn, db: Session = Depends(get_db),
                 user: User = Depends(require("EVC_COORDINATOR"))):
    v = db.get(EvcVisit, visit_id)
    if not v:
        raise HTTPException(404)
    clock.now(db)
    run(db, evc.schedule, db, v, user, body.date, body.panel, body.mode)
    return {"ok": True}


class ReportIn(BaseModel):
    outcome: str
    remarks: str
    file_id: int | None = None
    video_url: str | None = None
    video_minutes: int | None = None


@router.post("/evc/{visit_id}/report")
def evc_report(visit_id: int, body: ReportIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    v = db.get(EvcVisit, visit_id)
    if not v:
        raise HTTPException(404)
    clock.now(db)
    run(db, evc.submit_report, db, v, user, body.outcome, body.remarks, body.file_id, body.video_url, body.video_minutes)
    return {"ok": True}


# --------------------------------------------------------------------------- compliance
@router.get("/undertakings")
@router.get("/obligations/undertakings")
def list_undertakings(status: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = select(Undertaking).where(*_inst_scope(user, Undertaking))
    if status:
        q = q.where(Undertaking.status == status)
    now = clock.now(db)
    by = _open_obs_by(db, "undertaking")
    rows = [ser.undertaking(u, now, by.get(u.id)) for u in db.scalars(q)]
    return sorted(rows, key=lambda r: (r["status"] == "VERIFIED", r["days_left"]))


class EvidenceIn(BaseModel):
    remarks: str = ""
    file_ids: list[int]


@router.post("/undertakings/{uid}/evidence")
def undertaking_evidence(uid: int, body: EvidenceIn, db: Session = Depends(get_db), user: User = Depends(require("INSTITUTION"))):
    u = db.get(Undertaking, uid)
    if not u:
        raise HTTPException(404)
    clock.now(db)
    run(db, compliance.submit_evidence, db, u, user, body.remarks, body.file_ids)
    return {"ok": True}


class VerifyIn(BaseModel):
    accept: bool
    remarks: str


@router.post("/undertakings/{uid}/verify")
def undertaking_verify(uid: int, body: VerifyIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    u = db.get(Undertaking, uid)
    if not u:
        raise HTTPException(404)
    clock.now(db)
    run(db, compliance.verify_undertaking, db, u, user, body.accept, body.remarks)
    return {"ok": True}


@router.get("/documents")
def list_documents(include_superseded: bool = False, db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = select(TrackedDocument).where(*_inst_scope(user, TrackedDocument))
    if not include_superseded:
        q = q.where(TrackedDocument.superseded_by_id.is_(None))
    today = clock.today(db)
    by = _open_obs_by(db, "document")
    docs = list(db.scalars(q))
    pending = {(d.institution_id, d.doc_type) for d in docs if d.verification_status == "PENDING"}
    rows = []
    for d in docs:
        row = ser.document(db, d, today, by.get(d.id))
        if d.verification_status == "VERIFIED" and (d.institution_id, d.doc_type) in pending:
            row["status"] = "RENEWAL_SUBMITTED"
        rows.append(row)
    have = {(d.institution_id, d.doc_type) for d in docs if d.verification_status != "REJECTED"}
    iq = select(Institution)
    if user.role == "INSTITUTION":
        iq = iq.where(Institution.id == user.institution_id)
    elif user.role not in GLOBAL:
        iq = iq.where(Institution.region_id == user.region_id)
    for inst in db.scalars(iq):
        for dt in compliance.required_doc_types(db, inst):
            if (inst.id, dt) not in have:
                rows.append({"id": None, "institution": inst.name, "institution_id": inst.id, "region": inst.region.name,
                             "doc_type": dt, "title": compliance.DOC_TYPES[dt], "version": 0, "status": "MISSING",
                             "valid_from": None, "valid_until": None, "renew_by": None, "days_to_renew_by": -9999,
                             "source": compliance.DOC_SOURCE.get(dt, ""), "escalation_level": 0})
    rank = {"MISSING": -1, "AWAITING_VERIFICATION": 0, "RENEWAL_SUBMITTED": 0.5, "EXPIRED": 1,
            "LEASE_REVIEW_REQUIRED": 2, "EXPIRING_SOON": 3, "REJECTED": 4, "VALID": 5, "SUPERSEDED": 6}
    return sorted(rows, key=lambda r: (rank.get(r["status"], 9), r["days_to_renew_by"]))


class NewDocIn(BaseModel):
    doc_type: str
    valid_from: date
    valid_until: date
    file_id: int
    issuer_name: str = ""
    reference_no: str = ""


@router.post("/documents")
def document_new(body: NewDocIn, db: Session = Depends(get_db), user: User = Depends(require("INSTITUTION"))):
    inst = db.get(Institution, user.institution_id)
    clock.now(db)
    d = run(db, compliance.submit_new_document, db, inst, user, body.doc_type, body.valid_from, body.valid_until,
            body.file_id, body.issuer_name, body.reference_no)
    return {"ok": True, "id": d.id}


class RenewIn(BaseModel):
    valid_from: date
    valid_until: date
    file_id: int
    remarks: str = ""
    issuer_name: str = ""
    reference_no: str = ""


@router.post("/documents/{doc_id}/renew")
def document_renew(doc_id: int, body: RenewIn, db: Session = Depends(get_db), user: User = Depends(require("INSTITUTION"))):
    d = db.get(TrackedDocument, doc_id)
    if not d or d.institution_id != user.institution_id:
        raise HTTPException(404)
    clock.now(db)
    new = run(db, compliance.submit_renewal, db, d, user, body.valid_from, body.valid_until, body.file_id, body.remarks,
              body.issuer_name, body.reference_no)
    return {"ok": True, "id": new.id}


@router.post("/documents/{doc_id}/verify")
@router.post("/documents/{doc_id}/review")
def document_verify(doc_id: int, body: VerifyIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    d = db.get(TrackedDocument, doc_id)
    if not d:
        raise HTTPException(404)
    clock.now(db)
    run(db, compliance.verify_document, db, d, user, body.accept, body.remarks)
    return {"ok": True}


@router.get("/documents/{doc_id}/versions")
def document_versions(doc_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    d = db.get(TrackedDocument, doc_id)
    if not d or (user.role == "INSTITUTION" and d.institution_id != user.institution_id):
        raise HTTPException(404)
    today = clock.today(db)
    return [ser.document(db, x, today) for x in db.scalars(select(TrackedDocument).where(
        TrackedDocument.institution_id == d.institution_id, TrackedDocument.doc_type == d.doc_type)
        .order_by(TrackedDocument.version))]


# --------------------------------------------------------------------------- deadlines, escalations, alerts
@router.get("/obligations")
def list_obligations(state: str | None = None, kind: str | None = None, escalated: bool = False, mine: bool = False,
                     db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = select(Obligation).where(obl.visible_filter(user), Obligation.state != "CLOSED")
    if state:
        q = q.where(Obligation.state == state)
    if kind:
        q = q.where(Obligation.kind == kind)
    if escalated:
        q = q.where(Obligation.escalation_level > 0)
    obs = list(db.scalars(q.order_by(Obligation.due_at)))
    if mine:
        obs = [o for o in obs if o.owner_user_id == user.id or (o.owner_user_id is None and o.owner_role == user.role)]
    now = clock.now(db)
    return [ser.obligation(o, now) for o in obs]


@router.get("/escalations")
def list_escalations(open_only: bool = True, mine: bool = False, db: Session = Depends(get_db),
                     user: User = Depends(require(*OFFICIAL_ROLES))):
    q = select(Escalation).join(Obligation).where(obl.visible_filter(user))
    if open_only:
        q = q.where(Escalation.resolved_at.is_(None))
    rows = list(db.scalars(q.order_by(Escalation.created_at.desc())))
    if mine:
        rows = [e for e in rows if e.target_role == user.role]
    now = clock.now(db)
    return [{**ser.escalation(e, now), "can_acknowledge": e.target_role == user.role and not e.acknowledged_at}
            for e in rows]


class AckIn(BaseModel):
    note: str = ""


@router.post("/escalations/{eid}/acknowledge")
def ack_escalation(eid: int, body: AckIn, db: Session = Depends(get_db), user: User = Depends(require(*OFFICIAL_ROLES))):
    e = db.get(Escalation, eid)
    if not e:
        raise HTTPException(404)
    clock.now(db)
    run(db, obl.acknowledge, db, e, user, body.note)
    return {"ok": True}


@router.get("/notifications")
def list_notifications(unread: bool = False, limit: int = 100, db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = select(Notification).where(Notification.recipient_id == user.id, Notification.channel == "IN_APP")
    if unread:
        q = q.where(Notification.read_at.is_(None))
    rows = db.scalars(q.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit)).all()
    unread_count = len(db.scalars(select(Notification.id).where(Notification.recipient_id == user.id,
                                                               Notification.channel == "IN_APP",
                                                               Notification.read_at.is_(None))).all())
    return {"unread": unread_count, "items": [ser.notification(n) for n in rows]}


@router.get("/notifications/outbox")
def outbox(limit: int = 200, db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = select(Notification).where(Notification.channel == "EMAIL")
    if user.role not in ("ADMIN", "BUREAU"):
        q = q.where(Notification.recipient_id == user.id)
    users = {u.id: u.email for u in db.scalars(select(User))}
    return [{**ser.notification(n), "to": users.get(n.recipient_id), "attempts": n.attempts}
            for n in db.scalars(q.order_by(Notification.id.desc()).limit(limit))]


@router.post("/notifications/read-all")
def read_all(db: Session = Depends(get_db), user: User = Depends(current_user)):
    db.execute(update(Notification).where(Notification.recipient_id == user.id, Notification.read_at.is_(None))
               .values(read_at=clock.now(db)))
    db.commit()
    return {"ok": True}


@router.post("/notifications/{nid}/read")
@router.post("/notifications/{nid}/acknowledge")
def read_one(nid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    n = db.get(Notification, nid)
    if n and n.recipient_id == user.id and not n.read_at:
        n.read_at = clock.now(db)
        db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- audit
@router.get("/audit")
def list_audit(application_id: int | None = None, action: str | None = None, entity_type: str | None = None,
               entity_id: int | None = None, limit: int = 200, db: Session = Depends(get_db),
               user: User = Depends(require(*OFFICIAL_ROLES))):
    q = select(AuditEvent)
    if application_id:
        q = q.where(AuditEvent.application_id == application_id)
    if action:
        q = q.where(AuditEvent.action == action)
    if entity_type:
        q = q.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        q = q.where(AuditEvent.entity_id == entity_id)
    if user.role not in GLOBAL:
        q = q.where(AuditEvent.institution_id.in_(select(Institution.id).where(Institution.region_id == user.region_id)))
    return [ser.audit_event(e) for e in db.scalars(q.order_by(AuditEvent.seq.desc()).limit(limit))]


@router.get("/audit/verify")
def audit_verify(db: Session = Depends(get_db), user: User = Depends(require(*OFFICIAL_ROLES))):
    return audit.verify_chain(db)


# --------------------------------------------------------------------------- rules / configuration
@router.get("/config")
@router.get("/admin/rulesets")
def get_config(db: Session = Depends(get_db), user: User = Depends(require(*OFFICIAL_ROLES))):
    rs = rules.active_ruleset(db)
    routes = []
    for r in db.scalars(select(RouteTemplate).where(RouteTemplate.ruleset_id == rs.id).order_by(RouteTemplate.id)):
        routes.append({"id": r.id, "code": r.code, "name": r.name, "description": r.description,
                       "source_type": r.source_type, "aph_reference": r.aph_reference,
                       "stages": [{"id": s.id, "code": s.code, "name": s.name, "order": s.order, "sla_days": s.sla_days,
                                   "assignee_role": s.assignee_role, "conditional": s.conditional,
                                   "on_deficiency": s.on_deficiency, "managed_by": s.managed_by} for s in r.stages]})
    types = [{"code": t.code, "label": t.label, "chapter": t.chapter, "table_row": t.table_row, "route_code": t.route_code,
              "notice_category": t.notice_category, "notice_verified": t.notice_verified,
              "checklist_code": t.checklist_code, "initiated_by": t.initiated_by, "note": t.note}
             for t in db.scalars(select(ApplicationTypeDef).where(ApplicationTypeDef.ruleset_id == rs.id)
                                 .order_by(ApplicationTypeDef.id))]
    checklists = defaultdict(list)
    for d in db.scalars(select(DocumentRequirement).where(DocumentRequirement.ruleset_id == rs.id).order_by(DocumentRequirement.id)):
        checklists[d.checklist_code].append({"doc_code": d.doc_code, "label": d.label, "condition": d.condition,
                                             "source": d.source})
    pinned = Counter(a.ruleset_id for a in db.scalars(select(Application)))
    return {
        "ruleset": {"id": rs.id, "code": rs.code, "version": rs.version, "aph_edition": rs.aph_edition,
                    "source_url": rs.source_url, "effective_from": ser.iso(rs.effective_from), "notes": rs.notes},
        "versions": [{"id": r.id, "label": f"{r.code} v{r.version}", "status": r.status,
                      "effective_from": ser.iso(r.effective_from), "effective_to": ser.iso(r.effective_to),
                      "published_by": r.published_by, "notes": r.notes, "applications_pinned": pinned.get(r.id, 0)}
                     for r in db.scalars(select(Ruleset).order_by(Ruleset.version.desc()))],
        "routes": routes, "application_types": types, "checklists": checklists,
        "calendars": [{"academic_year": c.academic_year, "notice_ref": c.notice_ref,
                       "application_open": ser.iso(c.application_open), "application_close": ser.iso(c.application_close),
                       "odl_cycles": c.odl_cycles} for c in db.scalars(select(AcademicCalendar))],
        "policies": [{"id": p.id, "kind": p.kind, "name": p.name, "reminder_offsets_days": p.reminder_offsets_days,
                      "escalation_steps": p.escalation_steps} for p in db.scalars(select(EscalationPolicy))],
        "settings": [{"key": s.key, "value": s.value, "unit": s.unit, "source_type": s.source_type, "source": s.source}
                     for s in db.scalars(select(Setting)) if s.key != "clock_offset_days"],
        "can_edit": user.role == "RULE_ADMIN",
    }


class StageCfgIn(BaseModel):
    sla_days: int = Field(ge=1, le=120)
    reason: str


@router.put("/config/stages/{stage_id}")
def update_stage(stage_id: int, body: StageCfgIn, db: Session = Depends(get_db), user: User = Depends(require("RULE_ADMIN"))):
    s = db.get(StageDefinition, stage_id)
    if not s or s.route.ruleset.status != "ACTIVE":
        raise HTTPException(404, "Stage not found in the active ruleset")

    def mutate(new_rs, stage_map):
        ns = stage_map[s.id]
        old = ns.sla_days
        ns.sla_days = body.sla_days
        return {"route": s.route.code, "stage": s.code, "field": "sla_days", "from": old, "to": body.sla_days}

    new = run(db, rules.publish_new_version, db, user, body.reason, mutate)
    return {"ok": True, "ruleset": f"{new.code} v{new.version}"}


class PolicyIn(BaseModel):
    reminder_offsets_days: list[int]
    escalation_steps: list[dict]
    reason: str


@router.put("/config/policies/{pid}")
def update_policy(pid: int, body: PolicyIn, db: Session = Depends(get_db), user: User = Depends(require("RULE_ADMIN"))):
    p = db.get(EscalationPolicy, pid)
    if not p:
        raise HTTPException(404)
    if not body.reason.strip():
        raise HTTPException(422, "A reason is required for every configuration change")
    for st in body.escalation_steps:
        if st.get("to_role") not in ROLES or int(st.get("after_days", -1)) < 0:
            raise HTTPException(422, "Invalid escalation step")
    old = {"reminders": p.reminder_offsets_days, "steps": p.escalation_steps}
    p.reminder_offsets_days = sorted({int(x) for x in body.reminder_offsets_days if int(x) >= 0}, reverse=True)
    p.escalation_steps = body.escalation_steps
    audit.record(db, actor=user, action="CONFIG_CHANGED", entity_type="escalation_policy", entity_id=p.id,
                 detail={"kind": p.kind, "from": old, "to": {"reminders": p.reminder_offsets_days, "steps": p.escalation_steps},
                         "source_type": "DESIGN"}, reason=body.reason)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- reports
def _csv(rows: list[dict], name: str):
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow({k: (v if not isinstance(v, (list, dict)) else str(v)) for k, v in r.items()})
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})


@router.get("/reports/{kind}.csv")
@router.get("/reports/{kind}")
def report(kind: str, db: Session = Depends(get_db), user: User = Depends(require(*OFFICIAL_ROLES))):
    kind = kind.removesuffix(".csv")
    if kind == "pendency":
        rows = list_applications(status="ACTIVE", db=db, user=user)
        return _csv([{k: r[k] for k in ("application_no", "institution", "region", "type_label", "route", "ruleset",
                                         "status", "stage_name", "assignee", "submitted_at", "age_days",
                                         "processing_academic_year", "next_due_at", "next_due_state",
                                         "escalation_level")} for r in rows], "pendency")
    if kind == "evc":
        return _csv([{k: r[k] for k in ("application_no", "institution", "region", "status", "mode", "scheduled_on",
                                         "report_outcome", "report_submitted_by", "video_minutes",
                                         "priority_new_institution")} for r in evc_queue(include_done=True, db=db, user=user)],
                    "evc_status")
    if kind == "undertakings":
        return _csv([{k: r[k] for k in ("institution", "region", "kind", "title", "source_document", "due_on", "days_left",
                                         "status", "was_late", "aph_reference", "escalation_level")}
                     for r in list_undertakings(db=db, user=user)], "undertakings")
    if kind == "documents":
        return _csv([{k: r.get(k) for k in ("institution", "region", "title", "version", "valid_until", "renew_by",
                                             "days_to_renew_by", "status", "source", "escalation_level")}
                     for r in list_documents(db=db, user=user)], "document_validity")
    if kind == "overdue":
        return _csv([{k: r[k] for k in ("kind", "title", "owner_role", "owner", "institution", "due_at", "days_left",
                                         "escalation_level", "source_reference")}
                     for r in list_obligations(state="OVERDUE", db=db, user=user)], "overdue")
    if kind == "escalations":
        return _csv([{"level": e["level"], "target_role": e["target_role"], "raised": e["created_at"],
                      "acknowledged": e["acknowledged_at"], "resolved": e["resolved_at"],
                      "deadline": e["obligation"]["title"]} for e in list_escalations(open_only=False, db=db, user=user)],
                    "escalations")
    if kind == "regions":
        return _csv(dashboard(db=db, user=user)["by_region"], "region_performance")
    raise HTTPException(404, "Unknown report")


# --------------------------------------------------------------------------- files
@router.post("/files")
async def upload(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(current_user)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(422, "Only PDF, JPG and PNG files are accepted")
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(422, "File exceeds 10 MB")
    if b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE" in data:
        raise HTTPException(422, "File failed the malware scan")
    digest = hashlib.sha256(data).hexdigest()
    key = f"{digest[:2]}/{digest}{ext}"
    path = STORAGE / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    fo = FileObject(storage_key=key, original_name=Path(file.filename).name, sha256=digest,
                    mime=file.content_type or "application/octet-stream", size=len(data), uploaded_by=user.id,
                    institution_id=user.institution_id, uploaded_at=clock.now(db), scan_status="CLEAN")
    db.add(fo)
    db.flush()
    audit.record(db, actor=user, action="FILE_UPLOADED", entity_type="file", entity_id=fo.id,
                 institution_id=user.institution_id, detail={"name": fo.original_name, "sha256": digest, "size": fo.size})
    db.commit()
    return {"id": fo.id, "name": fo.original_name, "sha256": digest, "size": fo.size}


@router.get("/files/{fid}")
def download(fid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    fo = db.get(FileObject, fid)
    if not fo:
        raise HTTPException(404)
    if user.role == "INSTITUTION" and fo.institution_id != user.institution_id:
        raise HTTPException(403, "Not permitted")
    if user.role not in GLOBAL and user.role != "INSTITUTION" and fo.institution_id:
        inst = db.get(Institution, fo.institution_id)
        if user.role != "EVC_MEMBER" and inst.region_id != user.region_id:
            raise HTTPException(403, "Not permitted")
    audit.record(db, actor=user, action="FILE_DOWNLOADED", entity_type="file", entity_id=fo.id,
                 institution_id=fo.institution_id)
    db.commit()
    return FileResponse(STORAGE / fo.storage_key, filename=fo.original_name, media_type=fo.mime)
