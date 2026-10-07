"""
run_v2.py — engine_v2(정직한 엔진) 백테스트 CLI

  python backtest/run_v2.py --sym BTC-USDT-SWAP --strat legacy,tpb,don,rmr,adaptive
  python backtest/run_v2.py --sym BTC-USDT-SWAP --strat legacy_intrabar --since 2026-04-01

데이터: backtest/cache/{sym}_{tf}_{730|800}d.json (2년치, 2026-10-01 수집)
결과:   research/backtest_v2/{sym}_{strat}.json (요약 + 전체 거래)
"""

import argparse
import json
import os
import sys
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.path.insert(0, _HERE)

import engine_v2 as E  # noqa: E402
import strategies_v2 as S  # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(_HERE), "research", "backtest_v2")
DAYS = {"15m": 730, "1H": 730, "5m": 730, "1D": 800}


def load(sym, need_5m=False, horizon="2y"):
    if horizon == "4y":   # 1H 기반 신규 전략 전용 (15m/5m은 2년치만 있음)
        data = {"1H": E.load_df(sym, "1H", 1460), "1D": E.load_df(sym, "1D", 1600)}
        data["4H"] = E.resample(data["1H"], "1H", "4H")
        return data
    data = {tf: E.load_df(sym, tf, DAYS[tf]) for tf in ("15m", "1H", "1D")}
    data["4H"] = E.resample(data["1H"], "1H", "4H")
    p5 = os.path.join(E.CACHE_DIR, f"{sym}_5m_{DAYS['5m']}d.json")
    if need_5m or os.path.exists(p5):
        data["5m"] = E.load_df(sym, "5m", DAYS["5m"])
    return data


def tuning():
    with open(os.path.join(os.path.dirname(_HERE), "tuning.json"), encoding="utf-8") as f:
        return json.load(f)


LEGACY_LIMITS = {"max_losses": 3, "max_trades": 7, "loss_stop": 25, "profit_stop": 10}


def build(name, sym):
    tu = tuning()
    if name == "legacy":            # 현재 라이브: OTE→MTF, m15_confirm 2
        return S.LegacyChain(sym, tu), dict(risk_pct=tu.get("risk_pct", 10), daily_limits=LEGACY_LIMITS,
                                            cooldown_bars=1)
    if name == "legacy_all4":       # 9/23~9/30 라이브: OTE→MTF→KZ→BRK, 확인캔들 없음
        return (S.LegacyChain(sym, tu, chain=("OTE", "MTF", "KZ", "BRK"), m15_confirm_n=0, name="legacy_all4"),
                dict(risk_pct=tu.get("risk_pct", 10), daily_limits=LEGACY_LIMITS, cooldown_bars=1))
    if name == "legacy_intrabar":
        return S.LegacyIntrabar(sym, tu), dict(risk_pct=tu.get("risk_pct", 10), daily_limits=LEGACY_LIMITS,
                                               cooldown_bars=3)
    if name == "legacy_r2":          # 현재 라이브 로직, 리스크만 2%
        return S.LegacyChain(sym, tu, name="legacy_r2"), dict(risk_pct=2, daily_limits=LEGACY_LIMITS,
                                                               cooldown_bars=1)
    smc_chains = {
        "smc_raw": ("SMC",),       # BOS/ChoCh 또는 sweep + OB, 목표는 FVG/스윙 구조
        "smc_ote": ("OTE",),       # sweep 이후 0.618~0.786 되돌림
        "smc_mtf": ("MTF",),       # 세션 + HTF 방향 + OB/FVG 컨플루언스
        "smc_kz": ("KZ",),         # 뉴욕 세션의 HTF 정렬 OB/FVG
        "smc_breaker": ("BRK",),  # 실패한 OB의 역할전환 재시험
    }
    if name in smc_chains:
        strat = S.LegacyChain(sym, tu, chain=smc_chains[name], name=name)
        return strat, dict(risk_pct=2, daily_limits=LEGACY_LIMITS, cooldown_bars=1)
    smc_5m_chains = {
        "smc_raw_m5_40": ("SMC",),
        "smc_ote_m5_40": ("OTE",),
        "smc_mtf_m5_40": ("MTF",),
        "smc_kz_m5_40": ("KZ",),
    }
    if name in smc_5m_chains:
        strat = S.LegacyChain(sym, tu, chain=smc_5m_chains[name], name=name,
                              m5_structure_lookback=40)
        return strat, dict(risk_pct=2, daily_limits=LEGACY_LIMITS, cooldown_bars=1)
    smc_5m_30_chains = {
        "smc_raw_m5_30": ("SMC",),
        "smc_ote_m5_30": ("OTE",),
        "smc_mtf_m5_30": ("MTF",),
        "smc_kz_m5_30": ("KZ",),
    }
    if name in smc_5m_30_chains:
        strat = S.LegacyChain(sym, tu, chain=smc_5m_30_chains[name], name=name,
                              m5_structure_lookback=30)
        return strat, dict(risk_pct=2, daily_limits=LEGACY_LIMITS, cooldown_bars=1)
    smc_5m_60_chains = {
        "smc_raw_m5_60": ("SMC",),
        "smc_ote_m5_60": ("OTE",),
        "smc_mtf_m5_60": ("MTF",),
        "smc_kz_m5_60": ("KZ",),
    }
    if name in smc_5m_60_chains:
        strat = S.LegacyChain(sym, tu, chain=smc_5m_60_chains[name], name=name,
                              m5_structure_lookback=60)
        return strat, dict(risk_pct=2, daily_limits=LEGACY_LIMITS, cooldown_bars=1)
    if name == "dump_sweep_5m":
        return S.DumpSweepReversal5m(), dict(risk_pct=2)
    if name == "tpb":
        return S.TrendPullback(), dict(risk_pct=2)
    if name == "don":
        return S.DonchianBreakout(), dict(risk_pct=2)
    if name == "rmr":
        return S.RangeReversion(), dict(risk_pct=2)
    if name == "d1t":
        return S.DailyTrend(), dict(risk_pct=2)
    if name == "d1t_long":
        return S.DailyTrend(allow_short=False, name="daily_trend_long"), dict(risk_pct=2)
    if name == "regime_trend_long":
        return S.RegimeTrend(allow_short=False, name="regime_trend_long"), dict(risk_pct=2)
    if name == "regime_trend":
        return S.RegimeTrend(), dict(risk_pct=2)
    if name == "adaptive":
        return S.Adaptive(), dict(risk_pct=2)
    if name == "adaptive_trend":    # 횡보 역추세 제외
        return S.Adaptive(use_range=False, name="adaptive_trend"), dict(risk_pct=2)
    raise SystemExit(f"unknown strat {name}")


