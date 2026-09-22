"""
engine.py — 백테스팅 엔진
캔들 단위로 전략 시그널 확인 → 포지션 진입/청산 시뮬레이션
"""


def run_backtest(strategy, kl_all, h1_all=None, d1_all=None,
                 initial_balance=1000.0, risk_pct=1.0, leverage=10):
    """
    백테스팅 엔진
    - 각 캔들 시점에서 strategy.signal() 호출
    - 신호 발생 시 포지션 진입 (포지션 크기 = balance * risk_pct% / sl_distance_pct)
    - 이후 캔들에서 SL/TP 도달 여부 확인 → 청산
    반환: {"trades": [...], "equity_curve": [...], "summary": {...}}
    """
    balance      = initial_balance
    trades       = []
    equity_curve = [balance]
    open_pos     = None   # {"direction", "entry", "sl", "tp1", "tp2", "size", "pattern_key", "reason", "open_idx"}

    # MTF 슬라이싱용 타임스탬프 인덱스 빌드
    h1_ts_map = {k["t"]: i for i, k in enumerate(h1_all)} if h1_all else {}
    d1_ts_map = {k["t"]: i for i, k in enumerate(d1_all)} if d1_all else {}

    def _slice_mtf(ts_map, all_kl, current_t, window=50):
        """current_t 이전 캔들들 슬라이스"""
        if not ts_map or not all_kl:
            return None
        idx = None
        for ts, i in ts_map.items():
            if ts <= current_t:
                idx = i
        if idx is None:
            return None
        return all_kl[max(0, idx - window + 1): idx + 1]

    warmup = 30   # 스윙 탐지에 필요한 최소 캔들

    for i in range(warmup, len(kl_all)):
        kl_window = kl_all[max(0, i - 100): i + 1]
        current   = kl_all[i]
        price     = current["c"]
        high      = current["h"]
        low       = current["l"]

        # ── 오픈 포지션 청산 확인 ──────────────────────────────────
        if open_pos:
            d = open_pos["direction"]
            sl  = open_pos["sl"]
            tp1 = open_pos["tp1"]
            entry = open_pos["entry"]
            size  = open_pos["size"]

            closed = False
            exit_price = None
            exit_reason = ""

            if d == "long":
                if low <= sl:
                    exit_price  = sl
                    exit_reason = "SL"
                    closed      = True
                elif high >= tp1:
                    exit_price  = tp1
                    exit_reason = "TP1"
                    closed      = True
            else:  # short
                if high >= sl:
                    exit_price  = sl
                    exit_reason = "SL"
                    closed      = True
                elif low <= tp1:
                    exit_price  = tp1
                    exit_reason = "TP1"
                    closed      = True

            if closed:
                if d == "long":
                    pnl = (exit_price - entry) / entry * size * leverage
                else:
                    pnl = (entry - exit_price) / entry * size * leverage

                balance += pnl
                trades.append({
                    "open_idx":    open_pos["open_idx"],
                    "close_idx":   i,
                    "direction":   d,
                    "entry":       entry,
                    "exit":        exit_price,
                    "exit_reason": exit_reason,
                    "sl":          sl,
                    "tp1":         tp1,
                    "size":        size,
                    "pnl":         round(pnl, 4),
                    "pattern_key": open_pos["pattern_key"],
                    "reason":      open_pos["reason"],
                    "open_t":      kl_all[open_pos["open_idx"]]["t"],
                    "close_t":     current["t"],
                })
                equity_curve.append(round(balance, 4))
                open_pos = None

        # ── 신규 시그널 탐색 (포지션 없을 때만) ────────────────────
        if open_pos is None:
            h1_win = _slice_mtf(h1_ts_map, h1_all, current["t"])
            d1_win = _slice_mtf(d1_ts_map, d1_all, current["t"])

            sig = strategy.signal(kl_window, h1_kl=h1_win, d1_kl=d1_win)
            if sig:
                sl_dist_pct = abs(price - sig.sl) / price
                if sl_dist_pct > 0:
                    # 포지션 크기: balance의 risk_pct%를 sl_distance에 맞춰 조정
                    risk_amount = balance * (risk_pct / 100)
                    size = risk_amount / sl_dist_pct
                    open_pos = {
                        "direction":   sig.direction,
                        "entry":       price,
                        "sl":          sig.sl,
                        "tp1":         sig.tp1,
                        "tp2":         sig.tp2,
                        "size":        round(size, 4),
                        "pattern_key": sig.pattern_key,
                        "reason":      sig.reason,
                        "open_idx":    i,
                    }

    # 미청산 포지션 마지막 가격으로 강제 청산
    if open_pos and kl_all:
        last = kl_all[-1]
        d    = open_pos["direction"]
        exit_price = last["c"]
        entry = open_pos["entry"]
        size  = open_pos["size"]
        if d == "long":
            pnl = (exit_price - entry) / entry * size * leverage
        else:
            pnl = (entry - exit_price) / entry * size * leverage
        balance += pnl
        trades.append({
            "open_idx":    open_pos["open_idx"],
            "close_idx":   len(kl_all) - 1,
            "direction":   d,
            "entry":       entry,
            "exit":        exit_price,
            "exit_reason": "FORCE_CLOSE",
            "sl":          open_pos["sl"],
            "tp1":         open_pos["tp1"],
            "size":        size,
            "pnl":         round(pnl, 4),
            "pattern_key": open_pos["pattern_key"],
            "reason":      open_pos["reason"],
            "open_t":      kl_all[open_pos["open_idx"]]["t"],
            "close_t":     last["t"],
        })
        equity_curve.append(round(balance, 4))

    total_pnl  = balance - initial_balance
    peak       = initial_balance
    max_dd     = 0.0
    running    = initial_balance
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100
        if dd > max_dd:
            max_dd = dd

    summary = {
        "strategy":        strategy.name,
        "initial_balance": initial_balance,
        "final_balance":   round(balance, 4),
        "total_pnl":       round(total_pnl, 4),
        "total_return_pct": round(total_pnl / initial_balance * 100, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "total_candles":   len(kl_all),
        "trade_count":     len(trades),
    }

    return {
        "trades":       trades,
        "equity_curve": equity_curve,
        "summary":      summary,
    }
