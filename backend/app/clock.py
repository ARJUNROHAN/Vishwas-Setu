"""Clock and deadline arithmetic.

* Timestamps are stored as naive **UTC**; deadline semantics and display use **Asia/Kolkata**.
* Deadlines are counted in **calendar days** (the APH prescribes no working-day rule for these
  timings) and fall due at 17:30 IST on the last day.
* A demo clock offset (persisted in settings) lets the prototype fast-forward time.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from .models import Setting

IST = ZoneInfo("Asia/Kolkata")
OFFICE_CLOSE = time(17, 30)

_override: datetime | None = None
_offset_days: float | None = None


def _real_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def load_offset(db: Session) -> float:
    global _offset_days
    row = db.get(Setting, "clock_offset_days")
    _offset_days = float(row.value) if row else 0.0
    return _offset_days


def now(db: Session | None = None) -> datetime:
    """Current time, naive UTC."""
    if _override is not None:
        return _override
    if db is not None:
        load_offset(db)
    return _real_now() + timedelta(days=_offset_days or 0.0)


def to_ist(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc).astimezone(IST)


def today(db: Session | None = None) -> date:
    """Today's date in India."""
    return to_ist(now(db)).date()


def ist_close_of(d: date) -> datetime:
    """17:30 IST on date d, as naive UTC."""
    return datetime.combine(d, OFFICE_CLOSE, IST).astimezone(timezone.utc).replace(tzinfo=None)


def due_after_days(start: datetime, days: int) -> datetime:
    """Deadline = 17:30 IST on the calendar day `days` after `start` (IST date)."""
    return ist_close_of(to_ist(start).date() + timedelta(days=days))


def days_overdue(due_at: datetime, at: datetime) -> int:
    """Whole calendar days elapsed since the due instant (0 on the due day itself)."""
    if at <= due_at:
        return 0
    return (to_ist(at).date() - to_ist(due_at).date()).days


def advance(db: Session, days: float) -> datetime:
    offset = load_offset(db) + days
    row = db.get(Setting, "clock_offset_days")
    if row:
        row.value = str(offset)
    else:
        db.add(Setting(key="clock_offset_days", value=str(offset)))
    db.flush()
    global _offset_days
    _offset_days = offset
    return now()


@contextmanager
def frozen_at(moment: datetime):
    global _override
    prev = _override
    _override = moment
    try:
        yield
    finally:
        _override = prev


def set_frozen(moment: datetime | None):
    global _override
    _override = moment
