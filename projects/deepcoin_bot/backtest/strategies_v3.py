"""
strategies_v3.py — 단기수익률 후보 탐색용 전략군 (engine_v2 위에서 정직하게 측정, 라이브 미연결)

공통: base = 1H 봉. 판단은 1H 봉 종가, 체결은 다음 봉 시가(engine_v2). 일봉 국면은 완결 일봉 기준.
  F1 DipBuy     — 일봉 상승추세 안에서 1H 과매도 눌림 매수, ATR 손절·ATR 익절·타임스탑 (평균회귀를 추세 방향으로만)
  F2 DayBreak   — 일중 변동성 돌파(래리 윌리엄스식): 당일 시가 + k×전일 변동폭 돌파 시 진입, 당일 마감 청산
  F3 HourHold   — 하루 중 특정 시간대 보유(계절성) — 엣지 존재 여부 점검용
  F4 Donchian   — 1H/4H 돌파 변형 (n, 손절, 추적, 일봉 필터 유무, 롱/숏)
  F5 MomRotate  — 일봉 모멘텀이 양(+)이고 N일 수익률 상위일 때 보유 (일 단위 재평가, 단순 추세 필터)
"""
import numpy as np
import pandas as pd

from engine_v2 import TF_MS, adx, atr, ema, rsi


class _V3:
    base_tf = "1H"

    def prepare(self, data):
        if getattr(self, "_pf", None) is data:
            return
        self._pf = data
        h = data["1H"]; d1 = data["1D"]
        self.o, self.h, self.l, self.c = (h[k].values for k in ("o", "h", "l", "c"))
        self.t, self.ct = h["t"].values, h["ct"].values
        self.atr = atr(h, 14).values
        self.rsi14 = rsi(h["c"], 14).values
        self.rsi5 = rsi(h["c"], 5).values
        self.ema50 = ema(h["c"], 50).values
        self.ema200 = ema(h["c"], 200).values
        mid = h["c"].rolling(20).mean(); sd = h["c"].rolling(20).std()
        self.bb_lo = (mid - 2 * sd).values
        ap = pd.Series(self.atr / self.c)
        self.shock = (ap > ap.rolling(24 * 90, min_periods=24 * 30).quantile(0.97)).values
        # 일봉 (완결 기준 인덱스)
        self.d1 = d1
        self.d1o, self.d1h, self.d1l, self.d1c = (d1[k].values for k in ("o", "h", "l", "c"))
        self.d1ct = d1["ct"].values
        e20, e50 = ema(d1["c"], 20), ema(d1["c"], 50)
        slope = e50 - e50.shift(5)
        reg = np.where((d1["c"] > e50) & (e20 > e50) & (slope > 0), 1,
                       np.where((d1["c"] < e50) & (e20 < e50) & (slope < 0), -1, 0))
        reg[:55] = 0
        self.d1reg = reg
        self.d1ret = d1["c"].pct_change(1).values
        self.nd = np.searchsorted(self.d1ct, self.ct, side="right")   # i 시점에 완결된 일봉 개수
        self.d1atr = atr(d1, 14).values

    def reg(self, i):
        nd = self.nd[i]
        return int(self.d1reg[nd - 1]) if nd >= 56 else 0


class DipBuy(_V3):
    def __init__(self, rsi_thr=25, atr_stop=2.5, tp_atr=2.0, time_stop=48, need_up=True, use_bb=False, name=None):
        self.p = dict(rsi_thr=rsi_thr, atr_stop=atr_stop, tp_atr=tp_atr, time_stop=time_stop, need_up=need_up, use_bb=use_bb)
        self.name = name or "dipbuy"

    def signal(self, i, ctx):
        p = self.p
        if i < 250 or self.shock[i]:
            return None
        if p["need_up"] and self.reg(i) != 1:
            return None
        if not (self.c[i] > self.ema200[i]):      # 장기 추세 위에서만 눌림 매수
            return None
        cond = (self.rsi5[i] < p["rsi_thr"]) if not p["use_bb"] else (self.c[i] < self.bb_lo[i] and self.rsi14[i] < 40)
        if not cond:
            return None
        a, c = self.atr[i], self.c[i]
        return {"dir": 1, "sl": c - p["atr_stop"] * a, "tp": c + p["tp_atr"] * a, "time_stop": p["time_stop"], "tag": "DIP"}


