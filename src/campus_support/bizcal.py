"""Business-hours calendar arithmetic. All timestamps are naive campus-local, minute granular."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

_MAX_DAYS = 4000


@dataclass(frozen=True)
class Calendar:
    calendar_id: str
    hours: dict          # weekday (Mon=0) -> (open_minute_of_day, close_minute_of_day)
    holidays: frozenset = field(default_factory=frozenset)

    def window(self, d: date):
        if d in self.holidays:
            return None
        h = self.hours.get(d.weekday())
        if not h:
            return None
        base = datetime.combine(d, time.min)
        return base + timedelta(minutes=h[0]), base + timedelta(minutes=h[1])


def _next_midnight(dt: datetime) -> datetime:
    return datetime.combine(dt.date() + timedelta(days=1), time.min)


def add_business_minutes(cal: Calendar, start: datetime, minutes: float) -> datetime:
    """Instant reached after consuming `minutes` of open time, starting at `start`.
    A start outside open hours begins counting at the next opening."""
    cur, remaining = start, float(minutes)
    for _ in range(_MAX_DAYS):
        w = cal.window(cur.date())
        if w is None or cur >= w[1]:
            cur = _next_midnight(cur)
            continue
        if cur < w[0]:
            cur = w[0]
        avail = (w[1] - cur).total_seconds() / 60
        if remaining <= avail:
            return cur + timedelta(minutes=remaining)
        remaining -= avail
        cur = _next_midnight(cur)
    raise RuntimeError("calendar has no open time")


def business_minutes_between(cal: Calendar, a: datetime, b: datetime) -> int:
    """Open minutes in [a, b). Zero if b <= a."""
    if b <= a:
        return 0
    total, d = 0.0, a.date()
    while d <= b.date():
        w = cal.window(d)
        if w is not None:
            lo, hi = max(a, w[0]), min(b, w[1])
            if hi > lo:
                total += (hi - lo).total_seconds() / 60
        d += timedelta(days=1)
    return int(round(total))


def is_open(cal: Calendar, dt: datetime) -> bool:
    w = cal.window(dt.date())
    return w is not None and w[0] <= dt < w[1]


# Synthetic campus closures (observed-holiday style) inside the dataset horizon.
HOLIDAYS_2026 = [
    (date(2026, 1, 1), "New Year's Day"),
    (date(2026, 1, 19), "Winter Observance Day"),
    (date(2026, 2, 16), "Presidents' Day"),
    (date(2026, 5, 25), "Memorial Day"),
    (date(2026, 6, 19), "Juneteenth"),
    (date(2026, 7, 3), "Independence Day (observed)"),
    (date(2026, 9, 7), "Labor Day"),
    (date(2026, 10, 12), "Fall Observance Day"),
    (date(2026, 11, 26), "Thanksgiving"),
    (date(2026, 11, 27), "Thanksgiving Recess"),
    (date(2026, 12, 24), "Winter Recess"),
    (date(2026, 12, 25), "Winter Recess"),
]

# (calendar_id, name, {weekday: (open_min, close_min)})
CALENDAR_DEFS = [
    ("CAL-STD", "Standard office hours (Mon-Fri 09:00-17:00)",
     {d: (9 * 60, 17 * 60) for d in range(5)}),
    ("CAL-EXT", "Extended help-desk hours (Mon-Fri 08:00-20:00, Sat 10:00-14:00)",
     {**{d: (8 * 60, 20 * 60) for d in range(5)}, 5: (10 * 60, 14 * 60)}),
]


def calendar_24x7(calendar_id: str = "CAL-24X7") -> Calendar:
    """Wall-clock calendar used only to reproduce the 'ignores business hours' defect."""
    return Calendar(calendar_id, {d: (0, 1440) for d in range(7)}, frozenset())
