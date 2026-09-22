"""
signal_scorer.py — BTC 4H + 일봉 자동 스코어링
composite_score(0-100) = trend(0-30) + momentum(0-25) + volatility(0-15)
                        + volume(0-20) + smc(0-15) + candle_bonus(-10~+10)
30분마다 server.py 백그라운드 스레드에서 호출됨
"""
import json, os, urllib.request
from datetime import datetime, timezone, timedelta
from smc_engine import score_smc as _score_smc_engine

_DC_KLINES = "https://api.deepcoin.com/deepcoin/market/candles"


def _fetch(bar, n=100):
    url = f"{_DC_KLINES}?instId=BTC-USDT-SWAP&bar={bar}&limit={n}"
    try:
        r = urllib.request.urlopen(
            urllib.request.Request(url, headers={"Content-Type": "application/json"}),
            timeout=8)
        resp = json.loads(r.read())
        raw = resp.get("data", resp) if isinstance(resp, dict) else resp
        kl = [{"t": int(k[0]), "o": float(k[1]), "h": float(k[2]),
               "l": float(k[3]), "c": float(k[4]), "v": float(k[5])} for k in raw]
        kl.sort(key=lambda x: x["t"])
        return kl
    except Exception as e:
        print(f"[scorer] fetch({bar}) 실패: {e}")
        return []


def _ema(cl, n):
    if len(cl) < n: return cl[-1] if cl else 0.0
    k = 2.0 / (n + 1); e = sum(cl[:n]) / n
    for p in cl[n:]: e = p * k + e * (1 - k)
    return e


def _rsi(cl, n=14):
    if len(cl) < n + 1: return 50.0
    d = [cl[i] - cl[i-1] for i in range(1, len(cl))]
    g = sum(max(x, 0) for x in d[-n:]) / n
    l = sum(max(-x, 0) for x in d[-n:]) / n
    return round(100.0 if l == 0 else 100 - 100 / (1 + g / l), 2)


def _atr(kl, n=14):
    if len(kl) < n + 1: return 0.0
    hi = [k["h"] for k in kl]; lo = [k["l"] for k in kl]; cl = [k["c"] for k in kl]
    tr = [max(hi[i]-lo[i], abs(hi[i]-cl[i-1]), abs(lo[i]-cl[i-1]))
          for i in range(1, len(kl))]
    return sum(tr[-n:]) / n


def _williams_r(kl, n=14):
    """Williams %R: -100(과매도) ~ 0(과매수)"""
    if len(kl) < n: return -50.0
    window = kl[-n:]
    hh = max(k["h"] for k in window)
    ll = min(k["l"] for k in window)
    c  = kl[-1]["c"]
    return round(-(hh - c) / (hh - ll) * 100 if hh != ll else -50.0, 2)


def _stoch_k(kl, n=14):
    """Stochastic %K: 0(과매도) ~ 100(과매수)"""
    if len(kl) < n: return 50.0
    window = kl[-n:]
    hh = max(k["h"] for k in window)
    ll = min(k["l"] for k in window)
    c  = kl[-1]["c"]
    return round((c - ll) / (hh - ll) * 100 if hh != ll else 50.0, 2)


# ── 스코어링 함수들 ──────────────────────────────────────────────────

def score_trend(d_kl, h4_kl):
    """추세 강도 → 0~30점 (방향 중립: 강한 상승 = 강한 하락 = 30점), direction 반환
    핵심: 추세가 강하게 한쪽으로 정렬될수록 고점 — 방향 무관"""
    if len(d_kl) < 50 or len(h4_kl) < 21:
        return 15, "neutral"

    d_cl  = [k["c"] for k in d_kl]
    h4_cl = [k["c"] for k in h4_kl]

    price   = d_cl[-1]
    d_ema20 = _ema(d_cl, 20)
    d_ema50 = _ema(d_cl, 50)
    h4_e9   = _ema(h4_cl, 9)
    h4_e21  = _ema(h4_cl, 21)

    bull = 0
    bull += 1 if price   > d_ema50 else 0
    bull += 1 if d_ema20 > d_ema50 else 0
    bull += 1 if h4_e9   > h4_e21  else 0
    bull += 1 if price   > h4_e21  else 0
    bear = 4 - bull

    # 강도 = 한쪽으로 정렬된 조건 수 (2=혼조, 3=편향, 4=완전정렬)
    # 혼조(2) → 0점, 한쪽 3개 → 15점, 완전정렬(4) → 30점
    strength  = max(bull, bear)
    score     = round((strength - 2) / 2 * 30)
    direction = "long" if bull >= 3 else ("short" if bull <= 1 else "neutral")
    return score, direction


