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


# ── 멀티전략 4종 — 라이브(server.py)와 백테스트(backtest/strategy.py)가 공유하는 단일 원본 ──
# 우선순위: OTE → MTF → 킬존(NY전용) → Breaker (2026-09-23 6개월 BTC 백테스트:
# OTE +164.75%, 킬존 +25.16%, MTF +20.60%, Breaker -26.53% 순으로 반영)
# 각 함수는 자기 진입 조건을 전부 자체 포함한다 (킬존/D1레짐/1H추세/RR 등). server.py는
# 여기에 시그널 필터를 덧붙이지 않고 리스크 관리(일한도/쿨다운/RR·TP최소/직전SL)만 한다.
# 전부 get_smc_signal()과 동일한 dict 형태 + "kz" 필드로 반환.

def _regime_allows(regime, direction):
    if regime == "bull" and direction == "short":
        return False
    if regime == "bear" and direction == "long":
        return False
    return True


def _rr_ok(direction, price, sl, tp1, min_rr=1.5):
    if direction == "long":
        if sl >= price or tp1 <= price:
            return False
        return (tp1 - price) / max(price - sl, 1e-9) >= min_rr
    if sl <= price or tp1 >= price:
        return False
    return (price - tp1) / max(sl - price, 1e-9) >= min_rr


def _kz_of(kl):
    from datetime import datetime, timezone
    return get_kill_zone(datetime.fromtimestamp(kl[-1]["t"] / 1000, tz=timezone.utc))


def _m15_confirms(kl, direction, n=2):
    """최근 n개 15분봉(kl, 주 타임프레임)이 direction과 실제로 같은 방향으로 움직였는지 확인.
    get_htf_trend()의 1H 판정을 그대로 신뢰하지 않고, 신호 직전 확인캔들로 재검증하는 용도
    (2026-09-29~10-01 7전 7패 원인 분석 — B안, m15_confirm_n>0일 때만 활성화).
    """
    if n <= 0 or not kl or len(kl) < n:
        return False
    recent = kl[-n:]
    if direction == "bullish":
        return all(c["c"] > c["o"] for c in recent)
    if direction == "bearish":
        return all(c["c"] < c["o"] for c in recent)
    return False


_EMPTY_SIGNAL = {
    "signal": None, "sl": None, "tp1": None, "tp2": None,
    "bos_type": None, "bos_dir": None,
    "bull_ob_count": 0, "bear_ob_count": 0,
    "bull_fvg_count": 0, "bear_fvg_count": 0,
    "sweep": False, "sweep_dir": None, "sweep_lvl": None,
    "buy_liq": [], "sell_liq": [],
    "strong_high": None, "weak_high": None,
    "strong_low": None, "weak_low": None,
    "reason": "", "kz": None,
}


