"""POI lifecycle events: first retest, mitigation and close invalidation."""
from dataclasses import dataclass

from .zones import Zone


@dataclass(frozen=True)
class ZoneLifecycle:
    zone: Zone
    first_touch: int
    invalidated: int
    mitigation_count: int


def zone_lifecycles(frame, zones):
    """Track only bars strictly after zone availability to prevent lookahead."""
    result = []
    for zone in zones:
        first_touch, invalidated, touches = -1, len(frame), 0
        for i in range(zone.available + 1, len(frame)):
            bar = frame.iloc[i]
            if zone.side == 1 and float(bar.c) < zone.low:
                invalidated = i
                break
            if zone.side == -1 and float(bar.c) > zone.high:
                invalidated = i
                break
            if float(bar.l) <= zone.high and float(bar.h) >= zone.low:
                touches += 1
                if first_touch < 0:
                    first_touch = i
        result.append(ZoneLifecycle(zone, first_touch, invalidated, touches))
    return result


def active_at(lifecycle, bar_index):
    return (lifecycle.zone.available < bar_index and lifecycle.invalidated > bar_index and
            (lifecycle.first_touch < 0 or lifecycle.first_touch >= bar_index))
