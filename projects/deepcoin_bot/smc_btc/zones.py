"""PD 배열·블록 탐지 (4·6·7·8강). 한 TF의 OHLC 배열 → 구역 목록.

구역 = dict(kind, side, lo, hi, entry, inv, k, t0)
  side  : +1 매수 구역(상승), -1 매도 구역(하락)
  entry : 진입 기준가 (매수 구역은 위에서 내려와 처음 닿는 값)
  inv   : 무효 기준 — 매수 구역은 TF 종가 < inv 이면 무효, 매도 구역은 종가 > inv
  k     : 확정되는 TF 봉 인덱스 (그 봉 마감 후 사용 가능)
  t0    : 구역을 이루는 첫 봉 인덱스 (형성 시점 비교용)
[미정의] 표시는 강의에 수치가 없어 정한 값.
"""
from bisect import bisect_left

import numpy as np

from core import swings

WICK_RATIO = 0.5   # [미정의] 리젝션 '긴 꼬리' = 꼬리 ≥ 캔들 범위 50%
IND_K, IND_OVL = 5, 0.5  # [미정의] 인듀스먼트 = 이후 5봉 몸통 겹침 평균 ≥ 50% & FVG 없음
BPR_LOOK = 20      # [미정의] BPR: 반대 FVG를 찾는 과거 봉 수


def _body(o, c):
    return np.minimum(o, c), np.maximum(o, c)


def fvgs(o, h, l, c):
    """4강 FVG. 상승: 캔들1 고가 < 캔들3 저가 / 하락: 캔들1 저가 > 캔들3 고가."""
    out = []
    for k in range(2, len(h)):
        if h[k - 2] < l[k]:
            out.append(dict(kind="FVG", side=1, lo=h[k - 2], hi=l[k], entry=l[k], inv=h[k - 2], k=k, t0=k - 2))
        if l[k - 2] > h[k]:
            out.append(dict(kind="FVG", side=-1, lo=h[k], hi=l[k - 2], entry=h[k], inv=l[k - 2], k=k, t0=k - 2))
    return out


def vis(o, h, l, c):
    """6강 Volume Imbalance: 인접 캔들 몸통 사이 공백(꼬리만 겹침). 진입 = 50%(MT, 8·9강)."""
    bl, bh = _body(o, c)
    out = []
    for k in range(1, len(h)):
        if bl[k] > bh[k - 1] and l[k] <= h[k - 1] and c[k] > o[k]:
            lo, hi = bh[k - 1], bl[k]
            out.append(dict(kind="VI", side=1, lo=lo, hi=hi, entry=(lo + hi) / 2, inv=lo, k=k, t0=k - 1))
        if bh[k] < bl[k - 1] and h[k] >= l[k - 1] and c[k] < o[k]:
            lo, hi = bh[k], bl[k - 1]
            out.append(dict(kind="VI", side=-1, lo=lo, hi=hi, entry=(lo + hi) / 2, inv=hi, k=k, t0=k - 1))
    return out


def bprs(fv):
    """8강 BPR: 반대 방향 FVG 두 개가 겹친 구간. 나중 FVG 방향의 구역."""
    out = []
    by_k = sorted(fv, key=lambda z: z["k"])
    for i, z in enumerate(by_k):
        for y in reversed(by_k[max(0, i - 4 * BPR_LOOK):i]):
            if z["k"] - y["k"] > BPR_LOOK:
                break
            if y["side"] == -z["side"]:
                lo, hi = max(z["lo"], y["lo"]), min(z["hi"], y["hi"])
                if lo < hi:
                    s = z["side"]
                    out.append(dict(kind="BPR", side=s, lo=lo, hi=hi, entry=hi if s == 1 else lo,
                                    inv=lo if s == 1 else hi, k=z["k"], t0=y["t0"]))
                    break
    return out


def obs(o, h, l, c, fv):
    """4강 OB(+FVG): FVG 바로 아래(위) 직전 3봉 중 최저점(최고점) 캔들. 직전 캔들 저점을 꼬리로 그랩했으면 꼬리 부분, 아니면 몸통."""
    bl, bh = _body(o, c)
    out = []
    for z in fv:
        if z["kind"] != "FVG":
            continue
        k1 = z["t0"]
        if k1 < 1:
            continue
        rng = range(max(1, k1 - 2), k1 + 1)
        if z["side"] == 1:
            j = min(rng, key=lambda x: l[x])
            lo, hi = (l[j], bl[j]) if l[j] < l[j - 1] else (bl[j], bh[j])
            if hi <= lo:
                lo, hi = l[j], h[j]
            out.append(dict(kind="OB", side=1, lo=lo, hi=hi, entry=hi, inv=lo, k=z["k"], t0=j))
        else:
            j = max(rng, key=lambda x: h[x])
            lo, hi = (bh[j], h[j]) if h[j] > h[j - 1] else (bl[j], bh[j])
            if hi <= lo:
                lo, hi = l[j], h[j]
            out.append(dict(kind="OB", side=-1, lo=lo, hi=hi, entry=lo, inv=hi, k=z["k"], t0=j))
    return out


