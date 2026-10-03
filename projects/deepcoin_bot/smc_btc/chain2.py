"""탑다운 사슬 v2 — 체크리스트(체크리스트_v2.md) 전 항목. 1분봉 기준 컨텍스트 생성.

롱 관점으로만 작성. 숏은 build_chain(mirror(1m), mirror(1H 히스토리)).
상위 시간봉(1H·4H·일·주·월)은 4년치 1H 캐시 + 1분봉 병합으로 만든다 (일봉 경계 00:00 UTC).
모든 상위TF 값은 '완결봉'만 하위봉에 노출한다.
"""
import json
import os

import numpy as np
import pandas as pd

from core import CACHE, asof_last, atr, daily_bias, daily_trend, intermediate, killzone_mask, swings
from zones import all_zones, fvgs

REST_DAYS = 2      # 6강: 일봉 POI 도달 후 "2~3일" 매매 쉬기 → 2일
DOJI = 0.1         # [미정의] 10강 도지 = 몸통 ≤ 범위 10% → 다음 날 바이어스 없음
TF_RULE = {"5m": "5min", "15m": "15min", "1H": "1H", "4H": "4H"}
TF_MIN = {"5m": 5, "15m": 15, "1H": 60, "4H": 240, "1D": 1440, "1W": 10080, "1M": 43200}
LIQ_TF = {"15m": "5m", "1H": "15m", "4H": "1H", "1D": "1H", "1W": "4H"}  # 11강: 구역 앞 하위TF 유동성


# ── 데이터 ─────────────────────────────────────────────────────────
def load_hist_1h(sym="BTC-USDT-SWAP", days=1460):
    with open(os.path.join(CACHE, f"{sym}_1H_{days}d.json")) as f:
        d = json.load(f)
    df = pd.DataFrame(d).sort_values("t").drop_duplicates("t")
    df.index = pd.to_datetime(df["t"], unit="ms", utc=True)
    return df[["o", "h", "l", "c"]].astype(float)


def _rs(df, rule):
    return df.resample(rule, label="left", closed="left").agg(
        {"o": "first", "h": "max", "l": "min", "c": "last"}).dropna()


def frames(df1m, hist1h):
    start = df1m.index[0]
    h1 = pd.concat([hist1h[hist1h.index < start], _rs(df1m, "1H")])
    f = {"5m": _rs(df1m, "5min"), "15m": _rs(df1m, "15min"), "1H": h1, "4H": _rs(h1, "4H"), "1D": _rs(h1, "1D")}
    D = f["1D"]
    wk = D.index - pd.to_timedelta(D.index.dayofweek, unit="D")
    f["1W"] = D.groupby(wk).agg({"o": "first", "h": "max", "l": "min", "c": "last"})
    f["1M"] = _rs(D, "MS")
    return f


def frame_ends(fr, tf):
    idx = fr.index
    if tf == "1M":
        return (idx + pd.offsets.MonthBegin(1)).values
    return (idx + pd.Timedelta(minutes=TF_MIN[tf])).values


# ── 빠른 '처음 도달' 검색 ───────────────────────────────────────────
class FirstHit:
    """arr에서 start 이후 처음 arr<=x (below) / arr>=x (above) 인 인덱스. 없으면 len."""

    def __init__(self, arr, B=1024):
        self.a, self.B = np.asarray(arr, float), B
        nb = (len(self.a) + B - 1) // B
        pad = np.full(nb * B, np.nan)
        pad[:len(self.a)] = self.a
        blk = pad.reshape(nb, B)
        self.bmin, self.bmax = np.nanmin(blk, 1), np.nanmax(blk, 1)

    def below(self, start, x):
        return self._find(start, x, True)

    def above(self, start, x):
        return self._find(start, x, False)

    def _find(self, start, x, below):
        a, B, n = self.a, self.B, len(self.a)
        if start >= n:
            return n
        b0 = start // B
        end0 = min((b0 + 1) * B, n)
        seg = a[start:end0]
        hit = np.flatnonzero(seg <= x) if below else np.flatnonzero(seg >= x)
        if hit.size:
            return start + hit[0]
        bm = self.bmin[b0 + 1:] if below else self.bmax[b0 + 1:]
        cand = np.flatnonzero(bm <= x) if below else np.flatnonzero(bm >= x)
        if not cand.size:
            return n
        b = b0 + 1 + cand[0]
        seg = a[b * B:min((b + 1) * B, n)]
        hit = np.flatnonzero(seg <= x) if below else np.flatnonzero(seg >= x)
        return b * B + hit[0]


