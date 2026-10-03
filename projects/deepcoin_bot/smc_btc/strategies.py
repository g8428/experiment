"""S1(ITH/ITL 레인지) · S2(HTF POI 진입 모듈) · S3(전일 고/저 스윕) — 롱 로직만 작성, 숏은 미러 데이터로 실행.

window(봉 수, 5m 기준)는 강의에 없는 '셋업 유효 기간' 파라미터:
  S1: ITL 확정 → 진입 체결
  S2: POI 탭 → 스윕, 스윕 → MSS, MSS → 진입 체결 (각 단계별)
  S3: 스윕 → MSS, MSS → 진입 체결
"""
import numpy as np
import pandas as pd

from core import (asof_last, atr, bull_fvgs, daily_bias, daily_trend, htf_asof,
                  intermediate, killzone_mask, resample, swings)

FEE = 0.0006   # taker, 편도
SLIP = 0.0002  # 손절 슬리피지
BUF = 0.1      # SL 버퍼 = 0.1 × ATR


def build(df):
    """5m 기준 컨텍스트. 모든 HTF 값은 완결봉만."""
    idx = df.index
    d = {k: df[k].values for k in "ohlc"}
    n = len(df)
    m15, h1, h4, D = (resample(df, r) for r in ("15min", "1H", "4H", "1D"))
    ctx = dict(n=n, idx=idx, **d)
    ctx["kz"] = killzone_mask(idx)
    ctx["trend"] = htf_asof(D, idx, daily_trend(D))
    ctx["dbias"] = htf_asof(D, idx, daily_bias(D))
    ctx["pdh"] = htf_asof(D, idx, D["h"].values)
    ctx["pdl"] = htf_asof(D, idx, D["l"].values)
    # 9강 시가 규칙용: 진행 중인 일/주(월요일 00 UTC)/월 봉의 시가
    o = df["o"]
    day = idx.normalize()
    week = (idx - pd.to_timedelta(idx.dayofweek, unit="D")).normalize()
    month = idx.to_period("M").astype(str)
    ctx["dopen"] = o.groupby(day).transform("first").values
    ctx["wopen"] = o.groupby(week).transform("first").values
    ctx["mopen"] = o.groupby(month).transform("first").values
    ctx["atr5"] = atr(d["h"], d["l"], d["c"])
    ctx["atr15"] = htf_asof(m15, idx, atr(m15["h"].values, m15["l"].values, m15["c"].values))
    ctx["atr1h"] = htf_asof(h1, idx, atr(h1["h"].values, h1["l"].values, h1["c"].values))

    # 5m 스윙 · FVG
    sh5, sl5 = swings(d["h"], d["l"])
    ctx["sh5_p"], ctx["sh5_b"] = asof_last(sh5, n)
    ctx["sl5_p"], ctx["sl5_b"] = asof_last(sl5, n)
    f5 = bull_fvgs(d["h"], d["l"])
    ctx["fvg5"] = f5
    ctx["fvg5_c3"] = np.array([f[3] for f in f5])
    ctx["fvg5_c1"] = np.array([f[2] for f in f5])

    def avail(htf, bars):
        """HTF 봉 b 확정 후 첫 5m 봉 인덱스."""
        starts = htf.index
        step = starts[1] - starts[0]
        ends = (starts + step).values
        return np.searchsorted(idx.values, ends[np.asarray(bars, dtype=int)], side="left")

    ctx["m15_end_bar"] = np.zeros(n, bool)  # 15m 봉의 마지막 5m 봉 (그 종가 = 15m 종가)
    mins = idx.minute
    ctx["m15_end_bar"] = np.asarray((mins % 15) == 10)

    # 15m FVG (S1 진입 구역)
    f15 = bull_fvgs(m15["h"].values, m15["l"].values)
    av = avail(m15, [f[3] for f in f15]) if f15 else []
    ctx["fvg15"] = [(lo, hi, m15.index[c1], a) for (lo, hi, c1, c3), a in zip(f15, av)]

    # 1H 스윙 · ITH/ITL (S1, S2 TP1)
    sh1, sl1 = swings(h1["h"].values, h1["l"].values)
    ith1, itl1 = intermediate(sh1, "H"), intermediate(sl1, "L")
    ctx["itl1"] = [(p, h1.index[b], a) for (p, b, cf), a in zip(itl1, avail(h1, [e[2] for e in itl1]))]
    ctx["ith1"] = [(p, h1.index[b], a) for (p, b, cf), a in zip(ith1, avail(h1, [e[2] for e in ith1]))]
    ctx["sh1"] = sorted([(p, a) for (p, b, cf), a in zip(sh1, avail(h1, [e[2] for e in sh1]))], key=lambda x: x[1])

    # 4H FVG (S2 POI), 4H 스윙 (S2 다리·TP2), 4H 종가
    f4 = bull_fvgs(h4["h"].values, h4["l"].values)
    sh4, sl4 = swings(h4["h"].values, h4["l"].values)
    sl4_p, _ = asof_last(sl4, len(h4) + 1)
    ctx["fvg4"] = []
    for (lo, hi, c1, c3), a in zip(f4, avail(h4, [f[3] for f in f4])):
        leg_low = sl4_p[c1]  # c1 이전 확정된 4H 스윙 저점 = 다리 시작
        if not np.isnan(leg_low) and leg_low < lo:
            ctx["fvg4"].append((lo, hi, leg_low, a))
    ctx["sh4"] = sorted([(p, a) for (p, b, cf), a in zip(sh4, avail(h4, [e[2] for e in sh4]))], key=lambda x: x[1])
    ctx["h4_close"] = np.full(n, np.nan)  # 4H 봉 마감 시점 5m 봉에 그 4H 종가
    a4 = avail(h4, range(len(h4)))
    for b, a in enumerate(a4):
        if a < n:
            ctx["h4_close"][a] = h4["c"].values[b]
    return ctx


