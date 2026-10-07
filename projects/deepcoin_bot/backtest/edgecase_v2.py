"""
edgecase_v2.py — 상승/하락/횡보장 엣지케이스 점검

  python backtest/edgecase_v2.py --sym BTC-USDT-SWAP --strat regime_trend_long

점검 항목:
  · 국면별(상승/하락/횡보) 시간 비중, 그 국면에서 포지션 보유 비율, 국면별 전략 일수익 합 vs B&H
  · 최대 연속 손실, 최악 거래(R), 갭으로 손절을 뚫은 거래(R < -1.2)
  · 극단 변동일 Top 10 (일간 |등락| 최대) — 그날 포지션 방향과 계좌 손익
  · 월별 손익 분포 (음수 달 비율, 최악의 달)
"""
import argparse
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE)); sys.path.insert(0, _HERE)

import engine_v2 as E  # noqa: E402
from run_v2 import load, build  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sym", default="BTC-USDT-SWAP")
    ap.add_argument("--strat", default="regime_trend_long")
    ap.add_argument("--horizon", default="4y")
    args = ap.parse_args()
    data = load(args.sym, horizon=args.horizon)
    strat, kw = build(args.strat, args.sym)
    base = data[strat.base_tf]
    labels = E.label_for_base(data, strat.base_tf)
    res = E.run(strat, data, label_series=labels, **kw)
    tr = res["trades"]

    eq = pd.Series(res["equity"], index=pd.to_datetime(res["t"], unit="ms", utc=True)).ffill()
    px = pd.Series(base["c"].values, index=pd.to_datetime(base["t"].values, unit="ms", utc=True))
    lab = pd.Series(labels, index=px.index)
    # 보유 여부 (base 캔들 단위)
    held = pd.Series(0, index=px.index)
    for x in tr:
        a = pd.to_datetime(x["open_t"], unit="ms", utc=True); b = pd.to_datetime(x["close_t"], unit="ms", utc=True)
        held[(held.index >= a) & (held.index <= b)] = x["dir"]

    day = lambda s: s.resample("1D").last()  # noqa: E731
    d_eq, d_px = day(eq), day(px)
    d_lab = lab.resample("1D").last(); d_held = held.resample("1D").agg(lambda v: v.iloc[-1] if len(v) else 0)
    r_eq, r_px = d_eq.pct_change(), d_px.pct_change()

    print(f"\n## {args.sym} {strat.name} 엣지케이스 점검 ({d_eq.index[0].date()} ~ {d_eq.index[-1].date()})\n")
    print("### 국면별")
    print("| 국면 | 일수 비중 | 포지션 보유일 비율 | 전략 누적(일수익 합) | B&H 누적(일수익 합) |")
    print("|---|---|---|---|---|")
    for g in ("상승", "횡보", "하락"):
        m = d_lab == g
        if m.sum() == 0:
            continue
        print(f"| {g} | {m.mean()*100:.0f}% | {(d_held[m] != 0).mean()*100:.0f}% | "
              f"{r_eq[m].sum()*100:+.1f}% | {r_px[m].sum()*100:+.1f}% |")

    pnl = [x["r"] for x in tr]
    streak = best = 0
    for r in pnl:
        streak = streak + 1 if r < 0 else 0
        best = max(best, streak)
    gaps = [x for x in tr if x["r"] < -1.2]
    print(f"\n### 손실 꼬리\n- 거래 {len(tr)}건, 최대 연속 손실 {best}회, 최악 거래 {min(pnl):.2f}R, "
          f"갭으로 손절 관통(R<-1.2) {len(gaps)}건"
          + (": " + ", ".join(f"{datetime.fromtimestamp(x['close_t']/1000, tz=timezone.utc).date()} {x['r']:.2f}R"
                                for x in gaps[:5]) if gaps else ""))
    print(f"- 시간 기준 포지션 보유율 {(held != 0).mean()*100:.0f}% (나머지는 현금 대기)")

    print("\n### 극단 변동일 Top 10 (일간 |등락| 기준)")
    print("| 날짜 | 가격 등락 | 국면 | 그날 포지션 | 계좌 손익 |")
    print("|---|---|---|---|---|")
    for dt in r_px.abs().sort_values(ascending=False).index[:10]:
        pos = {1: "롱", -1: "숏", 0: "없음"}[int(d_held.get(dt, 0))]
        print(f"| {dt.date()} | {r_px[dt]*100:+.1f}% | {d_lab.get(dt, '-')} | {pos} | {r_eq[dt]*100:+.2f}% |")

    m_eq = eq.resample("M").last().pct_change().dropna()
    print(f"\n### 월별\n- 음수 달 {(m_eq < 0).sum()}/{len(m_eq)}개월, 최악의 달 {m_eq.min()*100:.1f}% "
          f"({m_eq.idxmin().strftime('%Y-%m')}), 최고의 달 {m_eq.max()*100:.1f}% ({m_eq.idxmax().strftime('%Y-%m')})")


if __name__ == "__main__":
    main()