def periods(data):
    t0 = int(data["1H"]["t"].iloc[0]); t1 = int(data["1H"]["t"].iloc[-1])
    mid = t0 + (t1 - t0) // 2
    out = [("전체", None, None), ("전반(IS)", None, mid), ("후반(OOS)", mid, None)]
    # 반기
    step = 182 * 86_400_000
    s = t0 + 60 * 86_400_000   # 지표 워밍업 이후
    k = 1
    while s < t1:
        out.append((f"H{k}", s, min(s + step, t1 + 1)))
        s += step; k += 1
    return out


def buy_hold(data, a, b):
    d = data["1H"]
    if a is not None:
        d = d[d["t"] >= a]
    if b is not None:
        d = d[d["t"] < b]
    if len(d) < 2:
        return 0.0
    return round((d["c"].iloc[-1] / d["o"].iloc[0] - 1) * 100, 1)


def fmt_date(ms):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sym", default="BTC-USDT-SWAP")
    ap.add_argument("--strat", default="legacy,tpb,don,rmr,adaptive")
    ap.add_argument("--since", default=None)
    ap.add_argument("--fee", type=float, default=0.0006)
    ap.add_argument("--slip", type=float, default=0.0002)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--horizon", default="2y", choices=["2y", "4y"])
    args = ap.parse_args()

    names = args.strat.split(",")
    need5 = any(n.endswith("intrabar") or n == "dump_sweep_5m"
                or n.endswith("_m5_40") or n.endswith("_m5_30") or n.endswith("_m5_60")
                for n in names)
    data = load(args.sym, need_5m=need5, horizon=args.horizon)
    os.makedirs(OUT_DIR, exist_ok=True)
    since = E.ts(args.since) if args.since else None

    for name in names:
        strat, kw = build(name, args.sym)
        base_tf = strat.base_tf
        labels = E.label_for_base(data, base_tf)
        rows = []
        t_start = time.time()
        for pname, a, b in periods(data):
            if since is not None:
                if pname != "전체":
                    continue
                a = since
            res = E.run(strat, data, fee=args.fee, slip=args.slip, start_ts=a, end_ts=b,
                        label_series=labels, **kw)
            sm = E.summarize(res, pname)
            sm["bh_pct"] = buy_hold(data, a, b)
            sm["from"] = fmt_date(a or int(data[base_tf]["t"].iloc[0]))
            sm["to"] = fmt_date(b or int(data[base_tf]["t"].iloc[-1]))
            rows.append(sm)
            if pname == "전체":
                full_trades = res["trades"]
                eq = res["equity"]; tt = res["t"]
                keep = ~np.isnan(eq)
                curve = [[int(x), round(float(y), 2)] for x, y in zip(tt[keep][::24], eq[keep][::24])]
        el = time.time() - t_start
        out = {"sym": args.sym, "strategy": strat.name, "params": getattr(strat, "p", None),
               "risk_pct": kw.get("risk_pct"), "fee": args.fee, "slip": args.slip,
               "periods": rows, "trades": full_trades, "equity_curve": curve}
        tag = name + (f"_since{args.since}" if args.since else "") + ("_4y" if args.horizon == "4y" else "")
        with open(os.path.join(OUT_DIR, f"{args.sym.split('-')[0]}_{tag}.json"), "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, default=float)
        print(f"\n### {args.sym} {strat.name} (risk {kw.get('risk_pct')}%, fee {args.fee*100:.2f}%, {el:.0f}s)")
        print("| 구간 | 기간 | 거래 | 승률 | PF | 기대R | 수익률 | MDD | 수수료(초기자본%) | B&H |")
        print("|---|---|---|---|---|---|---|---|---|---|")
        for r in rows:
            print(f"| {r['label']} | {r['from']}~{r['to']} | {r['trades']} | {r['win_rate']}% | {r['pf']} | "
                  f"{r['exp_r']} | {r['return_pct']}% | {r['mdd_pct']}% | {r['fees_pct']}% | {r['bh_pct']}% |")
        if not args.quiet and rows and rows[0].get("by_regime"):
            print("국면별(전체):", json.dumps(rows[0]["by_regime"], ensure_ascii=False))


if __name__ == "__main__":
    main()
