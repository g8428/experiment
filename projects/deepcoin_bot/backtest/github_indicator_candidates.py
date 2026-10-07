"""Fixed-rule comparison of popular indicator strategy families.

Research only. Uses engine_v2's next-hour-open execution, taker fee, slippage,
stop-first intrabar resolution, leverage cap and risk sizing.
"""
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


def _bollinger(close, n=20, k=2.0):
    mid = close.rolling(n).mean()
    sd = close.rolling(n).std(ddof=0)
    return mid, mid + k * sd, mid - k * sd


class Candidate:
    base_tf = "1H"

    def __init__(self, name):
        self.name = name

    def prepare(self, data):
        h, d = data["1H"], data["1D"]
        self.h, self.d = h, d
        self.hc = h.c.to_numpy(); self.hh = h.h.to_numpy(); self.hl = h.l.to_numpy()
        self.ht = h.t.to_numpy(); self.hct = h.ct.to_numpy()
        self.atrh = E.atr(h, 14).to_numpy()
        self.ema5 = E.ema(h.c, 5).to_numpy()
        self.ema200 = E.ema(h.c, 200).to_numpy()
        self.rsi2 = E.rsi(h.c, 2).to_numpy()
        self.rsi5 = E.rsi(h.c, 5).to_numpy()
        self.bmid, self.bup, self.blo = [x.to_numpy() for x in _bollinger(h.c)]
        self.mean24 = h.c.rolling(24).mean().to_numpy()
        self.sd24 = h.c.rolling(24).std(ddof=0).to_numpy()
        self.da = E.atr(d, 14).to_numpy()
        self.dct = d.ct.to_numpy()
        self.do = d.o.to_numpy(); self.dh = d.h.to_numpy(); self.dl = d.l.to_numpy(); self.dc = d.c.to_numpy()
        # Number of fully closed daily bars at the decision time.
        self.nd = np.searchsorted(self.dct, self.hct, side="right")
        self.ema50d = E.ema(d.c, 50).to_numpy()
        self.ema20d = E.ema(d.c, 20).to_numpy()
        self.hh20 = d.h.shift(1).rolling(20).max().to_numpy()
        self.ll20 = d.l.shift(1).rolling(20).min().to_numpy()

    def signal(self, i, ctx):
        raise NotImplementedError


class Turtle20(Candidate):
    """20-day breakout; 2N initial stop and 3N chandelier trail (no pyramiding)."""
    def __init__(self): super().__init__("Turtle20")

    def signal(self, i, ctx):
        j = self.nd[i] - 1
        if j < 55 or self.dct[j] != self.hct[i]:
            return None
        c, n = self.dc[j], self.da[j]
        if not np.isfinite(n) or n <= 0: return None
        if c > self.hh20[j]: d = 1
        elif c < self.ll20[j]: d = -1
        else: return None
        return {"dir": d, "sl": c - d * 2 * n, "tp": None,
                "trail_dist": 3 * n, "trail_after_r": 0.5,
                "time_stop": 24 * 30, "tag": "TURTLE20"}


class DualThrust(Candidate):
    """4-day Dual Thrust range, 0.5 breakout coefficients, 1.5 ATR stop, 12h max hold."""
    def __init__(self): super().__init__("DualThrust")

    def signal(self, i, ctx):
        j = self.nd[i] - 1
        if j < 5: return None
        # Only evaluate during an active daily candle, using its known open and
        # the prior four completed daily candles for range construction.
        day_open = self.do[j + 1] if j + 1 < len(self.do) else np.nan
        if not np.isfinite(day_open): return None
        a, b = j - 3, j + 1
        hh = np.max(self.dh[a:b]); lc = np.min(self.dc[a:b]); hc = np.max(self.dc[a:b]); ll = np.min(self.dl[a:b])
        rng = max(hh - lc, hc - ll)
        up, dn = day_open + 0.5 * rng, day_open - 0.5 * rng
        c, prev = self.hc[i], self.hc[i - 1]
        d = 1 if prev <= up < c else (-1 if prev >= dn > c else 0)
        atr = self.atrh[i]
        if not d or not np.isfinite(atr) or atr <= 0: return None
        return {"dir": d, "sl": c - d * 1.5 * atr, "tp": None,
                "time_stop": 12, "tag": "DUALTHRUST"}


