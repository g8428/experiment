"""Daily Ichimoku Kumo breakout research backtest.

Visible Senkou spans are shifted forward 26 periods on the chart, so the cloud
at date i is the raw span calculated at i-26. Decisions use a completed daily
close and execute at the next daily open. Futures short PnL excludes funding.
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
    high, low = d.h, d.l
    tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
    kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2
    span_a_raw = (tenkan + kijun) / 2
    span_b_raw = (high.rolling(52).max() + low.rolling(52).min()) / 2
    # Cloud visible at date t was calculated 26 sessions earlier.
    cloud_a = span_a_raw.shift(26)
    cloud_b = span_b_raw.shift(26)
    spans = pd.concat([cloud_a, cloud_b], axis=1)
    both_spans_ready = cloud_a.notna() & cloud_b.notna()
    cloud_top = spans.max(axis=1).where(both_spans_ready)
    cloud_bottom = spans.min(axis=1).where(both_spans_ready)
    bull = d.c > cloud_top
    bear = d.c < cloud_bottom
    state = np.select([bull, bear], [1, -1], default=0)
    # Require both projected spans: Span B is unavailable until 52 bars plus
    # the 26-bar displacement have elapsed.
    first = max(int(cloud_a.first_valid_index()), int(cloud_b.first_valid_index())) + 1
    cost = fee + slip
    result = {}

    for name, target_fn in (
        ("long_only", lambda s: 1 if s == 1 else 0),
        ("long_short_cash", lambda s: s),
    ):
        equity = peak = 1.0
        max_dd = 0.0
        pos = 0
        changes = 0
        exposure = 0
        for i in range(first, len(d) - 1):
            # The prior completed candle sets target for today's open.
            target = target_fn(int(state[i - 1]))
            if target != pos:
                equity *= max(0.0, 1.0 - abs(target - pos) * cost)
                changes += 1
                pos = target
            exposure += int(pos != 0)
            # Match the user-specific strategy's intraday adverse-price MDD.
            if pos != 0:
                adverse_ratio = (float(d.l.iloc[i]) / float(d.o.iloc[i]) if pos == 1
                                 else 2.0 - float(d.h.iloc[i]) / float(d.o.iloc[i]))
                adverse_equity = max(0.0, equity * adverse_ratio)
                peak = max(peak, equity)
                max_dd = max(max_dd, (peak - adverse_equity) / peak if peak else 0.0)
            r = float(d.o.iloc[i + 1] / d.o.iloc[i])
            equity *= r if pos == 1 else (2.0 - r if pos == -1 else 1.0)
            peak = max(peak, equity)
            max_dd = max(max_dd, (peak - equity) / peak)
        # Last close mark and final flattening cost.
        if len(d) > first:
            target = target_fn(int(state[len(d) - 2]))
            if target != pos:
                equity *= max(0.0, 1.0 - abs(target - pos) * cost)
                changes += 1
                pos = target
            last = len(d) - 1
            if pos != 0:
                adverse_ratio = (float(d.l.iloc[last]) / float(d.o.iloc[last]) if pos == 1
                                 else 2.0 - float(d.h.iloc[last]) / float(d.o.iloc[last]))
                adverse_equity = max(0.0, equity * adverse_ratio)
                peak = max(peak, equity)
                max_dd = max(max_dd, (peak - adverse_equity) / peak if peak else 0.0)
            r = float(d.c.iloc[last] / d.o.iloc[last])
            equity *= r if pos == 1 else (2.0 - r if pos == -1 else 1.0)
            if pos != 0:
                equity *= max(0.0, 1.0 - abs(pos) * cost)
                changes += 1
            peak = max(peak, equity)
            max_dd = max(max_dd, (peak - equity) / peak)
        result[name] = {
            "return_pct": round((equity - 1) * 100, 2),
            "mdd_pct": round(max_dd * 100, 2),
            "position_changes_including_final_exit": changes,
            "exposure_pct": round(100 * exposure / max(1, len(d) - first), 1),
        }

    cost_factor = 1.0 - cost
    bh = cost_factor * float(d.c.iloc[-1] / d.o.iloc[first]) * cost_factor
    result["buy_hold"] = {"return_pct": round((bh - 1) * 100, 2)}
    result["range"] = {
        "from": pd.to_datetime(int(d.t.iloc[first]), unit="ms", utc=True).strftime("%Y-%m-%d"),
        "to": pd.to_datetime(int(d.t.iloc[-1]), unit="ms", utc=True).strftime("%Y-%m-%d"),
        "daily_bars": int(len(d) - first),
        "fee_per_side_pct": fee * 100,
        "slippage_per_side_pct": slip * 100,
        "ma": "Ichimoku 9/26/52, displacement 26",
        "state_rule": "close above cloud top=long; below cloud bottom=short; inside=flat",
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
    out = os.path.join(out_dir, f"{args.sym.split('-')[0]}_ichimoku_cloud_breakout.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
