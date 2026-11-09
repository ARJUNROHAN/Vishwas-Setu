"""Append-only, hash-chained audit trail.

Each event stores the hash of the previous event; altering or deleting any past row
breaks the chain, which `verify_chain` detects.
"""
from __future__ import annotations

import hashlib
import json
from contextvars import ContextVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import clock
from .models import AuditEvent, User

GENESIS = "0" * 64
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def _digest(prev_hash: str, payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256((prev_hash + body).encode()).hexdigest()


def _payload(ev: AuditEvent) -> dict:
    return {
        "seq": ev.seq, "ts": ev.ts.isoformat(), "actor_id": ev.actor_id,
        "actor_label": ev.actor_label, "action": ev.action, "entity_type": ev.entity_type,
        "entity_id": ev.entity_id, "application_id": ev.application_id,
        "institution_id": ev.institution_id, "detail": ev.detail, "reason": ev.reason,
        "request_id": ev.request_id,
    }


def record(db: Session, *, actor: User | None, action: str, entity_type: str, entity_id: int,
           application_id: int | None = None, institution_id: int | None = None,
           detail: dict | None = None, reason: str | None = None) -> AuditEvent:
    last = db.scalars(select(AuditEvent).order_by(AuditEvent.seq.desc()).limit(1)).first()
    prev_hash = last.hash if last else GENESIS
    seq = (last.seq + 1) if last else 1
    label = f"{actor.full_name} ({actor.role})" if actor else "System"
    ev = AuditEvent(
        seq=seq, ts=clock.now(), actor_id=actor.id if actor else None, actor_label=label,
        action=action, entity_type=entity_type, entity_id=entity_id,
        application_id=application_id, institution_id=institution_id,
        detail=detail or {}, reason=reason, request_id=request_id_var.get(), prev_hash=prev_hash, hash="",
    )
    ev.hash = _digest(prev_hash, _payload(ev))
    db.add(ev)
    db.flush()
    return ev


def verify_chain(db: Session) -> dict:
    prev = GENESIS
    count = 0
    for ev in db.scalars(select(AuditEvent).order_by(AuditEvent.seq)):
        count += 1
        if ev.prev_hash != prev or _digest(prev, _payload(ev)) != ev.hash:
            return {"valid": False, "events_checked": count, "broken_at_seq": ev.seq}
        prev = ev.hash
    return {"valid": True, "events_checked": count, "head_hash": prev}
