"""Lecture traceability and mechanical SMC-C entry prototypes.

Each setup remains an independent experiment. Only setups with unambiguous
causal event sequences are marked implemented; discretionary families are
listed explicitly rather than being silently approximated as trades.
"""
from .models import EntryIntent, StrategySpec
from .events import (LiquidityLevel, displacement_legs, equal_swing_levels,
                     prior_period_levels, wick_sweeps)
from .structure import confirmed_swings
from .zones import fair_value_gaps
import numpy as np


SPECS = [
    StrategySpec("A1", "IDM sweep", "3,4,6", "liquidity", "deferred", ["IDM mapping in these lectures is not BTC-specific"]),
    StrategySpec("A2", "First OB after IDM failure", "3,4,6", "block", "deferred", ["IDM failure / first valid OB selection is discretionary"]),
    StrategySpec("A3", "Extreme OB", "3,6", "block", "deferred", ["which intermediate blocks to skip is not fully mechanical"]),
    StrategySpec("B", "Order Flow pullback", "4", "continuation", "deferred", ["trend leg / last unmitigated pullback requires discretionary classification"]),
    StrategySpec("C", "Refined OB", "4,7", "refinement", "context-only", ["must refine a separate parent setup"]),
    StrategySpec("D", "Mitigation block", "7", "block", "deferred", ["swing failure plus overlapping FVG/OB proxy needs exact anchor-selection rule"]),
    StrategySpec("E", "ITH/ITL range", "8,11", "structure", "deferred", ["structure primitives exist; discount/premium entry requires a chosen leg/target rule"]),
    StrategySpec("F", "HTF three-candle continuation", "8", "continuation", "deferred", ["lecture pattern requires visual candle/context judgment"]),
    StrategySpec("G", "Fractal pullback", "11", "continuation", "deferred", ["HTF POI and pullback-target sequence needs discretionary selection"]),
    StrategySpec("H", "PDH/PDL or PWH/PWL sweep", "5,9", "liquidity", "implemented", ["close reclaim/reject then lower-TF MSS/retest proxy"]),
    StrategySpec("I", "Liquidity-displacement-retest", "6,11", "reversal", "implemented", ["two consecutive same-direction FVGs is an explicit coding interpretation"]),
    StrategySpec("J1", "BOS sweep reversal", "5,6", "liquidity", "implemented", ["wick through close back; countertrend MSS proxy"]),
    StrategySpec("J2", "CHoCH sweep continuation", "5,6", "liquidity", "deferred", ["requires reliable lecture-specific BOS/CHoCH anchor mapping"]),
    StrategySpec("K", "First pullback after CHoCH", "5", "continuation", "deferred", ["counter leg vs main leg classification is discretionary"]),
    StrategySpec("L", "Breaker block", "7", "block", "deferred", ["swept swing block reuse is represented in primitives; no order generator yet"]),
    StrategySpec("M", "Reclaimed OB", "7", "block", "deferred", ["activation order described qualitatively, not a complete algorithm"]),
    StrategySpec("N", "Rejection block", "7", "block", "deferred", ["wick-count and extreme selection need parameterized configuration"]),
    StrategySpec("O", "Asian session sweep", "10", "session", "deferred", ["session primitives exist; no session-specific order generator yet"]),
    StrategySpec("P", "CBDR", "10", "session", "deferred", ["range/context outcome relies on discretionary narrative"]),
    StrategySpec("Q", "OTE", "10", "retracement", "deferred", ["clean impulse-leg selection and rejection trigger need exact definitions"]),
    StrategySpec("R", "Time-cycle spike", "11", "reversal", "deferred", ["1-2 taps and cycle-spike judgment lack mechanical threshold"]),
    StrategySpec("S1", "STL/STH failure pullback", "11", "structure", "deferred", ["temporary pullback vs genuine reversal is discretionary"]),
    StrategySpec("S2", "IRL/ERL sequence", "5,11", "context", "context-only", ["context tag, not standalone entry"]),
]


def implemented_specs():
    return [spec for spec in SPECS if spec.status in ("implemented", "interpreted")]