class DayBreak(_V3):
    def __init__(self, k=0.7, sl_mult=1.0, need_up=True, allow_short=False, name=None):
        self.p = dict(k=k, sl_mult=sl_mult, need_up=need_up, allow_short=allow_short)
        self.name = name or "daybreak"

    def signal(self, i, ctx):
        p = self.p
        nd = self.nd[i]
        if nd < 60 or i < 30 or self.shock[i]:
            return None
        # 당일 일봉(진행 중)의 시가와 전일 변동폭
        day_open = self.d1o[nd] if nd < len(self.d1o) else None
        if day_open is None:
            return None
        rng = self.d1h[nd - 1] - self.d1l[nd - 1]
        left_h = (self.d1ct[nd] - self.ct[i]) / 3_600_000 if nd < len(self.d1ct) else 0
        if left_h < 2:
            return None
        c = self.c[i]
        reg = self.reg(i)
        if c > day_open + p["k"] * rng and (not p["need_up"] or reg == 1) and c > self.c[i - 1]:
            d = 1
        elif p["allow_short"] and c < day_open - p["k"] * rng and (not p["need_up"] or reg == -1):
            d = -1
        else:
            return None
        return {"dir": d, "sl": c - d * p["sl_mult"] * rng, "tp": None, "time_stop": int(left_h) - 1, "tag": "DAYBRK"}


class HourHold(_V3):
    def __init__(self, hour=0, hold=8, atr_stop=3.0, need_up=False, name=None):
        self.p = dict(hour=hour, hold=hold, atr_stop=atr_stop, need_up=need_up)
        self.name = name or f"hour{hour}"

    def signal(self, i, ctx):
        p = self.p
        if i < 30:
            return None
        hr = (int(self.ct[i] // 3_600_000)) % 24          # 봉 종료 시각의 UTC 시
        if hr != p["hour"]:
            return None
        if p["need_up"] and self.reg(i) != 1:
            return None
        c, a = self.c[i], self.atr[i]
        return {"dir": 1, "sl": c - p["atr_stop"] * a, "tp": None, "time_stop": p["hold"], "tag": "HOUR"}


class Donchian(_V3):
    def __init__(self, tf="4H", n=20, sl_atr=2.0, trail_atr=3.0, need_up=True, allow_short=False, time_days=10, name=None):
        self.base_tf = "1H"
        self.p = dict(tf=tf, n=n, sl_atr=sl_atr, trail_atr=trail_atr, need_up=need_up, allow_short=allow_short, time_days=time_days)
        self.name = name or f"don_{tf}_{n}"

    def prepare(self, data):
        super().prepare(data)
        p = self.p
        df = data["4H"] if p["tf"] == "4H" else data["1H"]
        self.s_ct = df["ct"].values
        self.s_c = df["c"].values
        self.s_hh = df["h"].shift(1).rolling(p["n"]).max().values
        self.s_ll = df["l"].shift(1).rolling(p["n"]).min().values
        self.s_atr = atr(df, 14).values
        self.s_idx = {int(t): k for k, t in enumerate(self.s_ct)}

    def signal(self, i, ctx):
        p = self.p
        k = self.s_idx.get(int(self.ct[i]))        # 이 1H 봉 종료 시각에 마감하는 s-타임프레임 봉
        if k is None or k < p["n"] + 15 or self.shock[i]:
            return None
        reg = self.reg(i)
        c, a = self.s_c[k], self.s_atr[k]
        if c > self.s_hh[k] and (not p["need_up"] or reg == 1):
            d = 1
        elif p["allow_short"] and c < self.s_ll[k] and (not p["need_up"] or reg == -1):
            d = -1
        else:
            return None
        return {"dir": d, "sl": c - d * p["sl_atr"] * a, "tp": None, "trail_dist": p["trail_atr"] * a,
                "trail_after_r": 0.5, "be_after_r": None, "time_stop": p["time_days"] * 24, "tag": "DON"}


class MomHold(_V3):
    """일봉 마감 시 (N일 수익률>thr, 국면 상승)이면 보유, ATR 손절 + 추적. 모멘텀 지속 가정."""
    def __init__(self, n=20, thr=0.05, sl_atr=2.5, trail_atr=3.0, name=None):
        self.p = dict(n=n, thr=thr, sl_atr=sl_atr, trail_atr=trail_atr)
        self.name = name or f"mom{n}"

    def signal(self, i, ctx):
        p = self.p
        nd = self.nd[i]
        if nd < 60 or self.d1ct[nd - 1] != self.ct[i]:    # 일봉이 막 마감된 1H 봉에서만
            return None
        j = nd - 1
        ret = self.d1c[j] / self.d1c[j - p["n"]] - 1
        if ret < p["thr"] or self.reg(i) != 1:
            return None
        a = self.d1atr[j]
        c = self.c[i]
        return {"dir": 1, "sl": c - p["sl_atr"] * a, "tp": None, "trail_dist": p["trail_atr"] * a,
                "trail_after_r": 0.0, "be_after_r": None, "time_stop": 24 * 30, "tag": "MOM"}
