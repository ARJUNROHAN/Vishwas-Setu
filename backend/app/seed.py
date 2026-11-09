"""Seed rules and a fictional demo dataset, replaying history through the real engines.

Includes the three blueprint scenario institutions:
  Demo A — Northern Demo Institute (increase in intake, clean slate for the live walk-through)
  Demo B — Western Demo College (leased land near the cl. 2.1(e) threshold, fire certificate near expiry,
           building older than 30 years with a structural stability certificate)
  Demo C — Central Demo Polytechnic (security-deposit undertaking from a synthetic approval order, due soon)
All institutions, people and numbers are fictional.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import clock, compliance, evc, obligations as obl, rules, workflow
from .auth import hash_password
from .config_data import APPLICATION_TYPES, CALENDARS, CHECKLISTS, POLICIES, REGIONS, ROUTES, RULESET, SETTINGS
from .db import Base, engine
from .models import (
    AcademicCalendar, Application, ApplicationTypeDef, DocumentRequirement, EscalationPolicy, EvcVisit, Expert,
    Institution, Region, RouteTemplate, Ruleset, Setting, StageDefinition, TrackedDocument, Undertaking, User,
)

DEMO_PASSWORD = "demo123"
CITY_BY_STATE = {
    "Uttar Pradesh": ["Kanpur", "Lucknow", "Prayagraj", "Varanasi"], "Bihar": ["Patna", "Gaya"],
    "Jharkhand": ["Ranchi", "Dhanbad"], "Maharashtra": ["Pune", "Nagpur", "Nashik", "Kolhapur"], "Goa": ["Panaji"],
    "Tamil Nadu": ["Coimbatore", "Madurai", "Salem", "Vellore"], "Puducherry": ["Puducherry"],
    "Madhya Pradesh": ["Bhopal", "Indore", "Jabalpur"], "Chhattisgarh": ["Raipur", "Bilaspur"],
}
NAME_A = ["Aranya", "Bhaskara", "Chitrakoot", "Devagiri", "Ekalavya", "Gangotri", "Himadri", "Jyotirmay", "Kaveri",
          "Lokmanya", "Madhuvan", "Nalanda Vihar", "Omkar", "Pragati", "Rudraksh", "Sahyadri", "Tapovan", "Udayagiri",
          "Vaishali", "Yamunotri", "Akashdeep", "Brahmaputra", "Charak", "Dhanvantari", "Garuda", "Malaya", "Narmada",
          "Prabhat", "Sankalp", "Trivikram", "Vasundhara", "Shivalik", "Saptagiri", "Neelgiri", "Satpura", "Vindhya"]
NAME_B = ["Institute of Technology", "College of Engineering", "Institute of Management Studies", "Polytechnic",
          "School of Engineering & Technology", "Institute of Computer Applications"]
PEOPLE = ["A. Sharma", "R. Iyer", "P. Kulkarni", "S. Verma", "M. Nair", "K. Reddy", "N. Banerjee", "V. Patil",
          "D. Mishra", "L. Pillai", "T. Joshi", "G. Menon", "H. Saxena", "J. Rao", "B. Deshpande", "C. Natarajan",
          "F. Khan", "E. Bose", "I. Dutta", "O. Chauhan", "U. Hegde", "Y. Thakur", "W. Bhatia", "Z. Ansari"]
EXPERT_POOL = [
    ("Prof. Anil Khurana", "Civil Engineering", "Delhi"), ("Dr. Meera Raghavan", "Computer Science", "Karnataka"),
    ("Prof. Sunil Bhatt", "Mechanical Engineering", "Gujarat"), ("Dr. Farah Siddiqui", "Electronics", "Telangana"),
    ("Prof. Gopal Mehta", "Management", "Rajasthan"), ("Dr. Kavita Rao", "Architecture", "Karnataka"),
    ("Prof. Rakesh Tiwari", "Electrical Engineering", "Madhya Pradesh"), ("Dr. Anita Das", "Computer Applications", "West Bengal"),
    ("Prof. Harish Chandra", "Civil Engineering", "Uttar Pradesh"), ("Dr. Pooja Kulkarni", "Chemical Engineering", "Maharashtra"),
    ("Prof. S. Venkatesh", "Mechanical Engineering", "Tamil Nadu"), ("Dr. Imran Qureshi", "Electronics", "Delhi"),
    ("Prof. Neha Agarwal", "Management", "Haryana"), ("Dr. Joseph Mathew", "Computer Science", "Kerala"),
    ("Prof. Ritu Kapoor", "Information Technology", "Punjab"), ("Dr. Arvind Swamy", "Electrical Engineering", "Andhra Pradesh"),
]
PROGRAMMES = ["B.Tech Computer Science & Engineering", "B.Tech Civil Engineering", "MBA", "MCA",
              "Diploma in Mechanical Engineering", "B.Tech Electronics & Communication", "BBA", "BCA",
              "B.Tech Artificial Intelligence & Data Science", "M.Tech VLSI Design"]
TYPE_WEIGHTS = [("EOA_SELF_DISCLOSURE", 26), ("INCREASE_INTAKE", 20), ("NEW_PROGRAMME_LEVEL", 7), ("CHANGE_OF_SITE", 4),
                ("DIPLOMA_DEGREE_CONVERSION", 3), ("NAME_OR_TYPE_CHANGE", 4), ("CLOSURE_OF_COURSE", 3),
                ("COURSE_NAME_MERGER_REDUCTION", 3), ("BANK_DETAILS_CHANGE", 2), ("COLLABORATION_TWINNING", 2),
                ("INTEGRATED_DUAL_DEGREE", 2), ("NRI_SEATS", 3), ("OFF_CAMPUS", 1)]
FINDINGS = [
    ("Affidavit 2 not in the prescribed format", "Affidavit 2 (Annexure 2)", "Upload Affidavit 2 on non-judicial stamp paper as prescribed"),
    ("Land conversion certificate not uploaded", "Land documents (Annexure 1)", "Upload the land conversion certificate"),
    ("Occupancy certificate does not cover the new block", "Occupancy / Completion Certificate", "Upload the revised occupancy certificate"),
    ("Fire safety certificate has expired", "Fire Safety Certificate", "Upload a valid fire safety certificate"),
    ("Audited accounts are for an earlier year", "Audited statement of accounts", "Upload previous year's audited accounts"),
]


def reset_db() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


# --------------------------------------------------------------------------- rules
def seed_rules(db: Session) -> Ruleset:
    for key, value, unit, st, src in SETTINGS:
        db.add(Setting(key=key, value=value, unit=unit, source_type=st, source=src))
    rs = Ruleset(code=RULESET["code"], version=RULESET["version"], aph_edition=RULESET["aph_edition"],
                 source_url=RULESET["source_url"], status="ACTIVE",
                 effective_from=datetime.fromisoformat(RULESET["effective_from"]), notes=RULESET["notes"])
    db.add(rs)
    db.flush()
    for r in ROUTES:
        rt = RouteTemplate(ruleset_id=rs.id, code=r["code"], name=r["name"], description=r["description"],
                           source_type=r["source_type"], aph_reference=r["source"])
        for order, s in enumerate(r["stages"], start=1):
            rt.stages.append(StageDefinition(code=s["code"], name=s["name"], order=order, sla_days=s["sla"],
                                             assignee_role=s["role"], conditional=s.get("conditional", False),
                                             on_deficiency=s.get("on_deficiency", "RETURN"),
                                             managed_by=s.get("managed_by", "officer")))
        db.add(rt)
    for t in APPLICATION_TYPES:
        db.add(ApplicationTypeDef(ruleset_id=rs.id, code=t["code"], label=t["label"], chapter=t["chapter"],
                                  table_row=t["row"], route_code=t["route"], notice_category=t["notice"],
                                  notice_verified=t["notice_verified"], checklist_code=t["checklist"],
                                  initiated_by=t.get("initiated_by", "INSTITUTION"), note=t.get("note", "")))
    for code, cl in CHECKLISTS.items():
        for doc_code, label, cond in cl["items"]:
            db.add(DocumentRequirement(ruleset_id=rs.id, checklist_code=code, doc_code=doc_code, label=label,
                                       condition=cond, source=cl["source"]))
    for c in CALENDARS:
        db.add(AcademicCalendar(academic_year=c["academic_year"], notice_ref=c["notice_ref"],
                                application_open=date.fromisoformat(c["application_open"]),
                                application_close=date.fromisoformat(c["application_close"]), odl_cycles=c["odl_cycles"]))
    for p in POLICIES:
        db.add(EscalationPolicy(kind=p["kind"], name=p["name"], reminder_offsets_days=p["reminders"],
                                escalation_steps=p["steps"]))
    db.flush()
    return rs


# --------------------------------------------------------------------------- people & institutions
def _user(db, username, name, role, designation, region=None, inst=None, expert=None) -> User:
    u = User(username=username, full_name=name, email=f"{username}@demo.vishwas-setu.in", role=role,
             designation=designation, region_id=region.id if region else None, institution_id=inst.id if inst else None,
             expert_id=expert.id if expert else None, password_hash=hash_password(DEMO_PASSWORD))
    db.add(u)
    return u


def _inst(db, rng, reg, name, city, state, itype, is_new, tenure, building_year, pid):
    inst = Institution(permanent_id=f"1-{pid}{rng.randint(100000, 999999)}", name=f"{name}, {city}", city=city,
                       state=state, region_id=reg.id, institution_type=itype,
                       max_course_years=3 if any(k in name for k in ("Polytechnic", "Management", "Computer")) else 4,
                       is_new=is_new, land_tenure=tenure,
                       building_completion_date=date(building_year, rng.randint(1, 12), 15) if building_year else None)
    db.add(inst)
    db.flush()
    _user(db, f"inst{inst.id}", f"Principal, {name}", "INSTITUTION", "Principal / Director", reg, inst)
    return inst


def seed_people(db: Session, rng: random.Random) -> dict:
    regions, institutions = {}, []
    people = iter(PEOPLE * 4)
    used = set()
    pid = 1000
    experts = []
    for name, exp, state in EXPERT_POOL:
        e = Expert(name=name, expertise=exp, home_state=state, organisation=f"Faculty, {state}")
        db.add(e)
        experts.append(e)
    db.flush()
    for i, e in enumerate(experts, start=1):
        _user(db, f"expert{i}", e.name, "EVC_MEMBER", f"EVC panel expert, {e.expertise}", None, None, e)
    for r in REGIONS:
        reg = Region(code=r["code"], name=r["name"], office_city=r["office_city"])
        db.add(reg)
        db.flush()
        regions[r["code"]] = reg
        c = r["code"].lower()
        _user(db, f"{c}.scrutiny1", next(people), "SCRUTINY_OFFICER", f"Assistant Director, {reg.name} RO", reg)
        _user(db, f"{c}.scrutiny2", next(people), "SCRUTINY_OFFICER", f"Assistant Director, {reg.name} RO", reg)
        _user(db, f"{c}.rescrutiny", next(people), "RESCRUTINY_OFFICER", f"Re-Scrutiny Committee, {reg.name}", reg)
        _user(db, f"{c}.evc", next(people), "EVC_COORDINATOR", f"Deputy Director (EVC), {reg.name} RO", reg)
        _user(db, f"{c}.shc", next(people), "SHC_MEMBER", f"Standing Hearing Committee, {reg.name}", reg)
        _user(db, f"{c}.head", next(people), "REGIONAL_HEAD", f"Regional Officer, {reg.name} RO, {reg.office_city}", reg)
        count = 6 if r["code"] == "CRO" else 11
        for i in range(count):
            state = rng.choice(r["states"])
            while True:
                nm = f"{rng.choice(NAME_A)} {rng.choice(NAME_B)}"
                if nm not in used:
                    used.add(nm)
                    break
            pid += rng.randint(3, 40)
            institutions.append(_inst(db, rng, reg, nm, rng.choice(CITY_BY_STATE[state]), state,
                                      rng.choice(["Private-Self Financing"] * 4 + ["Government", "Government aided"]),
                                      i < 2, "LEASED" if rng.random() < 0.55 else "OWNED",
                                      rng.choice([1985, 1990, 1994, 2001, 2008, 2012, 2016]), pid))
    # blueprint scenario institutions
    demo = {
        "A": _inst(db, rng, regions["NRO"], "Northern Demo Institute", "Lucknow", "Uttar Pradesh", "Private-Self Financing",
                   False, "OWNED", 2010, 9001),
        "B": _inst(db, rng, regions["WRO"], "Western Demo College", "Pune", "Maharashtra", "Private-Self Financing",
                   False, "LEASED", 1992, 9002),
        "C": _inst(db, rng, regions["CRO"], "Central Demo Polytechnic", "Bhopal", "Madhya Pradesh", "Private-Self Financing",
                   False, "OWNED", 2005, 9003),
    }
    _user(db, "sac1", "Prof. V. Raman", "SAC_MEMBER", "Member, Standing Appellate Committee")
    _user(db, "bureau", "Dr. R. K. Prasad", "BUREAU", "Advisor, Regulation Bureau (Approval)")
    _user(db, "bureau2", "Ms. S. Chatterjee", "BUREAU", "Director, Regulation Bureau")
    _user(db, "authority", "Shri A. K. Menon", "COMPETENT_AUTHORITY", "Member Secretary (for the Executive Committee)")
    _user(db, "ruleadmin", "Ms. P. Iyengar", "RULE_ADMIN", "Rule administrator, Regulation Bureau")
    _user(db, "admin", "System Administrator", "ADMIN", "e-Governance cell")
    db.flush()
    return {"regions": regions, "institutions": institutions, "demo": demo}


# --------------------------------------------------------------------------- history replay
def _pick_type(rng):
    total = sum(w for _, w in TYPE_WEIGHTS)
    x = rng.uniform(0, total)
    for t, w in TYPE_WEIGHTS:
        x -= w
        if x <= 0:
            return t
    return "EOA_SELF_DISCLOSURE"


def simulate_application(db: Session, rng: random.Random, inst: Institution, app_type: str, age_days: int,
                         now: datetime, sloth: float, max_steps: int = 14) -> Application:
    t = (now - timedelta(days=age_days)).replace(hour=5, minute=rng.randint(0, 59), second=0)
    inst_user = db.scalars(select(User).where(User.institution_id == inst.id)).first()
    authority = db.scalars(select(User).where(User.role == "COMPETENT_AUTHORITY")).first()
    rule_admin = db.scalars(select(User).where(User.role == "RULE_ADMIN")).first()
    coord = db.scalars(select(User).where(User.role == "EVC_COORDINATOR", User.region_id == inst.region_id)).first()
    with clock.frozen_at(t):
        app = workflow.submit_application(
            db, institution=inst, application_type=app_type, academic_year="2027-28", actor=inst_user,
            programme=rng.choice(PROGRAMMES) if app_type in ("INCREASE_INTAKE", "NEW_PROGRAMME_LEVEL", "INTEGRATED_DUAL_DEGREE",
                                                            "DIPLOMA_DEGREE_CONVERSION", "NEW_INSTITUTION") else "",
            intake_requested=rng.choice([30, 60, 60, 120]) if app_type == "INCREASE_INTAKE" else None,
            enforce_checklist=False)
    returned_once = False
    for _ in range(max_steps):
        db.refresh(app)
        slow = rng.random() < sloth
        si = workflow.current_instance(app)
        officer_stage = app.status == "IN_PROGRESS" and si and workflow.stage_def(app, si.stage_code).managed_by != "evc"
        step = (rng.randint(15, 28) if slow else rng.randint(4, 12)) if officer_stage else \
            (rng.randint(12, 20) if slow else rng.randint(3, 10)) if app.status == "READY_FOR_DECISION" else \
            (rng.randint(10, 20) if slow else rng.randint(2, 7))
        t = t + timedelta(days=step)
        if t >= now:
            return app
        with clock.frozen_at(t.replace(hour=5 + step % 6)):
            db.refresh(app)
            if app.status == "IN_PROGRESS":
                si = workflow.current_instance(app)
                sd = workflow.stage_def(app, si.stage_code)
                officer = si.assignee
                if sd.managed_by == "evc":
                    visit = db.scalars(select(EvcVisit).where(EvcVisit.stage_instance_id == si.id)).first()
                    if visit.status == "QUEUED":
                        on = (clock.to_ist(clock.now()) + timedelta(days=rng.randint(2, 6))).date()
                        mode = rng.choice(["PHYSICAL", "PHYSICAL", "ONLINE"])
                        evc.schedule(db, visit, coord, on, evc.draw_panel(db, visit, on, seed=visit.id), mode)
                        t = datetime.combine(on, datetime.min.time()).replace(hour=4)
                    elif visit.status == "SCHEDULED" and clock.today() >= visit.scheduled_on:
                        member = db.scalars(select(User).where(User.expert_id == visit.panel[0]["id"])).first()
                        ok = rng.random() < 0.72
                        evc.submit_report(db, visit, member, "CLEAR" if ok else "DEFICIENCY_FOUND",
                                          "Readiness verified in all areas." if ok else rng.choice([
                                              "Shortfall of 2 faculty; laboratory equipment incomplete.",
                                              "Built-up area short by 420 sq.m; library not as per norms."]), None,
                                          video_url="https://video.example.org/evc-demo" if visit.mode == "ONLINE" else None,
                                          video_minutes=34 if visit.mode == "ONLINE" else None)
                elif sd.managed_by == "deficiency_review":
                    items = [d for d in workflow.open_deficiencies(db, app) if d.status == "RESPONDED"]
                    verdicts = {d.id: {"resolved": rng.random() < 0.85, "remarks": "Checked against the uploaded evidence."}
                                for d in items}
                    workflow.verify_deficiencies(db, app, officer, verdicts, "Recorded deficiencies re-verified.")
                elif sd.managed_by == "rule_review":
                    workflow.assign_route(db, app, rule_admin, "SCRUTINY_EVC_CONDITIONAL",
                                          "Off-campus treated as scrutiny + EVC pending notification review (demo)")
                else:
                    roll = rng.random()
                    if roll < 0.08 and not returned_once and sd.code == "SCRUTINY":
                        returned_once = True
                        workflow.return_for_clarification(db, app, officer, "Please upload the latest encumbrance certificate.")
                    elif roll < 0.30 and sd.code in ("SCRUTINY", "SELF_DISCLOSURE", "SHC"):
                        picks = rng.sample(FINDINGS, rng.randint(1, 2))
                        workflow.record_outcome(db, app, officer, "DEFICIENCY", "Deficiencies observed; see items.",
                                                deficiencies=[{"finding": f, "reference": r, "correction": c} for f, r, c in picks])
                    else:
                        workflow.record_outcome(db, app, officer, "NIL_DEFICIENCY", "Documents verified; no deficiency observed.")
            elif app.status == "RETURNED":
                if rng.random() < 0.8:
                    items = workflow.open_deficiencies(db, app)
                    workflow.institution_respond(db, app, inst_user, "Compliance submitted against each deficiency.", [],
                                                 item_responses={d.id: {"response": "Corrected document uploaded.", "file_ids": []}
                                                                 for d in items if d.status == "OPEN"})
            elif app.status == "READY_FOR_DECISION":
                if rng.random() < 0.7:
                    rec = app.recommendation == "RECOMMENDED"
                    workflow.decide(db, app, authority, "APPROVED" if rec else "REJECTED",
                                    "As recommended by the committees." if rec else "Deficiencies not complied.",
                                    decision_ref=f"F.No. {inst.region.code}/{app.id:04d}/2027-28/EOA")
            elif app.status == "APPROVED":
                officer = db.scalars(select(User).where(User.role == "SCRUTINY_OFFICER", User.region_id == inst.region_id)).first()
                pending = list(db.scalars(select(Undertaking).where(Undertaking.application_id == app.id)))
                if not pending:
                    return app
                for u in pending:
                    if u.status == "OPEN" and rng.random() < 0.7:
                        compliance.submit_evidence(db, u, inst_user, "Proof and affidavit uploaded.", [0])
                    elif u.status == "SUBMITTED" and rng.random() < 0.75:
                        compliance.verify_undertaking(db, u, officer, True, "Verified against original documents.")
            elif app.status == "REJECTED":
                if rng.random() < 0.4:
                    workflow.file_appeal(db, app, inst_user, "Deficiencies since complied; request reconsideration.")
                return app
            else:
                return app
    return app


def _doc(db, inst, doc_type, valid_from, valid_until, issuer="", ref=""):
    d = TrackedDocument(institution_id=inst.id, doc_type=doc_type, title=compliance.DOC_TYPES[doc_type],
                        valid_from=valid_from, valid_until=valid_until, verification_status="VERIFIED",
                        issuer_name=issuer, reference_no=ref)
    db.add(d)
    db.flush()
    compliance.track_document(db, d, None)
    return d


def seed_documents(db: Session, rng: random.Random, institutions, now: datetime) -> None:
    today = clock.to_ist(now).date()
    scen = 0
    for inst in institutions:
        with clock.frozen_at(now - timedelta(days=200)):
            if inst.land_tenure == "LEASED":
                scen += 1
                crit_in = [rng.randint(-25, -3), rng.randint(4, 40), rng.randint(60, 200), rng.randint(900, 7000)][scen % 4]
                critical = today + timedelta(days=crit_in)
                vu = critical.replace(year=critical.year + inst.max_course_years)
                _doc(db, inst, "LAND_LEASE", vu.replace(year=vu.year - 30), vu, "Sub-Registrar", f"REG/{inst.id}/LL")
            exp_in = rng.choice([rng.randint(-12, -2), rng.randint(3, 25), rng.randint(40, 120), rng.randint(200, 700)])
            _doc(db, inst, "FIRE_NOC", today + timedelta(days=exp_in - 730), today + timedelta(days=exp_in),
                 "State Fire Services", f"FIRE/{inst.id}")
            age = rules.building_age_years(inst, today)
            if age and age > 30 and rng.random() < 0.6:  # some old buildings have no certificate → MISSING
                issued = today - timedelta(days=rng.randint(200, 1700))
                _doc(db, inst, "STABILITY_CERT", issued, issued.replace(year=issued.year + 5), "Structural engineer",
                     f"SSC/{inst.id}")
        if not inst.is_new and rng.random() < 0.3:
            due = today + timedelta(days=rng.choice([-20, -6, 9, 25, 160, 400]))
            with clock.frozen_at(now - timedelta(days=3 * 365 - 30)):
                compliance.create_undertaking(db, inst, "ACCREDITATION", None, due_on=due,
                                              source_document="EoA order 2024-25 (synthetic)")


def seed_demo_scenarios(db: Session, demo: dict, now: datetime) -> None:
    today = clock.to_ist(now).date()
    a, b, c = demo["A"], demo["B"], demo["C"]
    with clock.frozen_at(now - timedelta(days=100)):
        _doc(db, a, "FIRE_NOC", today - timedelta(days=200), today + timedelta(days=500), "UP Fire Services", "UPFS/5512")
    with clock.frozen_at(now - timedelta(days=150)):
        crit = today + timedelta(days=20)  # lease review threshold within the risk window
        vu = crit.replace(year=crit.year + b.max_course_years)
        _doc(db, b, "LAND_LEASE", vu.replace(year=vu.year - 30), vu, "Sub-Registrar, Pune", "REG/PUNE/1996/4471")
        _doc(db, b, "FIRE_NOC", today - timedelta(days=700), today + timedelta(days=12), "Maharashtra Fire Services",
             "MFS/2024/8812")
        _doc(db, b, "STABILITY_CERT", today - timedelta(days=1700), (today - timedelta(days=1700)).replace(
            year=(today - timedelta(days=1700)).year + 5), "Chartered structural engineer", "SSC/2022/119")
    with clock.frozen_at(now - timedelta(days=40)):
        _doc(db, c, "FIRE_NOC", today - timedelta(days=300), today + timedelta(days=400), "MP Fire Services", "MPFS/7781")
    with clock.frozen_at(now - timedelta(days=10)):
        compliance.create_undertaking(db, c, "SECURITY_DEPOSIT", None, due_on=today + timedelta(days=5),
                                      source_document="Synthetic order F.No. CRO/DEMO-C/2027-28 (demo)")


def seed_all(db: Session, seed: int = 2027) -> dict:
    rng = random.Random(seed)
    seed_rules(db)
    data = seed_people(db, rng)
    now = clock.now(db)
    insts = [i for i in data["institutions"]]
    count = 0
    for inst in insts:
        if inst.is_new:
            simulate_application(db, rng, inst, "NEW_INSTITUTION", rng.randint(5, 55), now, sloth=0.25)
            count += 1
    for _ in range(110):
        inst = rng.choice([i for i in insts if not i.is_new])
        simulate_application(db, rng, inst, _pick_type(rng), rng.randint(1, 75), now, sloth=rng.choice([0.08, 0.15, 0.3]))
        count += 1
    with clock.frozen_at(now - timedelta(days=30)):
        council = db.scalars(select(User).where(User.role == "BUREAU")).first()
        for inst in rng.sample([i for i in insts if i.is_new], 2):
            workflow.submit_application(db, institution=inst, application_type="PRE_FIRST_BATCH_INSPECTION",
                                        academic_year="2027-28", actor=council, enforce_checklist=False, initiated_by="COUNCIL")
            count += 1
    seed_documents(db, rng, insts, now)
    seed_demo_scenarios(db, data["demo"], now)
    db.flush()
    stats = obl.tick(db)
    compliance.sync_statuses(db)
    return {"applications": count, "institutions": len(insts) + 3, "tick": stats}


def run(seed: int = 2027) -> dict:
    from .db import session_scope
    reset_db()
    with session_scope() as db:
        return seed_all(db, seed)


if __name__ == "__main__":
    print(run())
