"""SMC 강의(Nilesh 1~11강) 기본 요소 — 데이터, 스윙, ITH/ITL, FVG, 바이어스, 킬존.

설계: research/smc_youtube/BTC_SMC_전략설계.md
- 모든 판정은 완결봉만 사용. 각 요소는 '확정 봉 인덱스'를 함께 가져 미래참조를 막는다.
- 숏은 가격을 부호 반전한 미러 데이터로 같은 롱 로직을 돌린다(스윙·FVG·ITH/ITL이 자동으로 대칭).
"""
import json
import os

import numpy as np
import pandas as pd

CACHE = os.path.join(os.path.dirname(__file__), "..", "backtest", "cache")


def load_5m(sym="BTC-USDT-SWAP", days=730):
    with open(os.path.join(CACHE, f"{sym}_5m_{days}d.json")) as f:
        d = json.load(f)
    df = pd.DataFrame(d).sort_values("t").drop_duplicates("t")
    df.index = pd.to_datetime(df["t"], unit="ms", utc=True)
    return df[["o", "h", "l", "c"]].astype(float)


def load_1m(sym="BTC-USDT-SWAP", start=None, end=None):
    """fetch_1m.py가 저장한 월별 CSV(backtest/cache/{sym}_1m/YYYY-MM.csv)를 합쳐 반환."""
    import glob
    files = sorted(glob.glob(os.path.join(CACHE, f"{sym}_1m", "*.csv")))
    if not files:
        raise FileNotFoundError(f"1분봉 캐시 없음 — python fetch_1m.py {sym} 실행")
    df = pd.concat([pd.read_csv(f) for f in files]).sort_values("t").drop_duplicates("t")
    df.index = pd.to_datetime(df["t"], unit="ms", utc=True)
    df = df[["o", "h", "l", "c"]].astype(float)
    return df.loc[start:end] if (start or end) else df


def mirror(df):
    """숏 로직용: 가격 부호 반전 (고가<->저가)."""
    return pd.DataFrame({"o": -df["o"], "h": -df["l"], "l": -df["h"], "c": -df["c"]}, index=df.index)


def resample(df, rule):
    agg = df.resample(rule, label="left", closed="left").agg({"o": "first", "h": "max", "l": "min", "c": "last"})
    return agg.dropna()


# ── 스윙 (8강: 3캔들 스윙, 인사이드바는 모캔들에 병합) ─────────────────────
def swings(h, l):
    """returns (highs, lows): 각 원소 (가격, 스윙봉 idx, 확정봉 idx).
    인사이드바(고가<=직전 기준 고가, 저가>=직전 기준 저가)는 건너뛴 유효 시퀀스에서 판정."""
    eff = []
    for i in range(len(h)):
        if eff and h[i] <= h[eff[-1]] and l[i] >= l[eff[-1]]:
            continue  # 인사이드바: 모캔들 범위 안 → 병합(모캔들 유지)
        eff.append(i)
    highs, lows = [], []
    for k in range(1, len(eff) - 1):
        a, b, c = eff[k - 1], eff[k], eff[k + 1]
        if h[b] > h[a] and h[b] > h[c]:
            highs.append((h[b], b, c))
        if l[b] < l[a] and l[b] < l[c]:
            lows.append((l[b], b, c))
    return highs, lows


def intermediate(sw, kind):
    """8강 ITH/ITL: 가운데 스윙이 좌우 이웃 스윙보다 높은(ITH)/낮은(ITL) 것. 확정 = 오른쪽 스윙 확정봉."""
    out = []
    for k in range(1, len(sw) - 1):
        p, b, _ = sw[k]
        lp, rp = sw[k - 1][0], sw[k + 1][0]
        if (kind == "H" and p > lp and p > rp) or (kind == "L" and p < lp and p < rp):
            out.append((p, b, sw[k + 1][2]))
    return out


