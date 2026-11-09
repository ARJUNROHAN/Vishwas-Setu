"""Deadline engine.

Every deadline is an Obligation. A periodic, repeat-safe tick:
  * sends advance reminders (T−n) once per offset, a due-today alert (T+0) and an overdue alert (T+1),
  * marks DUE_SOON / OVERDUE,
  * escalates level by level, recording an Escalation that the target role acknowledges,
and every send is de-duplicated by key, so re-running the tick never duplicates anything.
Emails are SIMULATED: recorded in the notification outbox and a log file, never sent.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from . import audit, clock
from .models import Escalation, EscalationPolicy, Notification, Obligation, User

log = logging.getLogger("obligations")
OUTBOX = Path(__file__).resolve().parent.parent / "storage" / "email_outbox_SIMULATED.log"

ROLE_LABEL = {
    "INSTITUTION": "Institution", "SCRUTINY_OFFICER": "Scrutiny officer", "RESCRUTINY_OFFICER": "Re-scrutiny officer",
    "EVC_COORDINATOR": "EVC coordinator", "EVC_MEMBER": "EVC member", "SHC_MEMBER": "SHC member",
    "SAC_MEMBER": "SAC member", "REGIONAL_HEAD": "Regional officer", "BUREAU": "Bureau officer",
    "COMPETENT_AUTHORITY": "Competent authority", "RULE_ADMIN": "Rule administrator", "ADMIN": "System administrator",
}


# --------------------------------------------------------------------------- recipients
def users_for_role(db: Session, role: str, region_id: int | None, institution_id: int | None) -> list[User]:
    q = select(User).where(User.role == role, User.active.is_(True))
    if role == "INSTITUTION":
        q = q.where(User.institution_id == institution_id)
    elif role not in ("BUREAU", "COMPETENT_AUTHORITY", "RULE_ADMIN", "SAC_MEMBER", "ADMIN") and region_id is not None:
        q = q.where(User.region_id == region_id)
    return list(db.scalars(q))


def owners(db: Session, ob: Obligation) -> list[User]:
    if ob.owner_user_id:
        u = db.get(User, ob.owner_user_id)
        return [u] if u else []
    return users_for_role(db, ob.owner_role, ob.region_id, ob.institution_id)


def link_for(ob: Obligation) -> str:
    if ob.application_id:
        return f"/applications/{ob.application_id}"
    if ob.subject_type == "undertaking":
        return "/compliance?tab=undertakings"
    if ob.subject_type == "document":
        return "/compliance?tab=documents"
    return "/deadlines"


def notify(db: Session, *, recipients: list[User], category: str, subject: str, body: str,
           dedupe_key: str, obligation: Obligation | None = None, link: str | None = None,
           channels: list[str] | None = None) -> int:
    sent = 0
    unique = {u.id: u for u in recipients if u is not None}
    for user in unique.values():
        for ch in channels or ["IN_APP", "EMAIL"]:
            exists = db.scalars(select(Notification.id).where(
                Notification.dedupe_key == dedupe_key, Notification.recipient_id == user.id,
                Notification.channel == ch)).first()
            if exists:
                continue
            db.add(Notification(
                obligation_id=obligation.id if obligation else None, recipient_id=user.id, channel=ch,
                category=category, subject=subject, body=body, dedupe_key=dedupe_key,
                status="SIMULATED" if ch == "EMAIL" else "DELIVERED", created_at=clock.now(), link=link,
                read_at=None if ch == "IN_APP" else clock.now()))
            if ch == "EMAIL":
                _write_outbox(user, subject)
            sent += 1
    db.flush()
    return sent


def _write_outbox(user: User, subject: str) -> None:
    try:
        OUTBOX.parent.mkdir(parents=True, exist_ok=True)
        with OUTBOX.open("a", encoding="utf-8") as f:
            f.write(f"[SIMULATED {clock.to_ist(clock.now()):%Y-%m-%d %H:%M} IST] To: {user.email} | {subject}\n")
    except OSError:
        log.warning("could not write simulated outbox")


# --------------------------------------------------------------------------- lifecycle
def open_obligation(db: Session, *, kind: str, title: str, subject_type: str, subject_id: int,
                    due_at: datetime, owner_role: str, owner_user_id: int | None = None,
                    application_id: int | None = None, institution_id: int | None = None,
                    region_id: int | None = None, actor: User | None = None,
                    source_reference: str = "") -> Obligation:
    ob = Obligation(kind=kind, title=title, subject_type=subject_type, subject_id=subject_id,
                    application_id=application_id, institution_id=institution_id, region_id=region_id,
                    owner_role=owner_role, owner_user_id=owner_user_id, opened_at=clock.now(), due_at=due_at,
                    source_reference=source_reference)
    db.add(ob)
    db.flush()
    audit.record(db, actor=actor, action="OBLIGATION_OPENED", entity_type="obligation", entity_id=ob.id,
                 application_id=application_id, institution_id=institution_id,
                 detail={"kind": kind, "title": title, "due_at": due_at.isoformat(), "owner_role": owner_role,
                         "owner_user_id": owner_user_id, "source": source_reference})
    evaluate(db, ob, _policies(db))
    return ob


def close_obligation(db: Session, ob: Obligation, reason: str, actor: User | None = None) -> None:
    if ob.state == "CLOSED":
        return
    late = clock.now() > ob.due_at
    ob.was_overdue = ob.was_overdue or late
    ob.state = "CLOSED"
    ob.closed_at = clock.now()
    ob.close_reason = reason
    for esc in db.scalars(select(Escalation).where(Escalation.obligation_id == ob.id, Escalation.resolved_at.is_(None))):
        esc.resolved_at = clock.now()
    audit.record(db, actor=actor, action="OBLIGATION_CLOSED", entity_type="obligation", entity_id=ob.id,
                 application_id=ob.application_id, institution_id=ob.institution_id,
                 detail={"kind": ob.kind, "on_time": not ob.was_overdue, "escalation_level": ob.escalation_level},
                 reason=reason)


def pause(db: Session, ob: Obligation, reason: str, actor: User | None = None) -> None:
    if ob.state in ("CLOSED", "PAUSED"):
        return
    ob.state = "PAUSED"
    ob.paused_since = clock.now()
    audit.record(db, actor=actor, action="CLOCK_PAUSED", entity_type="obligation", entity_id=ob.id,
                 application_id=ob.application_id, institution_id=ob.institution_id, reason=reason)


def resume(db: Session, ob: Obligation, actor: User | None = None) -> float:
    if ob.state != "PAUSED" or not ob.paused_since:
        return 0.0
    paused = clock.now() - ob.paused_since
    ob.due_at = ob.due_at + paused
    ob.paused_since = None
    ob.state = "UPCOMING"
    days = round(paused.total_seconds() / 86400, 2)
    audit.record(db, actor=actor, action="CLOCK_RESUMED", entity_type="obligation", entity_id=ob.id,
                 application_id=ob.application_id, institution_id=ob.institution_id,
                 detail={"paused_days": days, "new_due_at": ob.due_at.isoformat()})
    evaluate(db, ob, _policies(db))
    return days


def open_for(db: Session, subject_type: str, subject_id: int, kinds: list[str] | None = None) -> list[Obligation]:
    q = select(Obligation).where(Obligation.subject_type == subject_type, Obligation.subject_id == subject_id,
                                 Obligation.state != "CLOSED")
    if kinds:
        q = q.where(Obligation.kind.in_(kinds))
    return list(db.scalars(q))


# --------------------------------------------------------------------------- evaluation
def _policies(db: Session) -> dict[str, EscalationPolicy]:
    return {p.kind: p for p in db.scalars(select(EscalationPolicy))}


def evaluate(db: Session, ob: Obligation, policies: dict) -> dict:
    stats = {"reminders": 0, "overdue": 0, "escalations": 0}
    if ob.state in ("CLOSED", "PAUSED"):
        return stats
    now = clock.now()
    policy = policies.get(ob.kind)
    offsets = sorted(policy.reminder_offsets_days if policy else [2])
    steps = sorted(policy.escalation_steps if policy else [], key=lambda s: s["level"])
    days_left = (ob.due_at - now).total_seconds() / 86400
    if ob.kind == "APPEAL_WINDOW" and days_left < 0:
        close_obligation(db, ob, "Appeal window expired without an appeal")
        return stats
    link = link_for(ob)
    who = owners(db, ob)

    if days_left > 0:
        if clock.to_ist(ob.due_at).date() == clock.today():
            stats["reminders"] += notify(db, recipients=who, category="DUE_TODAY", obligation=ob, link=link,
                                         subject=f"Due today: {ob.title}",
                                         body=f"'{ob.title}' is due today by {clock.to_ist(ob.due_at):%H:%M} IST.",
                                         dedupe_key=f"ob{ob.id}:T+0")
        else:
            applicable = [o for o in offsets if days_left <= o]
            if applicable:
                off = min(applicable)
                stats["reminders"] += notify(
                    db, recipients=who, category="REMINDER", obligation=ob, link=link,
                    subject=f"Reminder: {ob.title} due {clock.to_ist(ob.due_at):%d %b %Y}",
                    body=f"'{ob.title}' is due on {clock.to_ist(ob.due_at):%d %b %Y} ({max(1, round(days_left))} day(s) left).",
                    dedupe_key=f"ob{ob.id}:T-{off}")

    new_state = "OVERDUE" if now > ob.due_at else ("DUE_SOON" if offsets and days_left <= max(offsets) else "UPCOMING")
    if new_state == "OVERDUE" and ob.state != "OVERDUE":
        stats["overdue"] += 1
        ob.was_overdue = True
        notify(db, recipients=who, category="OVERDUE", obligation=ob, link=link, subject=f"Overdue: {ob.title}",
               body=f"'{ob.title}' was due on {clock.to_ist(ob.due_at):%d %b %Y} and is now overdue.",
               dedupe_key=f"ob{ob.id}:T+1")
        audit.record(db, actor=None, action="OBLIGATION_OVERDUE", entity_type="obligation", entity_id=ob.id,
                     application_id=ob.application_id, institution_id=ob.institution_id,
                     detail={"kind": ob.kind, "due_at": ob.due_at.isoformat()})
    ob.state = new_state

    if new_state == "OVERDUE":
        over = clock.days_overdue(ob.due_at, now)
        for step in steps:
            if over >= step["after_days"] and ob.escalation_level < step["level"]:
                ob.escalation_level = step["level"]
                exists = db.scalars(select(Escalation).where(Escalation.obligation_id == ob.id,
                                                             Escalation.level == step["level"])).first()
                if not exists:
                    db.add(Escalation(obligation_id=ob.id, level=step["level"], target_role=step["to_role"],
                                      region_id=ob.region_id, created_at=now))
                targets = users_for_role(db, step["to_role"], ob.region_id, ob.institution_id)
                label = ROLE_LABEL.get(step["to_role"], step["to_role"])
                notify(db, recipients=targets + who, category="ESCALATION", obligation=ob, link=link,
                       subject=f"Escalation L{step['level']}: {ob.title}",
                       body=f"'{ob.title}' is {over} day(s) overdue (due {clock.to_ist(ob.due_at):%d %b %Y}). "
                            f"Escalated to {label} for acknowledgement.",
                       dedupe_key=f"ob{ob.id}:esc:{step['level']}")
                audit.record(db, actor=None, action="ESCALATED", entity_type="obligation", entity_id=ob.id,
                             application_id=ob.application_id, institution_id=ob.institution_id,
                             detail={"level": step["level"], "to_role": step["to_role"], "days_overdue": over,
                                     "kind": ob.kind})
                stats["escalations"] += 1
    return stats


def tick(db: Session) -> dict:
    """Re-evaluate all open obligations. Idempotent; recovers missed runs because it is state-based."""
    policies = _policies(db)
    total = {"evaluated": 0, "reminders": 0, "overdue": 0, "escalations": 0}
    for ob in db.scalars(select(Obligation).where(Obligation.state.notin_(["CLOSED", "PAUSED"]))):
        s = evaluate(db, ob, policies)
        total["evaluated"] += 1
        for k in ("reminders", "overdue", "escalations"):
            total[k] += s[k]
    db.flush()
    return total


def acknowledge(db: Session, esc: Escalation, user: User, note: str) -> None:
    from .errors import Forbidden, WorkflowError
    if user.role != esc.target_role or (esc.region_id and user.region_id not in (None, esc.region_id)):
        raise Forbidden("Only the role this was escalated to can acknowledge it")
    if esc.acknowledged_at:
        raise WorkflowError("Already acknowledged")
    esc.acknowledged_by, esc.acknowledged_at, esc.ack_note = user.id, clock.now(), note
    ob = esc.obligation
    audit.record(db, actor=user, action="ESCALATION_ACKNOWLEDGED", entity_type="escalation", entity_id=esc.id,
                 application_id=ob.application_id, institution_id=ob.institution_id,
                 detail={"level": esc.level, "obligation_id": ob.id}, reason=note or None)


def visible_filter(user: User):
    if user.role == "INSTITUTION":
        return Obligation.institution_id == user.institution_id
    if user.role in ("BUREAU", "ADMIN", "COMPETENT_AUTHORITY", "RULE_ADMIN", "SAC_MEMBER"):
        return True
    return or_(Obligation.region_id == user.region_id, Obligation.owner_user_id == user.id)


def due_in(days: int) -> datetime:
    return clock.now() + timedelta(days=days)
