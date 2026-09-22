"""
ict_engine.py — ICT (Inner Circle Trader) 분석 엔진
smc_engine.py의 모든 함수 재활용 + ICT 전용 기능 추가:
  Premium/Discount/OTE/Breaker Block/NDOG
"""

from smc_engine import *


def get_premium_discount(range_high, range_low, price):
    """Premium/Discount/Equilibrium 판별
    반환: {"zone": "premium"|"discount"|"equilibrium", "eq": float, "pct": float}
    """
    if range_high == range_low:
        return {"zone": "equilibrium", "eq": range_high, "pct": 50.0}
    rng = range_high - range_low
    eq = range_low + rng * 0.5
    pct = (price - range_low) / rng * 100
    if pct > 55:
        zone = "premium"
    elif pct < 45:
        zone = "discount"
    else:
        zone = "equilibrium"
    return {"zone": zone, "eq": round(eq, 2), "pct": round(pct, 2)}


def get_ote(swing_low, swing_high, direction="bullish"):
    """OTE (Optimal Trade Entry) zone — 0.618~0.786 피보나치 되돌림
    반환: {"low": float, "high": float, "mid": float}
    """
    rng = swing_high - swing_low
    if direction == "bullish":
        # 상승 이후 되돌림 → 매수 구간 (낮은 쪽이 진입)
        ote_low  = round(swing_high - rng * 0.786, 2)
        ote_high = round(swing_high - rng * 0.618, 2)
    else:
        # 하락 이후 되돌림 → 매도 구간 (높은 쪽이 진입)
        ote_low  = round(swing_low + rng * 0.618, 2)
        ote_high = round(swing_low + rng * 0.786, 2)
    ote_mid = round((ote_low + ote_high) / 2, 2)
    return {"low": ote_low, "high": ote_high, "mid": ote_mid}


def find_breaker_blocks(kl, highs, lows, lookback=40):
    """Breaker Block 탐지 — 실패한 OB가 반대 POI로 전환
    Bullish Breaker: Bearish OB였으나 가격이 위로 돌파 → 지지 구간
    Bearish Breaker: Bullish OB였으나 가격이 아래로 돌파 → 저항 구간
    반환: (bull_breakers, bear_breakers)
    """
    price   = kl[-1]["c"]
    min_idx = max(0, len(kl) - lookback)
    bull_breakers = []
    bear_breakers = []

    # Bullish Breaker: Bearish OB (스윙 고점 직전 양봉) 위로 현재가 돌파한 경우
    for sh in sorted(highs, key=lambda x: x["i"], reverse=True)[:3]:
        idx = sh["i"]
        if idx < min_idx:
            continue
        for j in range(idx - 1, max(min_idx, idx - 8), -1):
            if kl[j]["c"] > kl[j]["o"]:  # 양봉 (Bearish OB 후보)
                ob_top = kl[j]["h"]
                ob_bot = kl[j]["c"]
                ob_mid = (ob_top + ob_bot) / 2
                # 현재가가 OB 상단을 넘어섰으면 → Bullish Breaker (지지)
                if price > ob_top:
                    bull_breakers.append({
                        "top": round(ob_top, 2),
                        "bot": round(ob_bot, 2),
                        "mid": round(ob_mid, 2),
                    })
                break

    # Bearish Breaker: Bullish OB (스윙 저점 직전 음봉) 아래로 현재가 돌파한 경우
    for sl in sorted(lows, key=lambda x: x["i"], reverse=True)[:3]:
        idx = sl["i"]
        if idx < min_idx:
            continue
        for j in range(idx - 1, max(min_idx, idx - 8), -1):
            if kl[j]["c"] < kl[j]["o"]:  # 음봉 (Bullish OB 후보)
                ob_top = kl[j]["o"]
                ob_bot = kl[j]["l"]
                ob_mid = (ob_top + ob_bot) / 2
                # 현재가가 OB 하단 아래로 돌파했으면 → Bearish Breaker (저항)
                if price < ob_bot:
                    bear_breakers.append({
                        "top": round(ob_top, 2),
                        "bot": round(ob_bot, 2),
                        "mid": round(ob_mid, 2),
                    })
                break

    return bull_breakers, bear_breakers


