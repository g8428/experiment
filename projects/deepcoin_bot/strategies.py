"""
strategies.py — 추가 매매 전략 모음
server.py에서 SMC 외 다중 전략으로 진입 기회 확대

전략 목록:
  1. ema_cross   — EMA9/21 크로스오버 (추세장 최적)
  2. bb_reversion — 볼린저밴드 평균회귀 (횡보장 최적)
  3. asian_breakout — 아시안레인지 브레이크아웃 (런던/뉴욕 오픈 최적)

공통 반환 형식:
  {
    "signal": "long" | "short" | None,
    "sl": <float>,
    "tp": <float>,
    "reason": <str>,
    "confidence": "high" | "medium" | "low",
    "strategy": <str>
  }
"""


def _ema(cl, n):
    if len(cl) < n:
        return cl[-1] if cl else 0.0
    k = 2.0 / (n + 1)
    e = sum(cl[:n]) / n
    for p in cl[n:]:
        e = p * k + e * (1 - k)
    return e


def _atr(kl, n=14):
    if len(kl) < n + 1:
        return 0.0
    tr_list = [
        max(kl[i]["h"] - kl[i]["l"],
            abs(kl[i]["h"] - kl[i - 1]["c"]),
            abs(kl[i]["l"] - kl[i - 1]["c"]))
        for i in range(1, len(kl))
    ]
    return sum(tr_list[-n:]) / n


def _rsi(cl, n=14):
    if len(cl) < n + 1:
        return 50.0
    d = [cl[i] - cl[i - 1] for i in range(1, len(cl))]
    g = sum(max(x, 0) for x in d[-n:]) / n
    l = sum(max(-x, 0) for x in d[-n:]) / n
    return round(100.0 if l == 0 else 100 - 100 / (1 + g / l), 2)


# ── 1. EMA 크로스오버 전략 ─────────────────────────────────────────
def ema_cross_signal(kl_15m, tp_atr=2.5, sl_atr=1.0):
    """
    EMA9가 EMA21을 크로스할 때 진입.
    - 골든크로스 (9 > 21) + 직전 캔들은 9 < 21 → 롱
    - 데드크로스 (9 < 21) + 직전 캔들은 9 > 21 → 숏
    조건: RSI 35~65 구간 (과매수/과매도 제외), 거래량 MA 이상

    Args:
        kl_15m: 15분봉 캔들 리스트 [{"t","o","h","l","c","v"}, ...]
        tp_atr: TP = ATR × tp_atr
        sl_atr: SL = ATR × sl_atr
    """
    if len(kl_15m) < 25:
        return {"signal": None, "reason": "EMA크로스: 데이터 부족", "strategy": "ema_cross"}

    cl    = [k["c"] for k in kl_15m]
    price = cl[-1]
    atr   = _atr(kl_15m, 14)
    rsi   = _rsi(cl, 14)

    # 현재 vs 직전 EMA 상태
    e9_now  = _ema(cl,  9)
    e21_now = _ema(cl, 21)
    e9_prev  = _ema(cl[:-1],  9)
    e21_prev = _ema(cl[:-1], 21)

    vol_ma  = sum(k["v"] for k in kl_15m[-20:]) / 20
    vol_now = kl_15m[-1]["v"]

    signal = None
    reason = ""

    # 골든크로스
    if e9_prev <= e21_prev and e9_now > e21_now:
        if 30 < rsi < 65 and vol_now >= vol_ma * 0.8:
            signal = "long"
            reason = (f"EMA골든크로스 EMA9={e9_now:.0f}>EMA21={e21_now:.0f} "
                      f"RSI={rsi:.1f} Vol={vol_now/vol_ma:.1f}x")
        else:
            reason = f"EMA골든크로스 스킵 (RSI={rsi:.1f} or 거래량 부족)"

    # 데드크로스
    elif e9_prev >= e21_prev and e9_now < e21_now:
        if 35 < rsi < 70 and vol_now >= vol_ma * 0.8:
            signal = "short"
            reason = (f"EMA데드크로스 EMA9={e9_now:.0f}<EMA21={e21_now:.0f} "
                      f"RSI={rsi:.1f} Vol={vol_now/vol_ma:.1f}x")
        else:
            reason = f"EMA데드크로스 스킵 (RSI={rsi:.1f} or 거래량 부족)"
    else:
        reason = f"EMA크로스 없음 (EMA9={e9_now:.0f} EMA21={e21_now:.0f})"

    if not signal:
        return {"signal": None, "reason": reason, "strategy": "ema_cross"}

    tp = round(price * (1 + tp_atr * atr / price) if signal == "long"
               else price * (1 - tp_atr * atr / price), 1)
    sl = round(price * (1 - sl_atr * atr / price) if signal == "long"
               else price * (1 + sl_atr * atr / price), 1)

    return {
        "signal":     signal,
        "sl":         sl,
        "tp":         tp,
        "reason":     reason,
        "confidence": "medium",
        "strategy":   "ema_cross",
    }


