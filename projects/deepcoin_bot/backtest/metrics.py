"""
metrics.py — 백테스팅 성과 지표 계산
"""

import math


def calc_metrics(trades):
    """
    trades: list of {"pnl": float, "direction": str, "pattern_key": str, ...}
    반환: {
        "total_trades", "win_rate", "profit_factor",
        "avg_rr", "max_drawdown", "sharpe",
        "by_pattern": {pattern_key: {"trades", "wins", "win_rate", "total_pnl"}}
    }
    """
    if not trades:
        return {
            "total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
            "avg_rr": 0.0, "max_drawdown": 0.0, "sharpe": 0.0,
            "by_pattern": {},
        }

    wins        = [t for t in trades if t["pnl"] > 0]
    losses      = [t for t in trades if t["pnl"] <= 0]
    total       = len(trades)
    win_rate    = len(wins) / total * 100

    gross_profit = sum(t["pnl"] for t in wins)
    gross_loss   = abs(sum(t["pnl"] for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # avg RR: avg_win / avg_loss (절대값 기준)
    avg_win  = gross_profit / len(wins)  if wins   else 0.0
    avg_loss = gross_loss   / len(losses) if losses else 0.0
    avg_rr   = avg_win / avg_loss if avg_loss > 0 else 0.0

    # Max Drawdown (누적 PnL 기준)
    cumulative = 0.0
    peak       = 0.0
    max_dd     = 0.0
    for t in trades:
        cumulative += t["pnl"]
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd

    # Sharpe (일별 수익률 기준 간이 계산)
    pnls = [t["pnl"] for t in trades]
    mean_pnl = sum(pnls) / total
    variance = sum((p - mean_pnl) ** 2 for p in pnls) / total
    std_pnl  = math.sqrt(variance) if variance > 0 else 0.0
    sharpe   = (mean_pnl / std_pnl * math.sqrt(total)) if std_pnl > 0 else 0.0

    # by_pattern
    by_pattern = {}
    for t in trades:
        pk = t.get("pattern_key", "unknown")
        if pk not in by_pattern:
            by_pattern[pk] = {"trades": 0, "wins": 0, "total_pnl": 0.0}
        by_pattern[pk]["trades"]    += 1
        by_pattern[pk]["total_pnl"] += t["pnl"]
        if t["pnl"] > 0:
            by_pattern[pk]["wins"] += 1
    for pk, v in by_pattern.items():
        v["win_rate"]  = round(v["wins"] / v["trades"] * 100, 1) if v["trades"] else 0.0
        v["total_pnl"] = round(v["total_pnl"], 4)

    return {
        "total_trades":  total,
        "win_rate":      round(win_rate, 1),
        "profit_factor": round(profit_factor, 3),
        "avg_rr":        round(avg_rr, 3),
        "max_drawdown":  round(max_dd, 4),
        "sharpe":        round(sharpe, 3),
        "by_pattern":    by_pattern,
    }
