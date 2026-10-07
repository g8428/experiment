"""Advanced block families described in lecture 7.

Block detection is an event layer: block zones are never entry signals by
themselves. Strategy code must apply HTF context, liquidity and retest rules.
"""
from dataclasses import dataclass

from .structure import StructureBreak, Swing
from .zones import Zone, fair_value_gaps


@dataclass(frozen=True)
class BlockEvent:
    zone: Zone
    trigger: int
    rule: str


def _last_opposite_group(frame, before, side):
    """side +1 finds a down candle; side -1 finds an up candle."""
    for i in range(before - 1, -1, -1):
        row = frame.iloc[i]
        if (side == 1 and float(row.c) < float(row.o)) or (side == -1 and float(row.c) > float(row.o)):
            return i
    return None


def mitigation_blocks(frame, breaks, swings):
    """Failed-swing continuation block + an overlapping FVG requirement."""
    gaps = fair_value_gaps(frame)
    out = []
    for event in breaks:
        if event.kind != "BOS":
            continue
        i, side = event.bar, event.direction
        # Continuation means the opposite protected swing did not fail before
        # the break. The last opposing candle is the proxy block.
        opposing = _last_opposite_group(frame, i + 1, side)
        if opposing is None:
            continue
        row = frame.iloc[opposing]
        lo, hi = sorted((float(row.o), float(row.c)))
        associated = [gap for gap in gaps if gap.side == side and gap.available <= i and
                      gap.low <= hi and gap.high >= lo]
        if associated:
            out.append(BlockEvent(Zone("MIT", side, lo, hi, opposing, i,
                                       "failed opposite swing + FVG overlap"), i,
                                  "swing failure continuation"))
    return out


def breaker_blocks(frame, sweeps, breaks, swings):
    """Sweep one external side, close through the other, retest swept swing block."""
    out = []
    highs = [s for s in swings if s.kind == "H"]
    lows = [s for s in swings if s.kind == "L"]
    for sweep in sweeps:
        # Bullish: sell-side low swept, then confirmed close above a prior high.
        # Bearish: buy-side high swept, then confirmed close below a prior low.
        side = sweep.direction
        follow = [event for event in breaks if event.bar > sweep.bar and event.direction == side
                  and event.kind in ("BOS", "CHOCH")]
        if not follow:
            continue
        trigger = follow[0]
        candidates = highs if side == 1 else lows
        anchor = min(candidates, key=lambda s: abs(s.bar - sweep.bar)) if candidates else None
        if anchor is None:
            continue
        candle_index = anchor.bar
        row = frame.iloc[candle_index]
        zone_side = side
        lo, hi = float(row.l), float(row.h)
        out.append(BlockEvent(Zone("BRK", zone_side, lo, hi, candle_index,
                                   trigger.bar, "sweep both sides then opposing structure break"),
                              trigger.bar, "breaker retest"))
    return out


def rejection_blocks(frame, swings, timeframe_minutes):
    """Extreme wick midpoint zones, with timeframe-specific wick-count rule.

    'Long wick' has no numeric definition in the lecture. SMC-C operationally
    requires wick length >= real body and exposes each event for sensitivity
    review; the required count (2 below 30m, 1 at/above 30m) is from the lecture.
    """
    count_required = 2 if timeframe_minutes < 30 else 1
    by_kind = {"H": [s for s in swings if s.kind == "H"],
               "L": [s for s in swings if s.kind == "L"]}
    out = []
    for kind, items in by_kind.items():
        for swing in items:
            row = frame.iloc[swing.bar]
            body_hi, body_lo = max(float(row.o), float(row.c)), min(float(row.o), float(row.c))
            if kind == "H":
                wick_size = float(row.h) - body_hi
                wick_lo, wick_hi, side = body_hi, float(row.h), -1
            else:
                wick_size = body_lo - float(row.l)
                wick_lo, wick_hi, side = float(row.l), body_lo, 1
            if wick_size < body_hi - body_lo or wick_lo >= wick_hi:
                continue
            same_zone = []
            for other in items:
                if other.bar > swing.bar or swing.available - other.available > 30:
                    continue
                r = frame.iloc[other.bar]
                if kind == "H" and abs(float(r.h) - float(row.h)) == 0:
                    same_zone.append(other)
                elif kind == "L" and abs(float(r.l) - float(row.l)) == 0:
                    same_zone.append(other)
            if len(same_zone) < count_required:
                continue
            out.append(BlockEvent(Zone("REJ", side, wick_lo, wick_hi, swing.bar,
                                       swing.available, "extreme wick midpoint"),
                                  swing.available, "rejection block"))
    return out


def reclaimed_blocks(frame, swings, breaks, outer_zones):
    """Sequential old swing blocks enabled after an HTF POI and MSS event."""
    out = []
    for break_event in breaks:
        if break_event.kind != "CHOCH":
            continue
        side = break_event.direction
        earlier = [s for s in swings if s.available < break_event.bar and
                   ((side == 1 and s.kind == "L") or (side == -1 and s.kind == "H"))]
        poi_nearby = any(z.available < break_event.bar and z.side == -side and
                         z.low <= float(frame.iloc[break_event.bar].h) and
                         z.high >= float(frame.iloc[break_event.bar].l)
                         for z in outer_zones)
        if not earlier or not poi_nearby:
            continue
        for swing in earlier[-5:]:
            row = frame.iloc[swing.bar]
            # Last opposite-color candle at the swing; the candle block is
            # activated in chronological order by its own close reclaim.
            candle_index = _last_opposite_group(frame, swing.bar + 1, side)
            if candle_index is None:
                continue
            block = frame.iloc[candle_index]
            lo, hi = float(block.l), float(block.h)
            out.append(BlockEvent(Zone("RECLAIM", side, lo, hi, candle_index,
                                       break_event.bar, "POI + MSS; left swing OB"),
                                  break_event.bar, "sequential reclaimed OB"))
    return out
