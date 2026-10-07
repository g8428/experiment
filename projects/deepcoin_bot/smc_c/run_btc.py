"""Run isolated first-pass SMC-C BTC experiments over local 1m candle cache."""
from pathlib import Path
import argparse

import pandas as pd

from .data import build_timeframes, load_one_minute
from .models import RiskConfig
from .setups import generate_reversal_intents
from .simulator import simulate_intents


HERE = Path(__file__).resolve().parent
CACHE = HERE.parent / "backtest" / "cache"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=None,
                        help="optional trailing calendar-day sample (not a substitute for full evaluation)")
    args = parser.parse_args()
    start = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=args.days) if args.days else None
    minute = load_one_minute(CACHE, "BTC-USDT-SWAP", start=start,
                             end=pd.Timestamp.now(tz="UTC"))
    frames = build_timeframes(minute, ("5m",))
    candidates = generate_reversal_intents(frames["1m"], frames["5m"], tick_size=0.1)
    # Transparent stress assumption only; replace with the account's actual fee tier.
    costs = RiskConfig(tick_size=0.1, fee_per_side=0.0005,
                       slippage_per_side=0.0002, partial_fraction=0.5)
    rows, trade_rows = [], []
    for strategy, intents in candidates.items():
        trades = simulate_intents(minute, intents, costs)
        net = [t.net_r for t in trades]
        rows.append({
            "strategy": strategy, "candidate_intents": len(intents),
            "executed_trades": len(trades), "win_rate": sum(r > 0 for r in net) / len(net) if net else 0.0,
            "mean_net_R": sum(net) / len(net) if net else 0.0,
            "median_net_R": float(pd.Series(net).median()) if net else 0.0,
            "total_net_R": sum(net), "profit_factor_R": (sum(r for r in net if r > 0) /
                abs(sum(r for r in net if r < 0))) if any(r < 0 for r in net) else None,
            "max_drawdown_R": _max_drawdown(net),
        })
        for t in trades:
            trade_rows.append({"strategy": strategy, "direction": t.direction,
                "signal_time": minute.index[t.signal_bar], "entry_time": minute.index[t.entry_bar],
                "exit_time": minute.index[t.exit_bar], "entry": t.entry, "stop": t.stop,
                "exit": t.exit_price, "gross_R": t.gross_r, "net_R": t.net_r,
                "exit_reason": t.exit_reason, "source": t.source, "tags": "|".join(t.tags)})
    pd.DataFrame(rows).to_csv(HERE / "btc_first_pass_summary.csv", index=False)
    pd.DataFrame(trade_rows).to_csv(HERE / "btc_first_pass_trades.csv", index=False)
    print("period", minute.index[0], "to", minute.index[-1], "1m_bars", len(minute))
    print(pd.DataFrame(rows).to_string(index=False))


def _max_drawdown(returns):
    equity, peak, worst = 0.0, 0.0, 0.0
    for value in returns:
        equity += value
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


if __name__ == "__main__":
    main()