def get_ndog(kl_1h):
    """New Day Opening Gap (NDOG)
    오늘 첫 캔들 open vs 어제 마지막 캔들 close 사이의 갭
    반환: {"gap": float, "direction": "up"|"down"|None, "today_open": float, "prev_close": float} or None
    """
    if not kl_1h or len(kl_1h) < 2:
        return None

    from datetime import datetime, timezone

    today_open_candle = None
    prev_close_candle = None

    for i in range(len(kl_1h) - 1, -1, -1):
        t = datetime.fromtimestamp(kl_1h[i]["t"] / 1000, tz=timezone.utc)
        if t.hour == 0 and t.minute == 0:
            today_open_candle = kl_1h[i]
            if i > 0:
                prev_close_candle = kl_1h[i - 1]
            break

    if not today_open_candle or not prev_close_candle:
        return None

    today_open = today_open_candle["o"]
    prev_close = prev_close_candle["c"]
    gap = today_open - prev_close

    if abs(gap) < 0.01:
        direction = None
    elif gap > 0:
        direction = "up"
    else:
        direction = "down"

    return {
        "gap": round(gap, 2),
        "direction": direction,
        "today_open": round(today_open, 2),
        "prev_close": round(prev_close, 2),
    }


def get_htf_trend(h1_kl, ema_period=20):
    """1H 타임프레임 추세 방향 판별
    EMA20 위치 + 스윙 구조(HH+HL / LH+LL) 두 가지 일치 시 확정
    반환: "bullish" | "bearish" | "neutral"
    """
    if not h1_kl or len(h1_kl) < ema_period + 5:
        return "neutral"

    closes = [k["c"] for k in h1_kl]
    ema = closes[0]
    k_f = 2 / (ema_period + 1)
    for c in closes[1:]:
        ema = c * k_f + ema * (1 - k_f)
    ema_bias = "bullish" if closes[-1] > ema else "bearish"

    highs, lows = find_swings(h1_kl, n=3)
    swing_bias = "neutral"
    if len(highs) >= 2 and len(lows) >= 2:
        if highs[-1]["p"] > highs[-2]["p"] and lows[-1]["p"] > lows[-2]["p"]:
            swing_bias = "bullish"
        elif highs[-1]["p"] < highs[-2]["p"] and lows[-1]["p"] < lows[-2]["p"]:
            swing_bias = "bearish"

    if swing_bias != "neutral" and swing_bias == ema_bias:
        return swing_bias
    if swing_bias != "neutral":
        return swing_bias
    return ema_bias


def get_market_regime(d1_kl, fast=20, slow=50):
    """일봉 기반 시장 국면 감지
    반환: "bull" | "bear" | "ranging"
    - bull: EMA20 > EMA50 & 가격 > EMA20 (명확 상승장)
    - bear: EMA20 < EMA50 & 가격 < EMA20 (명확 하락장)
    - ranging: 그 외 (횡보 / 전환 구간)
    """
    if not d1_kl or len(d1_kl) < slow + 5:
        return "ranging"

    closes = [k["c"] for k in d1_kl]

    def ema(closes, period):
        k = 2 / (period + 1)
        e = closes[0]
        for c in closes[1:]:
            e = c * k + e * (1 - k)
        return e

    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    price = closes[-1]

    if price > ema_fast and ema_fast > ema_slow:
        return "bull"
    if price < ema_fast and ema_fast < ema_slow:
        return "bear"
    return "ranging"


