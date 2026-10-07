"""Liquidity, sweeps and displacement events with causal availability indices."""
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from .zones import fair_value_gaps


@dataclass(frozen=True)
class LiquidityLevel:
    kind: str
    price: float
    side: int  # +1 sell-side liquidity below price, -1 buy-side liquidity above
    formed: int
    available: int
    expires: Optional[int] = None


@dataclass(frozen=True)
class Sweep:
    level: LiquidityLevel
    direction: int  # +1 bullish reclaim, -1 bearish reclaim
    extreme: float
    bar: int


def equal_swing_levels(swings):
    """Exact-price equal highs/lows; no tolerance absent from lecture material."""
    out = []
    for kind, side in (("H", -1), ("L", 1)):
        seen = {}
        for swing in swings:
            if swing.kind != kind:
                continue
            price = float(swing.price)
            if price in seen:
                previous = seen[price]
                out.append(LiquidityLevel("EQUAL_HIGH" if kind == "H" else "EQUAL_LOW",
                                          price, side, previous.bar, swing.available))
            seen[price] = swing
    return out


def prior_period_levels(base_frame, period="1D"):
    """Map previous completed UTC day/week extremes onto each base candle."""
    if period not in ("1D", "1W"):
        raise ValueError("period must be '1D' or '1W'")
    agg = base_frame.resample(period, label="left", closed="left", origin="start_day").agg(
        {"h": "max", "l": "min"}).dropna()
    names = "PD" if period == "1D" else "PW"
    levels = []
    for i in range(1, len(agg)):
        new_period = agg.index[i]
        available = int(base_frame.index.searchsorted(new_period, side="left"))
        expires = int(base_frame.index.searchsorted(new_period + agg.index.freq, side="left")) if agg.index.freq else len(base_frame)
        previous = agg.iloc[i - 1]
        levels.append(LiquidityLevel(names + "H", float(previous.h), -1, available - 1, available, expires))
        levels.append(LiquidityLevel(names + "L", float(previous.l), 1, available - 1, available, expires))
    return levels


def wick_sweeps(frame, levels):
    """A level is swept only when a wick crosses it and the candle closes back."""
    by_available = {}
    for level in levels:
        by_available.setdefault(level.available, []).append(level)
    active = []
    sweeps = []
    for i, row in enumerate(frame.itertuples()):
        active.extend(by_available.get(i, ()))
        active = [level for level in active if level.expires is None or i < level.expires]
        remaining = []
        for level in active:
            if level.available >= i:
                remaining.append(level)
                continue
            if level.side > 0 and row.l < level.price and row.c > level.price:
                sweeps.append(Sweep(level, 1, float(row.l), i))
                continue
            elif level.side < 0 and row.h > level.price and row.c < level.price:
                sweeps.append(Sweep(level, -1, float(row.h), i))
                continue
            # Once a candle closes through a liquidity level, it is no longer
            # resting liquidity; only a wick rejection remains a live level.
            if (level.side > 0 and row.c < level.price) or (level.side < 0 and row.c > level.price):
                remaining.append(level)
        active = remaining
    return sweeps


def displacement_legs(frame, five_minute=None, min_consecutive_fvgs=2):
    """Find directional legs with successive FVGs and a relative large candle.

    The threshold of two is a transparent interpretation of the lecture's
    plural/continuous FVG wording, not an explicit lecturer-provided count.
    If 5m data is provided, one 1m range in the leg must exceed the trailing
    mean completed 5m range as described in the lecture.
    """
    gaps = fair_value_gaps(frame)
    events, recent = [], []
    one_min_range = (frame.h - frame.l).to_numpy()
    five_ns = None
    five_prefix = None
    if five_minute is not None:
        five_ns = five_minute.index.asi8
        five_ranges = (five_minute.h - five_minute.l).to_numpy(dtype=float)
        five_prefix = np.concatenate(([0.0], np.cumsum(five_ranges)))
    for gap in gaps:
        if recent and (recent[-1].side != gap.side or gap.available - recent[-1].available > 1):
            recent = []
        recent.append(gap)
        recent = recent[-min_consecutive_fvgs:]
        if len(recent) < min_consecutive_fvgs:
            continue
        if five_minute is not None:
            end_ns = frame.index[gap.available].value
            n_completed = int(np.searchsorted(five_ns, end_ns, side="left"))
            if n_completed < 2:
                continue
            first = max(0, n_completed - 20)
            baseline = (five_prefix[n_completed] - five_prefix[first]) / (n_completed - first)
            if not np.any(one_min_range[recent[0].formed:gap.available + 1] > baseline):
                continue
        events.append((gap.side, recent[0].formed, gap.available))
    # Collapse overlapping detection windows to distinct same-direction legs.
    compact = []
    for side, start, end in events:
        if compact and compact[-1][0] == side and start <= compact[-1][2]:
            compact[-1] = (side, compact[-1][1], end)
        else:
            compact.append((side, start, end))
    return compact
