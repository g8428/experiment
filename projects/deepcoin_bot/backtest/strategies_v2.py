"""
strategies_v2.py — engine_v2 용 전략 모음 (연구용, 라이브 server.py는 import하지 않음)

1) LegacyChain        — 현재 라이브 체인(OTE→MTF, m15_confirm_n=2)을 server.py 규칙 그대로 재현.
                        ict_engine.py 함수를 그대로 호출하고, 라이브와 같은 캔들 개수
                        (15m 60 / 1H 25 / 1D 120 / 5m 20)와 SL/TP/RR 게이트를 적용한다.
2) LegacyIntrabar     — 같은 체인을 "라이브처럼" 미완성 캔들로 평가 (5분마다, 15m/1H/1D 진행 중 봉 포함).
                        라이브 루프는 몇십 초마다 진행 중인 캔들로 판단하므로, 백테스트(종가 판단)와
                        실거래 결과가 다른 이유를 측정하기 위한 것.
3) TrendPullback      — 신규: D1 추세 + 4H ADX 추세강도 확인 → 1H 눌림목 후 재개 캔들에서 추세 방향 진입,
                        ATR 손절 + 1R 후 본절·샹들리에 트레일링 (손익비를 고정하지 않고 추세를 끝까지 탄다)
4) DonchianBreakout   — 신규: 4H 20봉 돌파 (D1 추세 방향만), 4H ATR 손절·트레일링 (터틀식)
5) RangeReversion     — 신규: 추세가 없을 때만(D1 무추세 + 4H ADX<20) 1H 볼린저 밴드 이탈 후 복귀 역추세
6) Adaptive           — 신규: 국면 라우터. 추세장 → 3/4, 횡보장 → 5, 변동성 쇼크(1H ATR% 90일 97분위 초과) → 진입 금지
"""

import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.path.insert(0, _HERE)

from engine_v2 import TF_MS, adx, atr, ema, rsi  # noqa: E402


def _records(df):
    return [{"t": int(r.t), "o": r.o, "h": r.h, "l": r.l, "c": r.c, "v": r.v}
            for r in df[["t", "o", "h", "l", "c", "v"]].itertuples(index=False)]


def _atr14_list(kl):
    if len(kl) < 15:
        return 0.0
    tr = [max(kl[i]["h"] - kl[i]["l"], abs(kl[i]["h"] - kl[i - 1]["c"]), abs(kl[i]["l"] - kl[i - 1]["c"]))
          for i in range(1, len(kl))]
    return sum(tr[-14:]) / 14


# ═══════════════════════════ 1) 현재 라이브 체인 ═══════════════════════════

