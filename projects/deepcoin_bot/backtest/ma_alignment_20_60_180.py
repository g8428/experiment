"""Daily SMA 20/60/180 alignment research backtest.

Signal is formed from completed daily closes and executed at the next daily open.
The futures long/short result excludes funding; both positions pay the configured
taker fee and slippage on entry, exit, and reversals.
"""

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import engine_v2 as E  # noqa: E402


def backtest(df, fee=0.0006, slip=0.0002):
    d = df.copy().reset_index(drop=True)
    for n in (20, 60, 180):
        d[f"sma{n}"] = d["c"].rolling(n).mean()
    bull = (d.sma20 > d.sma60) & (d.sma60 > d.sma180)
    bear = (d.sma20 < d.sma60) & (d.sma60 < d.sma180)
    state = np.select([bull, bear], [1, -1], default=0)
    # Decision at close i-1; execute at open i. Start after all MAs are defined.
    first = int(d.sma180.first_valid_index()) + 1
    cost = fee + slip
    result = {}

    for name, target_fn in (
        ("long_only", lambda s: 1 if s == 1 else 0),
        ("long_short_cash", lambda s: s),
    ):
        equity = peak = 1.0
        max_dd = 0.0
        pos = 0
        trades = 0
        exposure = 0
        daily = []
        for i in range(first, len(d) - 1):
            target = target_fn(int(state[i - 1]))
            if target != pos:
                equity *= max(0.0, 1.0 - abs(target - pos) * cost)
                trades += 1
                pos = target
            exposure += int(pos != 0)
            r = float(d.o.iloc[i + 1] / d.o.iloc[i])
            equity *= r if pos == 1 else (2.0 - r if pos == -1 else 1.0)
            peak = max(peak, equity)
            max_dd = max(max_dd, (peak - equity) / peak)
            daily.append(equity)
        # Mark final open-to-close move, then pay to flatten any remaining position.
        if len(d) > first:
            target = target_fn(int(state[len(d) - 2]))
            if target != pos:
                equity *= max(0.0, 1.0 - abs(target - pos) * cost)
                trades += 1
                pos = target
            last = len(d) - 1
            r = float(d.c.iloc[last] / d.o.iloc[last])
            equity *= r if pos == 1 else (2.0 - r if pos == -1 else 1.0)
            if pos != 0:
                equity *= max(0.0, 1.0 - abs(pos) * cost)
                trades += 1
            peak = max(peak, equity)
            max_dd = max(max_dd, (peak - equity) / peak)
        result[name] = {
            "return_pct": round((equity - 1) * 100, 2),
            "mdd_pct": round(max_dd * 100, 2),
            "position_changes_including_final_exit": trades,
            "exposure_pct": round(100 * exposure / max(1, len(d) - first), 1),
        }

    # Buy and hold over the exact same evaluation window, including round-trip costs.
    bh = 1.0
    bh *= 1.0 - cost
    bh *= float(d.c.iloc[-1] / d.o.iloc[first])
    bh *= 1.0 - cost
    result["buy_hold"] = {"return_pct": round((bh - 1) * 100, 2)}
    result["range"] = {
        "from": pd.to_datetime(int(d.t.iloc[first]), unit="ms", utc=True).strftime("%Y-%m-%d"),
        "to": pd.to_datetime(int(d.t.iloc[-1]), unit="ms", utc=True).strftime("%Y-%m-%d"),
        "daily_bars": int(len(d) - first),
        "fee_per_side_pct": fee * 100,
        "slippage_per_side_pct": slip * 100,
        "commission_plus_slippage_per_side_pct": cost * 100,
        "ma": "SMA 20/60/180",
        "neutral_state": "flat/cash",
    }
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sym", default="BTC-USDT-SWAP")
    ap.add_argument("--fee", type=float, default=0.0006)
    ap.add_argument("--slip", type=float, default=0.0002)
    args = ap.parse_args()
    df = E.load_df(args.sym, "1D", 800)
    result = {"sym": args.sym, **backtest(df, args.fee, args.slip)}
    out_dir = os.path.join(os.path.dirname(HERE), "research", "backtest_v2")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{args.sym.split('-')[0]}_ma_alignment_20_60_180.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
