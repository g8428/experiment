"""Lecture session windows in New York local time with automatic DST."""
from zoneinfo import ZoneInfo


NY = ZoneInfo("America/New_York")
WINDOWS = {
    "asian": (20 * 60, 24 * 60),
    "london": (2 * 60, 5 * 60),
    "new_york": (7 * 60, 10 * 60),
    "london_close": (10 * 60, 12 * 60),
    "pre_asian_marking": (15 * 60 + 30, 20 * 60),
    "cbdr": (14 * 60, 20 * 60),
}


def session_name(timestamp):
    local = timestamp.to_pydatetime().astimezone(NY)
    minute = local.hour * 60 + local.minute
    for name in ("asian", "london", "new_york", "london_close", "cbdr", "pre_asian_marking"):
        start, end = WINDOWS[name]
        if start <= minute < end or (end == 24 * 60 and minute >= start):
            return name
    return None


def entries_allowed(timestamp):
    """Only the four lecture killzones; no new trades after London close."""
    return session_name(timestamp) in {"asian", "london", "new_york"}


def is_early_session_judas(timestamp, minutes=30):
    """Flag the initial interval of London/New York/Asian for OTE caution."""
    local = timestamp.to_pydatetime().astimezone(NY)
    minute = local.hour * 60 + local.minute
    starts = (20 * 60, 2 * 60, 7 * 60)
    return any(start <= minute < start + minutes for start in starts)
