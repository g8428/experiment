"""
robust_v2.py — 파라미터 '최적화'가 아니라 '견고성' 확인용 그리드.
모든 조합을 전반(IS)/후반(OOS) × 심볼로 돌려서, 조합 대부분이 양수인 '평평한 고원'인지 본다.
한두 조합만 좋으면 과최적화 → 채택하지 않는다.

  python backtest/robust_v2.py --strat don --syms BTC,ETH,XRP
"""
import argparse
import itertools
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE)); sys.path.insert(0, _HERE)

import engine_v2 as E  # noqa: E402
import strategies_v2 as S  # noqa: E402
from run_v2 import load, OUT_DIR  # noqa: E402

GRIDS = {
    "don": (S.DonchianBreakout, {"n": [20, 40, 55], "sl_atr": [1.5, 2.0, 3.0], "trail_atr": [2.0, 3.0, 4.0]}),
    "d1t": (S.DailyTrend, {"n": [10, 20, 40], "sl_atr": [1.5, 2.0, 3.0], "trail_atr": [2.0, 3.0, 4.0]}),
    "tpb": (S.TrendPullback, {"adx_min": [15, 20, 25], "rsi_pb": [40, 45, 50], "trail": [2.0, 3.0, 4.0]}),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strat", default="don")
    ap.add_argument("--syms", default="BTC,ETH,XRP")
    ap.add_argument("--risk", type=float, default=2.0)
    args = ap.parse_args()
    cls, grid = GRIDS[args.strat]
    keys = list(grid)
    combos = list(itertools.product(*grid.values()))
    out = []
    for sym in args.syms.split(","):
        data = load(f"{sym}-USDT-SWAP", horizon="4y")
        t0, t1 = int(data["1H"]["t"].iloc[0]), int(data["1H"]["t"].iloc[-1])
        mid = t0 + (t1 - t0) // 2
        for combo in combos:
            kw = dict(zip(keys, combo))
            row = {"sym": sym, **kw}
            for pname, a, b in (("is", None, mid), ("oos", mid, None)):
                st = cls(**kw)
                sm = E.summarize(E.run(st, data, risk_pct=args.risk, start_ts=a, end_ts=b))
                row[f"{pname}_ret"] = sm["return_pct"]; row[f"{pname}_pf"] = sm["pf"]
                row[f"{pname}_n"] = sm["trades"]; row[f"{pname}_mdd"] = sm["mdd_pct"]
            out.append(row)
        rows = [r for r in out if r["sym"] == sym]
        both = sum(1 for r in rows if r["is_ret"] > 0 and r["oos_ret"] > 0)
        oos = sum(1 for r in rows if r["oos_ret"] > 0)
        med_oos = sorted(r["oos_ret"] for r in rows)[len(rows) // 2]
        print(f"{sym} {args.strat}: 조합 {len(rows)}개 중 IS·OOS 둘다 양수 {both}개, OOS 양수 {oos}개, "
              f"OOS 수익률 중앙값 {med_oos}%", flush=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, f"robust_{args.strat}.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=0, default=float)


if __name__ == "__main__":
    main()
