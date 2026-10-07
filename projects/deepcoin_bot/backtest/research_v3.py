"""
research_v3.py — 단기수익률 후보 전략군 일괄 탐색 (정직한 엔진, 4년, BTC/ETH/XRP, 전반/후반 분리)

  python backtest/research_v3.py [--risk 2]

채택 기준(엄격): 6개 칸(3심볼 × 전반/후반) 중 플러스 칸이 많고 최악의 칸이 크게 나쁘지 않을 것.
탐색한 변형 수를 전부 기록해 다중검정(우연히 좋은 칸) 위험을 같이 본다.
"""
import argparse
import itertools
import json
import os
import sys
from multiprocessing import Pool

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE)); sys.path.insert(0, _HERE)

SYMS = ["BTC", "ETH", "XRP"]
OUT = os.path.join(os.path.dirname(_HERE), "research", "backtest_v3")


def variants():
    import strategies_v3 as S
    V = []
    for r, a, tp, ts, bb in itertools.product((15, 25, 30), (2.0, 3.0), (1.5, 3.0), (24, 72), (False, True)):
        V.append(("DipBuy", dict(rsi_thr=r, atr_stop=a, tp_atr=tp, time_stop=ts, use_bb=bb), lambda kw=dict(rsi_thr=r, atr_stop=a, tp_atr=tp, time_stop=ts, use_bb=bb): S.DipBuy(**kw)))
    for k, sl, up, sh in itertools.product((0.3, 0.5, 0.7, 1.0), (0.5, 1.0), (True, False), (False, True)):
        V.append(("DayBreak", dict(k=k, sl_mult=sl, need_up=up, allow_short=sh), lambda kw=dict(k=k, sl_mult=sl, need_up=up, allow_short=sh): S.DayBreak(**kw)))
    for hr, up in itertools.product(range(24), (False, True)):
        V.append(("HourHold", dict(hour=hr, hold=6, need_up=up), lambda kw=dict(hour=hr, hold=6, need_up=up): S.HourHold(**kw)))
    for tf, ns in (("4H", (10, 20, 30, 55)), ("1H", (40, 80, 160))):
        for n, sl, sh in itertools.product(ns, (1.5, 2.5), (False, True)):
            V.append(("Donchian", dict(tf=tf, n=n, sl_atr=sl, allow_short=sh), lambda kw=dict(tf=tf, n=n, sl_atr=sl, allow_short=sh): S.Donchian(**kw)))
    for n, thr in itertools.product((10, 20, 40), (0.03, 0.06, 0.10)):
        V.append(("MomHold", dict(n=n, thr=thr), lambda kw=dict(n=n, thr=thr): S.MomHold(**kw)))
    return V


def job(a):
    vi, sym, risk = a
    import engine_v2 as E
    from run_v2 import load
    fam, params, mk = variants()[vi]
    data = load(f"{sym}-USDT-SWAP", horizon="4y")
    t0, t1 = int(data["1H"]["t"].iloc[0]), int(data["1H"]["t"].iloc[-1]); mid = t0 + (t1 - t0) // 2
    out = {"vi": vi, "fam": fam, "params": params, "sym": sym}
    for key, (s, e) in (("full", (None, None)), ("is", (None, mid)), ("oos", (mid, None))):
        sm = E.summarize(E.run(mk(), data, risk_pct=risk, start_ts=s, end_ts=e))
        out[key] = dict(n=sm["trades"], ret=sm["return_pct"], mdd=sm["mdd_pct"], er=sm["exp_r"], wr=sm["win_rate"])
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--risk", type=float, default=2.0); args = ap.parse_args()
    nv = len(variants())
    jobs = [(vi, s, args.risk) for vi in range(nv) for s in SYMS]
    print(f"변형 {nv}개 × {len(SYMS)}심볼 = {len(jobs)}건 실행", flush=True)
    with Pool(12) as p:
        res = p.map(job, jobs, chunksize=4)
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(os.path.join(OUT, f"grid_risk{args.risk:g}.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print("저장 완료")
