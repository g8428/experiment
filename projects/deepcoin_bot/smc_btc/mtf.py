"""탑다운 MTF 사슬 (9·11·8·6강) — 1분봉 기준 컨텍스트.

월/주/일 : 시가 규칙 + 주간·데일리 바이어스 (9강)
일봉     : ITH/ITL 추세(8강), 딜링 레인지 프리미엄/디스카운트(9강), 상위TF 목표(유동성)
4H       : 3캔들 스윙 저점 보호(8강) — 몸통 종가로 깨지면 롱 금지
1H       : ITH/ITL·스윙 (S1 매핑: 1H 단기저점 = 15m ITL, 8강)
15m      : 진입 구역 FVG, 1H 스윙 고점 = 1차 목표
1m       : 스윕 → displacement → MSS → FVG 리테스트 (6·11강)
모든 상위TF 값은 완결봉만 노출. 숏은 미러 데이터.
"""
import numpy as np
import pandas as pd

from core import (asof_last, atr, bull_fvgs, daily_bias, daily_trend, htf_asof,
                  intermediate, killzone_mask, resample, swings)


def _avail(htf, base_idx, bars):
    step = htf.index[1] - htf.index[0]
    ends = (htf.index + step).values
    return np.searchsorted(base_idx.values, ends[np.asarray(bars, dtype=int)], side="left")


def dealing_range(D):
    """9강: 양쪽 유동성(스윙 저점 SSL, 스윙 고점 BSL)을 모두 사냥한 범위.
    SSL 스윕 시 저점 극값 L(다음 BSL 스윕 전까지 갱신), BSL 스윕 시 고점 극값 H. 둘 다 있으면 레인지."""
    h, l = D["h"].values, D["l"].values
    sh, sl = swings(h, l)
    n = len(D)
    sh_p, _ = asof_last(sh, n)
    sl_p, _ = asof_last(sl, n)
    L = H = np.nan
    last = None
    lo_arr, hi_arr = np.full(n, np.nan), np.full(n, np.nan)
    for i in range(n):
        if not np.isnan(sl_p[i]) and l[i] < sl_p[i]:
            L = l[i] if last != "S" else min(L, l[i])
            last = "S"
        elif last == "S":
            L = min(L, l[i])
        if not np.isnan(sh_p[i]) and h[i] > sh_p[i]:
            H = h[i] if last != "B" else max(H, h[i])
            last = "B"
        elif last == "B":
            H = max(H, h[i])
        lo_arr[i], hi_arr[i] = L, H
    return lo_arr, hi_arr


def protected_low_4h(h4):
    """8강: 3캔들 스윙 저점은 바이어스 완료 전까지 몸통으로 깨지지 않는다.
    가장 최근 확정 4H 스윙 저점이 이후 4H 종가로 깨졌으면 0(롱 금지), 아니면 1."""
    h, l, c = h4["h"].values, h4["l"].values, h4["c"].values
    _, sl = swings(h, l)
    p, _ = asof_last(sl, len(h4) + 1)
    ok = np.ones(len(h4))
    broken_level = None
    for i in range(len(h4)):
        lv = p[i + 1]
        if np.isnan(lv):
            continue
        if c[i] < lv:
            broken_level = lv
        ok[i] = 0.0 if broken_level == lv else 1.0
    return ok


