"""
engine.py — 백테스팅 엔진
캔들 단위로 전략 시그널 확인 → 포지션 진입/청산 시뮬레이션
"""


def _atr14(kl):
    """server.py의 _ind()와 동일한 ATR(14) 계산 — 백테스트 SL이 라이브와 같은 폭을 쓰도록 공유."""
    if len(kl) < 15:
        return 0.0
    hi = [k["h"] for k in kl]; lo = [k["l"] for k in kl]; cl = [k["c"] for k in kl]
    tr = [max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1]))
          for i in range(1, len(kl))]
    return sum(tr[-14:]) / 14


def run_backtest(strategy, kl_all, h1_all=None, d1_all=None, m5_all=None,
                 initial_balance=1000.0, risk_pct=1.0, leverage=10,
                 use_weights=True, sym="", tp_min_pct=0.0, rr_min=1.5,
                 sl_min_atr_mult=0.8, sl_cap_pct=None,
                 m15_confirm_n=0, require_h1_trend=True):
    """
    백테스팅 엔진
    - 각 캔들 시점에서 strategy.signal() 호출
    - 신호 발생 시 포지션 진입 (포지션 크기 = balance * risk_pct% / sl_distance_pct)
    - 이후 캔들에서 SL/TP 도달 여부 확인 → 청산

    sl_min_atr_mult, sl_cap_pct: server.py _run_claude_bot의 SL 폭 규칙과 동일하게
    맞춘 것. 실제 청산에 쓰는 SL은 전략이 찾은 구조 레벨(sig.sl)이 아니라
    max(구조거리, ATR(14)×sl_min_atr_mult, 0.3%) 를 sl_cap_pct로 자른 값이다 —
    라이브와 다른 SL을 쓰면 백테스트 숫자가 실거래를 대표하지 못한다(2026-09-25 확인된 문제).

    m15_confirm_n, require_h1_trend: ict_engine.py의 전략 함수에 그대로 전달하는 비교용
    파라미터(2026-10-01 B안 백테스트). 기본값은 라이브(server.py)와 동일 동작.
    반환: {"trades": [...], "equity_curve": [...], "summary": {...}}
    """
    balance      = initial_balance
    trades       = []
    equity_curve = [balance]
    open_pos     = None   # {"direction", "entry", "sl", "tp1", "tp2", "size", "pattern_key", "reason", "open_idx"}

    from weights import get_weight

    # MTF 슬라이싱용 타임스탬프 인덱스 빌드
    h1_ts_map = {k["t"]: i for i, k in enumerate(h1_all)} if h1_all else {}
    d1_ts_map = {k["t"]: i for i, k in enumerate(d1_all)} if d1_all else {}
    m5_ts_map = {k["t"]: i for i, k in enumerate(m5_all)} if m5_all else {}

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
            m5_win = _slice_mtf(m5_ts_map, m5_all, current["t"], window=20)

            sig = strategy.signal(kl_window, h1_kl=h1_win, d1_kl=d1_win, m5_kl=m5_win,
                                  m15_confirm_n=m15_confirm_n, require_h1_trend=require_h1_trend)
            if sig:
                # TP 최소 거리 필터
                _tp_dist = (sig.tp1 - price) / price if sig.direction == "long" else (price - sig.tp1) / price
                if tp_min_pct > 0 and _tp_dist < tp_min_pct / 100:
                    continue

                # ── SL 폭: 구조 레벨 vs ATR 최소폭 vs 상한 — 라이브와 동일 규칙 ──
                raw_sl_dist = abs(price - sig.sl) / price
                atr = _atr14(kl_window)
                sl_min = max(atr / price * sl_min_atr_mult, 0.003) if price else 0.003
                sl_dist_pct = max(raw_sl_dist, sl_min)
                if sl_cap_pct is not None:
                    sl_dist_pct = min(sl_dist_pct, sl_cap_pct / 100)
                if sl_dist_pct <= 0:
                    continue
                effective_sl = (price * (1 - sl_dist_pct) if sig.direction == "long"
                                else price * (1 + sl_dist_pct))

                # RR 최소 필터 재검증 — 실제로 쓸 SL 폭 기준으로 (구조 레벨 기준이면 과대평가됨)
                if _tp_dist / sl_dist_pct < rr_min:
                    continue

                # 가중치 기반 포지션 크기 조정
                wkey = f"{sig.pattern_key}_{sym.split('-')[0]}" if sym else sig.pattern_key
                weight = get_weight(wkey) if use_weights else 1.0
                # 리스크 = balance * risk_pct% (레버리지 포함 실제 손실 기준)
                risk_amount = balance * (risk_pct / 100) * weight
                size = min(risk_amount / (sl_dist_pct * leverage), balance)  # 레버리지 보정, 잔고 초과 금지
                open_pos = {
                    "direction":   sig.direction,
                    "entry":       price,
                    "sl":          effective_sl,
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