def get_ote_signal(kl, h1_kl=None, d1_kl=None, m5_kl=None,
                    m15_confirm_n: int = 0, require_h1_trend: bool = True):
    """OTE(Optimal Trade Entry) — 유동성 스윕 후 0.618~0.786 되돌림 재진입.
    조건: 1H 추세 확정(neutral 제외) + D1 레짐 허용 + 스윕 + OTE 구간 + RR≥1.5. 킬존 조건 없음.

    m15_confirm_n: 0(기본, 비활성)이면 기존과 100% 동일 동작. >0이면 신호 직전 15분봉
        n개가 방향과 실제로 일치하는지 추가 확인(2026-10-01 B안, server.py는 미적용).
    require_h1_trend: True(기본)면 기존처럼 1H 추세 확정·방향 일치를 요구. False면 1H 추세
        체크를 건너뛰고 D1 레짐 + 자체 스윕/되돌림 신호만으로 판단(비교용, server.py는 미적용).
    """
    result = dict(_EMPTY_SIGNAL, reason="OTE 데이터 부족")
    if len(kl) < 30:
        return result
    result["kz"] = _kz_of(kl)
    regime   = get_market_regime(d1_kl) if d1_kl else "ranging"
    h1_trend = get_htf_trend(h1_kl) if h1_kl else "neutral"
    if require_h1_trend and h1_trend == "neutral":
        result["reason"] = "OTE 1H추세 중립"
        return result
    price = kl[-1]["c"]
    highs, lows = find_swings(kl, n=3)
    if not highs or not lows:
        result["reason"] = "OTE 스윙 탐지 실패"
        return result
    sweep_dir, sweep_lvl = find_liquidity_sweep(kl, highs, lows)
    result.update({"sweep": bool(sweep_dir), "sweep_dir": sweep_dir, "sweep_lvl": sweep_lvl})
    if not sweep_dir:
        result["reason"] = f"OTE 스윕 없음 (1H:{h1_trend})"
        return result

    if sweep_dir == "bullish" and (not require_h1_trend or h1_trend == "bullish") and regime != "bear":
        if len(lows) < 2 or len(highs) < 1:
            result["reason"] = "OTE 스윙 부족(롱)"; return result
        ote = get_ote(lows[-2]["p"], highs[-1]["p"], direction="bullish")
        if not (ote["low"] <= price <= ote["high"]):
            result["reason"] = f"OTE 구간 밖(롱) 되돌림{ote['low']:.4f}~{ote['high']:.4f} 현재{price:.4f}"
            return result
        sl, tp1 = round(lows[-1]["p"] * 0.9995, 6), round(highs[-1]["p"], 6)
        if not _rr_ok("long", price, sl, tp1):
            result["reason"] = f"OTE RR<1.5(롱) SL{sl:.4f} TP{tp1:.4f}"; return result
        if m15_confirm_n > 0 and not _m15_confirms(kl, "bullish", m15_confirm_n):
            result["reason"] = "15m 확인캔들 불일치(롱)"; return result
        result.update({
            "signal": "long", "sl": sl, "tp1": tp1, "bos_dir": "bullish",
            "weak_low": lows[-1]["p"], "strong_high": highs[-1]["p"],
            "reason": f"OTE롱 Sweep@{sweep_lvl:.4f}→되돌림{ote['low']:.4f}~{ote['high']:.4f}",
        })
    elif sweep_dir == "bearish" and (not require_h1_trend or h1_trend == "bearish") and regime != "bull":
        if len(highs) < 2 or len(lows) < 1:
            result["reason"] = "OTE 스윙 부족(숏)"; return result
        ote = get_ote(lows[-1]["p"], highs[-2]["p"], direction="bearish")
        if not (ote["low"] <= price <= ote["high"]):
            result["reason"] = f"OTE 구간 밖(숏) 되돌림{ote['low']:.4f}~{ote['high']:.4f} 현재{price:.4f}"
            return result
        sl, tp1 = round(highs[-1]["p"] * 1.0005, 6), round(lows[-1]["p"], 6)
        if not _rr_ok("short", price, sl, tp1):
            result["reason"] = f"OTE RR<1.5(숏) SL{sl:.4f} TP{tp1:.4f}"; return result
        if m15_confirm_n > 0 and not _m15_confirms(kl, "bearish", m15_confirm_n):
            result["reason"] = "15m 확인캔들 불일치(숏)"; return result
        result.update({
            "signal": "short", "sl": sl, "tp1": tp1, "bos_dir": "bearish",
            "weak_high": highs[-1]["p"], "strong_low": lows[-1]["p"],
            "reason": f"OTE숏 Sweep@{sweep_lvl:.4f}→되돌림{ote['low']:.4f}~{ote['high']:.4f}",
        })
    else:
        result["reason"] = f"OTE 방향불일치 sweep={sweep_dir} 1H={h1_trend} D1={regime}"
    return result