def build_mtf(df):
    idx, n = df.index, len(df)
    a = {k: df[k].values for k in "ohlc"}
    m15, h1, h4, D = (resample(df, r) for r in ("15min", "1H", "4H", "1D"))
    week = (D.index - pd.to_timedelta(D.index.dayofweek, unit="D"))
    Wk = D.groupby(week).agg({"o": "first", "h": "max", "l": "min", "c": "last"})
    ctx = dict(n=n, idx=idx, **a)

    # ── 상위 바이어스 층 ─────────────────────────────
    ctx["kz"] = killzone_mask(idx)
    ctx["trend"] = htf_asof(D, idx, daily_trend(D))
    ctx["dbias"] = htf_asof(D, idx, daily_bias(D))
    ctx["wbias"] = htf_asof(Wk, idx, daily_bias(Wk))   # 9강: 전주 고/저 동일 규칙
    o = df["o"]
    ctx["dopen"] = o.groupby(idx.normalize()).transform("first").values
    ctx["wopen"] = o.groupby((idx - pd.to_timedelta(idx.dayofweek, unit="D")).normalize()).transform("first").values
    ctx["mopen"] = o.groupby(idx.strftime("%Y-%m")).transform("first").values
    lo, hi = dealing_range(D)
    ctx["dr_lo"], ctx["dr_hi"] = htf_asof(D, idx, lo), htf_asof(D, idx, hi)
    ctx["pdh"], ctx["pdl"] = htf_asof(D, idx, D["h"].values), htf_asof(D, idx, D["l"].values)
    ctx["pwh"] = htf_asof(Wk, idx, Wk["h"].values)
    ctx["h4_ok"] = htf_asof(h4, idx, protected_low_4h(h4))
    # 상위TF 목표 후보: 일봉 스윙 고점(확정분), 딜링레인지 고점, 전주 고점
    shD, _ = swings(D["h"].values, D["l"].values)
    ctx["shD"] = sorted([(p, av) for (p, b, cf), av in zip(shD, _avail(D, idx, [e[2] for e in shD]))], key=lambda x: x[1])

    # ── 실행 층 ────────────────────────────────────
    ctx["m15_end_bar"] = np.asarray(idx.minute % 15 == 14)
    ctx["atr1"] = atr(a["h"], a["l"], a["c"])
    ctx["atr15"] = htf_asof(m15, idx, atr(m15["h"].values, m15["l"].values, m15["c"].values))
    ctx["atr1h"] = htf_asof(h1, idx, atr(h1["h"].values, h1["l"].values, h1["c"].values))
    sh1m, sl1m = swings(a["h"], a["l"])
    ctx["sh1m_p"], _ = asof_last(sh1m, n)
    ctx["sl1m_p"], _ = asof_last(sl1m, n)
    f1 = bull_fvgs(a["h"], a["l"])
    ctx["fvg1"], ctx["fvg1_c1"], ctx["fvg1_c3"] = f1, np.array([f[2] for f in f1]), np.array([f[3] for f in f1])
    # 15m: FVG 구역, 스윙 고점(1차 목표)
    f15 = bull_fvgs(m15["h"].values, m15["l"].values)
    ctx["fvg15"] = [(lo_, hi_, m15.index[c1], av) for (lo_, hi_, c1, c3), av in
                    zip(f15, _avail(m15, idx, [f[3] for f in f15]))]
    sh15, _ = swings(m15["h"].values, m15["l"].values)
    ctx["sh15"] = sorted([(p, av) for (p, b, cf), av in zip(sh15, _avail(m15, idx, [e[2] for e in sh15]))], key=lambda x: x[1])
    # 1H: 스윙 저점(=15m ITL), ITH
    sh1, sl1 = swings(h1["h"].values, h1["l"].values)
    ith1 = intermediate(sh1, "H")
    ctx["sl1h"] = [(p, h1.index[b], av) for (p, b, cf), av in zip(sl1, _avail(h1, idx, [e[2] for e in sl1]))]
    ctx["ith1"] = [(p, h1.index[b], av) for (p, b, cf), av in zip(ith1, _avail(h1, idx, [e[2] for e in ith1]))]
    ctx["sh1h"] = sorted([(p, av) for (p, b, cf), av in zip(sh1, _avail(h1, idx, [e[2] for e in sh1]))], key=lambda x: x[1])
    # HTF POI: 4H·일봉 상승 FVG
    pois = []
    for tf in (h4, D):
        f = bull_fvgs(tf["h"].values, tf["l"].values)
        pois += [(lo_, hi_, av) for (lo_, hi_, c1, c3), av in zip(f, _avail(tf, idx, [x[3] for x in f]))]
    ctx["poi"] = sorted(pois, key=lambda x: x[2])
    ctx["h4_close"] = np.full(n, np.nan)
    for b, av in enumerate(_avail(h4, idx, range(len(h4)))):
        if av < n:
            ctx["h4_close"][av] = h4["c"].values[b]
    return ctx
