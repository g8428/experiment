"""일목 A vs 일봉+4H 추세돌파 — 같은 4년 데이터·같은 비용으로 비교 (2026-10-03)

- 추세돌파: strategies_v2.RegimeTrend(롱 전용), engine_v2, 1회 손절 = 계좌 2% (실거래 risk_pct)
- 일목 A: ichimoku_cloud_state와 같은 규칙(완결 일봉 종가 vs 현재 표시 구름). 진입 때 계좌의
  f배 명목으로 보유(실거래: BTC·XRP 3x×10% = 0.3배, ETH 10x×25% = 2.5배), 손절 없음.
  신호 다음 일봉 시가 체결. 비용은 편도 수수료 0.06% + 슬리피지 0.02% (펀딩비 제외).
- 두 전략을 한 계좌에서 같이 돌렸을 때(실거래 구성)의 합산 곡선도 계산.
python backtest/compare_ichi_trend.py → research/일목A_vs_추세돌파_2026-10-03.md 표 원자료 출력
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import engine_v2 as E  # noqa: E402
import strategies_v2 as S  # noqa: E402
from run_v2 import load  # noqa: E402

FEE, SLIP = 0.0006, 0.0002
LIVE_F = {"BTC-USDT-SWAP": 0.3, "ETH-USDT-SWAP": 2.5, "XRP-USDT-SWAP": 0.3}


def ichi_state(d1):
    h, l, c = d1["h"], d1["l"], d1["c"]
    mid = lambda n: (h.rolling(n).max() + l.rolling(n).min()) / 2  # noqa: E731
    a = ((mid(9) + mid(26)) / 2).shift(26)
    b = mid(52).shift(26)
    top, bot = np.maximum(a, b), np.minimum(a, b)
    st = np.where(c > top, 1, np.where(c < bot, -1, 0))
    st[(a.isna() | b.isna()).values] = 0
    return st


def run_ichi(d1, f, allow_short=True):
    """일봉 단위 계좌 곡선(종가 평가)과 거래 목록. 진입 시 명목 = f × 계좌."""
    st = ichi_state(d1)
    o, h, l, c = (d1[k].values for k in "ohlc")
    n = len(d1)
    eq = np.full(n, np.nan)
    eq_low = np.full(n, np.nan)
    cash, pos, entry, notional, trades = 1.0, 0, 0.0, 0.0, []
    for i in range(1, n):
        tgt = int(st[i - 1])
        if tgt == -1 and not allow_short:
            tgt = 0
        if tgt != pos:
            if pos:
                px = o[i] * (1 - SLIP * pos)
                pnl = notional * (px / entry - 1) * pos - notional * FEE * (1 + px / entry)
                cash += pnl
                trades.append(pnl)
            pos = tgt
            if pos:
                entry = o[i] * (1 + SLIP * pos)
                notional = f * cash
        if pos:
            worst = l[i] if pos == 1 else h[i]
            eq_low[i] = cash + notional * (worst / entry - 1) * pos
            eq[i] = cash + notional * (c[i] / entry - 1) * pos
        else:
            eq[i] = eq_low[i] = cash
    return eq, eq_low, trades, st


def stats(eq, eq_low=None):
    eq = pd.Series(eq).dropna()
    if len(eq) < 2:
        return dict(ret=0, cagr=0, mdd=0, sharpe=0)
    r = eq.pct_change().dropna()
    yrs = len(eq) / 365
    low = pd.Series(eq_low).dropna().values if eq_low is not None else eq.values
    peak = np.maximum.accumulate(eq.values)
    mdd = max(0, np.max(1 - np.minimum(low[-len(peak):], eq.values) / peak))
    return dict(ret=(eq.iloc[-1] / eq.iloc[0] - 1) * 100, cagr=((eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1) * 100,
                mdd=mdd * 100, sharpe=r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else 0)


def main():
    rows, out = [], []
    for sym in ("BTC-USDT-SWAP", "ETH-USDT-SWAP", "XRP-USDT-SWAP"):
        data = load(sym, horizon="4y")
        d1 = data["1D"].reset_index(drop=True)
        t0 = int(data["1H"]["t"].iloc[0]) + 60 * 86_400_000          # 지표 워밍업 이후 공통 시작
        d1 = d1[d1["t"] >= t0 - 120 * 86_400_000].reset_index(drop=True)  # 구름 계산용 여유분 포함
        res = E.run(S.RegimeTrend(name="trend_long", allow_short=False), data, risk_pct=2.0)
        tr_eq_h = pd.Series(res["equity"], index=res["t"]).ffill()
        # 일봉 종가 시각 기준으로 정렬
        keep = d1["ct"].values >= t0
        ct = d1["ct"].values
        tr_eq = tr_eq_h.reindex(tr_eq_h.index.union(ct - 3_600_000)).ffill().reindex(ct - 3_600_000).values
        # 추세 평균 명목 노출(보유 시)
        tr_tr = res["trades"]
        curves = {"추세돌파(2%)": (tr_eq, None, len(tr_tr))}
        for lab, f, sh in (("일목A 실거래", LIVE_F[sym], True), ("일목A 1배 롱숏", 1.0, True), ("일목A 1배 롱만", 1.0, False)):
            e, el, tds, _ = run_ichi(d1, f, sh)
            curves[lab] = (e, el, len(tds))
        bh = d1["c"].values
        curves["보유(1배)"] = (bh / bh[keep][0], None, 1)
        # 합산(한 계좌): 일간 수익률 합
        rt = pd.Series(tr_eq[keep]).pct_change().fillna(0).values
        ei = curves["일목A 실거래"][0][keep]
        ri = pd.Series(ei).pct_change().fillna(0).values
        comb = np.cumprod(1 + rt + ri)
        curves["합산(실거래 구성)"] = (np.concatenate([np.full((~keep).sum(), np.nan), comb]), None, 0)
        corr = np.corrcoef(rt[1:], ri[1:])[0, 1]
        # 구간
        tk = ct[keep]
        mid = tk[0] + (tk[-1] - tk[0]) // 2
        segs = [("4년 전체", tk[0], tk[-1] + 1), ("전반 2년", tk[0], mid), ("후반 2년", mid, tk[-1] + 1)]
        s = tk[0]
        k = 1
        while s < tk[-1]:
            segs.append((f"H{k}", s, min(s + 182 * 86_400_000, tk[-1] + 1)))
            s += 182 * 86_400_000
            k += 1
        for lab, (e, el, ntr) in curves.items():
            for sname, a, b in segs:
                m = (ct >= a) & (ct < b)
                st_ = stats(e[m], el[m] if el is not None else None)
                rows.append(dict(sym=sym[:3], strat=lab, seg=sname, trades=ntr, **{k_: round(v, 2) for k_, v in st_.items()}))
        exp = np.mean([abs(x) for x in ichi_state(d1)[keep]])
        out.append(f"{sym[:3]}: 추세-일목 일간수익 상관 {corr:+.2f}, 일목 시장노출 {exp:.0%}, "
                   f"추세 거래 {len(tr_tr)}건 / 기간 {pd.to_datetime(tk[0], unit='ms'):%Y-%m-%d}~{pd.to_datetime(tk[-1], unit='ms'):%Y-%m-%d}")
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(os.path.dirname(HERE), "research", "ichiA_vs_trend_2026-10-03.csv"), index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 200)
    for sym in ("BTC", "ETH", "XRP"):
        x = df[(df.sym == sym) & df.seg.isin(["4년 전체", "전반 2년", "후반 2년"])]
        print(f"\n== {sym}")
        print(x.pivot_table(index="strat", columns="seg", values=["ret", "mdd", "sharpe"], sort=False).round(1).to_string())
        h = df[(df.sym == sym) & df.seg.str.startswith("H")]
        print(h.pivot_table(index="strat", columns="seg", values="ret", sort=False).round(1).to_string())
    print("\n" + "\n".join(out))


if __name__ == "__main__":
    main()