def _inducement_after(o, h, l, c, k, side):
    """11강: 이후 IND_K봉이 서로 절반 이상 겹치며 힘없이 진행(FVG 없음) → 인듀스먼트."""
    if k + IND_K + 2 >= len(h):
        return False
    bl, bh = _body(o, c)
    ov = []
    for j in range(k + 1, k + 1 + IND_K):
        a = max(bl[j], bl[j - 1])
        b = min(bh[j], bh[j - 1])
        rng = max(bh[j] - bl[j], 1e-12)
        ov.append(max(0.0, b - a) / rng)
        if (side == 1 and h[j - 1] < l[j + 1]) or (side == -1 and l[j - 1] > h[j + 1]):
            return False
    return np.mean(ov) >= IND_OVL


def adv_obs(o, h, l, c, fv):
    """7강 Advanced OB: 연속 반대색 캔들 묶음(인사이드바는 묶음) → 이어 강하게 돌파.
    진입 = 묶음 50%(MT). 묶음 꼬리가 인접 미충전 FVG와 겹치면 MT까지 안 옴 → FVG 끝(첫 닿는 값)에서 진입."""
    n = len(h)
    bull_fvg_by_t0 = {z["t0"]: z for z in fv if z["side"] == 1}
    bear_fvg_by_t0 = {z["t0"]: z for z in fv if z["side"] == -1}
    out = []
    j = 0
    while j < n - 1:
        col = np.sign(c[j] - o[j])
        if col == 0:
            j += 1
            continue
        s, e = j, j
        while e + 1 < n and (np.sign(c[e + 1] - o[e + 1]) == col or (h[e + 1] <= h[e] and l[e + 1] >= l[e])):
            e += 1
        lo, hi = l[s:e + 1].min(), h[s:e + 1].max()
        nx = e + 1
        if nx < n:
            if col < 0 and c[nx] > hi:  # 음봉 묶음 후 상향 돌파 → 매수 Advanced OB
                f = bull_fvg_by_t0.get(e) or bull_fvg_by_t0.get(e - 1)
                if f and f["lo"] <= hi:
                    out.append(dict(kind="AOB", side=1, lo=lo, hi=f["hi"], entry=f["hi"], inv=lo, k=nx, t0=s))
                else:
                    mt = (lo + hi) / 2
                    out.append(dict(kind="AOB", side=1, lo=lo, hi=hi, entry=mt, inv=mt, k=nx, t0=s))
            if col > 0 and c[nx] < lo:  # 양봉 묶음 후 하향 돌파 → 매도 Advanced OB
                f = bear_fvg_by_t0.get(e) or bear_fvg_by_t0.get(e - 1)
                ind = _inducement_after(o, h, l, c, nx, -1)
                if f and f["hi"] >= lo:
                    out.append(dict(kind="AOB", side=-1, lo=f["lo"], hi=hi, entry=f["lo"], inv=hi, k=nx, t0=s, ind=ind))
                else:
                    mt = (lo + hi) / 2
                    out.append(dict(kind="AOB", side=-1, lo=lo, hi=hi, entry=mt, inv=mt, k=nx, t0=s, ind=ind))
        j = e + 1
    return out