# ── 2. 볼린저밴드 평균회귀 전략 ──────────────────────────────────────
def bb_reversion_signal(kl_15m, tp_atr=1.8, sl_atr=0.8):
    """
    BB 하단 터치 + RSI 과매도 → 롱
    BB 상단 터치 + RSI 과매수 → 숏
    TP는 BB 중간선, SL은 밴드 바깥

    Args:
        kl_15m: 15분봉 캔들
        tp_atr: TP ATR 배수
        sl_atr: SL ATR 배수
    """
    if len(kl_15m) < 22:
        return {"signal": None, "reason": "BB평균회귀: 데이터 부족", "strategy": "bb_reversion"}

    cl    = [k["c"] for k in kl_15m]
    price = cl[-1]
    atr   = _atr(kl_15m, 14)
    rsi   = _rsi(cl, 14)

    bb20 = cl[-20:]
    bm   = sum(bb20) / 20
    bstd = (sum((x - bm) ** 2 for x in bb20) / 20) ** 0.5
    bb_upper = bm + 2.0 * bstd
    bb_lower = bm - 2.0 * bstd

    signal = None
    reason = ""
    confidence = "low"

    # 롱 조건: 가격이 BB 하단 아래 or 터치 + RSI 과매도
    if price <= bb_lower * 1.002 and rsi < 32:
        signal = "long"
        confidence = "high" if rsi < 25 else "medium"
        reason = (f"BB하단터치({price:.0f}<={bb_lower:.0f}) + RSI과매도({rsi:.1f}) "
                  f"TP=BB중간({bm:.0f})")
        tp = round(bm, 1)  # TP = BB 중간선
        sl = round(price * (1 - sl_atr * atr / price), 1)

    # 숏 조건: 가격이 BB 상단 위 or 터치 + RSI 과매수
    elif price >= bb_upper * 0.998 and rsi > 68:
        signal = "short"
        confidence = "high" if rsi > 75 else "medium"
        reason = (f"BB상단터치({price:.0f}>={bb_upper:.0f}) + RSI과매수({rsi:.1f}) "
                  f"TP=BB중간({bm:.0f})")
        tp = round(bm, 1)
        sl = round(price * (1 + sl_atr * atr / price), 1)

    else:
        return {"signal": None,
                "reason": f"BB평균회귀 대기 (BB:{bb_lower:.0f}~{bb_upper:.0f} RSI:{rsi:.1f})",
                "strategy": "bb_reversion"}

    return {
        "signal":     signal,
        "sl":         sl,
        "tp":         tp,
        "reason":     reason,
        "confidence": confidence,
        "strategy":   "bb_reversion",
    }


# ── 3. 아시안 레인지 브레이크아웃 전략 ───────────────────────────────
def asian_breakout_signal(kl_15m, asian_high, asian_low, tp_atr=3.0, sl_atr=1.2):
    """
    아시안 세션(00~09 KST) 고/저 돌파 시 진입.
    런던(16KST~) / 뉴욕(22KST~) 오픈 직후 효과적.

    Args:
        kl_15m: 15분봉 캔들
        asian_high: 아시안 세션 최고가
        asian_low:  아시안 세션 최저가
        tp_atr: TP ATR 배수
        sl_atr: SL ATR 배수
    """
    if not asian_high or not asian_low or len(kl_15m) < 20:
        return {"signal": None, "reason": "아시안브레이크: 데이터 부족", "strategy": "asian_breakout"}

    cl    = [k["c"] for k in kl_15m]
    price = cl[-1]
    prev  = cl[-2]  # 직전 캔들 종가
    atr   = _atr(kl_15m, 14)
    rsi   = _rsi(cl, 14)

    range_size = asian_high - asian_low
    if range_size < atr * 0.5:
        return {"signal": None,
                "reason": f"아시안레인지 너무 좁음 ({range_size:.0f} < ATR×0.5={atr*0.5:.0f})",
                "strategy": "asian_breakout"}

    signal = None
    reason = ""

    # 상향 돌파: 직전 캔들이 레인지 내 → 현재 캔들이 고점 돌파
    if prev <= asian_high and price > asian_high * 1.001 and rsi < 70:
        signal = "long"
        reason = (f"아시안고점돌파 ${asian_high:,.0f} 브레이크아웃 "
                  f"(레인지=${range_size:.0f}) RSI={rsi:.1f}")

    # 하향 돌파: 직전 캔들이 레인지 내 → 현재 캔들이 저점 돌파
    elif prev >= asian_low and price < asian_low * 0.999 and rsi > 30:
        signal = "short"
        reason = (f"아시안저점돌파 ${asian_low:,.0f} 브레이크아웃 "
                  f"(레인지=${range_size:.0f}) RSI={rsi:.1f}")

    if not signal:
        return {"signal": None,
                "reason": f"아시안브레이크 대기 ({asian_low:.0f}~{asian_high:.0f})",
                "strategy": "asian_breakout"}

    tp = round(price * (1 + tp_atr * atr / price) if signal == "long"
               else price * (1 - tp_atr * atr / price), 1)
    sl = round(price * (1 - sl_atr * atr / price) if signal == "long"
               else price * (1 + sl_atr * atr / price), 1)

    return {
        "signal":     signal,
        "sl":         sl,
        "tp":         tp,
        "reason":     reason,
        "confidence": "medium",
        "strategy":   "asian_breakout",
    }


