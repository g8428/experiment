"""MTF 사슬 + 1분봉 트리거 백테스트: S1~S3 × window 1·3·7·15일 × 킬존 on/off × 시가규칙 daily/strict.

python run_mtf.py → 표 출력 + results_mtf.csv
"""
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from core import load_1m, mirror  # noqa: E402
from mtf import build_mtf  # noqa: E402
from mtf_strategies import RUNNERS  # noqa: E402
from run_windows import WINDOWS, stats  # noqa: E402

BARS_PER_DAY = 1440


def main():
    t0 = time.time()
    df = load_1m()
    ctxs = (("L", build_mtf(df)), ("S", build_mtf(mirror(df))))
    split = df.index[0] + (df.index[-1] - df.index[0]) / 2
    print(f"1m {len(df)}봉 {df.index[0]:%Y-%m-%d} ~ {df.index[-1]:%Y-%m-%d}, 컨텍스트 {time.time()-t0:.0f}s", flush=True)
    rows = []
    for strat, fn in RUNNERS.items():
        for wname, wd in WINDOWS.items():
            for kz in (True, False):
                for om in ("daily", "strict"):
                    tr = []
                    for side, ctx in ctxs:
                        for t in fn(ctx, wd * BARS_PER_DAY, kz, om):
                            t["side"] = side
                            tr.append(t)
                    tr.sort(key=lambda t: t["t"])
                    s = stats(tr)
                    a, b = stats([t for t in tr if t["t"] < split]), stats([t for t in tr if t["t"] >= split])
                    r = dict(strat=strat, window=wname, killzone=kz, open_rule=om, **s,
                             long_n=sum(t["side"] == "L" for t in tr), y1_n=a["n"], y1_totR=a["totR"],
                             y2_n=b["n"], y2_totR=b["totR"],
                             med_risk_pct=np.median([t["risk"] for t in tr]) * 100 if tr else np.nan)
                    rows.append(r)
                    print(f"{strat} {wname:>3} kz={'on ' if kz else 'off'} {om:6} n={r['n']:4} win={r['win']:.2f} "
                          f"avgR={r['avgR']:+.3f} totR={r['totR']:+7.1f} PF={r['PF']:.2f} mddR={r['mddR']:5.1f} "
                          f"| 1년차 {r['y1_n']:3}/{r['y1_totR']:+6.1f}R 2년차 {r['y2_n']:3}/{r['y2_totR']:+6.1f}R "
                          f"| 롱 {r['long_n']} | 손절폭 {r['med_risk_pct']:.2f}%", flush=True)
    pd.DataFrame(rows).to_csv(os.path.join(os.path.dirname(__file__), "results_mtf.csv"), index=False, encoding="utf-8-sig")
    print(f"완료 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