def eligible_retest_intents(strategy, frame, zones, direction, start_bar, end_bar,
                            stop_extreme, target, tick_size, refs, tag=None):
    """Build causal limit intents when a newly-available directional zone is retested.

    This is an execution primitive, not a signal by itself: the calling setup
    must establish bias, liquidity event and displacement before calling.
    """
    intents = []
    for zone in zones:
        if zone.side != direction or zone.available < start_bar or zone.available > end_bar:
            continue
        limit = zone.midpoint
        stop = (min(stop_extreme, zone.low) - tick_size if direction > 0
                else max(stop_extreme, zone.high) + tick_size)
        if (direction > 0 and stop >= limit) or (direction < 0 and stop <= limit):
            continue
        targets = [target]
        if (direction > 0 and target <= limit) or (direction < 0 and target >= limit):
            continue
        intents.append(EntryIntent(strategy, direction, zone.available, limit, stop,
                                   targets, zone.source, refs,
                                   [tag] if tag else []))
    return intents


def generate_reversal_intents(frame, five_minute, tick_size=0.1):
    """Generate three distinct sweep-to-retest experiment streams (BTC 1m).

    H uses completed previous-day/week extremes, I uses equal swing liquidity,
    and J1 uses any confirmed swing liquidity. Entries require post-sweep
    consecutive-FVG displacement and retest. Stops sit past sweep extreme;
    the nearest unswept opposite swing is the single target. Higher-timeframe
    bias filtering remains a separate, inspectable study dimension.
    """
    if len(frame) < 100:
        return {"H": [], "I": [], "J1": []}
    swings = confirmed_swings(frame, group_inside=True)
    levels = {
        "H": prior_period_levels(frame, "1D") + prior_period_levels(frame, "1W"),
        "I": equal_swing_levels(swings),
        "J1": [
            # Both swing sides are eligible external liquidity anchors.
            LiquidityLevel("SWING_" + s.kind, float(s.price),
                           -1 if s.kind == "H" else 1,
                           int(s.bar), int(s.available))
            for s in swings if s.kind in ("H", "L")
        ],
    }
    gaps = fair_value_gaps(frame)
    legs = displacement_legs(frame, five_minute)
    output = {key: [] for key in levels}
    for strategy, anchors in levels.items():
        sweeps = wick_sweeps(frame, anchors)
        for sweep in sweeps:
            confirmation = next((leg for leg in legs
                                 if leg[0] == sweep.direction and leg[1] > sweep.bar), None)
            if confirmation is None:
                continue
            _, _, available = confirmation
            retests = [z for z in gaps if z.side == sweep.direction
                       and z.available >= sweep.bar and z.available <= available]
            if not retests:
                continue
            zone = retests[-1]
            entry = zone.midpoint
            stop = (min(float(sweep.extreme), zone.low) - tick_size if sweep.direction > 0
                    else max(float(sweep.extreme), zone.high) + tick_size)
            opposite = [s.price for s in swings if s.available <= available
                        and ((sweep.direction > 0 and s.kind == "H" and s.price > entry)
                             or (sweep.direction < 0 and s.kind == "L" and s.price < entry))]
            if not opposite:
                continue
            target = min(opposite) if sweep.direction > 0 else max(opposite)
            if (sweep.direction > 0 and (stop >= entry or target <= entry)) or (
                    sweep.direction < 0 and (stop <= entry or target >= entry)):
                continue
            after = slice(available + 1, len(frame))
            if sweep.direction > 0:
                dead = ((frame.c.to_numpy()[after] < zone.low) |
                        (frame.h.to_numpy()[after] >= target))
            else:
                dead = ((frame.c.to_numpy()[after] > zone.high) |
                        (frame.l.to_numpy()[after] <= target))
            dead_at = np.flatnonzero(dead)
            # Expire before the OHLC candle that invalidates the zone or reaches
            # the target; its internal price path cannot be reconstructed.
            expires = available + int(dead_at[0]) - 1 if len(dead_at) else len(frame) - 1
            output[strategy].append(EntryIntent(strategy, sweep.direction, available,
                entry, stop, [float(target)], zone.source,
                next(spec.lecture_refs for spec in SPECS if spec.id == strategy),
                ["sweep-to-displacement-FVG-retest", sweep.level.kind], expires))
    return output