class RSI2MeanReversion(Candidate):
    """RSI(2) extreme with EMA200 direction filter; ATR stop/target and 48h timeout."""
    def __init__(self): super().__init__("RSI2_EMA200")

    def signal(self, i, ctx):
        if i < 220 or not np.isfinite(self.rsi2[i]): return None
        c, a = self.hc[i], self.atrh[i]
        if c > self.ema200[i] and self.rsi2[i] <= 10: d = 1
        elif c < self.ema200[i] and self.rsi2[i] >= 90: d = -1
        else: return None
        return {"dir": d, "sl": c - d * 2 * a, "tp": c + d * 1.5 * a,
                "time_stop": 48, "tag": "RSI2_MR"}


class BollingerReentry(Candidate):
    """Fade a close that returns inside the 2σ band; target middle band."""
    def __init__(self): super().__init__("BollingerReentry")

    def signal(self, i, ctx):
        if i < 30: return None
        c, p = self.hc[i], self.hc[i - 1]
        if p < self.blo[i - 1] and c >= self.blo[i]: d = 1
        elif p > self.bup[i - 1] and c <= self.bup[i]: d = -1
        else: return None
        a = self.atrh[i]
        sl = c - d * 1.5 * a
        tp = self.bmid[i]
        if not np.isfinite(tp) or (tp - c) * d <= 0: return None
        return {"dir": d, "sl": sl, "tp": tp, "time_stop": 24, "tag": "BB_REENTRY"}


class ZScoreReversion(Candidate):
    """24h rolling z-score re-entry from ±2σ toward the mean; 1.5 ATR stop."""
    def __init__(self): super().__init__("ZScore24Reversion")

    def signal(self, i, ctx):
        if i < 30 or not np.isfinite(self.sd24[i]) or self.sd24[i] <= 0: return None
        z0 = (self.hc[i - 1] - self.mean24[i - 1]) / self.sd24[i - 1]
        z1 = (self.hc[i] - self.mean24[i]) / self.sd24[i]
        if z0 <= -2 and z1 > -2: d = 1
        elif z0 >= 2 and z1 < 2: d = -1
        else: return None
        c, a, target = self.hc[i], self.atrh[i], self.mean24[i]
        if (target - c) * d <= 0: return None
        return {"dir": d, "sl": c - d * 1.5 * a, "tp": target,
                "time_stop": 24, "tag": "ZSCORE24"}


FACTORIES = [Turtle20, DualThrust, RSI2MeanReversion, BollingerReentry, ZScoreReversion]
SYMBOLS = ["BTC", "ETH", "XRP"]
FEE, SLIP, RISK = 0.0006, 0.0002, 2.0


def main():
    out_dir = os.path.join(os.path.dirname(HERE), "research")
    rows, trade_rows = [], []
    for sym in SYMBOLS:
        ticker = f"{sym}-USDT-SWAP"
        data = load(ticker, horizon="4y")
        base = data["1H"]
        mid = int(base.t.iloc[0] + (base.t.iloc[-1] - base.t.iloc[0]) // 2)
        for factory in FACTORIES:
            strategy = factory()
            # engine_v2 currently marks an open trade at i == hi_i on a bounded
            # run; move the IS cutoff back one full base bar so that forced
            # end-of-window liquidation stays inside the IS sample.
            for label, start, end in (("전체", None, None), ("전반(IS)", None, mid - E.TF_MS["1H"]), ("후반(OOS)", mid, None)):
                result = E.run(strategy, data, risk_pct=RISK, fee=FEE, slip=SLIP,
                               start_ts=start, end_ts=end, fill="next_open")
                sm = E.summarize(result, label)
                row = {"symbol": sym, "strategy": strategy.name, "period": label,
                       "from": datetime.fromtimestamp((start or int(base.t.iloc[0])) / 1000, timezone.utc).strftime("%Y-%m-%d"),
                       "to": datetime.fromtimestamp((mid - E.TF_MS["1H"] if label == "전반(IS)" else end or int(base.t.iloc[-1])) / 1000, timezone.utc).strftime("%Y-%m-%d"),
                       **sm, "fee_each_side": FEE, "slippage_each_side": SLIP,
                       "risk_pct": RISK}
                rows.append(row)
                if label == "전체":
                    for t in result["trades"]:
                        trade_rows.append({"symbol": sym, "strategy": strategy.name, **t})
    stem = os.path.join(out_dir, "indicator_candidate_backtest_2026-10-03")
    with open(stem + ".json", "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2, default=float)
    pd.DataFrame(rows).to_csv(stem + ".csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(trade_rows).to_csv(stem + "_trades.csv", index=False, encoding="utf-8-sig")
    for row in rows:
        print("| {symbol} | {strategy} | {period} | {trades} | {win_rate}% | {pf} | {exp_r}R | {return_pct}% | {mdd_pct}% | {fees_pct}% |".format(**row))


if __name__ == "__main__":
    main()