# ── EMA200 추세 필터 ───────────────────────────────────────────────
def ema200_filter(kl_1h):
    """
    1시간봉 EMA200 기준 추세 방향 반환.
    Returns: "bull" (롱 허용), "bear" (숏 허용), "neutral"
    """
    if len(kl_1h) < 50:
        return "neutral"
    cl = [k["c"] for k in kl_1h]
    n  = min(200, len(cl))
    e200 = _ema(cl, n)
    price = cl[-1]
    margin = e200 * 0.003  # 0.3% 버퍼
    if price > e200 + margin:
        return "bull"
    elif price < e200 - margin:
        return "bear"
    return "neutral"


# ── 멀티전략 통합 평가 ─────────────────────────────────────────────
def get_best_signal(kl_15m, kl_1h=None, asian_high=None, asian_low=None, tuning=None):
    """
    활성화된 전략들을 모두 평가해서 가장 신뢰도 높은 시그널 반환.
    SMC 시그널이 이미 있으면 이 함수는 호출하지 않아도 됨.

    Returns: signal dict 또는 None
    """
    if tuning is None:
        tuning = {}

    enabled   = tuning.get("enabled_strategies", ["ema_cross", "bb_reversion", "asian_breakout"])
    trend     = ema200_filter(kl_1h) if kl_1h else "neutral"

    candidates = []

    if "ema_cross" in enabled:
        sig = ema_cross_signal(kl_15m,
                               tp_atr=tuning.get("ema_cross_tp_atr", 2.5),
                               sl_atr=tuning.get("ema_cross_sl_atr", 1.0))
        if sig["signal"]:
            candidates.append(sig)

    if "bb_reversion" in enabled:
        sig = bb_reversion_signal(kl_15m,
                                  tp_atr=tuning.get("bb_rev_tp_atr", 1.8),
                                  sl_atr=tuning.get("bb_rev_sl_atr", 0.8))
        if sig["signal"]:
            candidates.append(sig)

    if "asian_breakout" in enabled and asian_high and asian_low:
        sig = asian_breakout_signal(kl_15m, asian_high, asian_low,
                                    tp_atr=tuning.get("asian_break_tp_atr", 3.0),
                                    sl_atr=tuning.get("asian_break_sl_atr", 1.2))
        if sig["signal"]:
            candidates.append(sig)

    if not candidates:
        return None

    # EMA200 추세 필터: 추세 반대 방향 시그널 제거
    if trend == "bull":
        candidates = [c for c in candidates if c["signal"] == "long"] or candidates
    elif trend == "bear":
        candidates = [c for c in candidates if c["signal"] == "short"] or candidates

    # 신뢰도 우선순위: high > medium > low
    priority = {"high": 3, "medium": 2, "low": 1}
    candidates.sort(key=lambda x: priority.get(x.get("confidence", "low"), 0), reverse=True)

    best = candidates[0]
    best["trend_filter"] = trend
    return best


if __name__ == "__main__":
    # 간단 테스트
    import json
    # 더미 캔들 생성
    import random, time
    base = 70000
    kl = []
    t = int(time.time() * 1000) - 100 * 900000
    for i in range(100):
        o = base + random.gauss(0, 200)
        h = o + abs(random.gauss(0, 100))
        l = o - abs(random.gauss(0, 100))
        c = l + random.random() * (h - l)
        kl.append({"t": t, "o": round(o, 1), "h": round(h, 1),
                   "l": round(l, 1), "c": round(c, 1), "v": round(random.uniform(10, 80), 1)})
        t += 900000
        base = c

    print("=== 전략 테스트 ===")
    print("EMA크로스:", ema_cross_signal(kl))
    print("BB평균회귀:", bb_reversion_signal(kl))
    print("EMA200필터:", ema200_filter(kl))
    print("통합시그널:", get_best_signal(kl, kl))
