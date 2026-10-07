"""Top-down bias facts from completed higher-timeframe candles."""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class BiasEvent:
    direction: int
    target: Optional[float]
    formed: int
    available: int
    timeframe: str
    reason: str
    counter: bool = False


def daily_bias_events(daily):
    """9th-lecture daily sweep/rejection and close-through continuation rules.

    An event from candle i is usable from candle i+1; same-day lookahead is
    therefore impossible. Two-sided outside bars without a decisive close are
    neutral because their intended path is not encoded in OHLC.
    """
    events = []
    for i in range(1, len(daily)):
        prev = daily.iloc[i - 1]
        bar = daily.iloc[i]
        took_low = float(bar.l) < float(prev.l)
        took_high = float(bar.h) > float(prev.h)
        if took_low and float(bar.c) > float(prev.l) and not (took_high and float(bar.c) < float(prev.h)):
            events.append(BiasEvent(1, float(bar.h), i, i + 1, "1D", "prior-day low sweep, close reclaimed"))
        elif took_high and float(bar.c) < float(prev.h) and not (took_low and float(bar.c) > float(prev.l)):
            events.append(BiasEvent(-1, float(bar.l), i, i + 1, "1D", "prior-day high sweep, close rejected"))
        elif float(bar.c) > float(prev.h) and not took_low:
            events.append(BiasEvent(1, float(bar.h), i, i + 1, "1D", "close above prior-day high"))
        elif float(bar.c) < float(prev.l) and not took_high:
            events.append(BiasEvent(-1, float(bar.l), i, i + 1, "1D", "close below prior-day low"))
    return events


def higher_period_bias_events(frame, timeframe):
    """Weekly/monthly OHLC continuation and sweep events.

    This operational proxy records objective close/sweep facts. It does not
    claim to reproduce the lecture's discretionary POI+displacement monthly
    narrative; callers should tag these as structural evidence, not full bias.
    """
    events = []
    for i in range(1, len(frame)):
        prev, bar = frame.iloc[i - 1], frame.iloc[i]
        took_low, took_high = float(bar.l) < float(prev.l), float(bar.h) > float(prev.h)
        if took_low and float(bar.c) > float(prev.l) and not (took_high and float(bar.c) < float(prev.h)):
            events.append(BiasEvent(1, float(bar.h), i, i + 1, timeframe, "prior-period low sweep/reclaim"))
        elif took_high and float(bar.c) < float(prev.h) and not (took_low and float(bar.c) > float(prev.l)):
            events.append(BiasEvent(-1, float(bar.l), i, i + 1, timeframe, "prior-period high sweep/reject"))
        elif float(bar.c) > float(prev.h) and not took_low:
            events.append(BiasEvent(1, float(bar.h), i, i + 1, timeframe, "close above prior-period high"))
        elif float(bar.c) < float(prev.l) and not took_high:
            events.append(BiasEvent(-1, float(bar.l), i, i + 1, timeframe, "close below prior-period low"))
    return events


def opening_filter(direction, price, month_open, week_open, day_open):
    """9th-lecture time/price filter for month, week and day opens."""
    opens = (month_open, week_open, day_open)
    if direction > 0:
        return all(value is not None and price < value for value in opens)
    if direction < 0:
        return all(value is not None and price > value for value in opens)
    return False


def resolve_bias(events, at_index):
    """Select the most recent known event from the highest available timeframe."""
    available = [event for event in events if event.available <= at_index]
    for timeframe in ("1M", "1W", "1D", "4H", "1H"):
        candidates = [event for event in available if event.timeframe == timeframe]
        if candidates:
            return max(candidates, key=lambda event: event.available)
    return None
