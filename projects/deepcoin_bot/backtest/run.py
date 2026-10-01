"""
run.py — 백테스팅 CLI 실행 엔트리포인트

사용법:
  python backtest/run.py --strategy ict_killzone --bar 15m --days 30
  python backtest/run.py --all --bar 15m --days 30
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from data_fetcher import fetch_historical
from strategy import STRATEGIES
from engine import run_backtest
from metrics import calc_metrics
from weights import update_weights, print_weights

_TUNING_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tuning.json")


def _load_tuning():
    try:
        with open(_TUNING_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _print_summary(name, result):
    s = result["summary"]
    m = calc_metrics(result["trades"])
    print(f"\n{'='*50}")
    print(f"전략: {name}")
    print(f"{'='*50}")
    print(f"  총 거래:       {m['total_trades']}건")
    print(f"  승률:          {m['win_rate']}%")
    print(f"  손익비(avg):   {m['avg_rr']:.2f}")
    print(f"  수익팩터:      {m['profit_factor']:.3f}")
    print(f"  Sharpe:        {m['sharpe']:.3f}")
    print(f"  최대 낙폭:     {s['max_drawdown_pct']:.2f}%")
    print(f"  총 수익률:     {s['total_return_pct']:.2f}%")
    print(f"  최종 잔고:     ${s['final_balance']:.2f}")
    if m["by_pattern"]:
        print("\n  [패턴별 성과]")
        for pk, v in m["by_pattern"].items():
            print(f"    {pk}: {v['trades']}건 승률{v['win_rate']}% PnL{v['total_pnl']:.2f}")


def main():
    parser = argparse.ArgumentParser(description="ICT 전략 백테스팅")
    parser.add_argument("--strategy", type=str, help="전략 이름 (ict_killzone|ict_ote|ict_breaker)")
    parser.add_argument("--all",      action="store_true", help="모든 전략 비교")
    parser.add_argument("--sym",      type=str, default="BTC-USDT-SWAP")
    parser.add_argument("--bar",      type=str, default="15m")
    parser.add_argument("--days",     type=int, default=30)
    parser.add_argument("--balance",  type=float, default=1000.0)
    parser.add_argument("--risk",     type=float, default=10.0, help="리스크 % (기본 10%)")
    parser.add_argument("--leverage", type=int, default=20)
    parser.add_argument("--tp_min",   type=float, default=0.0, help="최소 TP % (기본 0=비활성)")
    parser.add_argument("--rr_min",   type=float, default=1.5, help="최소 RR (기본 1.5)")
    parser.add_argument("--sl_min_atr_mult", type=float, default=None,
                         help="SL 최소폭 ATR 배율 — 안 주면 tuning.json의 심볼별/전역값 사용 (라이브와 동일)")
    parser.add_argument("--sl_cap",   type=float, default=None,
                         help="SL 상한 %% — 안 주면 tuning.json의 심볼별/전역값 사용 (라이브와 동일)")
    parser.add_argument("--json",     action="store_true", help="JSON 출력")
    parser.add_argument("--refresh",  action="store_true", help="캐시 무시하고 캔들 새로 수집")
    parser.add_argument("--m15_confirm_n", type=int, default=0,
                         help="B안: 신호 직전 15분봉 n개가 방향과 일치하는지 확인 필터 "
                              "(기본 0=비활성, server.py와 동일 동작)")
    parser.add_argument("--no_h1_trend", action="store_true",
                         help="1H 추세(get_htf_trend) 체크를 건너뛰고 D1레짐+자체 신호만으로 판단 "
                              "(기본은 끔=server.py와 동일 동작)")
    args = parser.parse_args()
    require_h1_trend = not args.no_h1_trend

    tuning = _load_tuning()
    sl_min_atr_mult = args.sl_min_atr_mult
    if sl_min_atr_mult is None:
        sl_min_atr_mult = tuning.get("sl_min_atr_mult_by_sym", {}).get(
            args.sym, tuning.get("sl_min_atr_mult", 0.8))
    sl_cap_pct = args.sl_cap
    if sl_cap_pct is None:
        sl_cap_pct = tuning.get("sl_cap_pct_by_sym", {}).get(
            args.sym, tuning.get("sl_cap_pct"))
    print(f"SL 규칙: ATR×{sl_min_atr_mult} 최소폭, 상한 {sl_cap_pct}% "
          f"({'tuning.json' if args.sl_min_atr_mult is None else 'CLI 지정'}) — server.py와 동일 소스")
    print(f"비교 파라미터: m15_confirm_n={args.m15_confirm_n} (0=비활성/server.py 동일), "
          f"require_h1_trend={require_h1_trend} (True=server.py 동일)")

    print(f"데이터 준비 중: {args.sym} {args.bar} {args.days}일... (캐시 있으면 재사용, --refresh 시 새로 수집)")
    kl = fetch_historical(args.sym, args.bar, args.days, refresh=args.refresh)
    if not kl:
        print("캔들 데이터 없음. 네트워크 확인 필요.")
        sys.exit(1)
    print(f"캔들 {len(kl)}개 준비 완료.")

    h1_kl = fetch_historical(args.sym, "1H", args.days, refresh=args.refresh)
    m5_kl = fetch_historical(args.sym, "5m", args.days, refresh=args.refresh)
    d1_kl = fetch_historical(args.sym, "1D", args.days + 60, refresh=args.refresh)  # 일봉 EMA50 계산용 여유 확보
    print(f"1H={len(h1_kl)}개 / 5m={len(m5_kl)}개 / 1D={len(d1_kl)}개")

    names = list(STRATEGIES.keys()) if args.all else [args.strategy]
    if not args.all and not args.strategy:
        parser.print_help()
        sys.exit(1)

    results = {}
    for name in names:
        strat = STRATEGIES.get(name)
        if not strat:
            print(f"알 수 없는 전략: {name}. 선택 가능: {list(STRATEGIES.keys())}")
            continue
        result = run_backtest(
            strat, kl, h1_all=h1_kl, d1_all=d1_kl, m5_all=m5_kl,
            initial_balance=args.balance,
            risk_pct=args.risk,
            leverage=args.leverage,
            sym=args.sym,
            tp_min_pct=args.tp_min,
            rr_min=args.rr_min,
            sl_min_atr_mult=sl_min_atr_mult,
            sl_cap_pct=sl_cap_pct,
            m15_confirm_n=args.m15_confirm_n,
            require_h1_trend=require_h1_trend,
        )
        # 가중치 업데이트
        update_weights(result["trades"], sym=args.sym)
        results[name] = result
        if not args.json:
            _print_summary(name, result)

    if args.json:
        out = {name: {
            "summary":  r["summary"],
            "metrics":  calc_metrics(r["trades"]),
            "trades":   r["trades"][:20],  # 최근 20건만
        } for name, r in results.items()}
        print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