def nearest_above(levels, price, i, lookback=200):
    """확정된(avail<=i) 스윙 고점 중 price 위 가장 가까운 것."""
    best = None
    for p, a in reversed(levels):
        if a > i:
            continue
        lookback -= 1
        if p > price and (best is None or p < best):
            best = p
        if lookback <= 0:
            break
    return best


class Book:
    """한 방향 한 포지션. 지정가 체결·SL 우선·부분익절."""

    def __init__(self, ctx, kz_on, open_mode):
        self.c, self.kz_on, self.open_mode = ctx, kz_on, open_mode
        self.pos, self.trades = None, []

    def allowed(self, i):
        c = self.c
        return c["trend"][i] == 1 and c["dbias"][i] != -1

    def try_fill(self, i, entry, sl, tp1, tp2=None, exit_level=None, tag=""):
        c = self.c
        if self.kz_on and not c["kz"][i]:
            return False
        if c["l"][i] > entry:
            return False
        px = min(c["o"][i], entry)
        if px <= sl or (tp2 or tp1) <= px:
            return False
        # 9강 시가 규칙: 상승 바이어스면 시가 아래에서만 매수
        if px >= c["dopen"][i]:
            return False
        if self.open_mode == "strict" and (px >= c["wopen"][i] or px >= c["mopen"][i]):
            return False
        self.pos = dict(e=px, sl=sl, sl0=sl, tp1=tp1, tp2=tp2, left=1.0, parts=[], i0=i,
                        xl=exit_level, tag=tag, t=c["idx"][i])
        if c["l"][i] <= sl:  # 체결 봉에서 손절까지 닿으면 손절로 간주(보수적)
            self._close(sl, 1.0, True)
        return True

    def step(self, i):
        p, c = self.pos, self.c
        if p is None or i == p["i0"]:
            return
        o, h, l, cl = c["o"][i], c["h"][i], c["l"][i], c["c"][i]
        if l <= p["sl"]:
            self._close(min(o, p["sl"]), p["left"], p["sl"] < p["e"])
            return
        if p["tp2"] is not None and p["left"] == 1.0 and h >= p["tp1"]:
            p["parts"].append((p["tp1"], 0.5, False))  # 10강: 유동성1 부분익절 + SL 본절
            p["left"], p["sl"] = 0.5, p["e"]
        tp = p["tp2"] if p["tp2"] is not None else p["tp1"]
        if h >= tp:
            self._close(max(o, tp), p["left"], False)
            return
        if p["xl"] is not None and c["m15_end_bar"][i] and cl < p["xl"]:  # 8강: ITL 아래 15m 몸통 마감 → 청산
            self._close(cl, p["left"], True)

    def _close(self, px, frac, slip):
        p = self.pos
        p["parts"].append((px, frac, slip))
        ae = abs(p["e"])
        risk = (p["e"] - p["sl0"]) / ae
        ret = sum((x - p["e"]) / ae * f - (2 * FEE + (SLIP if s else 0)) * f for x, f, s in p["parts"])
        self.trades.append(dict(t=p["t"], tag=p["tag"], R=ret / risk, ret=ret, risk=risk))
        self.pos = None