def mitigations(o, h, l, c, fv, sh, sl):
    """7강 Mitigation: 스윙 실패(상승에서 HH는 깨고 HL은 못 깸) → 깨진 직전 HH의 최고점 캔들로 되돌아오면 매수.
    단독 금지 — 같은 TF 미충전 FVG와 겹칠 때만 생성."""
    out = []
    for side, sws, opp in ((1, sh, sl), (-1, sl, sh)):
        sws = sorted(sws, key=lambda x: x[1])
        opp = sorted(opp, key=lambda x: x[1])
        opp_b = [x[1] for x in opp]
        for (p, b, cf) in sws:
            # 확정 이후 종가 돌파 봉
            k = None
            for j in range(cf + 1, min(len(c), cf + 500)):
                if (side == 1 and c[j] > p) or (side == -1 and c[j] < p):
                    k = j
                    break
            if k is None:
                continue
            pi = bisect_left(opp_b, b) - 1
            if pi < 0:
                continue
            pl = opp[pi][0]
            mid_ext = l[b:k + 1].min() if side == 1 else h[b:k + 1].max()
            if (side == 1 and mid_ext <= pl) or (side == -1 and mid_ext >= pl):
                continue  # 반대쪽 스윙이 깨졌으면 스윙 실패 아님
            lo, hi = l[b], h[b]
            ov = [z for z in fv if z["side"] == side and b <= z["k"] <= k and z["lo"] < hi and z["hi"] > lo]
            if not ov:
                continue
            out.append(dict(kind="MIT", side=side, lo=lo, hi=hi, entry=hi if side == 1 else lo,
                            inv=lo if side == 1 else hi, k=k, t0=b))
    return out


def breakers(o, h, l, c, sh, sl):
    """7강 Breaker: (상승) 스윙 저점(SSL) 스윕 → 스윙 고점(BSL) 종가 돌파 → 스윕당한 저점 스윙의 블록(최저점 캔들)으로 복귀 시 매수."""
    out = []
    for side, lows, highs in ((1, sl, sh), (-1, sh, sl)):
        lows = sorted(lows, key=lambda x: x[2])
        highs = sorted(highs, key=lambda x: x[2])
        highs_cf = [x[2] for x in highs]
        for (p, b, cf) in lows:
            s = None
            for j in range(cf + 1, min(len(c), cf + 300)):
                if (side == 1 and l[j] < p) or (side == -1 and h[j] > p):
                    s = j
                    break
            if s is None:
                continue
            ti = bisect_left(highs_cf, s) - 1
            if ti < 0 or highs[ti][1] <= b:
                continue
            q = highs[ti][0]
            k = None
            for j in range(s, min(len(c), s + 300)):
                if (side == 1 and c[j] > q) or (side == -1 and c[j] < q):
                    k = j
                    break
            if k is None:
                continue
            lo, hi = l[b], h[b]
            out.append(dict(kind="BRK", side=side, lo=lo, hi=hi, entry=hi if side == 1 else lo,
                            inv=lo if side == 1 else hi, k=k, t0=b))
    return out


def rejections(o, h, l, c, sh, sl, min_wicks):
    """7강 Rejection: 스윙 극점의 긴 꼬리. 하위TF는 꼬리 2개 이상, 30m 이상은 1개. 진입 = 꼬리 구간 50%, MT 너머 몸통 마감 = 무효."""
    bl, bh = _body(o, c)
    rng = np.maximum(h - l, 1e-12)
    out = []
    for (p, b, cf) in sl:
        js = [j for j in (b - 1, b, b + 1) if 0 <= j < len(h)]
        wk = [j for j in js if (bl[j] - l[j]) / rng[j] >= WICK_RATIO]
        if len(wk) >= min_wicks:
            lo, hi = l[b], min(bl[j] for j in wk)
            if hi > lo:
                mt = (lo + hi) / 2
                out.append(dict(kind="REJ", side=1, lo=lo, hi=hi, entry=mt, inv=mt, k=cf, t0=b))
    for (p, b, cf) in sh:
        js = [j for j in (b - 1, b, b + 1) if 0 <= j < len(h)]
        wk = [j for j in js if (h[j] - bh[j]) / rng[j] >= WICK_RATIO]
        if len(wk) >= min_wicks:
            lo, hi = max(bh[j] for j in wk), h[b]
            if hi > lo:
                mt = (lo + hi) / 2
                out.append(dict(kind="REJ", side=-1, lo=lo, hi=hi, entry=mt, inv=mt, k=cf, t0=b))
    return out


def all_zones(df, tf_minutes):
    """TF 데이터프레임 → 전체 구역 목록 (+스윙)."""
    o, h, l, c = (df[x].values for x in "ohlc")
    sh, sl = swings(h, l)
    fv = fvgs(o, h, l, c)
    z = fv + vis(o, h, l, c) + bprs(fv) + obs(o, h, l, c, fv) + adv_obs(o, h, l, c, fv)
    z += mitigations(o, h, l, c, fv, sh, sl) + breakers(o, h, l, c, sh, sl)
    z += rejections(o, h, l, c, sh, sl, min_wicks=2 if tf_minutes < 30 else 1)
    return z, sh, sl
