"""추세돌파(RegimeTrend 롱, BTC) 반익절 변형 비교. python backtest/partial_tp_test.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_v2 as E
import strategies_v2 as S

data = {"1H": E.load_df("BTC-USDT-SWAP", "1H", 1460), "1D": E.load_df("BTC-USDT-SWAP", "1D", 1600)}
data["4H"] = E.resample(data["1H"], "1H", "4H")


class WithPartial:
    def __init__(self, inner, r, frac=0.5, be=False):
        self.inner, self.r, self.frac, self.be = inner, r, frac, be
        self.base_tf, self.name = inner.base_tf, inner.name

    def prepare(self, d):
        self.inner.prepare(d)

    def signal(self, i, ctx):
        s = self.inner.signal(i, ctx)
        if s and self.r is not None:
            s = dict(s, partial_r=self.r, partial_frac=self.frac, partial_be=self.be)
        return s


def base():
    return S.RegimeTrend(allow_short=False, name="regime_trend_long")


half = len(data["1H"]) // 2
mid_ts = int(data["1H"]["t"].iloc[half])
rows = []
variants = [("반익절 없음(현재)", None, 0.5, False)]
for r in (1.0, 1.618, 2.0, 3.0):
    for be in (False, True):
        variants.append((f"50% @ {r}R" + (" +본절" if be else ""), r, 0.5, be))
variants.append(("30% @ 1.0R +본절", 1.0, 0.3, True))

for label, r, frac, be in variants:
    out = {}
    for part, kw in (("전체", {}), ("전반", {"end_ts": mid_ts}), ("후반", {"start_ts": mid_ts})):
        res = E.run(WithPartial(base(), r, frac, be), data, risk_pct=2, **kw)
        out[part] = E.summarize(res, label)
    rows.append((label, out))

print(f"{'변형':<22}{'구간':<5}{'거래':>5}{'승률':>7}{'PF':>7}{'거래당R':>8}{'수익률':>9}{'MDD':>7}")
for label, out in rows:
    for part in ("전체", "전반", "후반"):
        s = out[part]
        print(f"{label:<22}{part:<5}{s['trades']:>5}{s['win_rate']:>7}{s['pf']:>7}{s['exp_r']:>8}{s['return_pct']:>8}%{s['mdd_pct']:>6}%")
    print()