class RMQ:
    """구간 최대 (구역 앞 유동성 검사용)."""

    def __init__(self, v):
        v = np.asarray(v, float)
        self.t = [v]
        k = 1
        while 2 * k <= len(v):
            p = self.t[-1]
            self.t.append(np.maximum(p[:-k], p[k:]))
            k *= 2

    def max(self, a, b):  # [a, b)
        if b <= a:
            return -np.inf
        j = int(np.log2(b - a))
        t = self.t[j]
        return max(t[a], t[b - (1 << j)])


# ── 상위 층 계산 (프레임 단위) ─────────────────────────────────────
def monthly_dir(M, mz):
    """9강: 월봉 구역 탭 후 그 위 마감(=거부·displacement) → 상승, 반대는 하락.
    없으면 월봉 3캔들 스윙 종가 돌파 구조 상태. 가장 최근 이벤트가 방향."""
    h, l, c = M["h"].values, M["l"].values, M["c"].values
    sh, sl = swings(h, l)
    shp, _ = asof_last(sh, len(M) + 1)
    slp, _ = asof_last(sl, len(M) + 1)
    state = np.zeros(len(M))
    s = 0
    live = []
    for j in range(len(M)):
        live += [z for z in mz if z["k"] == j - 1]
        ev = 0
        for z in list(live):
            if z["side"] == 1 and l[j] <= z["entry"]:
                if c[j] > z["hi"]:
                    ev = 1
                live.remove(z)
            elif z["side"] == -1 and h[j] >= z["entry"]:
                if c[j] < z["lo"]:
                    ev = -1
                live.remove(z)
        if ev == 0:
            if not np.isnan(shp[j]) and c[j] > shp[j]:
                ev = 1
            elif not np.isnan(slp[j]) and c[j] < slp[j]:
                ev = -1
        if ev:
            s = ev
        state[j] = s
    return state


def narrative_dir(D, dz, W):
    """10강 내러티브·3B: 마지막 이벤트의 반대 방향으로 간다.
    SSL(일봉 스윙 저점·전주 저점) 스윕 또는 매수 PD 배열 탭 후 그 위 마감 → 상승. 반대는 하락.
    같은 날 양쪽이면 종가 위치(범위 중앙 위/아래). 도지 다음 날은 0."""
    o, h, l, c = (D[x].values for x in "ohlc")
    sh, sl = swings(h, l)
    shp, _ = asof_last(sh, len(D) + 1)
    slp, _ = asof_last(sl, len(D) + 1)
    wk = D.index - pd.to_timedelta(D.index.dayofweek, unit="D")
    wpos = np.searchsorted(W.index.values, wk.values) - 1
    pwh = np.where(wpos >= 0, W["h"].values[np.clip(wpos, 0, None)], np.nan)
    pwl = np.where(wpos >= 0, W["l"].values[np.clip(wpos, 0, None)], np.nan)
    out = np.zeros(len(D))
    s, live = 0, []
    byk = {}
    for z in dz:
        byk.setdefault(z["k"], []).append(z)
    for j in range(len(D)):
        live += byk.get(j - 1, [])
        up = (not np.isnan(slp[j]) and l[j] < slp[j]) or (not np.isnan(pwl[j]) and l[j] < pwl[j])
        dn = (not np.isnan(shp[j]) and h[j] > shp[j]) or (not np.isnan(pwh[j]) and h[j] > pwh[j])
        for z in list(live):
            if z["side"] == 1 and l[j] <= z["entry"]:
                up = up or c[j] > z["inv"]
                live.remove(z)
            elif z["side"] == -1 and h[j] >= z["entry"]:
                dn = dn or c[j] < z["inv"]
                live.remove(z)
        live = live[-400:]
        if up and dn:
            s = 1 if c[j] > (h[j] + l[j]) / 2 else -1
        elif up:
            s = 1
        elif dn:
            s = -1
        doji = abs(c[j] - o[j]) <= DOJI * max(h[j] - l[j], 1e-12)
        out[j] = 0 if doji else s
    return out