# ── S3: 전일 고/저 스윕 (5·9강) ───────────────────────────────────────
def run_s3(ctx, window, kz_on, open_mode):
    c, bk = ctx, Book(ctx, kz_on, open_mode)
    st, last_day = None, None
    for i in range(1, c["n"]):
        bk.step(i)
        if bk.pos is not None:
            st = None
            continue
        day = c["idx"][i].date()
        if st is None:
            if day != last_day and bk.allowed(i) and c["l"][i] < c["pdl"][i] and not np.isnan(c["sh5_p"][i]):
                st = dict(low=c["l"][i], sb=i, s0=i, mss=c["sh5_p"][i], tp=c["pdh"][i], order=None)
                last_day = day
            continue
        if st["order"] is None:
            if i - st["sb"] > window:
                st = None
                continue
            if c["l"][i] < st["low"]:  # 더 깊은 유동성 → 스윕 갱신
                st.update(low=c["l"][i], sb=i, mss=c["sh5_p"][i])
                continue
            if c["c"][i] > st["mss"]:  # MSS: 왼쪽 첫 스윙 몸통 돌파 (5강: IDM 아닌 CHoCH로 간주)
                sel = (ctx["fvg5_c1"] >= st["sb"]) & (ctx["fvg5_c3"] <= i)
                if not sel.any():
                    st = None
                    continue
                k = np.flatnonzero(sel)[0]  # 다리 시작(OB 쪽) 첫 FVG
                entry = ctx["fvg5"][k][1]
                sl = st["low"] - BUF * c["atr15"][i]
                st["order"] = dict(e=entry, sl=sl, mb=i)
            continue
        od = st["order"]
        if i - od["mb"] > window or c["l"][i] < st["low"]:
            st = None
            continue
        if bk.try_fill(i, od["e"], od["sl"], st["tp"], tag="S3"):
            st = None
    return bk.trades