def score_momentum(h4_kl):
    """모멘텀 강도 → 0~25점 (방향 중립: RSI 극단 = 과매수든 과매도든 고점)
    핵심: 중심(RSI 50)에서 멀수록 강한 모멘텀 = 진입 기회"""
    if len(h4_kl) < 20:
        return 12

    h4_cl = [k["c"] for k in h4_kl]
    rsi   = _rsi(h4_cl, 14)
    wR    = _williams_r(h4_kl, 14)
    stoch = _stoch_k(h4_kl, 14)

    # RSI 강도: 중심(50)에서 멀수록 강함 — RSI 30 or 70 = 최대
    rsi_strength = abs(rsi - 50) / 20.0          # 0.0 ~ 1.25 (clamped)
    base = max(0.0, min(25.0, rsi_strength * 25))

    # Williams %R 극단 보너스 (방향 무관): -90 이하 or -10 이상 → +3
    wR_bonus = 3 if (wR <= -85 or wR >= -15) else 0

    # Stochastic 기울기 (방향 무관 — 꺾이는 중이면 전환 신호)
    stoch_prev  = _stoch_k(h4_kl[:-2], 14) if len(h4_kl) > 16 else stoch
    stoch_bonus = 1 if abs(stoch - stoch_prev) > 5 else 0  # 방향 무관, 변화량만

    # RSI 기울기 강도 (방향 무관)
    rsi_prev    = _rsi(h4_cl[:-3], 14) if len(h4_cl) >= 17 else rsi
    slope_bonus = 2 if abs(rsi - rsi_prev) > 2 else 0

    return round(max(0, min(25, base + wR_bonus + stoch_bonus + slope_bonus)))


def score_volatility(h4_kl):
    """4H ATR% 기반 변동성 → 0~15점 + TP/SL 배수 추천"""
    if len(h4_kl) < 15:
        return 8, 2.0, 1.0, 1.0

    price   = h4_kl[-1]["c"]
    atr     = _atr(h4_kl, 14)
    atr_pct = round(atr / price * 100, 3) if price else 1.0

    # 이상적 ATR%: 0.6~1.4 → 최고 15점
    dev       = abs(atr_pct - 1.0)
    vol_score = round(max(0, 15 - dev * 6))

    # 변동성 역비례 배수 (10x 레버리지 기준)
    TARGET_TP_PCT = 1.2
    TARGET_SL_PCT = 0.6
    MIN_DIST_PCT  = 0.5
    MAX_MULT      = 8.0

    tp_m = round(min(TARGET_TP_PCT / atr_pct, MAX_MULT), 2)
    sl_m = round(min(TARGET_SL_PCT / atr_pct, MAX_MULT), 2)

    if tp_m * atr_pct < MIN_DIST_PCT: tp_m = round(MIN_DIST_PCT / atr_pct, 2)
    if sl_m * atr_pct < MIN_DIST_PCT: sl_m = round(MIN_DIST_PCT / atr_pct, 2)

    return vol_score, round(tp_m, 1), round(sl_m, 1), atr_pct


def score_volume(h4_kl):
    """거래량 강도 → 0~20점 (방향 중립: 방향 무관 거래량 집중 = 유효 시그널)
    핵심: 강한 방향성 거래량은 상승이든 하락이든 유효한 매매 신호"""
    if len(h4_kl) < 20:
        return 10

    vols   = [k["v"] for k in h4_kl]
    closes = [k["c"] for k in h4_kl]

    vol_ma20 = sum(vols[-20:]) / 20
    vol_ma5  = sum(vols[-5:])  / 5
    score    = 10  # 중립 기준점

    # 단기 거래량 강도 (방향 무관)
    if   vol_ma5 > vol_ma20 * 1.3: score += 4
    elif vol_ma5 < vol_ma20 * 0.7: score -= 2  # 수축은 VCP 준비일 수 있으므로 약한 감점만

    # 거래량 집중도 (방향 무관): 어느 방향이든 거래량이 쏠리면 유효 시그널
    up_vol = 0.0; dn_vol = 0.0
    for i in range(1, min(6, len(closes))):
        if   closes[-i] > closes[-i-1]: up_vol += vols[-i]
        elif closes[-i] < closes[-i-1]: dn_vol += vols[-i]

    total_vol = up_vol + dn_vol
    if total_vol > 0:
        concentration = abs(up_vol - dn_vol) / total_vol  # 0(균등) ~ 1(완전집중)
        if   concentration > 0.4: score += 4   # 뚜렷한 방향성 거래량
        elif concentration < 0.1: score -= 2   # 완전 혼조 = 방향 불명

    # 최근 거래량 스파이크 (브레이크아웃/브레이크다운 확인 — 방향 무관)
    if vols[-1] > vol_ma20 * 2.5: score += 2

    return round(max(0, min(20, score)))


