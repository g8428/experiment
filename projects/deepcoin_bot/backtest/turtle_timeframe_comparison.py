"""Compare one Turtle-style Donchian breakout rule on 5m and 15m candles."""
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import engine_v2 as E
from run_v2 import load


class TurtleBars:
    def __init__(self, tf, n=20, name=None, daily_atr=False):
        self.base_tf = tf
        self.n = n
        self.daily_atr = daily_atr
        self.name = name or f"Turtle{n}_{tf}"

    def prepare(self, data):
        b = data[self.base_tf]
        self.c = b.c.to_numpy(); self.t = b.t.to_numpy()
        self.hi = b.h.to_numpy(); self.lo = b.l.to_numpy()
        self.atr = E.atr(b, 14).to_numpy()
        self.hh = b.h.shift(1).rolling(self.n).max().to_numpy()
        self.ll = b.l.shift(1).rolling(self.n).min().to_numpy()
        if self.daily_atr:
            d = data["1D"]
            da = E.atr(d, 14).to_numpy()
            dct = d.ct.to_numpy()
            nd = np.searchsorted(dct, b.ct.to_numpy(), side="right")
            self.atr = np.array([da[k - 1] if k > 0 else np.nan for k in nd])

    def signal(self, i, ctx):
        if i < self.n + 1 or not np.isfinite(self.atr[i]) or self.atr[i] <= 0:
            return None
        c = self.c[i]
        if c > self.hh[i] and self.c[i - 1] <= self.hh[i]:
            d = 1
        elif c < self.ll[i] and self.c[i - 1] >= self.ll[i]:
            d = -1
        else:
            return None
        n = self.atr[i]
        mins_per_bar = {"5m": 5, "15m": 15}[self.base_tf]
        return {"dir": d, "sl": c - d * 2 * n, "tp": None,
                "trail_dist": 3 * n, "trail_after_r": 0.5,
                "time_stop": int(30 * 24 * 60 / mins_per_bar), "tag": "TURTLE20"}


TFS = {"5m": ("5m", 300_000), "15m": ("15m", 900_000)}
SYMS = ("BTC", "ETH", "XRP")


def date(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d")


def main():
    result_rows, trade_rows = [], []
    for sym in SYMS:
        ticker = f"{sym}-USDT-SWAP"
        data = load(ticker, need_5m=True, horizon="2y")
        for tf, (key, bar_ms) in TFS.items():
            base = data[key]
            t0, t1 = int(base.t.iloc[0]), int(base.t.iloc[-1])
            mid = t0 + (t1 - t0) // 2
            variants = [("20bar", 20, False),
                        ("20day_equiv", int(20 * 24 * 60 / (bar_ms / 60_000)), True)]
            for variant, n, daily_atr in variants:
                strat = TurtleBars(tf, n=n, name=f"Turtle_{variant}_{tf}", daily_atr=daily_atr)
                strat.prepare(data)
                for label, start, end in (("전체", None, None),
                                          ("전반(IS)", None, mid - bar_ms),
                                          ("후반(OOS)", mid, None)):
                    res = E.run(strat, data, risk_pct=2.0, fee=0.0006, slip=0.0002,
                                start_ts=start, end_ts=end)
                    sm = E.summarize(res, label)
                    stamp0 = int(base.t.iloc[0]) if start is None else start
                    stamp1 = int(base.t.iloc[-1]) if end is None else end
                    c, hh, ll, tt = strat.c, strat.hh, strat.ll, strat.t
                    prev = np.r_[np.nan, c[:-1]]
                    mask = np.isfinite(hh) & np.isfinite(ll)
                    if start is not None: mask &= tt >= start
                    if end is not None: mask &= tt < end
                    raw_entries = int((((c > hh) & (prev <= hh)) | ((c < ll) & (prev >= ll)))[mask].sum())
                    years = max((min(stamp1, t1) - stamp0) / (365.25 * 24 * 60 * 60 * 1000), 1 / 365.25)
                    row = {"symbol": sym, "timeframe": tf, "variant": variant,
                           "lookback_bars": n, "daily_atr": daily_atr,
                           "from": date(stamp0), "to": date(stamp1), "bars": len(base),
                           "period": label, **sm,
                           "raw_breakout_signals": raw_entries,
                           "raw_signals_per_year": round(raw_entries / years, 2),
                           "risk_pct": 2.0, "fee_each_side": 0.0006,
                           "slippage_each_side": 0.0002}
                    result_rows.append(row)
                    if label == "전체":
                        mins = TFS[tf][1] / 60_000
                        row["avg_hold_hours"] = round(sm["avg_bars"] * mins / 60, 2)
                        for trade in res["trades"]:
                            trade_rows.append({"symbol": sym, "timeframe": tf, "variant": variant, **trade})
                    print(f"| {sym} | {tf} | {variant} | {label} | signals {raw_entries} ({row['raw_signals_per_year']}/y) | trades {sm['trades']} | PF {sm['pf']} | R {sm['exp_r']} | return {sm['return_pct']}% | MDD {sm['mdd_pct']}% |", flush=True)

    root = os.path.join(os.path.dirname(HERE), "research", "turtle_timeframe_2026-10-03")
    with open(root + ".json", "w", encoding="utf-8") as f:
        json.dump(result_rows, f, ensure_ascii=False, indent=2, default=float)
    pd.DataFrame(result_rows).to_csv(root + ".csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(trade_rows).to_csv(root + "_trades.csv", index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