# ── S2: 상위TF(4H) POI → 스윕 → displacement → MSS → FVG 리테스트 (6·11강) ──
def run_s2(ctx, window, kz_on, open_mode, min_fvg=2, disp_mult=2.0):
    c, bk = ctx, Book(ctx, kz_on, open_mode)
    pois, j, st = [], 0, None
    f4 = ctx["fvg4"]
    for i in range(1, c["n"]):
        while j < len(f4) and f4[j][3] <= i:
            lo, hi, leg_low, a = f4[j]
            pois.append(dict(lo=lo, hi=hi, leg=leg_low, hh=hi))
            j += 1
        h4c = c["h4_close"][i]
        alive = []
        for p in pois:  # 4H 종가가 FVG 하단 아래 마감 → POI 무효
            if not np.isnan(h4c) and h4c < p["lo"]:
                continue
            p["hh"] = max(p["hh"], c["h"][i])
            alive.append(p)
        pois = alive[-30:]
        bk.step(i)
        if bk.pos is not None:
            st = None
            continue
        if st is None:
            if not bk.allowed(i):
                continue
            for p in reversed(pois):
                mid = (p["leg"] + p["hh"]) / 2
                if c["l"][i] <= p["hi"] and p["hi"] <= mid:  # 디스카운트에 있는 POI 탭
                    st = dict(poi=p, tap=i, low=None, sb=None, mss=None, order=None)
                    pois.remove(p)
                    break
            continue
        p = st["poi"]
        if not np.isnan(h4c) and h4c < p["lo"]:  # 상위TF 몸통이 POI 아래 마감 → 무효
            st = None
            continue
        if st["low"] is None:  # 하위TF 유동성 스윕 대기
            if i - st["tap"] > window:
                st = None
            elif c["l"][i] < c["sl5_p"][i]:
                st.update(low=c["l"][i], sb=i, mss=c["sh5_p"][i])
            continue
        if st["order"] is None:
            if i - st["sb"] > window:
                st = None
                continue
            if c["l"][i] < st["low"]:
                st.update(low=c["l"][i], sb=i, mss=c["sh5_p"][i])
                continue
            if c["c"][i] > st["mss"]:
                sel = (ctx["fvg5_c1"] >= st["sb"]) & (ctx["fvg5_c3"] <= i)
                rng = (c["h"][st["sb"]:i + 1] - c["l"][st["sb"]:i + 1]).max()
                if sel.sum() >= min_fvg and rng >= disp_mult * c["atr5"][st["sb"]]:
                    k = np.flatnonzero(sel)[0]
                    entry = ctx["fvg5"][k][1]
                    sl = st["low"] - BUF * c["atr15"][i]
                    tp1 = nearest_above(ctx["sh1"], entry, i)
                    tp2 = nearest_above(ctx["sh4"], tp1, i) if tp1 else None
                    if tp1 is None:
                        st = None
                        continue
                    st["order"] = dict(e=entry, sl=sl, tp1=tp1, tp2=tp2, mb=i)
                else:  # displacement 없는 돌파 = 가짜 → 구조 갱신 후 계속 대기
                    st["mss"] = c["sh5_p"][i] if c["sh5_p"][i] > c["c"][i] else c["h"][i]
            continue
        od = st["order"]
        if i - od["mb"] > window or c["l"][i] < st["low"]:
            st = None
            continue
        if bk.try_fill(i, od["e"], od["sl"], od["tp1"], od["tp2"], tag="S2"):
            st = None
    return bk.trades


# ── S1: 1H ITH/ITL 레인지 (8강, BTC 권장 매핑) ──────────────────────────
def run_s1(ctx, window, kz_on, open_mode):
    c, bk = ctx, Book(ctx, kz_on, open_mode)
    itl, ith, f15 = ctx["itl1"], ctx["ith1"], ctx["fvg15"]
    ji, jh, jf = 0, 0, 0
    last_ith, st, zones_all = None, None, []
    for i in range(1, c["n"]):
        while jh < len(ith) and ith[jh][2] <= i:
            last_ith = ith[jh]
            jh += 1
        while jf < len(f15) and f15[jf][3] <= i:
            zones_all.append(f15[jf])
            jf += 1
        zones_all = zones_all[-200:]
        bk.step(i)
        new_itl = None
        while ji < len(itl) and itl[ji][2] <= i:
            new_itl = itl[ji]
            ji += 1
        if bk.pos is not None:
            st = None
            continue
        if new_itl is not None and bk.allowed(i) and last_ith is not None and last_ith[0] > new_itl[0]:
            st = dict(itl=new_itl[0], t_itl=new_itl[1], ith=last_ith[0], start=i,
                      mid=(last_ith[0] + new_itl[0]) / 2, dead=set())
        if st is None:
            continue
        if i - st["start"] > window or (c["m15_end_bar"][i] and c["c"][i] < st["itl"]):
            st = None
            continue
        best = None
        for z in zones_all:
            lo, hi, t1, a = z
            if t1 < st["t_itl"] or a > i or hi > st["mid"] or lo <= st["itl"] or id(z) in st["dead"]:
                continue
            if c["l"][i] <= hi and (best is None or hi > best[1]):
                best = z
        if best is not None:
            sl = st["itl"] - BUF * c["atr1h"][i]
            if bk.try_fill(i, best[1], sl, st["ith"], exit_level=st["itl"], tag="S1"):
                st = None
            else:
                st["dead"].add(id(best))  # 조건 불충족으로 못 들어간 구역은 소진
    return bk.trades


RUNNERS = {"S1": run_s1, "S2": run_s2, "S3": run_s3}
