"""
backtest/run.py — SMC 시그널 기반 15m 백테스트
사용: python backtest/run.py --all --bar 15m --days 30
"""
import argparse
import json
import sys
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

_BOT_ROOT = str(Path(__file__).resolve().parent.parent)
if _BOT_ROOT not in sys.path:
    sys.path.insert(0, _BOT_ROOT)
os.chdir(_BOT_ROOT)
from smc_engine import get_smc_signal, get_kill_zone

_DC_KLINES = "https://api.deepcoin.com/deepcoin/market/candles"

try:
    import urllib.request
    def _fetch(bar, n=500):
        url = f"{_DC_KLINES}?instId=BTC-USDT-SWAP&bar={bar}&limit={n}"
        r = urllib.request.urlopen(
            urllib.request.Request(url, headers={"Content-Type": "application/json"}),
            timeout=10)
        resp = json.loads(r.read())
        raw = resp.get("data", resp) if isinstance(resp, dict) else resp
        kl = [{"t": int(k[0]), "o": float(k[1]), "h": float(k[2]),
               "l": float(k[3]), "c": float(k[4]), "v": float(k[5])} for k in raw]
        kl.sort(key=lambda x: x["t"])
        return kl
except Exception:
    def _fetch(bar, n=500): return []


def run_backtest(bar="15m", days=30, leverage=10, rr_min=1.5):
    """SMC 시그널 기반 백테스트 실행."""
    # 15m 봉 수 계산: days * 24 * 4 = 15m 봉 수
    bars_per_day = {"15m": 96, "1H": 24, "4H": 6, "1D": 1}
    n_bars = days * bars_per_day.get(bar, 96)
    n_bars = min(n_bars, 1500)  # API 한도

    print(f"[backtest] {bar} {days}일치 데이터 요청 ({n_bars}봉)...")
    kl_15m = _fetch(bar, n_bars)
    kl_1h  = _fetch("1H", min(days * 24, 500))

    if len(kl_15m) < 50:
        return {"error": f"데이터 부족: {len(kl_15m)}봉"}

    print(f"[backtest] {len(kl_15m)}봉 수신. 시그널 스캔 중...")

    trades = []
    i = 40  # 최소 룩백 확보

    while i < len(kl_15m) - 1:
        window  = kl_15m[:i+1]
        h1_window = [k for k in kl_1h if k["t"] <= kl_15m[i]["t"]][-30:] if kl_1h else None
        sig = get_smc_signal(window, h1_kl=h1_window)

        if sig.get("signal") in ("long", "short"):
            entry = kl_15m[i]["c"]
            sl    = sig["sl"]
            tp1   = sig["tp1"]

            if not sl or not tp1:
                i += 1
                continue

            direction = sig["signal"]
            # 이후 봉에서 SL 또는 TP 도달 확인 (최대 40봉 대기)
            result = None
            exit_price = None
            exit_i = None

            for j in range(i+1, min(i+41, len(kl_15m))):
                k = kl_15m[j]
                if direction == "long":
                    if k["l"] <= sl:
                        result = "SL"; exit_price = sl; exit_i = j; break
                    if k["h"] >= tp1:
                        result = "TP1"; exit_price = tp1; exit_i = j; break
                else:
                    if k["h"] >= sl:
                        result = "SL"; exit_price = sl; exit_i = j; break
                    if k["l"] <= tp1:
                        result = "TP1"; exit_price = tp1; exit_i = j; break

            if result is None:
                result = "TIMEOUT"; exit_price = kl_15m[min(i+40, len(kl_15m)-1)]["c"]
                exit_i = min(i+40, len(kl_15m)-1)

            if direction == "long":
                pnl_pct = (exit_price - entry) / entry * 100 * leverage
            else:
                pnl_pct = (entry - exit_price) / entry * 100 * leverage

            dt_utc = datetime.fromtimestamp(kl_15m[i]["t"] / 1000, tz=timezone.utc)
            kz = get_kill_zone(dt_utc)

            trades.append({
                "i": i,
                "time": dt_utc.strftime("%Y-%m-%d %H:%M"),
                "direction": direction,
                "entry": round(entry, 1),
                "sl": sl, "tp1": tp1,
                "result": result,
                "exit_price": round(exit_price, 1),
                "pnl_pct": round(pnl_pct, 2),
                "killzone": kz or "off",
                "reason": sig.get("reason", "")[:60],
            })
            i = exit_i + 1  # 청산 봉 이후부터 재스캔
        else:
            i += 1

    return _summarize(trades, bar, days)