def score_candle(h4_kl):
    """최근 캔들 패턴 → -10~+10 보너스 점수
    오닐/미너비니: 거래량 동반 장대 양봉/장악형이 핵심 진입 시그널"""
    if len(h4_kl) < 4:
        return 0

    k1 = h4_kl[-1]; k2 = h4_kl[-2]; k3 = h4_kl[-3]
    body1    = k1["c"] - k1["o"]
    body2    = k2["c"] - k2["o"]
    body3    = k3["c"] - k3["o"]
    rng1     = k1["h"] - k1["l"]
    lo_wick1 = min(k1["o"], k1["c"]) - k1["l"]
    hi_wick1 = k1["h"] - max(k1["o"], k1["c"])

    score = 0

    # 망치형 (Hammer): 아랫꼬리 >= 몸통 2배, 윗꼬리 짧음 → 하락 반전 기대
    if rng1 > 0 and lo_wick1 >= abs(body1) * 2 and hi_wick1 <= abs(body1) * 0.5:
        score += 4

    # 핀바/슈팅스타 (Shooting Star): 윗꼬리 >= 몸통 2배, 아랫꼬리 짧음 → 상승 반전 기대
    elif rng1 > 0 and hi_wick1 >= abs(body1) * 2 and lo_wick1 <= abs(body1) * 0.5:
        score -= 4

    # 상승 장악형 (Bullish Engulfing): 전봉 음봉을 완전히 감싸는 양봉
    if body2 < 0 and body1 > 0 and k1["c"] > k2["o"] and k1["o"] < k2["c"]:
        score += 5

    # 하락 장악형 (Bearish Engulfing): 전봉 양봉을 완전히 감싸는 음봉
    elif body2 > 0 and body1 < 0 and k1["c"] < k2["o"] and k1["o"] > k2["c"]:
        score -= 5

    # 연속 3봉 방향
    if   body1 > 0 and body2 > 0 and body3 > 0: score += 3   # 3연속 양봉
    elif body1 < 0 and body2 < 0 and body3 < 0: score -= 3   # 3연속 음봉

    # 도지 (몸통이 범위의 10% 미만) → 불확실, 신호 약화
    if rng1 > 0 and abs(body1) / rng1 < 0.1:
        score = round(score * 0.5)

    return round(max(-10, min(10, score)))


def score_smc(d_kl, h4_kl):
    """SMC 강도 스코어 → 0~15점 (signal_scorer 래퍼 — smc_engine 호출)"""
    try:
        return _score_smc_engine(h4_kl)
    except Exception:
        return 5


# ── 메인 함수 ────────────────────────────────────────────────────────

