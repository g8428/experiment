"""Conservative next-bar limit-fill simulator for SMC-C entry intents."""
from .models import EntryIntent, RiskConfig, TradeResult


def _limit_fill(bar, intent):
    if intent.direction > 0:
        if float(bar.l) > intent.limit_price:
            return None
        return min(float(bar.o), intent.limit_price)
    if float(bar.h) < intent.limit_price:
        return None
    return max(float(bar.o), intent.limit_price)


def _stop_hit(bar, direction, stop):
    return float(bar.l) <= stop if direction > 0 else float(bar.h) >= stop


def _target_hit(bar, direction, target):
    return float(bar.h) >= target if direction > 0 else float(bar.l) <= target


def simulate_intents(frame, intents, config):
    """Simulate one independent strategy stream, sorted chronologically.

    The signal is known only at decision-bar close. A limit can fill starting
    on the following bar. If stop and target are both touched in one OHLC bar,
    stop wins. Fees/slippage are explicit test inputs, not lecture doctrine.
    """
    ordered = sorted(intents, key=lambda x: (x.decision_bar, x.strategy, x.direction))
    results, consumed = [], set()
    cursor = 0
    while cursor < len(ordered):
        intent = ordered[cursor]
        cursor += 1
        key = (intent.strategy, intent.decision_bar, intent.direction, intent.source)
        if key in consumed or intent.decision_bar + 1 >= len(frame):
            continue
        consumed.add(key)
        risk = abs(intent.limit_price - intent.stop_price) / abs(intent.limit_price)
        if risk <= 0 or not intent.targets:
            continue
        entry_bar, entry = None, None
        last_entry_bar = min(len(frame) - 1,
                             intent.expires_bar if intent.expires_bar is not None else len(frame) - 1)
        for i in range(intent.decision_bar + 1, last_entry_bar + 1):
            bar = frame.iloc[i]
            entry = _limit_fill(bar, intent)
            if entry is not None:
                entry_bar = i
                break
            # A target reached before any limit fill ends the setup. If the
            # entry and target share one bar, the exit loop uses stop-first.
            if any(_target_hit(bar, intent.direction, target) for target in intent.targets):
                break
        if entry_bar is None:
            continue

        remaining = 1.0
        realized_gross = 0.0
        fees = config.fee_per_side + config.slippage_per_side  # entry
        exit_bar, exit_price, exit_reason = entry_bar, entry, "OPEN"
        targets = list(intent.targets)
        first_fraction = min(max(config.partial_fraction, 0.0), 1.0)

        for i in range(entry_bar, len(frame)):
            bar = frame.iloc[i]
            if _stop_hit(bar, intent.direction, intent.stop_price):
                px = min(float(bar.o), intent.stop_price) if intent.direction > 0 else max(float(bar.o), intent.stop_price)
                realized_gross += intent.direction * (px - entry) / abs(entry) * remaining
                fees += (config.fee_per_side + config.slippage_per_side) * remaining
                remaining, exit_bar, exit_price, exit_reason = 0.0, i, px, "SL"
                break
            if targets and _target_hit(bar, intent.direction, targets[0]):
                px = max(float(bar.o), targets[0]) if intent.direction > 0 else min(float(bar.o), targets[0])
                fraction = min(remaining, first_fraction) if len(targets) > 1 else remaining
                realized_gross += intent.direction * (px - entry) / abs(entry) * fraction
                fees += config.fee_per_side * fraction
                remaining -= fraction
                targets.pop(0)
                if remaining <= 1e-12:
                    exit_bar, exit_price, exit_reason = i, px, "TP"
                    break
                # First liquidity reached: stop to breakeven per lecture.
                if len(intent.targets) > 1:
                    intent = EntryIntent(intent.strategy, intent.direction, intent.decision_bar,
                                         intent.limit_price, entry, intent.targets[1:], intent.source,
                                         intent.lecture_refs, intent.tags, intent.expires_bar)
                continue
            if targets and _target_hit(bar, intent.direction, targets[0]):
                continue
        if remaining > 0:
            final = float(frame.iloc[-1].c)
            realized_gross += intent.direction * (final - entry) / abs(entry) * remaining
            fees += (config.fee_per_side + config.slippage_per_side) * remaining
            exit_bar, exit_price, exit_reason = len(frame) - 1, final, "END_OF_DATA"
        net = realized_gross - fees
        results.append(TradeResult(intent.strategy, intent.direction, intent.decision_bar,
                                   entry_bar, exit_bar, entry, intent.stop_price, exit_price,
                                   risk, realized_gross / risk, net / risk, fees,
                                   exit_reason, intent.source, intent.lecture_refs,
                                   list(intent.tags)))
    return results