def dealing_range(D):
    """9강: 양쪽 유동성(일봉 스윙 저점=SSL, 스윙 고점=BSL)을 모두 사냥한 범위. 방향 = 마지막 사냥 쪽(BSL 마지막이면 상승 레인지)."""
    h, l = D["h"].values, D["l"].values
    sh, sl = swings(h, l)
    n = len(D)
    shp, _ = asof_last(sh, n)
    slp, _ = asof_last(sl, n)
    L = H = np.nan
    last = 0
    lo, hi, dr = np.full(n, np.nan), np.full(n, np.nan), np.zeros(n)
    for i in range(n):
        s_hit = not np.isnan(slp[i]) and l[i] < slp[i]
        b_hit = not np.isnan(shp[i]) and h[i] > shp[i]
        if s_hit:
            L = l[i] if last != -1 else min(L, l[i])
            last = -1
        elif last == -1:
            L = min(L, l[i])
        if b_hit:
            H = h[i] if last != 1 else max(H, h[i])
            last = 1
        elif last == 1:
            H = max(H, h[i])
        lo[i], hi[i], dr[i] = L, H, (last if not (np.isnan(L) or np.isnan(H)) else 0)
    return lo, hi, dr


def struct_state(fr):
    """1H 구조 상태(11강 MSS 판정용): 종가가 최근 확정 스윙 고점 위 → +1, 스윙 저점 아래 → -1."""
    h, l, c = fr["h"].values, fr["l"].values, fr["c"].values
    sh, sl = swings(h, l)
    shp, _ = asof_last(sh, len(fr) + 1)
    slp, _ = asof_last(sl, len(fr) + 1)
    st = np.zeros(len(fr))
    s = 0
    for j in range(len(fr)):
        if not np.isnan(shp[j]) and c[j] > shp[j]:
            s = 1
        elif not np.isnan(slp[j]) and c[j] < slp[j]:
            s = -1
        st[j] = s
    return st


def three_candle_state(H4, pois, tgt_levels, side):
    """8강: 상위TF(4H/일봉) POI에서 3캔들 스윙 → 방향 확정. 이후 가장 최근 3캔들 스윙 저점은 목표 도달 전까지
    4H 몸통 종가로 깨지지 않는다(깨지면 해제). 목표(확정 시점 위쪽 첫 대상) 도달 시 완료.
    side=+1 상승 확정 상태, -1 하락 확정 상태(가격 반전으로 같은 로직)."""
    s = side
    h, l, c = H4["h"].values * s, H4["l"].values * s, H4["c"].values * s
    if s == -1:
        h, l = l, h
    sh, sl = swings(h, l)
    sl = sorted(sl, key=lambda x: x[2])
    pz = sorted([(z["entry"] * s, z["inv"] * s, a, t) for (z, a, t) in pois], key=lambda x: x[2])
    tl = sorted([(p * s, a, t) for (p, a, t) in tgt_levels], key=lambda x: x[1])
    st = np.zeros(len(H4))
    state, prot, tgt, jz, js = 0, None, None, 0, 0
    active = []
    for i in range(len(H4)):
        while jz < len(pz) and pz[jz][2] <= i:
            active.append(pz[jz])
            jz += 1
        active = [p for p in active if p[3] > i][-300:]  # p[3] = 소진(탭/무효) 4H 인덱스
        if state == 1:
            if c[i] < prot:
                state = 0
            elif tgt is not None and h[i] >= tgt:
                state = 0
        while js < len(sl) and sl[js][2] <= i:
            p, b, cf = sl[js]
            js += 1
            if state == 1:
                prot = p
            else:
                hit = any(l[b] <= e and c[b] >= inv and a <= b for (e, inv, a, t) in active)
                if hit:
                    state, prot = 1, p
                    up = [x[0] for x in tl if x[1] <= i and x[2] > i and x[0] > h[i]]
                    tgt = min(up) if up else None
        st[i] = state
    return st


