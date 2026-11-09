"""Expert Visit Committee (APH cl. 1.9).

The coordinator draws a conflict-free panel and schedules the visit; only an assigned panel
member submits the report. An online EVC needs a video link of at least 30 minutes.
"""
from __future__ import annotations

import random
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import audit, clock, obligations as obl, rules, workflow
from .errors import Forbidden, Invalid, WorkflowError
from .models import Application, EvcVisit, Expert, User

PANEL_SIZE = 3
READINESS_AREAS = ["Instructional", "Administrative", "Amenities", "Laboratory / equipment", "Documents", "Faculty"]


def _busy_experts(db: Session, on: date) -> set[int]:
    busy: set[int] = set()
    for v in db.scalars(select(EvcVisit).where(EvcVisit.scheduled_on == on, EvcVisit.status == "SCHEDULED")):
        busy |= {p["id"] for p in v.panel or []}
    return busy


def check_panel(db: Session, visit: EvcVisit, panel: list[dict], on: date) -> list[str]:
    issues: list[str] = []
    inst = visit.application.institution
    busy = _busy_experts(db, on) - {p["id"] for p in (visit.panel or [])}
    for p in panel:
        if p.get("home_state") == inst.state:
            issues.append(f"{p['name']} is from {inst.state}, the institution's own state (conflict of interest)")
        if p["id"] in busy:
            issues.append(f"{p['name']} already has a visit on {on:%d %b %Y} (double booking)")
    return issues


def draw_panel(db: Session, visit: EvcVisit, on: date, seed: int | None = None) -> list[dict]:
    inst = visit.application.institution
    busy = _busy_experts(db, on)
    pool = [e for e in db.scalars(select(Expert)) if e.home_state != inst.state and e.id not in busy]
    rng = random.Random(seed if seed is not None else visit.id * 31 + on.toordinal())
    return [{"id": e.id, "name": e.name, "expertise": e.expertise, "organisation": e.organisation,
             "home_state": e.home_state} for e in rng.sample(pool, min(PANEL_SIZE, len(pool)))]


def schedule(db: Session, visit: EvcVisit, actor: User, on: date, panel: list[dict], mode: str = "PHYSICAL") -> list[str]:
    if actor.role != "EVC_COORDINATOR" or actor.region_id != visit.application.institution.region_id:
        raise Forbidden("Only the Region's EVC coordinator can schedule this visit")
    if visit.status not in ("QUEUED", "SCHEDULED"):
        raise WorkflowError("Visit can no longer be scheduled")
    if on < clock.today():
        raise Invalid("Visit date cannot be in the past")
    if mode not in ("PHYSICAL", "ONLINE"):
        raise Invalid("Mode must be PHYSICAL or ONLINE")
    if len(panel) < PANEL_SIZE:
        raise Invalid(f"A panel of {PANEL_SIZE} experts is required")
    known = {e.id: e for e in db.scalars(select(Expert))}
    if any(p.get("id") not in known for p in panel):
        raise Invalid("Panel members must come from the approved expert panel")
    panel = [{"id": e.id, "name": e.name, "expertise": e.expertise, "organisation": e.organisation,
              "home_state": e.home_state} for e in (known[p["id"]] for p in panel)]
    issues = check_panel(db, visit, panel, on)
    if issues:
        raise Invalid("; ".join(issues))
    rescheduled = visit.status == "SCHEDULED"
    visit.scheduled_on, visit.panel, visit.mode, visit.status = on, panel, mode, "SCHEDULED"
    app = visit.application
    for ob in obl.open_for(db, "evc_visit", visit.id):
        obl.close_obligation(db, ob, "EVC rescheduled" if rescheduled else "EVC scheduled", actor)
    audit.record(db, actor=actor, action="EVC_RESCHEDULED" if rescheduled else "EVC_SCHEDULED",
                 entity_type="evc_visit", entity_id=visit.id, application_id=app.id, institution_id=app.institution_id,
                 detail={"date": on.isoformat(), "mode": mode, "panel": [p["name"] for p in panel]})
    member_users = list(db.scalars(select(User).where(User.role == "EVC_MEMBER",
                                                      User.expert_id.in_([p["id"] for p in panel]))))
    obl.open_obligation(db, kind="EVC_REPORT", title=f"Submit EVC report: {app.application_no} ({app.institution.name})",
                        subject_type="evc_visit", subject_id=visit.id,
                        due_at=clock.due_after_days(clock.ist_close_of(on), rules.setting_int(db, "evc_report_days", 3)),
                        owner_role="EVC_MEMBER", owner_user_id=member_users[0].id if member_users else None,
                        application_id=app.id, institution_id=app.institution_id, region_id=app.institution.region_id,
                        source_reference="Report time limit: prototype default (DESIGN)")
    inst_users = obl.users_for_role(db, "INSTITUTION", None, app.institution_id)
    note = (" Keep a video presenting all facilities (not less than 30 minutes, APH cl. 1.9) and supporting documents ready."
            if mode == "ONLINE" else " Keep all original documents and facilities ready for verification.")
    obl.notify(db, recipients=inst_users + member_users, category="INFO",
               subject=f"EVC scheduled on {on:%d %b %Y} for {app.application_no}",
               body=f"An Expert Visit Committee ({mode.lower()}) is scheduled on {on:%d %b %Y}.{note}",
               dedupe_key=f"evc{visit.id}:sched:{on.isoformat()}", link=f"/applications/{app.id}")
    return []