def compute_and_save(signal_path):
    """스코어 계산 → latest_signal.json 병합 저장. 결과 dict 반환"""
    d_kl  = _fetch("1D", 60)
    h4_kl = _fetch("4H", 80)

    if not d_kl or not h4_kl:
        return {"error": "klines fetch 실패"}

    trend_score, direction          = score_trend(d_kl, h4_kl)
    mom_score                       = score_momentum(h4_kl)
    vol_score, tp_m, sl_m, atr_pct = score_volatility(h4_kl)
    volume_score                    = score_volume(h4_kl)
    vcp_score                       = score_smc(d_kl, h4_kl)
    candle_bonus                    = score_candle(h4_kl)

    composite = max(0, min(100,
        trend_score + mom_score + vol_score + volume_score + vcp_score + candle_bonus
    ))

    if   composite >= 60 and direction == "long":  bias = "long"
    elif composite >= 60 and direction == "short": bias = "short"
    else:                                           bias = "neutral"

    if   atr_pct > 3.0:                               allowed = "none"
    elif composite >= 55 and direction != "neutral":   allowed = "both"
    elif composite >= 40:                              allowed = "scalp"
    else:                                              allowed = "none"

    kst = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")

    existing = {}
    if os.path.exists(signal_path):
        try:
            with open(signal_path, encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass

    existing.update({
        "composite_score": composite,
        "direction_bias":  bias,
        "allowed_bots":    allowed,
        "tp_atr_mult":     tp_m,
        "sl_atr_mult":     sl_m,
        "trend_score":     trend_score,
        "momentum_score":  mom_score,
        "vol_score":       vol_score,
        "volume_score":    volume_score,
        "smc_score":       vcp_score,
        "vcp_score":       vcp_score,  # backward compat
        "candle_bonus":    candle_bonus,
        "atr_pct":         atr_pct,
        "scored_at":       kst,
    })

    # ── Claude 기술적 분석 병합 ────────────────────────────────────
    try:
        from claude_signal import analyze
        ca = analyze()
        if "error" not in ca:
            existing.update({
                "claude_direction":        ca.get("direction"),
                "claude_confidence":       ca.get("confidence"),
                "claude_stage":            ca.get("stage"),
                "claude_vcp_detected":     ca.get("vcp_detected"),
                "claude_vcp_contractions": ca.get("vcp_contraction_count"),
                "claude_candle_pattern":   ca.get("candle_pattern"),
                "claude_candle_signal":    ca.get("candle_signal"),
                "claude_volume_trend":     ca.get("volume_trend"),
                "claude_vol_confirmed":    ca.get("volume_confirmation"),
                "entry_zone_low":          ca.get("entry_zone_low"),
                "entry_zone_high":         ca.get("entry_zone_high"),
                "claude_tp1":              ca.get("tp1"),
                "claude_tp2":              ca.get("tp2"),
                "claude_sl":               ca.get("sl"),
                "claude_invalidation":     ca.get("invalidation"),
                "key_support":             ca.get("key_support"),
                "key_resistance":          ca.get("key_resistance"),
                "claude_bos_type":         ca.get("bos_type"),
                "claude_bos_direction":    ca.get("bos_direction"),
                "claude_nearest_bull_ob":  ca.get("nearest_bull_ob"),
                "claude_nearest_bear_ob":  ca.get("nearest_bear_ob"),
                "claude_nearest_bull_fvg": ca.get("nearest_bull_fvg"),
                "claude_nearest_bear_fvg": ca.get("nearest_bear_fvg"),
                "claude_liquidity_above":  ca.get("liquidity_above"),
                "claude_liquidity_below":  ca.get("liquidity_below"),
                "bull_prob":               ca.get("bull_prob"),
                "bear_prob":               ca.get("bear_prob"),
                "neutral_prob":            ca.get("neutral_prob"),
                "claude_reasoning":        ca.get("reasoning"),
                "analyzed_at":             ca.get("analyzed_at"),
            })
            if ca.get("direction") == direction and ca.get("confidence") in ("high", "medium"):
                existing["direction_bias"] = ca["direction"]
            print(f"[scorer] Claude 분석 완료: {ca.get('direction')} ({ca.get('confidence')}) "
                  f"Stage{ca.get('stage')} VCP={ca.get('vcp_detected')} "
                  f"캔들={ca.get('candle_pattern')} 거래량={ca.get('volume_trend')}")
        else:
            print(f"[scorer] Claude 분석 실패: {ca['error']}")
    except Exception as e:
        print(f"[scorer] Claude 분석 예외: {e}")

    with open(signal_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    return {
        "composite_score": composite,
        "direction_bias":  existing.get("direction_bias", bias),
        "allowed_bots":    allowed,
        "trend_score":     trend_score,
        "momentum_score":  mom_score,
        "vol_score":       vol_score,
        "volume_score":    volume_score,
        "smc_score":       vcp_score,
        "candle_bonus":    candle_bonus,
        "atr_pct":         atr_pct,
        "tp_atr_mult":     tp_m,
        "sl_atr_mult":     sl_m,
        "scored_at":       kst,
    }


if __name__ == "__main__":
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "market_reports", "latest_signal.json")
    r = compute_and_save(path)
    if "error" in r:
        print(f"[scorer] 실패: {r['error']}")
    else:
        print(f"[scorer] composite={r['composite_score']}  bias={r['direction_bias']}  allowed={r['allowed_bots']}")
        print(f"         trend={r['trend_score']}  mom={r['momentum_score']}  vol={r['vol_score']}")
        print(f"         volume={r['volume_score']}  smc={r['smc_score']}  candle_bonus={r['candle_bonus']}")
        print(f"         tp_mult={r['tp_atr_mult']}  sl_mult={r['sl_atr_mult']}  scored_at={r['scored_at']}")