def _summarize(trades, bar, days):
    if not trades:
        return {"error": "시그널 없음", "trades": 0}

    wins   = [t for t in trades if t["pnl_pct"] > 0]
    losses = [t for t in trades if t["pnl_pct"] <= 0]
    total_pnl = sum(t["pnl_pct"] for t in trades)
    win_rate  = len(wins) / len(trades) * 100

    # 킬존별 집계
    kz_stats = {}
    for t in trades:
        kz = t["killzone"]
        if kz not in kz_stats:
            kz_stats[kz] = {"trades": 0, "wins": 0, "pnl": 0.0}
        kz_stats[kz]["trades"] += 1
        if t["pnl_pct"] > 0:
            kz_stats[kz]["wins"] += 1
        kz_stats[kz]["pnl"] = round(kz_stats[kz]["pnl"] + t["pnl_pct"], 2)

    # 방향별 집계
    long_trades  = [t for t in trades if t["direction"] == "long"]
    short_trades = [t for t in trades if t["direction"] == "short"]

    # 최대 드로우다운 (연속 손실)
    max_dd = 0.0
    cur_dd = 0.0
    for t in trades:
        if t["pnl_pct"] < 0:
            cur_dd += t["pnl_pct"]
            max_dd = min(max_dd, cur_dd)
        else:
            cur_dd = 0.0

    return {
        "bar": bar, "days": days,
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 1),
        "total_pnl_pct": round(total_pnl, 2),
        "avg_win_pct":  round(sum(t["pnl_pct"] for t in wins)  / len(wins),  2) if wins   else 0,
        "avg_loss_pct": round(sum(t["pnl_pct"] for t in losses) / len(losses), 2) if losses else 0,
        "max_drawdown_pct": round(max_dd, 2),
        "long_trades":  len(long_trades),
        "short_trades": len(short_trades),
        "long_win_rate":  round(sum(1 for t in long_trades  if t["pnl_pct"] > 0) / len(long_trades)  * 100, 1) if long_trades  else 0,
        "short_win_rate": round(sum(1 for t in short_trades if t["pnl_pct"] > 0) / len(short_trades) * 100, 1) if short_trades else 0,
        "killzone_stats": kz_stats,
        "last_10_trades": trades[-10:],
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def main():
    parser = argparse.ArgumentParser(description="딥코인봇 SMC 백테스트")
    parser.add_argument("--bar",  default="15m",  help="캔들 타임프레임 (default: 15m)")
    parser.add_argument("--days", default=30, type=int, help="백테스트 기간 (일)")
    parser.add_argument("--all",  action="store_true", help="전체 분석 모드")
    args = parser.parse_args()

    result = run_backtest(bar=args.bar, days=args.days)

    if "error" in result:
        print(f"[ERROR] {result['error']}")
        return

    print("\n" + "="*55)
    print(f"SMC 백테스트 결과 ({result['bar']} / {result['days']}일)")
    print("="*55)
    print(f"총 거래:    {result['total_trades']}회  (롱 {result['long_trades']} / 숏 {result['short_trades']})")
    print(f"승률:       {result['win_rate']}%  (롱 {result['long_win_rate']}% / 숏 {result['short_win_rate']}%)")
    print(f"총 PnL:     {result['total_pnl_pct']:+.2f}%")
    print(f"평균 수익:  {result['avg_win_pct']:+.2f}%  |  평균 손실: {result['avg_loss_pct']:+.2f}%")
    print(f"최대 드로우다운: {result['max_drawdown_pct']:+.2f}%")
    print("\n킬존별 성과:")
    for kz, s in result["killzone_stats"].items():
        wr = round(s["wins"] / s["trades"] * 100) if s["trades"] else 0
        print(f"  {kz:<10} {s['trades']:>3}거래  승률 {wr:>3}%  PnL {s['pnl']:>+7.2f}%")

    # JSON 저장
    out = Path(__file__).parent / "backtest_result.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[저장] {out}")


if __name__ == "__main__":
    main()