def submit_report(db: Session, visit: EvcVisit, actor: User, outcome: str, remarks: str, file_id: int | None,
                  video_url: str | None = None, video_minutes: int | None = None) -> None:
    if actor.role != "EVC_MEMBER" or actor.expert_id not in {p["id"] for p in (visit.panel or [])}:
        raise Forbidden("Only a member assigned to this EVC panel can submit its report")
    if visit.status != "SCHEDULED":
        raise WorkflowError("Visit must be scheduled before a report is submitted")
    if clock.today() < visit.scheduled_on:
        raise WorkflowError("Report cannot be submitted before the visit date")
    if outcome not in ("CLEAR", "DEFICIENCY_FOUND"):
        raise Invalid("Outcome must be CLEAR or DEFICIENCY_FOUND")
    if not (remarks or "").strip():
        raise Invalid("Committee observations are mandatory")
    if visit.mode == "ONLINE":
        mins = rules.setting_int(db, "online_evc_min_video_minutes", 30)
        if not (video_url or "").startswith(("http://", "https://")):
            raise Invalid("An online EVC needs the link to the facilities video (APH cl. 1.9)")
        if not video_minutes or video_minutes < mins:
            raise Invalid(f"The facilities video must be at least {mins} minutes (APH cl. 1.9)")
    visit.status = "REPORT_SUBMITTED"
    visit.report_outcome, visit.report_remarks, visit.report_file_id = outcome, remarks, file_id
    visit.report_submitted_by, visit.video_url, visit.video_minutes = actor.id, video_url, video_minutes
    app: Application = visit.application
    for ob in obl.open_for(db, "evc_visit", visit.id):
        obl.close_obligation(db, ob, "EVC report submitted", actor)
    audit.record(db, actor=actor, action="EVC_REPORT_SUBMITTED", entity_type="evc_visit", entity_id=visit.id,
                 application_id=app.id, institution_id=app.institution_id,
                 detail={"outcome": outcome, "file_id": file_id, "video_minutes": video_minutes,
                         "readiness_areas": READINESS_AREAS}, reason=remarks)
    workflow.record_outcome(db, app, actor, "NIL_DEFICIENCY" if outcome == "CLEAR" else "DEFICIENCY", remarks,
                            via_evc=True)


def queue_for(db: Session, user: User) -> list[EvcVisit]:
    visits = list(db.scalars(select(EvcVisit).where(EvcVisit.status.in_(["QUEUED", "SCHEDULED"]))))
    if user.role == "EVC_MEMBER":
        visits = [v for v in visits if user.expert_id in {p["id"] for p in (v.panel or [])}]
    elif user.role not in ("BUREAU", "ADMIN", "COMPETENT_AUTHORITY"):
        visits = [v for v in visits if v.application.institution.region_id == user.region_id]
    return sorted(visits, key=lambda v: (v.status != "QUEUED", not v.priority_new_institution, v.queued_at))