# ── 컨텍스트 ──────────────────────────────────────────────────────
def build_chain(df1m, hist1h):
    idx, n = df1m.index, len(df1m)
    a = {k: df1m[k].values for k in "ohlc"}
    F = frames(df1m, hist1h)
    ctx = dict(n=n, idx=idx, **a)
    tsec = idx.values

    ends = {tf: frame_ends(fr, tf) for tf, fr in F.items()}
    av = {tf: np.searchsorted(tsec, ends[tf], side="left") for tf in F}  # 프레임 봉 확정 후 첫 1m 인덱스

    def asof(tf, values):
        pos = np.searchsorted(ends[tf], tsec, side="right") - 1
        out = np.full(n, np.nan)
        ok = pos >= 0
        out[ok] = np.asarray(values, float)[pos[ok]]
        return out

    ctx["F"], ctx["av"], ctx["ends"] = F, av, ends
    # 프레임 종가가 확정되는 1m 봉 표시 (몸통 마감 판정용)
    for tf in ("5m", "15m", "1H", "4H", "1D"):
        cl = np.full(n, np.nan)
        lo = np.full(n, np.nan)
        m = av[tf] < n
        cl[av[tf][m] - 0] = F[tf]["c"].values[m]
        lo[av[tf][m]] = F[tf]["l"].values[m]
        # av는 '다음 봉 시작' 인덱스 → 그 봉에서 직전 프레임 봉 종가를 판단
        ctx[f"close_{tf}"], ctx[f"low_{tf}"] = cl, lo
        hi_ = np.full(n, np.nan)
        hi_[av[tf][m]] = F[tf]["h"].values[m]
        ctx[f"high_{tf}"] = hi_

    # ── 시가 규칙 (9강) ──
    o = df1m["o"]
    ctx["dopen"] = o.groupby(idx.normalize()).transform("first").values
    ctx["wopen"] = o.groupby((idx - pd.to_timedelta(idx.dayofweek, unit="D")).normalize()).transform("first").values
    ctx["mopen"] = o.groupby(idx.strftime("%Y-%m")).transform("first").values
    ctx["kz"] = killzone_mask(idx)
    ny = idx.tz_convert("America/New_York")
    ctx["ny_hour"] = np.asarray(ny.hour + ny.minute / 60.0)
    ctx["ny_date"] = np.asarray(ny.normalize().tz_localize(None).values.astype("datetime64[D]"))

    # ── 구역 (15m~월) ──
    Z, SW = {}, {}
    for tf in ("5m", "15m", "1H", "4H", "1D", "1W", "1M"):
        z, sh, sl = all_zones(F[tf], TF_MIN[tf])
        Z[tf], SW[tf] = z, (sh, sl)
    ctx["SW"] = SW

    # 스윙 → (가격, 확정 1m 인덱스, 스윙 봉 시각)
    def sw_list(tf, which):
        sws = SW[tf][0 if which == "H" else 1]
        fi = F[tf].index
        out = [(p, av[tf][cf], fi[b]) for (p, b, cf) in sws]
        return sorted(out, key=lambda x: x[1])
    for tf in ("5m", "15m", "1H", "4H", "1D"):
        ctx[f"sh_{tf}"], ctx[f"sl_{tf}"] = sw_list(tf, "H"), sw_list(tf, "L")
    ith1 = intermediate(SW["1H"][0], "H")
    ctx["ith_1H"] = sorted([(p, av["1H"][cf], F["1H"].index[b]) for (p, b, cf) in ith1], key=lambda x: x[1])

    # 구역 생애: avail(1m) / touch(처음 진입가 도달) / inval(프레임 종가 무효) — 1m 이전 히스토리는 1H로 판정
    FH_l, FH_h = FirstHit(a["l"]), FirstHit(a["h"])
    H1 = F["1H"]
    H1_l, H1_h = FirstHit(H1["l"].values), FirstHit(H1["h"].values)
    h1_ends = ends["1H"]
    start_t = tsec[0]
    for tf, zs in Z.items():
        fr = F[tf]
        c_hi, c_lo = FirstHit(fr["c"].values), None
        c_lo = c_hi
        for z in zs:
            k = z["k"]
            z["tf"] = tf
            z["avail"] = av[tf][k] if k < len(av[tf]) else n
            z["t0time"] = fr.index[z["t0"]]
            z["tk_end"] = ends[tf][k]
            # 무효: 이후 프레임 종가가 inv 넘어감
            j = c_lo.below(k + 1, z["inv"] - 1e-9) if z["side"] == 1 else c_hi.above(k + 1, z["inv"] + 1e-9)
            z["inval"] = av[tf][j] if j < len(fr) else n
            # 1m 시작 이전에 이미 닿았는지 1H로 확인
            if z["tk_end"] < start_t:
                hj = np.searchsorted(h1_ends, z["tk_end"], side="left")
                tj = H1_l.below(hj, z["entry"]) if z["side"] == 1 else H1_h.above(hj, z["entry"])
                if tj < len(H1) and H1.index.values[tj] < start_t:
                    z["touch"] = -1
                    continue
            s0 = min(z["avail"], n)
            z["touch"] = FH_l.below(s0, z["entry"]) if z["side"] == 1 else FH_h.above(s0, z["entry"])
    ctx["Z"] = Z

    # 구역 앞 유동성 (11강): 구역 형성 후 ~ 탭 사이에 확정된 하위TF 스윙 저점(고점) 중 구역 너머(가격 쪽)에 있는 것
    for tf, zs in Z.items():
        lt = LIQ_TF.get(tf)
        if lt is None:
            for z in zs:
                z["liq"] = True
            continue
        for side, key in ((1, f"sl_{lt}"), (-1, f"sh_{lt}")):
            sw = ctx[key]
            avs = np.array([x[1] for x in sw])
            ps = np.array([x[0] for x in sw]) * side
            rm = RMQ(ps) if len(ps) else None
            for z in zs:
                if z["side"] != side:
                    continue
                t_end = z["touch"] if z["touch"] >= 0 else n
                lo_i = np.searchsorted(avs, z["avail"], "left")
                hi_i = np.searchsorted(avs, t_end, "left")
                edge = z["hi"] if side == 1 else -z["lo"]
                z["liq"] = rm is not None and rm.max(lo_i, hi_i) > edge

    # ── 상위 바이어스 층 ──
    D, W, M, H4 = F["1D"], F["1W"], F["1M"], F["4H"]
    ctx["dbias"] = asof("1D", daily_bias(D))
    ctx["wbias"] = asof("1W", daily_bias(W))
    ctx["mdir"] = asof("1M", monthly_dir(M, Z["1M"]))
    ctx["ddir_structure"] = asof("1D", daily_trend(D))
    ctx["ddir_narrative"] = asof("1D", narrative_dir(D, Z["1D"] + Z["1W"], W))
    lo, hi, drd = dealing_range(D)
    ctx["dr_lo"], ctx["dr_hi"], ctx["dr_dir"] = asof("1D", lo), asof("1D", hi), asof("1D", drd)
    ctx["pdh"], ctx["pdl"] = asof("1D", D["h"].values), asof("1D", D["l"].values)
    ctx["pwh"], ctx["pwl"] = asof("1W", W["h"].values), asof("1W", W["l"].values)
    ctx["pmh"] = asof("1M", M["h"].values)   # 9강 월 목표(전월 고점 유동성)
    ctx["h1_state"] = asof("1H", struct_state(F["1H"]))

    # ATL/ATH 규칙 (10강): 사상 최저(롱 관점) 갱신 후 일봉 3캔들 스윙 저점이 확정되기 전엔 반전 롱 금지
    l_d = D["l"].values
    _, sld = swings(D["h"].values, l_d)
    atl = np.zeros(len(D))
    run_min, a_day = np.inf, -1
    for j in range(len(D)):
        if l_d[j] < run_min:
            run_min, a_day = l_d[j], j
        confirmed = any(b >= a_day for (_, b, cf) in sld if cf <= j)  # 갱신일 이후 형성된 스윙 저점 확정
        atl[j] = 0 if confirmed else 1
    ctx["atl_block"] = asof("1D", atl) == 1

    # 4H 3캔들 상태 (8강): POI = 4H·일봉 구역, 목표 = 위/아래 첫 대상
    H4s = H4.index.values
    far = np.datetime64("2100-01-01")

    def to4(t):
        return np.searchsorted(H4s, t, "left")

    def h4_pos(zs, side):
        """(구역, 사용가능 4H 인덱스, 소진 4H 인덱스). 소진 = 첫 탭 직후 2봉(3캔들 형성 허용) 또는 무효."""
        out = []
        for z in zs:
            if z["side"] != side:
                continue
            a4 = to4(z["tk_end"])
            inv4 = to4(idx.values[z["inval"]]) if z["inval"] < n else len(H4)
            if z["touch"] >= 0 and z["touch"] < n:
                inv4 = min(inv4, to4(idx.values[z["touch"]]) + 3)
            out.append((z, a4, inv4))
        return out
    poi_b = h4_pos(Z["4H"] + Z["1D"], 1)
    poi_s = h4_pos(Z["4H"] + Z["1D"], -1)
    H4h, H4l = FirstHit(H4["h"].values), FirstHit(H4["l"].values)
    tgt_up, tgt_dn = [], []
    for (p, b, cf) in SW["1D"][0]:
        a4 = to4(F["1D"].index.values[cf] + np.timedelta64(1, "D"))
        tgt_up.append((p, a4, H4h.above(a4, p)))
    for (p, b, cf) in SW["1D"][1]:
        a4 = to4(F["1D"].index.values[cf] + np.timedelta64(1, "D"))
        tgt_dn.append((p, a4, H4l.below(a4, p)))
    ctx["h4_bull"] = asof("4H", three_candle_state(H4, poi_b, tgt_up, 1))
    ctx["h4_bear"] = asof("4H", three_candle_state(H4, poi_s, tgt_dn, -1))

    # ── 목표·장애물 (9·10·11강) ──
    # 목표(롱): 위쪽 매도 구역(4H·일·주, 인듀스먼트 AOB 제외) 진입가 + 일봉 스윙 고점(미스윕)
    T = []
    for tf in ("4H", "1D", "1W", "1M"):
        for z in Z[tf]:
            if z["side"] == -1 and z["touch"] >= 0 and not z.get("ind", False):
                T.append((z["entry"], z["avail"], min(z["touch"], z["inval"])))
    for (p, a_, t_) in ctx["sh_1D"]:
        if a_ == 0:  # 1m 시작 전 확정 → 1H로 이미 스윕됐는지 확인
            hj = np.searchsorted(H1.index.values, np.datetime64(t_) + np.timedelta64(1, "D"), "left")
            tj = H1_h.above(hj, p)
            if tj < len(H1) and H1.index.values[tj] < start_t:
                continue
        T.append((p, a_, FH_h.above(min(a_, n), p)))
    T = np.array(T) if T else np.zeros((0, 3))
    ctx["T_lvl"], ctx["T_av"], ctx["T_end"] = T[:, 0], T[:, 1], T[:, 2]

    # 장애물(9강): 일·주 매도 구역 탭 → 롱 연속 진입 보류. 해제 = 장애물 무효(종가 돌파) 또는 4H·일 매수 POI 탭
    ev = []
    for tf in ("1D", "1W"):
        for z in Z[tf]:
            if z["side"] == -1 and z["touch"] >= 0 and not z.get("ind", False) and z["touch"] < min(z["inval"], n):
                ev.append((z["touch"], 1, id(z)))
                ev.append((z["inval"], -1, id(z)))
    for tf in ("4H", "1D"):
        for z in Z[tf]:
            if z["side"] == 1 and 0 <= z["touch"] < min(z["inval"], n):
                ev.append((z["touch"], 0, 0))
    ev.sort()
    blk = np.zeros(n + 1, int)
    act = set()
    last = 0
    cur = 0
    for (t_, typ, zid) in ev:
        t_ = min(t_, n)
        blk[last:t_] = cur
        if typ == 1:
            act.add(zid)
        elif typ == -1:
            act.discard(zid)
        else:
            act.clear()
        cur = 1 if act else 0
        last = t_
    blk[last:] = cur
    ctx["obstacle_block"] = blk[:n] == 1

    # 일봉 POI 탭 후 휴식 (6강): "일봉 오더블록에 도달하면 2~3일 매매 금지" → 일봉 OB·Advanced OB 첫 탭(양방향) 후 REST_DAYS일
    rest = np.zeros(n + 1, int)
    for z in Z["1D"]:
        if z["kind"] not in ("OB", "AOB"):
            continue
        t_ = z["touch"]
        if 0 <= t_ < min(z["inval"], n):
            rest[t_] += 1
            rest[min(n, t_ + REST_DAYS * 1440)] -= 1
    ctx["rest_block"] = np.cumsum(rest)[:n] > 0

    # ── 실행 층 ──
    ctx["atr1"] = atr(a["h"], a["l"], a["c"])
    for tf in ("15m", "1H"):
        fr = F[tf]
        ctx[f"atr{tf}"] = asof(tf, atr(fr["h"].values, fr["l"].values, fr["c"].values))
    sh1, sl1 = swings(a["h"], a["l"])
    ctx["sh1m_p"], _ = asof_last(sh1, n)
    ctx["sl1m_p"], _ = asof_last(sl1, n)
    f1 = [z for z in fvgs(a["o"], a["h"], a["l"], a["c"]) if z["side"] == 1]
    ctx["fvg1_top"] = np.array([z["hi"] for z in f1])
    ctx["fvg1_t0"] = np.array([z["t0"] for z in f1])
    ctx["fvg1_k"] = np.array([z["k"] for z in f1])
    # 15m 상승 FVG (S5 displacement 판정)
    m15 = F["15m"]
    f15 = [z for z in Z["15m"] if z["kind"] == "FVG" and z["side"] == 1]
    ctx["fvg15_av"] = np.array([z["avail"] for z in f15])
    ctx["fvg15_t0"] = np.array([z["t0time"].value for z in f15])
    ctx["m15_range"] = m15["h"].values - m15["l"].values
    ctx["m15_t"] = m15.index.values.astype("int64")
    ctx["m15_atr"] = atr(m15["h"].values, m15["l"].values, m15["c"].values)

    # 바이어스 게이트 (모드별)
    for mode in ("structure", "narrative"):
        dd = ctx[f"ddir_{mode}"]
        ctx[f"dir_{mode}"] = dd
        ctx[f"gate_{mode}"] = ((ctx["mdir"] == 1) & (dd == 1) & (ctx["wbias"] != -1) & (ctx["dbias"] != -1)
                               & ~ctx["atl_block"] & ~ctx["rest_block"])
    return ctx