def get_mtf_signal(kl, h1_kl=None, d1_kl=None, m5_kl=None,
                    m15_confirm_n: int = 0, require_h1_trend: bool = True):
    """MTF 컨플루언스 — 가장 엄격한 전략.
    조건: 킬존(런던/뉴욕) + D1 레짐 허용 + 1H 추세와 15m OB/FVG 시그널 방향 일치
          + 컨플루언스 점수 ≥3 + RR≥2.0 + 5m 확인봉 역방향 아님.

    m15_confirm_n, require_h1_trend: get_ote_signal() 참고 — 기본값은 기존 동작 그대로 보존.
    """
    if len(kl) < 50:
        return dict(_EMPTY_SIGNAL, reason="MTF 데이터 부족")
    kz = _kz_of(kl)
    if kz not in ("london", "newyork"):
        return dict(_EMPTY_SIGNAL, reason="MTF 킬존 아님", kz=kz)
    regime   = get_market_regime(d1_kl) if d1_kl else "ranging"
    h1_trend = get_htf_trend(h1_kl) if h1_kl else "neutral"
    if require_h1_trend and h1_trend == "neutral":
        return dict(_EMPTY_SIGNAL, reason="MTF 1H추세 중립", kz=kz)

    base = get_ict_signal(kl, h1_kl=h1_kl, d1_kl=d1_kl)
    base["kz"] = kz
    raw_dir = base.get("signal")
    if (not require_h1_trend or h1_trend == "bullish") and raw_dir == "long" and _regime_allows(regime, "long"):
        direction = "long"
    elif (not require_h1_trend or h1_trend == "bearish") and raw_dir == "short" and _regime_allows(regime, "short"):
        direction = "short"
    else:
        return dict(base, signal=None,
                    reason=f"MTF 방향불일치(1H:{h1_trend}/15m:{raw_dir or '없음'}/D1:{regime})")

    score = get_confluence_score(kl, h1_kl, direction, base)
    if score < 3:
        return dict(base, signal=None, reason=f"MTF 컨플루언스 부족({score}/3)")
    price, sl, tp1 = kl[-1]["c"], base.get("sl"), base.get("tp1")
    if not sl or not tp1 or not _rr_ok(direction, price, sl, tp1, min_rr=2.0):
        return dict(base, signal=None, reason="MTF RR<2.0")
    if m5_kl and len(m5_kl) >= 3:
        last_m5, prev_m5 = m5_kl[-1], m5_kl[-2]
        if direction == "long" and last_m5["c"] < last_m5["o"] and last_m5["c"] < prev_m5["l"]:
            return dict(base, signal=None, reason="MTF 5m 역방향 확인봉")
        if direction == "short" and last_m5["c"] > last_m5["o"] and last_m5["c"] > prev_m5["h"]:
            return dict(base, signal=None, reason="MTF 5m 역방향 확인봉")
    if m15_confirm_n > 0:
        m15_dir = "bullish" if direction == "long" else "bearish"
        if not _m15_confirms(kl, m15_dir, m15_confirm_n):
            return dict(base, signal=None, reason="MTF 15m 확인캔들 불일치")
    return dict(base, signal=direction,
                reason=f"MTF[1H:{h1_trend}][{kz}][conf:{score}] " + base.get("reason", ""))


def get_killzone_signal(kl, h1_kl=None, d1_kl=None, m5_kl=None,
                         m15_confirm_n: int = 0, require_h1_trend: bool = True):
    """킬존(NY전용) — OB/FVG 시그널을 뉴욕 세션 + 1H 추세 정렬 + D1 레짐으로 한정.
    조건: 뉴욕 킬존 + 1H 추세 확정·방향 일치 + D1 레짐 허용 + RR≥1.5.

    m15_confirm_n, require_h1_trend: get_ote_signal() 참고 — 기본값은 기존 동작 그대로 보존.
    """
    if not kl:
        return dict(_EMPTY_SIGNAL, reason="데이터 없음")
    kz = _kz_of(kl)
    if kz != "newyork":
        return dict(_EMPTY_SIGNAL, reason="뉴욕 킬존 아님", kz=kz)
    regime   = get_market_regime(d1_kl) if d1_kl else "ranging"
    h1_trend = get_htf_trend(h1_kl) if h1_kl else "neutral"
    if require_h1_trend and h1_trend == "neutral":
        return dict(_EMPTY_SIGNAL, reason="KZ 1H추세 중립", kz=kz)
    base = get_ict_signal(kl, h1_kl=h1_kl, d1_kl=d1_kl)
    base["kz"] = kz
    direction = base.get("signal")
    if direction not in ("long", "short"):
        return dict(base, signal=None, reason="KZ 15m 시그널 없음")
    if not _regime_allows(regime, direction):
        return dict(base, signal=None, reason=f"KZ D1레짐({regime}) 역방향")
    if require_h1_trend and (h1_trend == "bullish") != (direction == "long"):
        return dict(base, signal=None, reason=f"KZ 1H({h1_trend}) 불일치")
    price, sl, tp1 = kl[-1]["c"], base.get("sl"), base.get("tp1")
    if not sl or not tp1 or not _rr_ok(direction, price, sl, tp1):
        return dict(base, signal=None, reason="KZ RR<1.5")
    if m15_confirm_n > 0:
        m15_dir = "bullish" if direction == "long" else "bearish"
        if not _m15_confirms(kl, m15_dir, m15_confirm_n):
            return dict(base, signal=None, reason="KZ 15m 확인캔들 불일치")
    return dict(base, reason=f"[{kz}][1H:{h1_trend}] " + base.get("reason", ""))