class LegacyChain:
    base_tf = "15m"

    def __init__(self, sym, tuning, chain=("OTE", "MTF"), m15_confirm_n=2,
                 n15=60, n1h=25, n1d=120, n5=20, name=None,
                 m5_structure_lookback=0):
        import ict_engine as ie
        self.ie = ie
        self.sym = sym
        self.chain = chain
        self.m15 = m15_confirm_n
        self.n15, self.n1h, self.n1d = n15, n1h, n1d
        self.m5_structure_lookback = max(0, int(m5_structure_lookback))
        self.n5 = max(n5, self.m5_structure_lookback)
        self.name = name or "legacy_" + "+".join(chain)
        lev = tuning.get("leverage", 20)
        self.tp_cap = tuning.get("tp_max_pct", 15.0) / 100
        self.sl_cap = tuning.get("sl_cap_pct_by_sym", {}).get(sym, tuning.get("sl_cap_pct", 2.0)) / 100
        tpm = tuning.get("tp_min_margin_by_sym", {}).get(sym, tuning.get("tp_min_margin_pct", 0))
        self.tp_min = tpm / (100.0 * lev) if tpm > 0 else 0.0
        self.sl_mult = tuning.get("sl_min_atr_mult_by_sym", {}).get(sym, tuning.get("sl_min_atr_mult", 0.8))
        self.rr_min = tuning.get("rr_min", 2.5)
        self.fns = {
            "SMC": lambda kl, h1, d1, m5, struct: ie.get_smc_signal(kl, h1_kl=h1, structure_kl=struct),
            "OTE": lambda kl, h1, d1, m5, struct: ie.get_ote_signal(
                kl, h1_kl=h1, d1_kl=d1, m15_confirm_n=self.m15, structure_kl=struct),
            "MTF": lambda kl, h1, d1, m5, struct: ie.get_mtf_signal(
                kl, h1_kl=h1, d1_kl=d1, m5_kl=m5, m15_confirm_n=self.m15, structure_kl=struct),
            "KZ": lambda kl, h1, d1, m5, struct: ie.get_killzone_signal(
                kl, h1_kl=h1, d1_kl=d1, m15_confirm_n=self.m15, structure_kl=struct),
            "BRK": lambda kl, h1, d1, m5, struct: ie.get_breaker_signal(
                kl, h1_kl=h1, d1_kl=d1, m15_confirm_n=self.m15),
        }

    def prepare(self, data):
        self.k = {tf: _records(df) for tf, df in data.items() if tf in ("15m", "1H", "1D", "5m")}

    def _windows(self, i, ctx):
        kl = self.k["15m"][max(0, i - self.n15 + 1): i + 1]
        nh = ctx.n_closed("1H", i); h1 = self.k["1H"][max(0, nh - self.n1h): nh]
        nd = ctx.n_closed("1D", i); d1 = self.k["1D"][max(0, nd - self.n1d): nd]
        m5 = None
        if "5m" in self.k:
            n5 = ctx.n_closed("5m", i); m5 = self.k["5m"][max(0, n5 - self.n5): n5]
        return kl, h1, d1, m5

    def evaluate(self, kl, h1, d1, m5):
        """server.py _run_claude_bot 진입 블록과 동일한 SL/TP/RR 게이트."""
        if len(kl) < 30:
            return None
        structure = (m5[-self.m5_structure_lookback:]
                     if self.m5_structure_lookback and m5 else None)
        smc, src = None, None
        for name in self.chain:
            try:
                r = self.fns[name](kl, h1, d1, m5, structure)
            except Exception:
                continue
            if r.get("signal"):
                smc, src = r, name
                break
        if not smc:
            return None
        sig = smc["signal"]; s_sl = smc.get("sl"); s_tp = smc.get("tp1"); s_tp2 = smc.get("tp2")
        price = kl[-1]["c"]
        a = _atr14_list(kl) or price * 0.01
        sl_min = max(a / price * self.sl_mult, 0.003)
        if s_tp and s_tp2:
            if sig == "long" and s_tp2 > s_tp and 0 < (s_tp2 - price) / price <= 0.02:
                s_tp = s_tp2
            elif sig == "short" and s_tp2 < s_tp and 0 < (price - s_tp2) / price <= 0.02:
                s_tp = s_tp2
        if s_sl and s_tp:
            if sig == "long":
                tp_d = min((s_tp - price) / price, self.tp_cap) if s_tp > price else a / price * 2
                raw = (price - s_sl) / price if s_sl < price else a / price * self.sl_mult
            else:
                tp_d = min((price - s_tp) / price, self.tp_cap) if s_tp < price else a / price * 2
                raw = (s_sl - price) / price if s_sl > price else a / price * self.sl_mult
            sl_d = min(max(raw, sl_min), self.sl_cap)
        else:
            tp_d = min(a / price * 2, self.tp_cap)
            sl_d = min(max(a / price * self.sl_mult, sl_min), self.sl_cap)
        if self.tp_min > 0 and tp_d < self.tp_min:
            return None
        if tp_d < sl_d * self.rr_min:
            return None
        d = 1 if sig == "long" else -1
        return {"dir": d, "sl": price * (1 - sl_d * d), "tp": price * (1 + tp_d * d), "tag": src}

    def signal(self, i, ctx):
        return self.evaluate(*self._windows(i, ctx))