def htf_target(ctx, i, price):
    """9·10·11강: 위쪽 첫 상위TF 대상 — 매도 PD 배열(4H·일·주·월) 또는 일봉 스윙 고점 유동성, 전주·전월 고점, 딜링레인지 고점."""
    m = (ctx["T_av"] <= i) & (ctx["T_end"] > i) & (ctx["T_lvl"] > price)
    c = [ctx["T_lvl"][m].min()] if m.any() else []
    for x in (ctx["pwh"][i], ctx["pmh"][i], ctx["dr_hi"][i]):
        if not np.isnan(x) and x > price:
            c.append(x)
    return min(c) if c else None


def frame_pos_at(ctx, tf, i):
    """1m 봉 i 시점 마지막 완결 프레임 봉 인덱스."""
    return np.searchsorted(ctx["ends"][tf], ctx["idx"].values[i], side="right") - 1


def nearest_level(levels, price, i, above=True, look=300):
    """확정된(avail<=i) 스윙 중 price 위(아래) 가장 가까운 가격."""
    best = None
    cnt = 0
    for p, a_, _t in reversed(levels):
        if a_ > i:
            continue
        cnt += 1
        if above and p > price and (best is None or p < best):
            best = p
        if not above and p < price and (best is None or p > best):
            best = p
        if cnt >= look:
            break
    return best
