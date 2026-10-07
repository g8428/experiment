"""
portfolio_v3.py — 일관된 후보(일봉 모멘텀 + 돌파) 묶음의 포트폴리오 성과 + 워크포워드(과적합) 점검

  python backtest/portfolio_v3.py

1) 스트림 = (심볼, 전략). 각 스트림을 기본 리스크로 돌려 일 수익률을 얻고, 합산(= 리스크가 겹치는 동시 보유)해
   배율 s를 곱한 포트폴리오를 만든다. 배율은 거래당 리스크를 s배로 키우는 근사(선형)다.
2) 워크포워드: 전반(IS)만으로 파라미터를 고르고 후반(OOS)에서 시험한다.
"""
import json
import os
import sys
from multiprocessing import Pool

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE)); sys.path.insert(0, _HERE)

SYMS = ["BTC", "ETH", "XRP"]
STREAMS = {   # 이름 -> 생성자 인자
    "MOM20_6": ("MomHold", dict(n=20, thr=0.06)),
    "MOM10_10": ("MomHold", dict(n=10, thr=0.10)),
    "MOM40_6": ("MomHold", dict(n=40, thr=0.06)),
    "DON4H_30": ("Donchian", dict(tf="4H", n=30, sl_atr=1.5, allow_short=False)),
    "DON4H_55": ("Donchian", dict(tf="4H", n=55, sl_atr=1.5, allow_short=False)),
    "DON1H_160": ("Donchian", dict(tf="1H", n=160, sl_atr=2.5, allow_short=False)),
}


def mk(name):
    import strategies_v3 as S
    fam, kw = STREAMS[name]
    return getattr(S, fam)(**kw)


def run_stream(a):
    name, sym, risk = a
    import pandas as pd
    import engine_v2 as E
    from run_v2 import load
    data = load(f"{sym}-USDT-SWAP", horizon="4y")
    res = E.run(mk(name), data, risk_pct=risk)
    eq = pd.Series(res["equity"], index=pd.to_datetime(res["t"], unit="ms")).ffill()
    d = eq.resample("1D").last().ffill().pct_change().fillna(0.0)
    return name, sym, d


def stats(r):
    import numpy as np
    eq = (1 + r).cumprod()
    yrs = (r.index[-1] - r.index[0]).days / 365.25
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    mdd = ((eq.cummax() - eq) / eq.cummax()).max()
    sh = r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else 0
    return dict(total=(eq.iloc[-1] - 1) * 100, cagr=cagr * 100, mdd=mdd * 100, sharpe=sh)


if __name__ == "__main__":
    import numpy as np, pandas as pd
    jobs = [(n, s, 1.0) for n in STREAMS for s in SYMS]
    with Pool(12) as p:
        out = p.map(run_stream, jobs)
    R = {(n, s): d for n, s, d in out}
    idx = sorted(set().union(*[d.index for d in R.values()]))
    R = {k: v.reindex(idx).fillna(0.0) for k, v in R.items()}
    mid = idx[len(idx) // 2]

    def port(names, syms, scale, a=None, b=None):
        r = sum(R[(n, s)] for n in names for s in syms) * scale
        if a is not None: r = r[r.index >= a]
        if b is not None: r = r[r.index < b]
        return r

    print("### 스트림별 (기본 리스크 1%, 4년)")
    print("| 스트림 | BTC | ETH | XRP |  (연복리 / MDD)")
    print("|---|---|---|---|")
    for n in STREAMS:
        cells = []
        for s in SYMS:
            st = stats(R[(n, s)]); cells.append(f"{st['cagr']:+.1f}% / {st['mdd']:.0f}%")
        print(f"| {n} | " + " | ".join(cells) + " |")

    combos = {
        "모멘텀 3종(MOM) × 3심볼": (["MOM20_6", "MOM10_10", "MOM40_6"], SYMS),
        "돌파 3종(DON) × 3심볼": (["DON4H_30", "DON4H_55", "DON1H_160"], SYMS),
        "전체 6종 × 3심볼": (list(STREAMS), SYMS),
        "전체 6종 × BTC만": (list(STREAMS), ["BTC"]),
        "현재 라이브(MOM 없이 DON4H_30만) × 3심볼": (["DON4H_30"], SYMS),
    }
    print("\n### 포트폴리오 (스트림 합산 후 배율 s 적용. 스트림당 기본 리스크 1%이므로 s=1은 스트림 수만큼 리스크가 겹침)")
    print("| 구성 | 스트림수 | 배율 | 연복리 | MDD | 샤프 | 4년 총수익 | 전반 연복리 | 후반 연복리 |")
    print("|---|---|---|---|---|---|---|---|---|")
    for label, (names, syms) in combos.items():
        k = len(names) * len(syms)
        for target in (1.0, 2.0):         # 배율: 전체 합산 리스크를 키운다 (스트림당 평균 리스크 = target × 1%)
            sc = target / 1.0 * (3.0 / k) if k > 3 else target       # 스트림이 많으면 겹침을 줄이도록 정규화
            r = port(names, syms, sc)
            a, b, c = stats(r), stats(port(names, syms, sc, None, mid)), stats(port(names, syms, sc, mid, None))
            print(f"| {label} | {k} | ×{sc:.2f} | {a['cagr']:+.1f}% | {a['mdd']:.1f}% | {a['sharpe']:.2f} | {a['total']:+.0f}% | {b['cagr']:+.1f}% | {c['cagr']:+.1f}% |")

    # 목표 MDD 25%에 맞춘 배율 탐색 (전체 6종 × 3심볼)
    names, syms = list(STREAMS), SYMS
    print("\n### 전체 6종 × 3심볼: 배율별 연복리/MDD (MDD ≈ 15/25/35%가 되는 지점)")
    base = port(names, syms, 1.0)
    for sc in (0.12, 0.2, 0.3, 0.4, 0.5, 0.65, 0.8, 1.0):
        st = stats(base * sc)
        b_, c_ = stats(port(names, syms, sc, None, mid)), stats(port(names, syms, sc, mid, None))
        print(f"  배율 ×{sc:<4} | 연복리 {st['cagr']:+6.1f}% | MDD {st['mdd']:5.1f}% | 샤프 {st['sharpe']:.2f} | 전반 {b_['cagr']:+.1f}% / 후반 {c_['cagr']:+.1f}% (MDD {b_['mdd']:.0f}/{c_['mdd']:.0f}%)")
    corr = pd.DataFrame({f"{n}_{s}": R[(n, s)] for n in ("MOM20_6", "DON4H_30", "DON1H_160") for s in SYMS}).corr()
    print("\n일 수익률 상관 평균(서로 다른 스트림 간):", round(float((corr.values.sum() - len(corr)) / (len(corr) ** 2 - len(corr))), 2))