class LegacyIntrabar(LegacyChain):
    """5분마다 '진행 중인' 15m/1H/1D 캔들을 포함해 판단 — 라이브 루프와 같은 관점."""
    base_tf = "5m"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.name = (kw.get("name") or self.name) + "_intrabar"

    def prepare(self, data):
        super().prepare(data)
        m5 = data["5m"]
        self.t5 = m5["t"].values
        self.ct5 = m5["ct"].values
        self.forming = {}
        for tf in ("15m", "1H", "1D"):
            step = TF_MS[tf]
            if tf == "1D":
                # 딥코인 일봉 버킷 경계(UTC 0시가 아닐 수 있음)를 실제 데이터에서 추정
                off = int(data["1D"]["t"].iloc[-1] % step)
            else:
                off = 0
            b = ((m5["t"] - off) // step) * step + off
            g = m5.assign(b=b).groupby("b")
            fo = g["o"].transform("first").values
            fh = g["h"].cummax().values
            fl = g["l"].cummin().values
            fv = g["v"].cumsum().values
            self.forming[tf] = (b.values, fo, fh, fl, fv, step)

    def _form(self, tf, j, closed):
        b, fo, fh, fl, fv, step = self.forming[tf]
        if self.ct5[j] >= b[j] + step:      # 이 5분봉이 버킷을 닫았다 → 진행 중 봉 없음
            return closed
        bar = {"t": int(b[j]), "o": fo[j], "h": fh[j], "l": fl[j], "c": self.k["5m"][j]["c"], "v": fv[j]}
        return closed + [bar]

    def signal(self, j, ctx):
        n15 = ctx.n_closed("15m", j)
        kl = self._form("15m", j, self.k["15m"][max(0, n15 - self.n15 + 1): n15])
        nh = ctx.n_closed("1H", j)
        h1 = self._form("1H", j, self.k["1H"][max(0, nh - self.n1h + 1): nh])
        nd = ctx.n_closed("1D", j)
        d1 = self._form("1D", j, self.k["1D"][max(0, nd - self.n1d + 1): nd])
        m5 = self.k["5m"][max(0, j - self.n5 + 1): j + 1]
        return self.evaluate(kl, h1, d1, m5)


# ═══════════════════════════ 신규 전략 공통 ═══════════════════════════

class _HTF:
    """1H base 전략 공통: 1H/4H/1D 지표를 미리 계산하고 '완결 봉' 기준으로 꺼내 쓴다."""
    base_tf = "1H"

    def prepare(self, data):
        if getattr(self, "_prepared_for", None) is data:
            return
        self._prepared_for = data
        h, h4, d1 = data["1H"], data["4H"], data["1D"]
        self.o, self.h, self.l, self.c = (h[k].values for k in ("o", "h", "l", "c"))
        self.t = h["t"].values
        self.ema20 = ema(h["c"], 20).values
        self.ema50 = ema(h["c"], 50).values
        self.atr = atr(h, 14).values
        self.rsi = rsi(h["c"], 14).values
        mid = h["c"].rolling(20).mean(); sd = h["c"].rolling(20).std()
        self.bb_mid, self.bb_up, self.bb_lo = mid.values, (mid + 2 * sd).values, (mid - 2 * sd).values
        atrp = pd.Series(self.atr / self.c)
        self.shock = (atrp > atrp.rolling(24 * 90, min_periods=24 * 30).quantile(0.97)).values

        self.adx4, self.pdi4, self.mdi4 = (x.values for x in adx(h4, 14))
        self.atr4 = atr(h4, 14).values
        self.h4h, self.h4l, self.h4c = h4["h"].values, h4["l"].values, h4["c"].values
        self.h4ct = h4["ct"].values

        e20, e50 = ema(d1["c"], 20), ema(d1["c"], 50)
        slope = e50 - e50.shift(5)
        reg = np.where((d1["c"] > e50) & (e20 > e50) & (slope > 0), 1,
                       np.where((d1["c"] < e50) & (e20 < e50) & (slope < 0), -1, 0))
        reg[:55] = 0
        self.d1reg = reg
        self.d1h, self.d1l, self.d1c = d1["h"].values, d1["l"].values, d1["c"].values
        self.d1ct = d1["ct"].values
        self.d1atr = atr(d1, 14).values
        self.d1e50 = e50.values

    def regime(self, i, ctx):
        nd = ctx.n_closed("1D", i)
        n4 = ctx.n_closed("4H", i)
        if nd < 56 or n4 < 30:
            return None, None, None
        return int(self.d1reg[nd - 1]), float(self.adx4[n4 - 1]), n4


class TrendPullback(_HTF):
    def __init__(self, adx_min=20, rsi_pb=45, look=6, sl_atr_min=1.0, sl_atr_max=3.0,
                 trail=3.0, time_stop=120, name="trend_pullback"):
        self.p = dict(adx_min=adx_min, rsi_pb=rsi_pb, look=look, sl_atr_min=sl_atr_min,
                      sl_atr_max=sl_atr_max, trail=trail, time_stop=time_stop)
        self.name = name

    def signal(self, i, ctx):
        p = self.p
        reg, adx4, _ = self.regime(i, ctx)
        if not reg or adx4 < p["adx_min"] or i < 60 or self.shock[i]:
            return None
        k = p["look"]
        c, o, h, l, a = self.c, self.o, self.h, self.l, self.atr[i]
        lo, hi = i - k, i          # 직전 k개 봉 (현재 봉 제외)
        if reg == 1:
            if not (c[i] > self.ema50[i] and c[i] > self.ema20[i] and c[i] > o[i] and c[i] > h[i - 1]):
                return None
            touched = np.any(l[lo:hi] <= self.ema20[lo:hi] * 1.002)
            dipped = np.nanmin(self.rsi[lo:hi]) < p["rsi_pb"]
            if not (touched and dipped):
                return None
            sl = min(l[lo:i + 1]) - 0.3 * a
            dist = min(max(c[i] - sl, p["sl_atr_min"] * a), p["sl_atr_max"] * a)
            sl = c[i] - dist
        else:
            if not (c[i] < self.ema50[i] and c[i] < self.ema20[i] and c[i] < o[i] and c[i] < l[i - 1]):
                return None
            touched = np.any(h[lo:hi] >= self.ema20[lo:hi] * 0.998)
            popped = np.nanmax(self.rsi[lo:hi]) > 100 - p["rsi_pb"]
            if not (touched and popped):
                return None
            sl = max(h[lo:i + 1]) + 0.3 * a
            dist = min(max(sl - c[i], p["sl_atr_min"] * a), p["sl_atr_max"] * a)
            sl = c[i] + dist
        return {"dir": reg, "sl": sl, "tp": None, "trail_atr": p["trail"], "trail_after_r": 1.0,
                "be_after_r": 1.0, "time_stop": p["time_stop"], "tag": "TPB"}


class DonchianBreakout(_HTF):
    def __init__(self, n=20, sl_atr=2.0, trail_atr=3.0, need_regime=True, adx_min=0,
                 time_stop=24 * 10, allow_short=True, name="donchian4h"):
        self.p = dict(n=n, sl_atr=sl_atr, trail_atr=trail_atr, need_regime=need_regime,
                      adx_min=adx_min, time_stop=time_stop, allow_short=allow_short)
        self.name = name

    def signal(self, i, ctx):
        p = self.p
        # 4H 봉이 막 완결된 1H 봉에서만 판단
        if (self.t[i] + TF_MS["1H"]) % TF_MS["4H"] != 0:
            return None
        reg, adx4, n4 = self.regime(i, ctx)
        if reg is None or n4 < p["n"] + 2 or self.shock[i]:
            return None
        if adx4 < p["adx_min"]:
            return None
        j = n4 - 1
        if self.h4ct[j] != ctx.base_ct[i]:      # 방금 마감된 4H 봉이 아니면(데이터 공백 등) 판단 안 함
            return None
        hh = self.h4h[j - p["n"]:j].max(); ll = self.h4l[j - p["n"]:j].min()
        a4 = self.atr4[j]
        c = self.h4c[j]
        if c > hh and (reg == 1 or (not p["need_regime"] and reg >= 0)):
            d = 1
        elif p["allow_short"] and c < ll and (reg == -1 or (not p["need_regime"] and reg <= 0)):
            d = -1
        else:
            return None
        return {"dir": d, "sl": c - d * p["sl_atr"] * a4, "tp": None,
                "trail_dist": p["trail_atr"] * a4, "trail_after_r": 0.5, "be_after_r": None,
                "time_stop": p["time_stop"], "tag": "DON"}


class RangeReversion(_HTF):
    def __init__(self, adx_max=20, rsi_lo=30, sl_atr=0.6, min_rr=1.0, time_stop=24, name="range_mr"):
        self.p = dict(adx_max=adx_max, rsi_lo=rsi_lo, sl_atr=sl_atr, min_rr=min_rr, time_stop=time_stop)
        self.name = name

    def signal(self, i, ctx):
        p = self.p
        reg, adx4, _ = self.regime(i, ctx)
        if reg is None or reg != 0 or adx4 > p["adx_max"] or i < 30 or self.shock[i]:
            return None
        c, l, h, a = self.c, self.l, self.h, self.atr[i]
        if c[i - 1] < self.bb_lo[i - 1] and c[i] > self.bb_lo[i] and self.rsi[i - 1] < p["rsi_lo"]:
            d = 1; sl = min(l[i - 1], l[i]) - p["sl_atr"] * a; tp = self.bb_mid[i]
        elif c[i - 1] > self.bb_up[i - 1] and c[i] < self.bb_up[i] and self.rsi[i - 1] > 100 - p["rsi_lo"]:
            d = -1; sl = max(h[i - 1], h[i]) + p["sl_atr"] * a; tp = self.bb_mid[i]
        else:
            return None
        risk = (c[i] - sl) * d; reward = (tp - c[i]) * d
        if risk <= 0 or reward / risk < p["min_rr"]:
            return None
        return {"dir": d, "sl": sl, "tp": tp, "time_stop": p["time_stop"], "tag": "RMR"}


class DailyTrend(_HTF):
    """일봉 시계열 모멘텀(터틀식) — 일봉 마감 직후 1회 판단.
    롱: 종가 > 직전 n일 최고가 & 종가 > EMA50(D1) / 숏: 반대. 손절 sl_atr×ATR(D1),
    샹들리에 trail_atr×ATR(D1). 손절폭이 커서(5~10%) 명목 레버리지는 1배 안팎 — 수수료 영향 미미."""

    def __init__(self, n=20, sl_atr=2.0, trail_atr=3.0, allow_short=True, name="daily_trend"):
        self.p = dict(n=n, sl_atr=sl_atr, trail_atr=trail_atr, allow_short=allow_short)
        self.name = name
        self._last_nd = None

    def prepare(self, data):
        super().prepare(data)
        self._last_nd = None

    def signal(self, i, ctx):
        p = self.p
        nd = ctx.n_closed("1D", i)
        j = nd - 1
        # 일봉이 '방금' 마감된 1H 봉에서만 판단 — 포지션 청산 몇 시간 뒤에 묵은 일봉 신호로
        # 들어가는 엣지케이스 방지 (2024-03-05 급락 직후 손절폭 0.1% 진입 버그)
        if j < max(p["n"], 55) or self.d1ct[j] != ctx.base_ct[i]:
            return None
        c = self.c[i]; a = self.d1atr[j]
        hh = self.d1h[j - p["n"]:j].max(); ll = self.d1l[j - p["n"]:j].min()
        if c > hh and c > self.d1e50[j]:
            d = 1
        elif p["allow_short"] and c < ll and c < self.d1e50[j]:
            d = -1
        else:
            return None
        return {"dir": d, "sl": c - d * p["sl_atr"] * a, "tp": None, "trail_dist": p["trail_atr"] * a,
                "trail_after_r": 0.0, "be_after_r": None, "time_stop": None, "tag": "D1T"}


class BreakoutTF:
    """타임프레임을 바꿔가며 보는 돌파 전략 (롱 추세돌파의 타임프레임 비교용).
    D1 국면(완결 일봉)이 상승일 때, base 타임프레임 종가가 직전 n봉 최고가를 넘으면 진입.
    손절 sl_atr×ATR(base), 샹들리에 trail_atr×ATR(base), 타임스탑은 '일' 단위로 환산."""

    def __init__(self, tf="1H", n=20, sl_atr=2.0, trail_atr=3.0, time_stop_days=10, allow_short=False,
                 trail_after_r=0.5, name=None):
        self.base_tf = tf
        self.p = dict(tf=tf, n=n, sl_atr=sl_atr, trail_atr=trail_atr, time_stop_days=time_stop_days,
                      allow_short=allow_short, trail_after_r=trail_after_r)
        self.name = name or f"breakout_{tf}_n{n}"

    def prepare(self, data):
        p = self.p
        df = data[p["tf"]]
        self.c = df["c"].values
        self.atr = atr(df, 14).values
        self.hh = df["h"].shift(1).rolling(p["n"]).max().values
        self.ll = df["l"].shift(1).rolling(p["n"]).min().values
        step = TF_MS[p["tf"]]
        per_day = 86_400_000 // step
        ap = pd.Series(self.atr / self.c)
        self.shock = (ap > ap.rolling(per_day * 90, min_periods=per_day * 30).quantile(0.97)).values
        self.time_stop = int(p["time_stop_days"] * per_day)
        d1 = data["1D"]
        e20, e50 = ema(d1["c"], 20), ema(d1["c"], 50)
        slope = e50 - e50.shift(5)
        reg = np.where((d1["c"] > e50) & (e20 > e50) & (slope > 0), 1,
                       np.where((d1["c"] < e50) & (e20 < e50) & (slope < 0), -1, 0))
        reg[:55] = 0
        self.d1reg = reg

    def signal(self, i, ctx):
        p = self.p
        nd = ctx.n_closed("1D", i)
        if nd < 56 or i < p["n"] + 15 or self.shock[i] or np.isnan(self.hh[i]):
            return None
        reg = int(self.d1reg[nd - 1])
        c, a = self.c[i], self.atr[i]
        if c > self.hh[i] and reg == 1:
            d = 1
        elif p["allow_short"] and c < self.ll[i] and reg == -1:
            d = -1
        else:
            return None
        return {"dir": d, "sl": c - d * p["sl_atr"] * a, "tp": None, "trail_dist": p["trail_atr"] * a,
                "trail_after_r": p["trail_after_r"], "be_after_r": None, "time_stop": self.time_stop,
                "tag": "BRK" + p["tf"]}


class SweepReclaimLong(_HTF):
    """ICT식 롱 휩쏘 — 상승추세(D1) 안에서 직전 look개 1H 저점을 꼬리로 쓸고(스윕) 종가가 그 위로 복귀하면 롱.
    손절은 스윕 꼬리 아래, 익절은 고정 없이 트레일링. (15m 좁은 SL이 아니라 1H 꼬리 기준이라 비용 비중이 작다)"""

    def __init__(self, look=48, sl_pad_atr=0.3, trail=3.0, time_stop=120, min_wick_atr=0.0, name="sweep_reclaim_long"):
        self.p = dict(look=look, sl_pad_atr=sl_pad_atr, trail=trail, time_stop=time_stop, min_wick_atr=min_wick_atr)
        self.name = name

    def signal(self, i, ctx):
        p = self.p
        reg, _, _ = self.regime(i, ctx)
        if reg != 1 or i < p["look"] + 2 or self.shock[i]:
            return None
        lvl = self.l[i - p["look"]:i].min()
        a = self.atr[i]
        if not (self.l[i] < lvl and self.c[i] > lvl and self.c[i] > self.o[i]):
            return None
        if (lvl - self.l[i]) < p["min_wick_atr"] * a:
            return None
        sl = self.l[i] - p["sl_pad_atr"] * a
        dist = min(self.c[i] - sl, 3.0 * a)
        if dist < 0.8 * a:
            dist = 0.8 * a
        return {"dir": 1, "sl": self.c[i] - dist, "tp": None, "trail_atr": p["trail"], "trail_after_r": 1.0,
                "be_after_r": 1.0, "time_stop": p["time_stop"], "tag": "SWP"}


class DumpSweepReversal5m:
    """5분봉 급락 후 저점 스윕·회복을 매수하는 연구용 단타 전략.

    급락은 직전 12봉 최고 종가 대비 1.5×ATR(5m)×sqrt(12) 이상 하락,
    스윕은 직전 12봉(1시간) 저가를 하향 돌파한 뒤 그 레벨 위에서 양봉 마감으로 정의한다.
    다음 봉 시가 진입, 스윕 꼬리 아래 손절, 1.5R 익절, 12봉 타임스탑.
    라이브 주문에는 연결하지 않는다.
    """
    base_tf = "5m"

    def __init__(self, drop_atr=1.5, drop_look=12, sweep_look=12,
                 wick_atr=0.25, sl_pad_atr=0.2, tp_r=1.5,
                 time_stop=12, name="dump_sweep_reversal_5m"):
        self.p = dict(drop_atr=drop_atr, drop_look=drop_look, sweep_look=sweep_look,
                      wick_atr=wick_atr, sl_pad_atr=sl_pad_atr, tp_r=tp_r,
                      time_stop=time_stop)
        self.name = name

    def prepare(self, data):
        df = data[self.base_tf]
        self.o, self.h, self.l, self.c = (df[k].values for k in ("o", "h", "l", "c"))
        self.atr = atr(df, 14).values
        p = self.p
        self.prior_high_close = pd.Series(self.c).shift(1).rolling(p["drop_look"]).max().values
        self.prior_low = pd.Series(self.l).shift(1).rolling(p["sweep_look"]).min().values

    def signal(self, i, ctx):
        p = self.p
        if i < max(p["drop_look"], p["sweep_look"]) + 2:
            return None
        a, c, o, low = self.atr[i], self.c[i], self.o[i], self.l[i]
        level = self.prior_low[i]
        if not np.isfinite(a) or a <= 0 or not np.isfinite(level):
            return None
        flush = self.prior_high_close[i] - c >= p["drop_atr"] * a * np.sqrt(p["drop_look"])
        reclaim = low < level and c > level and c > o
        lower_wick = min(o, c) - low >= p["wick_atr"] * a
        if not (flush and reclaim and lower_wick):
            return None
        sl = low - p["sl_pad_atr"] * a
        risk = c - sl
        if risk < 0.6 * a:
            return None
        return {"dir": 1, "sl": sl, "tp": c + p["tp_r"] * risk,
                "time_stop": p["time_stop"], "tag": "DUMP_SWEEP_5M"}


class RegimeTrend(_HTF):
    """최종 제안 전략 — '추세가 있을 때만, 큰 타임프레임으로, 작은 리스크로'.
      국면 판정(완결 D1): 상승추세 / 하락추세 / 횡보
        · 추세장: ① 일봉 20일 돌파(DailyTrend)  ② 4H 20봉 돌파(D1 추세 방향만, DonchianBreakout)
        · 횡보장: 진입 안 함 (15m 역추세·볼밴 역추세는 수수료 후 음수로 검증됨 → '쉬는 게 포지션')
        · 쇼크:   1H ATR%가 최근 90일 97분위 초과 → 신규 진입 금지 (급락·급등 직후 휩쏘 회피)
      청산: ATR 손절 + 샹들리에 트레일링(이익은 끝까지), 4H는 10일 타임스탑.
      파라미터는 robust_v2 그리드의 '평평한 고원' 중앙값(기본값) — 결과 보고 고른 값 아님."""

    def __init__(self, name="regime_trend", use_d1=True, use_4h=True, allow_short=True):
        self.subs = (([DailyTrend(allow_short=allow_short)] if use_d1 else [])
                     + ([DonchianBreakout(allow_short=allow_short)] if use_4h else []))
        self.name = name

    def prepare(self, data):
        super().prepare(data)
        for s in self.subs:
            s.prepare(data)

    def signal(self, i, ctx):
        if self.shock[i]:
            return None
        for s in self.subs:
            r = s.signal(i, ctx)
            if r:
                return r
        return None


class Adaptive(_HTF):
    """국면 라우터 — 한 번에 포지션 1개(라이브와 동일). 우선순위: 추세 눌림목 → 돌파 → 횡보 역추세."""

    def __init__(self, trend=None, breakout=None, rng=None, use_range=True, name="adaptive"):
        self.subs = [s for s in (trend or TrendPullback(), breakout or DonchianBreakout(),
                                 (rng or RangeReversion()) if use_range else None) if s]
        self.name = name

    def prepare(self, data):
        super().prepare(data)
        for s in self.subs:
            s.prepare(data)

    def signal(self, i, ctx):
        for s in self.subs:
            r = s.signal(i, ctx)
            if r:
                return r
        return None
