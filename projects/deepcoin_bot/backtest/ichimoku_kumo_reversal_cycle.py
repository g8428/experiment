"""Backtest the user's Ichimoku current-cloud interaction / future-cloud exit.

Blue/current cloud is Senkou A/B shifted back 26 daily bars. Red/future cloud is
today's raw Senkou A/B projected 26 bars forward. Close-confirmed orders fill at
the next daily open. Funding is excluded.
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


def indicators(df):
    d = df.copy().reset_index(drop=True)
    tenkan = (d.h.rolling(9).max() + d.l.rolling(9).min()) / 2
    kijun = (d.h.rolling(26).max() + d.l.rolling(26).min()) / 2
    d["future_a"] = (tenkan + kijun) / 2
    d["future_b"] = (d.h.rolling(52).max() + d.l.rolling(52).min()) / 2
    d["future_top"] = d[["future_a", "future_b"]].max(axis=1)
    d["future_bottom"] = d[["future_a", "future_b"]].min(axis=1)
    # Today's blue cloud is the Senkou values plotted 26 days ago.
    d["current_a"] = d.future_a.shift(26)
    d["current_b"] = d.future_b.shift(26)
    d["current_top"] = d[["current_a", "current_b"]].max(axis=1)
    d["current_bottom"] = d[["current_a", "current_b"]].min(axis=1)
    return d


def backtest(df, fee=0.0006, slip=0.0002, body_min=0.04, allow_short=True):
    d = indicators(df)
    cost = fee + slip
    first = max(78, int(d.current_bottom.first_valid_index()) + 1)
    equity = peak = 1.0
    max_dd = 0.0
    pos = None
    pending_entry = None
    pending_exit = None
    phase = "look_long"  # look_long -> long -> wait_short -> short -> look_long
    phase_exit_signal_i = -1
    long_setup_armed = False
    long_lower_touch_seen = False
    short_cloud_touch_seen = False
    future_cloud_outside_seen = False
    trades = []
    canceled = 0
    exposure_bars = 0

    def enter(side, price, i):
        nonlocal equity, pos, long_setup_armed, long_lower_touch_seen
        nonlocal short_cloud_touch_seen, future_cloud_outside_seen
        capital = equity
        qty = capital / price  # 1x linear notional
        entry_fee = qty * price * cost
        equity = max(0.0, equity - entry_fee)
        pos = {
            "side": side, "entry": price, "entry_i": i,
            "capital": capital, "qty": qty, "entry_fee": entry_fee,
            "future_outside_seen": False, "below_future_confirmed": False,
        }
        long_setup_armed = False
        long_lower_touch_seen = False
        short_cloud_touch_seen = False
        future_cloud_outside_seen = False

    def exit_position(price, i, reason):
        nonlocal equity, pos, phase, phase_exit_signal_i
        nonlocal long_setup_armed, long_lower_touch_seen, short_cloud_touch_seen
        nonlocal future_cloud_outside_seen
        p = pos
        gross = p["side"] * p["qty"] * (price - p["entry"])
        exit_fee = p["qty"] * price * cost
        equity = max(0.0, p["capital"] + gross - p["entry_fee"] - exit_fee)
        trade_return = (equity / p["capital"] - 1) * 100 if p["capital"] else 0.0
        trades.append({
            "side": "long" if p["side"] == 1 else "short",
            "entry_date": pd.to_datetime(int(d.t.iloc[p["entry_i"]]), unit="ms", utc=True).strftime("%Y-%m-%d"),
            "exit_date": pd.to_datetime(int(d.t.iloc[i]), unit="ms", utc=True).strftime("%Y-%m-%d"),
            "entry": round(float(p["entry"]), 6), "exit": round(float(price), 6),
            "net_pnl_pct_on_trade_start_equity": round(trade_return, 3),
            "exit_reason": reason,
        })
        old_side = p["side"]
        pos = None
        if old_side == 1 and allow_short:
            phase = "wait_short"
            short_cloud_touch_seen = False
        else:
            phase = "look_long"
            long_setup_armed = False
            long_lower_touch_seen = False
        future_cloud_outside_seen = False
        # Exit signal was yesterday's completed close; fill is today's open.
        phase_exit_signal_i = i - 1

    for i in range(first, len(d)):
        # Prior daily close exit signal: liquidate at this day's open.
        if pending_exit is not None and pos is not None:
            exit_position(float(d.o.iloc[i]), i, pending_exit)
            pending_exit = None

        # Prior close entry signal: enter at this day's open if the breakout holds.
        if pending_entry is not None:
            side, invalid_edge = pending_entry
            open_px = float(d.o.iloc[i])
            still_outside = open_px > invalid_edge if side == 1 else open_px < invalid_edge
            if still_outside and pos is None:
                enter(side, open_px, i)
                phase = "long" if side == 1 else "short"
            else:
                canceled += 1
            pending_entry = None

        # Intraday adverse excursion for risk measurement; trading decisions stay close-based.
        if pos is not None:
            adverse_px = float(d.l.iloc[i]) if pos["side"] == 1 else float(d.h.iloc[i])
            adverse_equity = max(0.0, pos["capital"] - pos["entry_fee"] +
                                 pos["side"] * pos["qty"] * (adverse_px - pos["entry"]))
            peak = max(peak, equity)
            max_dd = max(max_dd, (peak - adverse_equity) / peak if peak else 0.0)

        # Position exits use a completed close touching/entering the projected red cloud.
        if pos is not None:
            close = float(d.c.iloc[i])
            f_top, f_bottom = float(d.future_top.iloc[i]), float(d.future_bottom.iloc[i])
            if pos["side"] == 1:
                if close > f_top or close < f_bottom:
                    pos["future_outside_seen"] = True
                elif pos["future_outside_seen"]:
                    pending_exit = "일봉 종가 미래 구름 접촉"
            else:
                if i > pos["entry_i"] and close < f_bottom:
                    pos["below_future_confirmed"] = True
                    pos["future_outside_seen"] = True
                elif pos["below_future_confirmed"] and close >= f_bottom:
                    pending_exit = "일봉 종가 미래 구름 재접촉"
            exposure_bars += 1
            marked = max(0.0, pos["capital"] - pos["entry_fee"] +
                         pos["side"] * pos["qty"] * (close - pos["entry"]))
        else:
            marked = equity
        peak = max(peak, marked)
        max_dd = max(max_dd, (peak - marked) / peak if peak else 0.0)

        # All signals form at daily close and execute no earlier than next open.
        if pos is not None or pending_entry is not None or pending_exit is not None or i + 1 >= len(d):
            continue
        if i <= first or not np.isfinite(d.current_bottom.iloc[i]):
            continue

        close = float(d.c.iloc[i])
        current_top = float(d.current_top.iloc[i])
        current_bottom = float(d.current_bottom.iloc[i])
        body_pct = close / float(d.o.iloc[i]) - 1
        in_current_cloud = current_bottom <= close <= current_top

        if phase == "look_long":
            if d.current_a.iloc[i] < d.current_b.iloc[i] and close < current_bottom:
                long_setup_armed = True
                long_lower_touch_seen = False
            elif long_setup_armed and in_current_cloud:
                # A daily close reached the lower edge or entered the blue cloud.
                long_lower_touch_seen = True
            elif long_setup_armed and close < current_bottom:
                long_lower_touch_seen = False
            if (long_setup_armed and long_lower_touch_seen and
                    body_pct >= body_min and close > current_top):
                pending_entry = (1, current_top)

        elif allow_short and phase == "wait_short" and i > phase_exit_signal_i:
            if in_current_cloud:
                short_cloud_touch_seen = True
            elif close > current_top:
                short_cloud_touch_seen = False
            if short_cloud_touch_seen and body_pct <= -body_min and close < current_bottom:
                pending_entry = (-1, current_bottom)

    # If a close signal is pending at the cache endpoint, use final close; otherwise
    # flatten any open trade at the final close so reported equity is realized.
    if pos is not None:
        reason = pending_exit or "데이터 종료 강제청산"
        exit_position(float(d.c.iloc[-1]), len(d) - 1, reason + " (마지막 종가)")
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak if peak else 0.0)

    bh = (1 - cost) * (float(d.c.iloc[-1]) / float(d.o.iloc[first])) * (1 - cost)
    wins = sum(t["net_pnl_pct_on_trade_start_equity"] > 0 for t in trades)
    longs = [t for t in trades if t["side"] == "long"]
    shorts = [t for t in trades if t["side"] == "short"]
    return {
        "strategy": "user_defined_ichimoku_current_cloud_interaction_future_cloud_exit",
        "range": {
            "from": pd.to_datetime(int(d.t.iloc[first]), unit="ms", utc=True).strftime("%Y-%m-%d"),
            "to": pd.to_datetime(int(d.t.iloc[-1]), unit="ms", utc=True).strftime("%Y-%m-%d"),
            "daily_bars": int(len(d) - first),
        },
        "rules": {
            "current_blue_cloud": "Senkou A/B plotted at current candle date: raw spans shifted back 26 daily bars",
            "future_red_cloud": "today's raw Senkou A/B plotted 26 bars ahead",
            "long_setup": "current blue cloud Span A < Span B and a close below its lower edge; then a daily close touches/enters the lower cloud",
            "long_entry": f"later bullish candle body >= {body_min:.1%} of open and close above current-cloud upper edge; enter next open",
            "long_exit": "after a close outside projected future cloud, exit next open when a daily close touches/enters it",
            "short_entry": f"after long exit, current-cloud close interaction then later bearish candle body <= -{body_min:.1%} and close below current-cloud lower edge; enter next open",
            "short_exit": "after a post-entry close below future cloud, exit next open when close retouches its lower edge",
            "fee_per_side_pct": fee * 100,
            "slippage_per_side_pct": slip * 100,
            "funding_included": False,
            "short_cycle_enabled": allow_short,
        },
        "summary": {
            "net_return_pct": round((equity - 1) * 100, 2),
            "max_drawdown_pct": round(max_dd * 100, 2),
            "closed_trades": len(trades),
            "long_trades": len(longs),
            "short_trades": len(shorts),
            "win_rate_pct": round(100 * wins / len(trades), 1) if trades else 0.0,
            "canceled_gap_entries": canceled,
            "position_exposure_pct": round(100 * exposure_bars / max(1, len(d) - first), 1),
            "buy_hold_same_period_pct": round((bh - 1) * 100, 2),
        },
        "trades": trades,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sym", default="BTC-USDT-SWAP")
    ap.add_argument("--fee", type=float, default=0.0006)
    ap.add_argument("--slip", type=float, default=0.0002)
    ap.add_argument("--body", type=float, default=0.04, help="minimum candle body change from open")
    ap.add_argument("--long-only", action="store_true", help="disable the symmetric short cycle")
    args = ap.parse_args()
    df = E.load_df(args.sym, "1D", 800)
    mode = "long_only" if args.long_only else "long_short_cycle"
    result = {"sym": args.sym, **backtest(df, args.fee, args.slip, args.body, not args.long_only)}
    out_dir = os.path.join(os.path.dirname(HERE), "research", "backtest_v2")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{args.sym.split('-')[0]}_ichimoku_kumo_reversal_{mode}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
