"""Confirmed candle structure primitives: inside-bar grouping, swings, ITH/ITL.

All returned event indices are confirmation indices. Consumers must not use a
swing before its confirmation candle has closed.
"""
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class CandleGroup:
    start: int
    end: int
    o: float
    h: float
    l: float
    c: float


@dataclass(frozen=True)
class Swing:
    kind: str  # "H" or "L"
    price: float
    bar: int
    available: int


@dataclass(frozen=True)
class StructureBreak:
    kind: str  # BOS or CHOCH
    direction: int  # +1 bullish, -1 bearish
    level: float
    bar: int


def group_inside_bars(frame):
    """Collapse an inside bar into its mother range while keeping latest close.

    This follows the lecture instruction to treat an inside bar as part of its
    mother candle for swing mapping; it does not discard its final close/time.
    """
    groups = []
    for i, row in enumerate(frame.itertuples()):
        candle = CandleGroup(i, i, float(row.o), float(row.h), float(row.l), float(row.c))
        if groups and candle.h <= groups[-1].h and candle.l >= groups[-1].l:
            mother = groups[-1]
            groups[-1] = CandleGroup(mother.start, i, mother.o, mother.h, mother.l, candle.c)
        else:
            groups.append(candle)
    return groups


def confirmed_swings(frame, group_inside=True):
    """Return strict 3-candle fractal swings, each available after right bar."""
    bars = group_inside_bars(frame) if group_inside else [
        CandleGroup(i, i, float(r.o), float(r.h), float(r.l), float(r.c))
        for i, r in enumerate(frame.itertuples())
    ]
    found = []
    for i in range(1, len(bars) - 1):
        left, mid, right = bars[i - 1], bars[i], bars[i + 1]
        available = right.end
        if mid.h > left.h and mid.h > right.h:
            found.append(Swing("H", mid.h, mid.end, available))
        if mid.l < left.l and mid.l < right.l:
            found.append(Swing("L", mid.l, mid.end, available))
    return sorted(found, key=lambda e: (e.available, e.bar, e.kind))


def intermediate_swings(swings):
    """ITH/ITL: central swing exceeds/is below the previous and next swing.

    The result becomes available only when the right-hand comparison swing is
    confirmed, so it cannot be used retrospectively.
    """
    result = []
    for kind in ("H", "L"):
        items = [event for event in swings if event.kind == kind]
        for i in range(1, len(items) - 1):
            a, b, c = items[i - 1:i + 2]
            valid = b.price > a.price and b.price > c.price if kind == "H" else b.price < a.price and b.price < c.price
            if valid:
                result.append(Swing("ITH" if kind == "H" else "ITL", b.price, b.bar, c.available))
    return sorted(result, key=lambda e: (e.available, e.bar, e.kind))


def breaks_and_sweeps(frame, swings):
    """Detect close-confirmed BOS/CHoCH and wick-only sweeps of prior swings.

    Initial trend is unknown until the first close-confirmed break. A break is
    BOS if it agrees with that trend and CHoCH otherwise.
    """
    highs = sorted((s for s in swings if s.kind == "H"), key=lambda s: s.available)
    lows = sorted((s for s in swings if s.kind == "L"), key=lambda s: s.available)
    events, used_h, used_l, trend = [], set(), set(), 0
    jh = jl = 0
    for i, row in enumerate(frame.itertuples()):
        while jh < len(highs) and highs[jh].available < i:
            jh += 1
        while jl < len(lows) and lows[jl].available < i:
            jl += 1
        prior_h = next((s for s in reversed(highs[:jh]) if s.bar not in used_h), None)
        prior_l = next((s for s in reversed(lows[:jl]) if s.bar not in used_l), None)
        if prior_h is not None and row.h > prior_h.price and row.c <= prior_h.price:
            events.append(StructureBreak("SWEEP", -1, prior_h.price, i))
        if prior_l is not None and row.l < prior_l.price and row.c >= prior_l.price:
            events.append(StructureBreak("SWEEP", 1, prior_l.price, i))
        if prior_h is not None and row.c > prior_h.price:
            kind = "BOS" if trend >= 0 else "CHOCH"
            events.append(StructureBreak(kind, 1, prior_h.price, i))
            trend, used_h = 1, used_h | {prior_h.bar}
        elif prior_l is not None and row.c < prior_l.price:
            kind = "BOS" if trend <= 0 else "CHOCH"
            events.append(StructureBreak(kind, -1, prior_l.price, i))
            trend, used_l = -1, used_l | {prior_l.bar}
    return events


def timeframe_structure(frame):
    swings = confirmed_swings(frame)
    return {"swings": swings, "ith_itl": intermediate_swings(swings),
            "breaks": breaks_and_sweeps(frame, swings)}
