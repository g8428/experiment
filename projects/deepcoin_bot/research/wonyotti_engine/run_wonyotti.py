"""
run_wonyotti.py — 워뇨띠 스타일(무손절+물타기+분할익절) 백테스트 실행.

사용법:
  python backtest/run_wonyotti.py --sym BTC-USDT-SWAP --days 180 --leverage 1
  python backtest/run_wonyotti.py --sweep   # 레버리지 1/2/3/5/10x 전부 비교
"""

import argparse
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "backtest"))   # data_fetcher 공용
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_fetcher import fetch_historical
from engine_wonyotti import run_wonyotti_backtest


def _print_summary(lev, result):
    s = result["summary"]
    print(f"\n{'='*50}")
    print(f"레버리지: {lev}x")
    print(f"{'='*50}")
    print(f"  청산/익절 이벤트: {s['event_count']}건 (승{s['wins']} 패{s['losses']})")
    print(f"  강제청산 횟수:    {s['liquidations']}회")
    print(f"  최대 낙폭:        {s['max_drawdown_pct']:.2f}%")
    print(f"  총 수익률:        {s['total_return_pct']:.2f}%")
    print(f"  최종 잔고:        ${s['final_balance']:.2f}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sym", default="BTC-USDT-SWAP")
    p.add_argument("--days", type=int, default=180)
    p.add_argument("--balance", type=float, default=1000.0)
    p.add_argument("--leverage", type=float, default=1.0)
    p.add_argument("--unit_risk", type=float, default=1.0, help="최초진입 증거금 %% (기본 1%%)")
    p.add_argument("--take_step", type=float, default=0.3, help="분할익절 step %% (기본 0.3%%)")
    p.add_argument("--max_adds", type=int, default=30)
    p.add_argument("--sweep", action="store_true", help="레버리지 1/2/3/5/10x 비교")
    p.add_argument("--refresh", action="store_true")
    args = p.parse_args()

    print(f"데이터 준비 중: {args.sym} 15m {args.days}일...")
    kl = fetch_historical(args.sym, "15m", args.days, refresh=args.refresh)
    m5 = fetch_historical(args.sym, "5m", args.days, refresh=args.refresh)
    print(f"15m={len(kl)}개 5m={len(m5)}개")

    levs = [1, 2, 3, 5, 10] if args.sweep else [args.leverage]
    for lev in levs:
        result = run_wonyotti_backtest(
            kl, m5_all=m5, initial_balance=args.balance, leverage=lev,
            unit_risk_pct=args.unit_risk, take_step_pct=args.take_step,
            max_adds=args.max_adds,
        )
        _print_summary(lev, result)


if __name__ == "__main__":
    main()
