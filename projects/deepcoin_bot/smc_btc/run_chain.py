"""사슬 v2 전체 백테스트: 전략 × 바이어스 모드(structure/narrative) × window(1·3·7·15일) × 킬존(on/off), 시가 규칙 strict.
롱(원본)+숏(미러) 합산. 결과: results_chain.csv, 콘솔 표.

python run_chain.py [--rebuild] [--only S1,S2]
"""
import os
import pickle
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from chain2 import build_chain, load_hist_1h  # noqa: E402
from core import load_1m, mirror  # noqa: E402
from run_windows import stats  # noqa: E402
from strats2 import RUNNERS  # noqa: E402

CACHE = os.path.join(os.path.dirname(__file__), "..", "backtest", "cache")
WINDOWS = {"1d": 1, "3d": 3, "7d": 7, "15d": 15}


def ctx(side, rebuild):
    pk = os.path.join(CACHE, f"ctx_v2_{'long' if side == 'L' else 'short'}.pkl")
    if os.path.exists(pk) and not rebuild:
        return pickle.load(open(pk, "rb"))
    df, h = load_1m(), load_hist_1h()
    if side == "S":
        df, h = mirror(df), mirror(h)
    c = build_chain(df, h)
    pickle.dump(c, open(pk, "wb"), protocol=4)
    return c


def main():
    rebuild = "--rebuild" in sys.argv
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1].split(",")
    t0 = time.time()
    C = {s: ctx(s, rebuild) for s in ("L", "S")}
    idx = C["L"]["idx"]
    split = idx[0] + (idx[-1] - idx[0]) / 2
    print(f"컨텍스트 {time.time()-t0:.0f}s, {idx[0]:%Y-%m-%d} ~ {idx[-1]:%Y-%m-%d}", flush=True)
    rows = []
    for name, (fn, uses_w) in RUNNERS.items():
        if only and name not in only:
            continue
        wins = WINDOWS if uses_w else {"-": 1}
        for mode in ("structure", "narrative"):
            for wname, wd in wins.items():
                for kz in (True, False):
                    t1 = time.time()
                    tr = []
                    for side, c in C.items():
                        for t in fn(c, mode, wd * 1440, kz, "strict"):
                            t["side"] = side
                            tr.append(t)
                    tr.sort(key=lambda t: t["t"])
                    s = stats(tr)
                    smk = stats([dict(R=t["R_mk"]) for t in tr])
                    a, b = stats([t for t in tr if t["t"] < split]), stats([t for t in tr if t["t"] >= split])
                    why = pd.Series([t["why"] for t in tr]).value_counts().to_dict() if tr else {}
                    r = dict(strat=name, mode=mode, window=wname, killzone=kz, **s,
                             mk_avgR=smk["avgR"], mk_totR=smk["totR"], mk_PF=smk["PF"],
                             long_n=sum(t["side"] == "L" for t in tr), y1_n=a["n"], y1_totR=a["totR"],
                             y2_n=b["n"], y2_totR=b["totR"],
                             med_risk_pct=np.median([t["risk"] for t in tr]) * 100 if tr else np.nan, exits=str(why))
                    rows.append(r)
                    print(f"{name:4} {mode[:6]} {wname:>3} kz={'on ' if kz else 'off'} n={r['n']:4} win={r['win']:.2f} "
                          f"avgR={r['avgR']:+.3f} totR={r['totR']:+7.1f} PF={r['PF']:.2f} mddR={r['mddR']:5.1f} "
                          f"[maker {r['mk_totR']:+6.1f} PF {r['mk_PF']:.2f}] "
                          f"| 1년차 {r['y1_n']:3}/{r['y1_totR']:+6.1f} 2년차 {r['y2_n']:3}/{r['y2_totR']:+6.1f} "
                          f"| 롱 {r['long_n']} | 손절폭 {r['med_risk_pct']:.2f}% | {why} ({time.time()-t1:.0f}s)", flush=True)
                    pd.DataFrame(rows).to_csv(os.path.join(os.path.dirname(__file__), "results_chain.csv"),
                                              index=False, encoding="utf-8-sig")
    print(f"완료 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