def asof_last(events, n):
    """events(가격, 봉, 확정봉) → 각 봉 i 시점(확정봉 < i)에서 가장 최근 확정된 이벤트의 (가격, 봉) 배열."""
    price = np.full(n, np.nan)
    bar = np.full(n, -1, dtype=np.int64)
    ev = sorted(events, key=lambda e: e[2])
    j, cur_p, cur_b = 0, np.nan, -1
    for i in range(n):
        while j < len(ev) and ev[j][2] < i:
            cur_p, cur_b = ev[j][0], ev[j][1]
            j += 1
        price[i], bar[i] = cur_p, cur_b
    return price, bar


# ── FVG (4강): 상승 = 캔들1 고가 < 캔들3 저가 ─────────────────────────────
def bull_fvgs(h, l):
    """(하단, 상단, c1 idx, c3 idx) — c3 마감 시 확정."""
    k = np.arange(2, len(h))
    m = h[k - 2] < l[k]
    return [(h[i - 2], l[i], i - 2, i) for i in k[m]]


def atr(h, l, c, n=20):
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    return pd.Series(tr).rolling(n, min_periods=1).mean().values


# ── 킬존 (10강, 뉴욕시간; DST 자동) ─────────────────────────────────────
def killzone_mask(index):
    ny = index.tz_convert("America/New_York")
    hr = ny.hour + ny.minute / 60.0
    asian = hr >= 20
    london = (hr >= 2) & (hr < 5)
    ny_lc = (hr >= 7) & (hr < 12)  # NY 07-10 + London Close 10-12
    return np.asarray(asian | london | ny_lc)


# ── 바이어스 (8·9강) ───────────────────────────────────────────────────
def daily_trend(d):
    """8강: 상승 바이어스면 ITH가 깨지고 하락이면 ITL이 깨진다 → 일봉 ITH/ITL 몸통 종가 돌파로 추세 상태.
    반환: 일봉별 상태(+1/-1/0) — 해당 일 마감 기준(다음 날부터 사용)."""
    h, l, c = d["h"].values, d["l"].values, d["c"].values
    sh, sl = swings(h, l)
    ith, itl = intermediate(sh, "H"), intermediate(sl, "L")
    n = len(d)
    ith_p, _ = asof_last(ith, n + 1)
    itl_p, _ = asof_last(itl, n + 1)
    state = np.zeros(n)
    s, used_h, used_l = 0, np.nan, np.nan
    for i in range(n):
        th, tl = ith_p[i + 1], itl_p[i + 1]  # i일 마감까지 확정된 것
        if not np.isnan(th) and th != used_h and c[i] > th:
            s, used_h = 1, th
        if not np.isnan(tl) and tl != used_l and c[i] < tl:
            s, used_l = -1, tl
        state[i] = s
    return state


def daily_bias(d):
    """9강 데일리 바이어스: i일 캔들 vs i-1일 → i+1일 방향(+1/-1/0)."""
    h, l, c = d["h"].values, d["l"].values, d["c"].values
    out = np.zeros(len(d))
    for i in range(1, len(d)):
        ph, pl = h[i - 1], l[i - 1]
        if c[i] > ph:
            out[i] = 1          # 전일 고점 위 종가 마감(지속)
        elif c[i] < pl:
            out[i] = -1
        elif l[i] < pl and h[i] <= ph:
            out[i] = 1          # 전일 저점 스윕 후 위 마감
        elif h[i] > ph and l[i] >= pl:
            out[i] = -1
    return out


def htf_asof(htf, base_index, values):
    """완결된 HTF 봉 값만 하위봉에 노출: base 봉 시작 시각 >= HTF 봉 종료 시각인 마지막 HTF 봉."""
    starts = htf.index.values
    ends = np.append(starts[1:], starts[-1] + (starts[-1] - starts[-2]))
    pos = np.searchsorted(ends, base_index.values, side="right") - 1
    out = np.full(len(base_index), np.nan)
    ok = pos >= 0
    out[ok] = np.asarray(values, dtype=float)[pos[ok]]
    return out


def period_open(htf, base_index):
    """현재 진행 중인 HTF 봉의 시가 (시가 규칙용, 9강) — 시가는 봉 시작 시 이미 알려짐."""
    pos = np.searchsorted(htf.index.values, base_index.values, side="right") - 1
    return htf["o"].values[pos]
