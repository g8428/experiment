"""Price delivery arrays directly expressed from lecture definitions."""
from dataclasses import dataclass

from .structure import group_inside_bars


@dataclass(frozen=True)
class Zone:
    kind: str
    side: int  # +1 demand, -1 supply
    low: float
    high: float
    formed: int
    available: int
    source: str

    @property
    def midpoint(self):
        return (self.low + self.high) / 2.0


def fair_value_gaps(frame):
    """Three-candle non-overlap; zone is available only after candle 3 closes."""
    bars = group_inside_bars(frame)
    zones = []
    for i in range(2, len(bars)):
        a, c = bars[i - 2], bars[i]
        if a.h < c.l:
            zones.append(Zone("FVG", 1, a.h, c.l, a.start, c.end, "3-candle gap"))
        elif a.l > c.h:
            zones.append(Zone("FVG", -1, c.h, a.l, a.start, c.end, "3-candle gap"))
    return zones


def volume_imbalances(frame):
    """Body gap with wick overlap (VI); full range gap is classified as FVG."""
    bars = group_inside_bars(frame)
    zones = []
    for i in range(1, len(bars)):
        a, b = bars[i - 1], bars[i]
        a_body_hi, a_body_lo = max(a.o, a.c), min(a.o, a.c)
        b_body_hi, b_body_lo = max(b.o, b.c), min(b.o, b.c)
        if a_body_hi < b_body_lo and max(a.l, b.l) <= min(a.h, b.h):
            zones.append(Zone("VI", 1, a_body_hi, b_body_lo, a.start, b.end, "body gap / wick overlap"))
        elif b_body_hi < a_body_lo and max(a.l, b.l) <= min(a.h, b.h):
            zones.append(Zone("VI", -1, b_body_hi, a_body_lo, a.start, b.end, "body gap / wick overlap"))
    return zones


def balanced_price_ranges(fvgs):
    """Intersect opposite-direction FVGs; availability follows the later gap."""
    ordered = sorted(fvgs, key=lambda z: z.available)
    active = {1: [], -1: []}
    out, seen = [], set()
    for zone in ordered:
        opposite = active[-zone.side]
        for other in opposite:
            lo, hi = max(zone.low, other.low), min(zone.high, other.high)
            key = (lo, hi, max(zone.available, other.available))
            if lo < hi and key not in seen:
                out.append(Zone("BPR", 0, lo, hi, min(zone.formed, other.formed),
                                key[2], "opposing FVG overlap"))
                seen.add(key)
        active[zone.side].append(zone)
    return out


def order_blocks(frame, fvgs, swing_lows=None, swing_highs=None):
    """Find the last opposing candle that directly precedes an FVG leg.

    Requiring an associated FVG follows the basic OB definition. This is a
    minimum objective proxy for 'strong move'; a future displacement event
    filter must still confirm the leg before a setup can enter.
    """
    swing_lows = swing_lows or []
    swing_highs = swing_highs or []
    zones = []
    grouped = group_inside_bars(frame)
    group_by_source_index = {}
    for group in grouped:
        for source_index in range(group.start, group.end + 1):
            group_by_source_index[source_index] = group
    for gap in fvgs:
        side = gap.side
        candidates = range(gap.formed, -1, -1)
        for i in candidates:
            group = group_by_source_index.get(i)
            if group is None:
                continue
            row = group
            bearish = row.c < row.o
            bullish = row.c > row.o
            if (side == 1 and bearish) or (side == -1 and bullish):
                # If the candidate swept the preceding swing, retain that wick;
                # otherwise use the candle body, following the lecture examples.
                prior = swing_lows if side == 1 else swing_highs
                earlier = [s for s in prior if getattr(s, "bar", -1) < i]
                swept = bool(earlier and (row.l < earlier[-1].price if side == 1 else row.h > earlier[-1].price))
                body_lo, body_hi = sorted((float(row.o), float(row.c)))
                lo, hi = (float(row.l), body_lo) if side == 1 and swept else (body_hi, float(row.h)) if side == -1 and swept else (body_lo, body_hi)
                if lo < hi:
                    zones.append(Zone("OB", side, lo, hi, row.start, gap.available, "last counter candle before FVG"))
                break
    # Deduplicate identical OBs associated with adjacent FVGs while preserving earliest availability.
    unique = {}
    for zone in zones:
        key = (zone.side, zone.low, zone.high, zone.formed)
        if key not in unique or zone.available < unique[key].available:
            unique[key] = zone
    return sorted(unique.values(), key=lambda z: z.available)


def advanced_order_blocks(frame, max_group=None):
    """Consecutive opposite-color candle groups; MT is their mean threshold."""
    bars = group_inside_bars(frame)
    zones, i, n = [], 0, len(bars)
    while i < n:
        row = bars[i]
        direction = 1 if row.c < row.o else -1 if row.c > row.o else 0
        if not direction:
            i += 1
            continue
        j = i + 1
        while j < n:
            nxt = bars[j]
            nxt_dir = 1 if nxt.c < nxt.o else -1 if nxt.c > nxt.o else 0
            if nxt_dir != direction or (max_group and j - i >= max_group):
                break
            j += 1
        lo = min(b.l for b in bars[i:j])
        hi = max(b.h for b in bars[i:j])
        zones.append(Zone("AOB", direction, lo, hi, bars[i].start, bars[j - 1].end,
                          "consecutive counter candles"))
        i = j
    return zones


def touched(zone, candle):
    return float(candle.l) <= zone.high and float(candle.h) >= zone.low


def invalidated_by_close(zone, candle):
    return float(candle.c) < zone.low if zone.side == 1 else float(candle.c) > zone.high if zone.side == -1 else False
