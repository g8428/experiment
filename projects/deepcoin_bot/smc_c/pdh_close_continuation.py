"""Backtest the lecture-9 daily close-above-prior-high continuation signal.

Signal: UTC daily close > prior UTC daily high.
Entry: next UTC day's first 1m open.
Target: signal-day high. Stops tested separately at prior-day high and signal-day low.
If target and stop occur in one 1m bar, stop is assumed first.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import t


HERE = Path(__file__).resolve().parent
CACHE = HERE.parent / "backtest" / "cache"
REPORT = HERE / "PDH_CLOSE_CONTINUATION_REPORT.md"
TRADES = HERE / "pdh_close_continuation_trades.csv"
BOOTSTRAPS = 5000
SEED = 20261003
TAKER_FEE = 0.0006
MAKER_FEE = 0.0002
STOP_SLIPPAGE = 0.0002


def load_1m():
    root = CACHE / "BTC-USDT-SWAP_1m"
    paths = sorted(root.glob("*.csv"))
    if not paths:
        raise FileNotFoundError(root)
    data = pd.concat((pd.read_csv(p) for p in paths), ignore_index=True)
    data = data.sort_values("t").drop_duplicates("t", keep="last")
    data.index = pd.to_datetime(data.pop("t"), unit="ms", utc=True)
    data = data[["o", "h", "l", "c", "v"]].apply(pd.to_numeric, errors="coerce").dropna()
    # Exclude future rows if the local cache contains candles beyond current UTC time.
    return data.loc[:pd.Timestamp.now(tz="UTC")]


def daily_bars(minute):
    grouped = minute.groupby(minute.index.floor("D"), sort=True)
    daily = grouped.agg(o=("o", "first"), h=("h", "max"), l=("l", "min"),
                        c=("c", "last"), bars=("c", "count"))
    daily["first_time"] = grouped.apply(lambda g: g.index[0])
    daily["last_time"] = grouped.apply(lambda g: g.index[-1])
    daily = daily[(daily.bars >= 1400) &
                  (daily.first_time == daily.index) &
                  (daily.last_time == daily.index + pd.Timedelta(hours=23, minutes=59))].copy()
    daily["prev_high"] = daily.h.shift(1)
    daily["signal"] = daily.c > daily.prev_high
    daily["next_high"] = daily.h.shift(-1)
    daily["next_open"] = daily.o.shift(-1)
    daily["next_close"] = daily.c.shift(-1)
    daily["next_date"] = daily.index + pd.Timedelta(days=1)
    next_index = pd.Series(daily.index, index=daily.index).shift(-1)
    daily["consecutive_next_day"] = next_index == daily.next_date
    return daily[daily.consecutive_next_day].dropna(subset=["prev_high", "next_high", "next_open", "next_close"])


def trade_one(minute, signal_day, day, stop_kind, exit_fee, target_kind="signal_high"):
    entry_time = signal_day + pd.Timedelta(days=1)
    exit_time_limit = signal_day + pd.Timedelta(days=2)
    if entry_time not in minute.index:
        return None, "no_exact_midnight_open"
    entry = float(minute.at[entry_time, "o"])
    target = (float(day.h) if target_kind == "signal_high" else
              entry + float(day.c - day.o))
    stop = {"prior_high": float(day.prev_high),
            "signal_low": float(day.l),
            "signal_open": float(day.o)}[stop_kind]
    if not stop < entry < target:
        return None, "invalid_next_open_vs_levels"
    bars = minute.loc[(minute.index >= entry_time) & (minute.index < exit_time_limit)]
    if bars.empty:
        return None, "no_next_day_bars"

    exit_price, reason, exit_stamp = None, None, None
    for stamp, bar in bars.iterrows():
        # Ambiguous OHLC path: use the adverse stop-first convention.
        stop_hit = float(bar.l) <= stop
        target_hit = float(bar.h) >= target
        if stop_hit:
            exit_price = min(float(bar.o), stop)
            reason, exit_stamp = "SL", stamp
            break
        if target_hit:
            # Resting sell limit is conservatively filled at its limit price.
            exit_price = target
            reason, exit_stamp = "TP", stamp
            break
    if exit_price is None:
        exit_stamp = bars.index[-1]
        exit_price = float(bars.iloc[-1].c)
        reason = "next_day_close"

    gross = (exit_price - entry) / entry
    entry_fee = TAKER_FEE
    actual_exit_fee = MAKER_FEE if reason == "TP" and exit_fee == MAKER_FEE else TAKER_FEE
    exit_cost = actual_exit_fee + (STOP_SLIPPAGE if reason == "SL" else 0.0)
    net = gross - entry_fee - exit_cost
    risk = (entry - stop) / entry
    return {
        "signal_day": signal_day, "entry_time": entry_time, "exit_time": exit_stamp,
        "stop_kind": stop_kind, "target_kind": target_kind,
        "entry": entry, "stop": stop, "target": target,
        "exit": exit_price, "exit_reason": reason, "gross_return_pct": gross * 100,
        "net_return_pct": net * 100, "risk_pct": risk * 100,
        "gross_R": gross / risk, "net_R": net / risk,
        "entry_fee_bps": entry_fee * 10000, "exit_fee_bps": actual_exit_fee * 10000,
        "stop_slippage_bps": STOP_SLIPPAGE * 10000 if reason == "SL" else 0,
    }, None


def week_bootstrap_diff(daily, reps=BOOTSTRAPS):
    rows = daily.dropna(subset=["next_high"]).copy()
    rows["success"] = rows.next_high > rows.h
    rows["week"] = rows.index.tz_localize(None).to_period("W")
    weekly = rows.groupby("week").apply(lambda g: np.array([
        np.sum(g.loc[g.signal, "success"]), np.sum(g.signal),
        np.sum(g.success), len(g)
    ], dtype=float)).tolist()
    matrix = np.vstack(weekly)
    rng = np.random.default_rng(SEED)
    diffs = np.empty(reps)
    for i in range(reps):
        sample = matrix[rng.integers(0, len(matrix), len(matrix))].sum(axis=0)
        diffs[i] = sample[0] / sample[1] - sample[2] / sample[3]
    point = rows.loc[rows.signal, "success"].mean() - rows.success.mean()
    return point, np.quantile(diffs, [0.025, 0.975]), float(np.mean(diffs <= 0)), int(rows.signal.sum()), int(len(rows))


def week_bootstrap_mean(trades, value_key, reps=BOOTSTRAPS):
    values = pd.DataFrame(trades)
    if values.empty:
        return np.nan, (np.nan, np.nan), np.nan
    values["week"] = pd.to_datetime(values.signal_day, utc=True).dt.tz_localize(None).dt.to_period("W")
    weekly = values.groupby("week")[value_key].apply(lambda s: s.to_numpy()).tolist()
    rng = np.random.default_rng(SEED)
    estimates = np.empty(reps)
    for i in range(reps):
        chosen = rng.integers(0, len(weekly), len(weekly))
        sample = np.concatenate([weekly[j] for j in chosen])
        estimates[i] = sample.mean()
    flat = values[value_key].to_numpy()
    return float(flat.mean()), np.quantile(estimates, [0.025, 0.975]), float(np.mean(estimates > 0))


def summarize(trades, label, exit_fee):
    if not trades:
        return {"stop": label, "exit_fee": exit_fee, "trades": 0}
    df = pd.DataFrame(trades)
    r = df.net_R.to_numpy()
    winners, losers = r[r > 0], r[r < 0]
    mean_r, ci_r, p_positive = week_bootstrap_mean(trades, "net_R")
    mean_pct, ci_pct, _ = week_bootstrap_mean(trades, "net_return_pct")
    return {
        "stop": label, "exit_fee": exit_fee, "trades": len(df),
        "tp_rate": float((df.exit_reason == "TP").mean()),
        "win_rate_net": float((r > 0).mean()), "avg_gross_R": float(df.gross_R.mean()),
        "avg_net_R": mean_r, "net_R_ci_low": float(ci_r[0]), "net_R_ci_high": float(ci_r[1]),
        "bootstrap_probability_mean_net_R_positive": p_positive,
        "total_net_R": float(r.sum()), "profit_factor_net_R": float(winners.sum() / abs(losers.sum())) if len(losers) else np.inf,
        "avg_net_return_pct": mean_pct, "net_return_pct_ci_low": float(ci_pct[0]),
        "net_return_pct_ci_high": float(ci_pct[1]),
        "avg_risk_pct": float(df.risk_pct.mean()),
        "median_risk_pct": float(df.risk_pct.median()),
        "time_exits": int((df.exit_reason == "next_day_close").sum()),
        "stops": int((df.exit_reason == "SL").sum()),
        "targets": int((df.exit_reason == "TP").sum()),
    }


def main():
    minute = load_1m()
    daily = daily_bars(minute)
    signaled = daily[daily.signal]
    rate = (signaled.next_high > signaled.h).mean() if len(signaled) else np.nan
    baseline = (daily.next_high > daily.h).mean()
    diff, diff_ci, diff_boot_p, n_signal, n_days = week_bootstrap_diff(daily)

    results = []
    all_trades = []
    # Main executable strategy compares two structurally motivated stops.
    run_specs = [
        ("prior_high", "signal_high", signaled),
        ("signal_low", "signal_high", signaled),
        ("signal_open", "signal_body", signaled[signaled.c > signaled.o]),
    ]
    for stop_kind, target_kind, eligible in run_specs:
        for exit_fee_name, exit_fee in (("taker", TAKER_FEE), ("maker_target", MAKER_FEE)):
            trades, skips = [], {}
            for signal_day, row in eligible.iterrows():
                trade, skip = trade_one(minute, signal_day, row, stop_kind,
                                        exit_fee, target_kind)
                if trade:
                    trade["cost_case"] = exit_fee_name
                    trades.append(trade)
                    all_trades.append(trade)
                else:
                    skips[skip] = skips.get(skip, 0) + 1
            result = summarize(trades, stop_kind, exit_fee_name)
            result.update({"target_kind": target_kind,
                           "eligible_signals": len(eligible),
                           "signal_days_skipped": len(eligible) - len(trades),
                           "skip_reasons": str(skips)})
            results.append(result)
    pd.DataFrame(all_trades).to_csv(TRADES, index=False)
    result_frame = pd.DataFrame(results)
    result_frame.to_csv(HERE / "pdh_close_continuation_summary.csv", index=False)

    start, end = daily.index[0], daily.index[-1]
    lines = [
        "# 일봉 전일 고점 종가 돌파 후 다음 날 고점 갱신 — BTC 백테스트",
        "",
        f"- UTC 데이터: {start:%Y-%m-%d} ~ {end:%Y-%m-%d}; 완결 일봉 {len(daily):,}개, 전일 고점 돌파 신호 {len(signaled):,}개",
        f"- 신호 정의: 당일 일봉 종가 > 전일 고가. 다음 UTC 일봉 고가가 신호일 고가를 초과하면 신호 성공.",
        f"- 신호 적중률: {rate:.1%}; 같은 구간 무조건 기준율: {baseline:.1%}; 차이 {diff:+.1%} (주 단위 블록 부트스트랩 95% CI {diff_ci[0]:+.1%}~{diff_ci[1]:+.1%}; P(diff>0)={1-diff_boot_p:.3f}). n={n_signal} signals / {n_days} daily outcomes.",
        "- 주의: 일별 신호가 겹치고 시장 구간이 연속되므로 블록 부트스트랩이 단순 이항검정보다 낫지만, 약 2년 단일 자산 결과다.",
        "",
        "## 실행 규칙",
        "",
        "- 신호가 확정된 뒤 다음 날 00:00 UTC의 첫 1분봉 시가에 롱 진입. 해당 시각 봉이 없으면 거래를 생략한다.",
        "- 기준 비교: 목표는 신호일 고가, 손절은 돌파 기준(전일 고가) 또는 신호일 저가.",
        "- 제안 bracket: 신호일이 양봉인 경우만 사용, 다음 일봉 시가 진입, SL=신호일 시가, TP=진입가+(신호일 종가-신호일 시가). 예시 85→86이면 진입 86, SL 85, TP 87.",
        "- 다음 날 1분봉에서 손절/목표를 감시하고, 동봉 양쪽 접촉은 손절 우선. 미도달은 다음 일봉 마감 직전 1분봉 종가 청산.",
        "- 진입 taker 수수료 6bp. 청산은 taker 6bp 또는 목표 체결 시 maker 2bp 가정. 손절 슬리피지 2bp. 실거래 수수료 티어는 별도 반영해야 한다.",
        "",
        "## 손익 결과",
        "",
        "| 손절 | 목표 | 청산 비용 | 신호/체결 | TP 비율 | 순승률 | 평균 순 R (주 블록 95% CI) | 합계 순 R | PF | 평균 순 수익률 (95% CI) | 제외 |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in results:
        lines.append(f"| {row['stop']} | {row['target_kind']} | {row['exit_fee']} | {row['eligible_signals']}/{row['trades']} | {row['tp_rate']:.1%} | {row['win_rate_net']:.1%} | {row['avg_net_R']:.3f} ({row['net_R_ci_low']:.3f}, {row['net_R_ci_high']:.3f}) | {row['total_net_R']:.2f} | {row['profit_factor_net_R']:.3f} | {row['avg_net_return_pct']:.3f}% ({row['net_return_pct_ci_low']:.3f}, {row['net_return_pct_ci_high']:.3f}) | {row['signal_days_skipped']} |")
    lines += [
        "",
        "## 해석",
        "",
        "이 신호가 다음 날 고점을 갱신하는 경향과, 다음 날 시가에 진입해 신호일 고가를 목표로 했을 때 수익이 나는지는 다른 질문이다. 손익표는 목표/손절까지 포함한 이 기계적 실행 규칙만 평가한다. 순 R의 주 단위 블록 부트스트랩 구간이 0을 넘지 않으면 양의 기대값 근거가 없다.",
        "",
        f"재현: `python -m projects.deepcoin_bot.smc_c.pdh_close_continuation`. 체결 내역: `{TRADES.name}`; 요약 CSV: `pdh_close_continuation_summary.csv`.",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("period", start, "to", end, "daily", len(daily), "signals", len(signaled))
    print(f"hit rate {rate:.4f}; baseline {baseline:.4f}; difference {diff:.4f}; week-bootstrap CI {diff_ci}; P(diff>0)={1-diff_boot_p:.4f}")
    print(result_frame.to_string(index=False))
    print("wrote", REPORT, TRADES)


if __name__ == "__main__":
    main()
