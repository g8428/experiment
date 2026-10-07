"""셋업 유효 기간(window) 비교: 1·3·7·15일 × 킬존 on/off × 시가규칙(daily/strict) × S1~S3, 롱+숏.

python run_windows.py  → 결과 표 출력 + results_windows.csv
"""
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from core import load_5m, mirror  # noqa: E402
from strategies import RUNNERS, build  # noqa: E402

BARS_PER_DAY = 288  # 5m
WINDOWS = {"1d": 1, "3d": 3, "7d": 7, "15d": 15}


def stats(tr):
    if not tr:
        return dict(n=0, win=np.nan, avgR=np.nan, totR=0.0, PF=np.nan, mddR=0.0)
    R = np.array([t["R"] for t in tr])
    eq = np.cumsum(R)
    mdd = (np.maximum.accumulate(np.concatenate([[0], eq])) - np.concatenate([[0], eq])).max()
    gp, gl = R[R > 0].sum(), -R[R < 0].sum()
    return dict(n=len(R), win=(R > 0).mean(), avgR=R.mean(), totR=R.sum(),
                PF=gp / gl if gl > 0 else np.inf, mddR=mdd)


def main():
    t0 = time.time()
    df = load_5m()
    ctx_long, ctx_short = build(df), build(mirror(df))
    split = df.index[0] + (df.index[-1] - df.index[0]) / 2
    print(f"데이터 {df.index[0]:%Y-%m-%d} ~ {df.index[-1]:%Y-%m-%d}, 컨텍스트 {time.time()-t0:.0f}s")
    rows = []
    for strat, fn in RUNNERS.items():
        for wname, wd in WINDOWS.items():
            for kz in (True, False):
                for om in ("daily", "strict"):
                    tr = []
                    for side, ctx in (("L", ctx_long), ("S", ctx_short)):
                        for t in fn(ctx, wd * BARS_PER_DAY, kz, om):
                            t["side"] = side
                            tr.append(t)
                    tr.sort(key=lambda t: t["t"])
                    s = stats(tr)
                    h1 = stats([t for t in tr if t["t"] < split])
                    h2 = stats([t for t in tr if t["t"] >= split])
                    rows.append(dict(strat=strat, window=wname, killzone=kz, open_rule=om, **s,
                                     long_n=sum(t["side"] == "L" for t in tr),
                                     y1_n=h1["n"], y1_totR=h1["totR"], y2_n=h2["n"], y2_totR=h2["totR"],
                                     med_risk_pct=np.median([t["risk"] for t in tr]) * 100 if tr else np.nan))
                    r = rows[-1]
                    print(f"{strat} {wname:>3} kz={'on ' if kz else 'off'} {om:6} n={r['n']:4} win={r['win']:.2f} "
                          f"avgR={r['avgR']:+.3f} totR={r['totR']:+7.1f} PF={r['PF']:.2f} mddR={r['mddR']:5.1f} "
                          f"| 1년차 {r['y1_n']:3}/{r['y1_totR']:+6.1f}R 2년차 {r['y2_n']:3}/{r['y2_totR']:+6.1f}R "
                          f"| 손절폭 중앙 {r['med_risk_pct']:.2f}%", flush=True)
    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(os.path.dirname(__file__), "results_windows.csv"), index=False, encoding="utf-8-sig")
    print(f"완료 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
