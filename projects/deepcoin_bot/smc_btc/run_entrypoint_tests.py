"""Run each lecture-derived entrypoint once under one frozen test profile.

Examples:
    python run_entrypoint_tests.py
    python run_entrypoint_tests.py --only S2,S3d,S6 --both-bias

This is a comparison harness, not a parameter optimizer. Rules live in
strats2.py; this file ensures each entrypoint is backtested independently.
"""
import argparse
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from run_chain import ctx  # noqa: E402
from strats2 import RUNNERS  # noqa: E402


# Trace each independently run implementation to the lecture entrypoint.
ENTRYPOINTS = {
    "S1": ("8, 11", "ITH/ITL range pullback or ITL sweep"),
    "S2": ("6, 11", "HTF POI reaction: liquidity sweep -> displacement/MSS -> retest"),
    "S3d": ("5, 9", "Previous-day high/low sweep"),
    "S3w": ("5, 9", "Previous-week high/low sweep"),
    "S4": ("9", "Dealing-range discount/premium entry"),
    "S5": ("11", "Fractal pullback: daily POI -> 1H MSS -> 4H POI retest"),
    "S6": ("5, 6, 8", "BOS/CHoCH level sweep and reclaim"),
    "S8a": ("10", "Asian-session POI/swing sweep and reversal"),
    "S8b": ("10", "CBDR range sweep and continuation"),
    "S8c": ("10", "OTE pullback entry"),
    "S9": ("11", "Time-cycle spike into higher-timeframe POI"),
}


def stats(trades):
    if not trades:
        return {"n": 0, "win_rate": np.nan, "avg_R": np.nan, "total_R": 0.0,
                "profit_factor": np.nan, "max_drawdown_R": 0.0}
    values = np.asarray([t["R"] for t in trades], dtype=float)
    equity = np.cumsum(values)
    peak = np.maximum.accumulate(np.r_[0.0, equity])
    drawdown = peak[1:] - equity
    gross_win = values[values > 0].sum()
    gross_loss = -values[values < 0].sum()
    return {
        "n": len(values),
        "win_rate": float((values > 0).mean()),
        "avg_R": float(values.mean()),
        "total_R": float(values.sum()),
        "profit_factor": float(gross_win / gross_loss) if gross_loss else np.inf,
        "max_drawdown_R": float(drawdown.max(initial=0.0)),
    }


def run_one(name, fn, uses_window, contexts, mode, window_days, killzone, open_rule, split):
    trades = []
    for side, context in contexts.items():
        window_bars = window_days * 1440 if uses_window else None
        result = fn(context, mode, window_bars, kz_on=killzone, open_mode=open_rule)
        for trade in result:
            row = dict(trade)
            row["side"] = side
            trades.append(row)
    trades.sort(key=lambda trade: trade["t"])

    early = [trade for trade in trades if trade["t"] < split]
    late = [trade for trade in trades if trade["t"] >= split]
    full_stats = stats(trades)
    first_stats, second_stats = stats(early), stats(late)
    summary = {
        "entrypoint": name,
        "lectures": ENTRYPOINTS[name][0],
        "setup": ENTRYPOINTS[name][1],
        "bias_mode": mode,
        "window_days": window_days if uses_window else "n/a",
        "killzone": killzone,
        "open_rule": open_rule,
        **full_stats,
        "maker_total_R_assumption": float(sum(t.get("R_mk", 0.0) for t in trades)),
        "long_trades": sum(t["side"] == "L" for t in trades),
        "median_stop_pct": float(np.median([t["risk"] for t in trades]) * 100) if trades else np.nan,
        "first_half_n": first_stats["n"],
        "first_half_R": first_stats["total_R"],
        "second_half_n": second_stats["n"],
        "second_half_R": second_stats["total_R"],
        "exit_reasons": str(pd.Series([t.get("why", "") for t in trades], dtype="object").value_counts().to_dict()),
    }
    trade_rows = [dict(entrypoint=name, bias_mode=mode, **trade) for trade in trades]
    return summary, trade_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="comma-separated entrypoint names; default: all")
    parser.add_argument("--both-bias", action="store_true", help="run structure and narrative bias separately")
    parser.add_argument("--window-days", type=int, default=3,
                        help="setup lifetime assumption for windowed strategies (default: 3)")
    parser.add_argument("--killzone", choices=("on", "off"), default="on")
    parser.add_argument("--open-rule", choices=("strict", "daily"), default="strict")
    parser.add_argument("--rebuild", action="store_true", help="rebuild the large cached contexts")
    args = parser.parse_args()

    selected = [x.strip() for x in args.only.split(",")] if args.only else list(ENTRYPOINTS)
    unknown = sorted(set(selected) - set(ENTRYPOINTS))
    if unknown:
        parser.error("unknown entrypoint(s): " + ",".join(unknown))
    missing = sorted(set(selected) - set(RUNNERS))
    if missing:
        parser.error("no implementation registered for: " + ",".join(missing))
    if args.window_days < 1:
        parser.error("--window-days must be >= 1")

    started = time.time()
    contexts = {side: ctx(side, args.rebuild) for side in ("L", "S")}
    index = contexts["L"]["idx"]
    split = index[0] + (index[-1] - index[0]) / 2
    modes = ("structure", "narrative") if args.both_bias else ("structure",)
    rows, trade_rows = [], []
    for name in selected:
        fn, uses_window = RUNNERS[name]
        for mode in modes:
            row, detail = run_one(name, fn, uses_window, contexts, mode, args.window_days,
                                  args.killzone == "on", args.open_rule, split)
            rows.append(row)
            trade_rows.extend(detail)
            print(f"{name:4} {mode:10} n={row['n']:4} avgR={row['avg_R']:+.3f} "
                  f"totalR={row['total_R']:+8.2f} PF={row['profit_factor']:.2f} "
                  f"DD={row['max_drawdown_R']:.2f} "
                  f"halves={row['first_half_n']}:{row['first_half_R']:+.2f}/"
                  f"{row['second_half_n']}:{row['second_half_R']:+.2f}", flush=True)

    output = os.path.join(HERE, "entrypoint_results.csv")
    pd.DataFrame(rows).to_csv(output, index=False, encoding="utf-8-sig")
    trade_output = os.path.join(HERE, "entrypoint_trades.csv")
    pd.DataFrame(trade_rows).to_csv(trade_output, index=False, encoding="utf-8-sig")
    print(f"기간 {index[0]:%Y-%m-%d} ~ {index[-1]:%Y-%m-%d}; "
          f"프로파일: window={args.window_days}d, killzone={args.killzone}, "
          f"open_rule={args.open_rule}; {time.time() - started:.0f}s")
    print(f"결과 저장: {output}")
    print(f"체결별 기록 저장: {trade_output}")


if __name__ == "__main__":
    main()