def get_breaker_signal(kl, h1_kl=None, d1_kl=None, m5_kl=None,
                        m15_confirm_n: int = 0, require_h1_trend: bool = True):
    """Breaker Block — 실패 OB가 반대 POI로 전환된 지점에서 반응.
    조건: 1H 추세 확정 + D1 레짐 허용 + 가격이 브레이커 구간 + RR≥1.5. 킬존 조건 없음.
    2026-09-23 BTC 백테스트 최하위(-26.53%) → 우선순위 최후, 저승률 지속 시 제외 검토.

    m15_confirm_n, require_h1_trend: get_ote_signal() 참고 — 기본값은 기존 동작 그대로 보존.
    require_h1_trend=False일 때는 D1 레짐이 막지 않는 양쪽 브레이커를 모두 시도한다
    (require_h1_trend=True일 때는 h1_trend가 bullish/bearish 둘 중 하나로 확정된 상태이므로
    항상 한쪽만 활성화되어 기존 if/elif 분기와 동일하게 동작한다).
    """
    result = dict(_EMPTY_SIGNAL, reason="Breaker 데이터 부족")
    if len(kl) < 30:
        return result
    result["kz"] = _kz_of(kl)
    regime   = get_market_regime(d1_kl) if d1_kl else "ranging"
    h1_trend = get_htf_trend(h1_kl) if h1_kl else "neutral"
    if require_h1_trend and h1_trend == "neutral":
        result["reason"] = "Breaker 1H추세 중립"
        return result
    price = kl[-1]["c"]
    highs, lows = find_swings(kl, n=3)
    if not highs or not lows:
        result["reason"] = "Breaker 스윙 탐지 실패"
        return result
    bull_bb, bear_bb = find_breaker_blocks(kl, highs, lows)

    try_bull = (not require_h1_trend or h1_trend == "bullish") and regime != "bear"
    try_bear = (not require_h1_trend or h1_trend == "bearish") and regime != "bull"

    if try_bull:
        if not bull_bb:
            result["reason"] = f"Breaker 없음(롱, 1H:{h1_trend})"
        else:
            near = [bb for bb in bull_bb if bb["bot"] * 0.999 <= price <= bb["top"] * 1.001]
            if not near:
                near_bb = min(bull_bb, key=lambda bb: abs(price - (bb["bot"] + bb["top"]) / 2))
                result["reason"] = f"Breaker 구간 밖(롱) {near_bb['bot']:.4f}~{near_bb['top']:.4f} 현재{price:.4f}"
            else:
                for bb in near:
                    sl = round(bb["bot"] * 0.9995, 6)
                    cands = [h["p"] for h in highs if h["p"] > price]
                    if not cands:
                        result["reason"] = "Breaker TP 후보 없음(롱)"; continue
                    tp1 = round(min(cands), 6)
                    if not _rr_ok("long", price, sl, tp1):
                        result["reason"] = f"Breaker RR<1.5(롱) SL{sl:.4f} TP{tp1:.4f}"; continue
                    if m15_confirm_n > 0 and not _m15_confirms(kl, "bullish", m15_confirm_n):
                        result["reason"] = "15m 확인캔들 불일치(롱)"; continue
                    result.update({"signal": "long", "sl": sl, "tp1": tp1, "bos_dir": "bullish",
                                   "reason": f"BullBreaker {bb['bot']:.4f}~{bb['top']:.4f}"})
                    return result
    if try_bear:
        if not bear_bb:
            result["reason"] = f"Breaker 없음(숏, 1H:{h1_trend})"
        else:
            near = [bb for bb in bear_bb if bb["bot"] * 0.999 <= price <= bb["top"] * 1.001]
            if not near:
                near_bb = min(bear_bb, key=lambda bb: abs(price - (bb["bot"] + bb["top"]) / 2))
                result["reason"] = f"Breaker 구간 밖(숏) {near_bb['bot']:.4f}~{near_bb['top']:.4f} 현재{price:.4f}"
            else:
                for bb in near:
                    sl = round(bb["top"] * 1.0005, 6)
                    cands = [l["p"] for l in lows if l["p"] < price]
                    if not cands:
                        result["reason"] = "Breaker TP 후보 없음(숏)"; continue
                    tp1 = round(max(cands), 6)
                    if not _rr_ok("short", price, sl, tp1):
                        result["reason"] = f"Breaker RR<1.5(숏) SL{sl:.4f} TP{tp1:.4f}"; continue
                    if m15_confirm_n > 0 and not _m15_confirms(kl, "bearish", m15_confirm_n):
                        result["reason"] = "15m 확인캔들 불일치(숏)"; continue
                    result.update({"signal": "short", "sl": sl, "tp1": tp1, "bos_dir": "bearish",
                                   "reason": f"BearBreaker {bb['bot']:.4f}~{bb['top']:.4f}"})
                    return result
    if not try_bull and not try_bear:
        result["reason"] = f"Breaker D1레짐({regime}) 역방향 1H={h1_trend}"
    return result
