"""Small deterministic checks for SMC-C causality and execution conventions."""
import pandas as pd

from .events import LiquidityLevel, wick_sweeps
from .models import EntryIntent, RiskConfig
from .simulator import simulate_intents
from .structure import confirmed_swings
from .zones import fair_value_gaps


def _frame(rows, index=None):
    frame = pd.DataFrame(rows, columns=("o", "h", "l", "c", "v"), dtype=float)
    frame.index = index or pd.date_range("2025-01-01", periods=len(frame), freq="min", tz="UTC")
    return frame


def run():
    # Strict three-candle swing appears only after the right candle.
    bars = _frame([(2, 3, 1, 2, 1), (2, 5, 2, 4, 1), (4, 4, 2, 3, 1), (3, 3, 1, 2, 1)])
    swings = confirmed_swings(bars, group_inside=False)
    assert any(s.kind == "H" and s.bar == 1 and s.available == 2 for s in swings)

    # FVG is only available after its third candle closes.
    gaps = fair_value_gaps(_frame([(10, 11, 9, 10, 1), (11, 13, 11, 12, 1), (13, 14, 12, 13, 1)]))
    assert len(gaps) == 1 and gaps[0].available == 2 and gaps[0].low == 11

    # Sell-side liquidity stays active above its level, then wick-reclaims once.
    frame = _frame([(12, 13, 11, 12, 1), (12, 14, 11, 12, 1), (12, 16, 13, 14, 1),
                    (14, 15, 12, 14, 1)])
    level = LiquidityLevel("TEST_HIGH", 15, -1, 0, 1)
    sweeps = wick_sweeps(frame, [level])
    assert len(sweeps) == 1 and sweeps[0].bar == 2 and sweeps[0].direction == -1

    # Signals fill no earlier than the next candle; stop wins same-candle tie.
    execution = _frame([(100, 101, 99, 100, 1), (100, 102, 98, 100, 1),
                        (100, 101, 99, 100, 1)])
    intent = EntryIntent("T", 1, 0, 100, 98, [102], "test", "test")
    trades = simulate_intents(execution, [intent], RiskConfig(0.1, 0, 0))
    assert len(trades) == 1 and trades[0].entry_bar == 1 and trades[0].exit_reason == "SL"
    return 4


if __name__ == "__main__":
    print("SMC-C self-checks passed:", run())