def get_confluence_score(kl, h1_kl, direction, sig):
    """ICT 컨플루언스 점수 (0~5)
    direction: "long" | "short"
    sig: get_ict_signal() 결과 dict
    """
    score = 0
    price = kl[-1]["c"] if kl else 0

    pd_zone = sig.get("premium_discount")
    if direction == "long" and pd_zone and pd_zone["zone"] == "discount":
        score += 1
    elif direction == "short" and pd_zone and pd_zone["zone"] == "premium":
        score += 1

    if sig.get("ict_confirmation"):
        score += 1

    bos_dir = sig.get("bos_direction") or (sig.get("bos") or {}).get("direction")
    want = "bullish" if direction == "long" else "bearish"
    if bos_dir == want:
        score += 1

    bull_bb = sig.get("bull_breakers", [])
    bear_bb = sig.get("bear_breakers", [])
    if direction == "long" and any(b["bot"] * 0.999 <= price <= b["top"] * 1.001 for b in bull_bb):
        score += 1
    elif direction == "short" and any(b["bot"] * 0.999 <= price <= b["top"] * 1.001 for b in bear_bb):
        score += 1

    from datetime import datetime, timezone
    last_t = datetime.fromtimestamp(kl[-1]["t"] / 1000, tz=timezone.utc)
    if get_kill_zone(last_t) in ("london", "newyork"):
        score += 1

    return score


def get_ict_signal(kl, h1_kl=None, d1_kl=None):
    """ICT 종합 시그널 — get_smc_signal() 확장
    반환: smc_signal dict + {
        "premium_discount", "ote_zone", "bull_breakers", "bear_breakers",
        "ndog", "ict_confirmation"
    }
    """
    # 1. 기본 SMC 시그널 획득
    smc_sig = get_smc_signal(kl, h1_kl=h1_kl)

    if len(kl) < 30:
        smc_sig.update({
            "premium_discount": None, "ote_zone": None,
            "bull_breakers": [], "bear_breakers": [],
            "ndog": None, "ict_confirmation": False,
        })
        return smc_sig

    price = kl[-1]["c"]
    highs, lows = find_swings(kl, n=3)

    # 2. Premium/Discount zone (스윙 고저 기준)
    pd_zone = None
    if highs and lows:
        swing_h = highs[-1]["p"]
        swing_l = lows[-1]["p"]
        pd_zone = get_premium_discount(swing_h, swing_l, price)

    # 3. OTE zone (최근 스윙 기준)
    ote_zone = None
    if highs and lows:
        bos = find_bos_choch(kl, highs, lows)
        bos_dir = bos.get("direction")
        if bos_dir == "bullish" and len(lows) >= 2:
            # 불리쉬 BOS: 직전 저점 → 고점 스윙의 되돌림 구간
            ote_zone = get_ote(lows[-2]["p"], highs[-1]["p"], direction="bullish")
        elif bos_dir == "bearish" and len(highs) >= 2:
            ote_zone = get_ote(lows[-1]["p"], highs[-2]["p"], direction="bearish")
        elif len(highs) >= 1 and len(lows) >= 1:
            ote_zone = get_ote(lows[-1]["p"], highs[-1]["p"], direction="bullish")

    # 4. Breaker Block
    bull_breakers, bear_breakers = ([], [])
    if highs and lows:
        bull_breakers, bear_breakers = find_breaker_blocks(kl, highs, lows)

    # 5. NDOG
    ndog = None
    if d1_kl and len(d1_kl) >= 2:
        ndog = get_ndog(d1_kl)
    elif h1_kl and len(h1_kl) >= 2:
        ndog = get_ndog(h1_kl)

    # 6. ICT 추가 조건 판별
    ict_confirmation = False
    signal = smc_sig.get("signal")

    if signal == "long":
        in_discount = pd_zone and pd_zone["zone"] == "discount"
        in_ote = ote_zone and ote_zone["low"] <= price <= ote_zone["high"]
        at_bull_breaker = any(
            b["bot"] * 0.999 <= price <= b["top"] * 1.001 for b in bull_breakers
        )
        ict_confirmation = (in_discount and in_ote) or at_bull_breaker

    elif signal == "short":
        in_premium = pd_zone and pd_zone["zone"] == "premium"
        in_ote = ote_zone and ote_zone["low"] <= price <= ote_zone["high"]
        at_bear_breaker = any(
            b["bot"] * 0.999 <= price <= b["top"] * 1.001 for b in bear_breakers
        )
        ict_confirmation = (in_premium and in_ote) or at_bear_breaker

    smc_sig.update({
        "premium_discount": pd_zone,
        "ote_zone": ote_zone,
        "bull_breakers": bull_breakers,
        "bear_breakers": bear_breakers,
        "ndog": ndog,
        "ict_confirmation": ict_confirmation,
    })
    return smc_sig
