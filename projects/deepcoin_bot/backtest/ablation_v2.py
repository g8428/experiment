"""
ablation_v2.py — "옛 백테스트 +206%"가 어디서 나왔는지 결함을 하나씩 고치며 측정.

  python backtest/ablation_v2.py --sym BTC-USDT-SWAP --days 180 --chain OTE,MTF --m15 2
"""
import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE)); sys.path.insert(0, _HERE)

import engine_v2 as E  # noqa: E402
import strategies_v2 as S  # noqa: E402
from run_v2 import load, tuning, LEGACY_LIMITS, OUT_DIR  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sym", default="BTC-USDT-SWAP")
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--chain", default="OTE,MTF")
    ap.add_argument("--m15", type=int, default=2)
    args = ap.parse_args()
    data = load(args.sym)
    tu = tuning()
    t_end = int(data["15m"]["t"].iloc[-1])
    start = t_end - args.days * 86_400_000
    chain = tuple(args.chain.split(","))
    labels = E.label_for_base(data, "15m")

    steps = [
        ("0 옛 엔진 재현 (15m 101/1H 50/D1 50봉, 미래누수, 수수료0, 종가체결, 일한도 없음)",
         dict(n15=101, n1h=50, n1d=50), dict(lookahead=True, fee=0, slip=0, fill="close")),
        ("1 + 라이브와 같은 캔들 개수 (15m 60/1H 25/D1 120 → D1 레짐 필터 실제 작동)",
         dict(n15=60, n1h=25, n1d=120), dict(lookahead=True, fee=0, slip=0, fill="close")),
        ("2 + 미래 데이터 누수 제거 (완결된 1H/D1만)",
         dict(), dict(lookahead=False, fee=0, slip=0, fill="close")),
        ("3 + 수수료 0.06%×2 + 슬리피지 0.02%",
         dict(), dict(lookahead=False, fee=0.0006, slip=0.0002, fill="close")),
        ("4 + 다음 봉 시가 체결",
         dict(), dict(lookahead=False, fee=0.0006, slip=0.0002, fill="next_open")),
        ("5 + 라이브 일한도/쿨다운 (= 정직한 현재 라이브)",
         dict(), dict(lookahead=False, fee=0.0006, slip=0.0002, fill="next_open",
                      daily_limits=LEGACY_LIMITS, cooldown_bars=1)),
    ]
    rows = []
    for name, skw, ekw in steps:
        st = S.LegacyChain(args.sym, tu, chain=chain, m15_confirm_n=args.m15, **skw)
        res = E.run(st, data, risk_pct=tu.get("risk_pct", 10), start_ts=start, label_series=labels, **ekw)
        sm = E.summarize(res, name)
        rows.append(sm)
        print(f"| {name} | {sm['trades']} | {sm['win_rate']}% | {sm['pf']} | {sm['exp_r']} | "
              f"{sm['return_pct']}% | {sm['mdd_pct']}% |", flush=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    fn = f"ablation_{args.sym.split('-')[0]}_{'+'.join(chain)}_m15{args.m15}_{args.days}d.json"
    with open(os.path.join(OUT_DIR, fn), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, default=float, indent=1)


if __name__ == "__main__":
    main()
