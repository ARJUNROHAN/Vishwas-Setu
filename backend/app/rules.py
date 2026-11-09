"""Rule service: versioned rulesets, category routing, calendars, checklists, settings."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import audit, clock
from .errors import Invalid, WorkflowError
from .models import (
    AcademicCalendar, ApplicationTypeDef, DocumentRequirement, Institution, RouteTemplate, Ruleset, Setting,
    StageDefinition, User,
)


def setting(db: Session, key: str, default: str = "") -> str:
    row = db.get(Setting, key)
    return row.value if row else default


def setting_int(db: Session, key: str, default: int) -> int:
    try:
        return int(setting(db, key, str(default)))
    except ValueError:
        return default


def active_ruleset(db: Session) -> Ruleset:
    rs = db.scalars(select(Ruleset).where(Ruleset.status == "ACTIVE").order_by(Ruleset.version.desc())).first()
    if not rs:
        raise WorkflowError("No active ruleset is published")
    return rs


def type_def(db: Session, ruleset: Ruleset, code: str) -> ApplicationTypeDef:
    t = db.scalars(select(ApplicationTypeDef).where(ApplicationTypeDef.ruleset_id == ruleset.id,
                                                    ApplicationTypeDef.code == code)).first()
    if not t:
        raise Invalid(f"Application category {code} is not defined in {ruleset.code} v{ruleset.version}")
    return t


def route(db: Session, ruleset_id: int, code: str) -> RouteTemplate:
    r = db.scalars(select(RouteTemplate).where(RouteTemplate.ruleset_id == ruleset_id,
                                               RouteTemplate.code == code)).first()
    if not r:
        raise WorkflowError(f"Route {code} missing from ruleset {ruleset_id}")
    return r


def type_labels(db: Session) -> dict[str, str]:
    rs = active_ruleset(db)
    return {t.code: t.label for t in db.scalars(select(ApplicationTypeDef).where(ApplicationTypeDef.ruleset_id == rs.id))}


# --------------------------------------------------------------------------- calendar (Table 2.2, cl. 2.22)
def assign_academic_year(db: Session, t: ApplicationTypeDef, requested_year: str, on: date) -> str:
    """Return the academic year (or ODL cycle) the application will be processed for."""
    cals = list(db.scalars(select(AcademicCalendar).order_by(AcademicCalendar.academic_year)))
    cal = next((c for c in cals if c.academic_year == requested_year), None)
    if not cal:
        raise Invalid(f"No academic calendar is published for {requested_year}")
    if t.notice_category == "ODL_CYCLE":
        for cyc in cal.odl_cycles or []:
            if date.fromisoformat(cyc["open"]) <= on <= date.fromisoformat(cyc["close"]):
                return f"{cal.academic_year} — {cyc['cycle']}"
        raise Invalid("ODL applications are accepted only within a published twice-yearly cycle (Table 2.3 footnote)")
    if t.notice_category == "PUBLIC_NOTICE" or t.initiated_by == "APPEAL":
        if t.initiated_by != "APPEAL" and not (cal.application_open <= on <= cal.application_close):
            raise Invalid(f"{t.label} is accepted only within the public-notice window for {cal.academic_year} "
                          f"({cal.application_open:%d %b %Y} – {cal.application_close:%d %b %Y}; {cal.notice_ref})")
        return cal.academic_year
    # YEAR_ROUND: after the relevant public-notice cut-off, processed for the successive year (cl. 2.22)
    if on > cal.application_close:
        nxt = next((c for c in cals if c.academic_year > cal.academic_year), None)
        return nxt.academic_year if nxt else f"after {cal.academic_year}"
    return cal.academic_year


# --------------------------------------------------------------------------- checklists (Annexures 1–2)
def building_age_years(inst: Institution, on: date) -> float | None:
    if not inst.building_completion_date:
        return None
    return (on - inst.building_completion_date).days / 365.25


def condition_applies(cond: str, inst: Institution, on: date, db: Session) -> tuple[bool, bool]:
    """(applies, mandatory)"""
    if cond == "always":
        return True, True
    if cond == "optional":
        return True, False
    if cond == "building_over_30":
        age = building_age_years(inst, on)
        return (age is not None and age > setting_int(db, "stability_building_age_years", 30)), True
    if cond == "land_leased":
        return inst.land_tenure == "LEASED", True
    return False, False


def checklist_for(db: Session, ruleset_id: int, t: ApplicationTypeDef, inst: Institution, on: date) -> list[dict]:
    if not t.checklist_code:
        return []
    out = []
    for r in db.scalars(select(DocumentRequirement).where(DocumentRequirement.ruleset_id == ruleset_id,
                                                          DocumentRequirement.checklist_code == t.checklist_code)
                        .order_by(DocumentRequirement.id)):
        applies, mandatory = condition_applies(r.condition, inst, on, db)
        if applies:
            out.append({"doc_code": r.doc_code, "label": r.label, "mandatory": mandatory, "source": r.source,
                        "condition": r.condition})
    return out


# --------------------------------------------------------------------------- versioning
def publish_new_version(db: Session, actor: User, reason: str, mutate) -> Ruleset:
    """Clone the active ruleset into version N+1, apply `mutate(new_ruleset, stage_map)`, retire the old one.
    Applications keep the version they were submitted under (pinned)."""
    if not reason.strip():
        raise Invalid("A reason / authority is required to publish a rule change")
    old = active_ruleset(db)
    new = Ruleset(code=old.code, version=old.version + 1, aph_edition=old.aph_edition, source_url=old.source_url,
                  status="ACTIVE", effective_from=clock.now(), published_by=actor.full_name, notes=reason)
    db.add(new)
    db.flush()
    stage_map: dict[int, StageDefinition] = {}
    for r in db.scalars(select(RouteTemplate).where(RouteTemplate.ruleset_id == old.id)):
        nr = RouteTemplate(ruleset_id=new.id, code=r.code, name=r.name, description=r.description,
                           source_type=r.source_type, aph_reference=r.aph_reference)
        for s in r.stages:
            ns = StageDefinition(code=s.code, name=s.name, order=s.order, sla_days=s.sla_days,
                                 assignee_role=s.assignee_role, conditional=s.conditional,
                                 on_deficiency=s.on_deficiency, managed_by=s.managed_by)
            nr.stages.append(ns)
            stage_map[s.id] = ns
        db.add(nr)
    for t in db.scalars(select(ApplicationTypeDef).where(ApplicationTypeDef.ruleset_id == old.id)):
        db.add(ApplicationTypeDef(ruleset_id=new.id, code=t.code, label=t.label, chapter=t.chapter,
                                  table_row=t.table_row, route_code=t.route_code, notice_category=t.notice_category,
                                  notice_verified=t.notice_verified, checklist_code=t.checklist_code,
                                  initiated_by=t.initiated_by, note=t.note))
    for d in db.scalars(select(DocumentRequirement).where(DocumentRequirement.ruleset_id == old.id)):
        db.add(DocumentRequirement(ruleset_id=new.id, checklist_code=d.checklist_code, doc_code=d.doc_code,
                                   label=d.label, condition=d.condition, source=d.source))
    db.flush()
    change = mutate(new, stage_map)
    old.status, old.effective_to = "RETIRED", clock.now()
    audit.record(db, actor=actor, action="RULESET_PUBLISHED", entity_type="ruleset", entity_id=new.id,
                 detail={"code": new.code, "from_version": old.version, "to_version": new.version, "change": change,
                         "note": "Applications already submitted keep their pinned version"},
                 reason=reason)
    return new
