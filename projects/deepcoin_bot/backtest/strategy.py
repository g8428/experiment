"""
strategy.py — 백테스팅용 전략 정의
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dataclasses import dataclass
from typing import Optional
from ict_engine import (
    get_ict_signal, get_kill_zone, get_ote,
    find_swings, find_breaker_blocks, find_liquidity_sweep,
    get_htf_trend, get_confluence_score, get_market_regime,
)


@dataclass
class TradeSignal:
    direction:   str
    entry:       float
    sl:          float
    tp1:         float
    tp2:         Optional[float]
    reason:      str
    pattern_key: str


class BaseStrategy:
    name: str

    def signal(self, kl, h1_kl=None, d1_kl=None, m5_kl=None) -> Optional[TradeSignal]:
        raise NotImplementedError


def _regime_allows(regime, direction):
    """시장 국면과 방향 호환 여부
    - bull → 롱 허용 / 숏 금지
    - bear → 숏 허용 / 롱 금지
    - ranging → 양방향 허용 (단, 위험도 낮은 셋업만)
    """
    if regime == "bull" and direction == "short":
        return False
    if regime == "bear" and direction == "long":
        return False
    return True


def _check_rr(direction, price, sl, tp1, min_rr=1.5):
    if direction == "long":
        if sl >= price or tp1 <= price:
            return False
        return (tp1 - price) / max(price - sl, 1e-9) >= min_rr
    else:
        if sl <= price or tp1 >= price:
            return False
        return (price - tp1) / max(sl - price, 1e-9) >= min_rr


class ICTKillzoneStrategy(BaseStrategy):
    """ICT 킬존 전략: NY 킬존 내 BOS + OB/FVG POI 진입 + 1H 추세 필터"""
    name = "ict_killzone"

    def signal(self, kl, h1_kl=None, d1_kl=None, m5_kl=None) -> Optional[TradeSignal]:
        if not kl:
            return None
        from datetime import datetime, timezone
        last_t = datetime.fromtimestamp(kl[-1]["t"] / 1000, tz=timezone.utc)
        kz = get_kill_zone(last_t)
        if kz != "newyork":
            return None

        # 일봉 시장 국면 필터
        regime = get_market_regime(d1_kl) if d1_kl else "ranging"

        # 1H 추세 필터
        h1_trend = get_htf_trend(h1_kl) if h1_kl else "neutral"
        if h1_trend == "neutral":
            return None

        sig = get_ict_signal(kl, h1_kl=h1_kl, d1_kl=d1_kl)
        direction = sig.get("signal")
        if not direction or direction not in ("long", "short"):
            return None

        # 국면 + 1H 추세 이중 필터
        if not _regime_allows(regime, direction):
            return None
        if h1_trend == "bullish" and direction != "long":
            return None
        if h1_trend == "bearish" and direction != "short":
            return None

        price = kl[-1]["c"]
        sl    = sig.get("sl")
        tp1   = sig.get("tp1")
        if not sl or not tp1 or not _check_rr(direction, price, sl, tp1):
            return None

        return TradeSignal(
            direction   = direction,
            entry       = price,
            sl          = sl,
            tp1         = tp1,
            tp2         = sig.get("tp2"),
            reason      = f"[{kz}][1H:{h1_trend}] " + sig.get("reason", ""),
            pattern_key = f"{self.name}_{direction}_{kz}",
        )


class ICTOTEStrategy(BaseStrategy):
    """ICT OTE 전략: Sweep 후 OTE zone (0.618~0.786) 재진입 + 1H 추세 필터"""
    name = "ict_ote"

    def signal(self, kl, h1_kl=None, d1_kl=None, m5_kl=None) -> Optional[TradeSignal]:
        if len(kl) < 30:
            return None

        regime   = get_market_regime(d1_kl) if d1_kl else "ranging"
        h1_trend = get_htf_trend(h1_kl) if h1_kl else "neutral"
        if h1_trend == "neutral":
            return None

        price = kl[-1]["c"]
        highs, lows = find_swings(kl, n=3)
        if not highs or not lows:
            return None

        sweep_dir, _ = find_liquidity_sweep(kl, highs, lows)
        if not sweep_dir:
            return None

        if (sweep_dir == "bullish" and h1_trend == "bullish"
                and _regime_allows(regime, "long")
                and len(lows) >= 2 and len(highs) >= 1):
            ote = get_ote(lows[-2]["p"], highs[-1]["p"], direction="bullish")
            if ote["low"] <= price <= ote["high"]:
                sl  = round(lows[-1]["p"] * 0.9995, 4)
                tp1 = round(highs[-1]["p"], 4)
                if _check_rr("long", price, sl, tp1):
                    return TradeSignal(
                        direction   = "long",
                        entry       = price,
                        sl          = sl,
                        tp1         = tp1,
                        tp2         = None,
                        reason      = f"OTE롱[1H:{h1_trend}] Sweep→{ote['low']:.0f}~{ote['high']:.0f}",
                        pattern_key = f"{self.name}_long",
                    )

        elif (sweep_dir == "bearish" and h1_trend == "bearish"
              and _regime_allows(regime, "short")
              and len(highs) >= 2 and len(lows) >= 1):
            ote = get_ote(lows[-1]["p"], highs[-2]["p"], direction="bearish")
            if ote["low"] <= price <= ote["high"]:
                sl  = round(highs[-1]["p"] * 1.0005, 4)
                tp1 = round(lows[-1]["p"], 4)
                if _check_rr("short", price, sl, tp1):
                    return TradeSignal(
                        direction   = "short",
                        entry       = price,
                        sl          = sl,
                        tp1         = tp1,
                        tp2         = None,
                        reason      = f"OTE숏[1H:{h1_trend}] Sweep→{ote['low']:.0f}~{ote['high']:.0f}",
                        pattern_key = f"{self.name}_short",
                    )

        return None


class ICTBreakerStrategy(BaseStrategy):
    """ICT Breaker Block 전략: 실패 OB 전환 후 Breaker에서 반응 + 1H 추세 필터"""
    name = "ict_breaker"

    def signal(self, kl, h1_kl=None, d1_kl=None, m5_kl=None) -> Optional[TradeSignal]:
        if len(kl) < 30:
            return None

        regime   = get_market_regime(d1_kl) if d1_kl else "ranging"
        h1_trend = get_htf_trend(h1_kl) if h1_kl else "neutral"
        if h1_trend == "neutral":
            return None

        price = kl[-1]["c"]
        highs, lows = find_swings(kl, n=3)
        if not highs or not lows:
            return None

        bull_bb, bear_bb = find_breaker_blocks(kl, highs, lows)

        if h1_trend == "bullish" and _regime_allows(regime, "long"):
            for bb in bull_bb:
                if bb["bot"] * 0.999 <= price <= bb["top"] * 1.001:
                    sl = round(bb["bot"] * 0.9995, 4)
                    tp1_cands = [h["p"] for h in highs if h["p"] > price]
                    if not tp1_cands:
                        continue
                    tp1 = round(min(tp1_cands), 4)
                    if _check_rr("long", price, sl, tp1):
                        return TradeSignal(
                            direction   = "long",
                            entry       = price,
                            sl          = sl,
                            tp1         = tp1,
                            tp2         = None,
                            reason      = f"BullBreaker[1H:{h1_trend}] {bb['bot']:.0f}~{bb['top']:.0f}",
                            pattern_key = f"{self.name}_long",
                        )

        elif h1_trend == "bearish" and _regime_allows(regime, "short"):
            for bb in bear_bb:
                if bb["bot"] * 0.999 <= price <= bb["top"] * 1.001:
                    sl = round(bb["top"] * 1.0005, 4)
                    tp1_cands = [l["p"] for l in lows if l["p"] < price]
                    if not tp1_cands:
                        continue
                    tp1 = round(max(tp1_cands), 4)
                    if _check_rr("short", price, sl, tp1):
                        return TradeSignal(
                            direction   = "short",
                            entry       = price,
                            sl          = sl,
                            tp1         = tp1,
                            tp2         = None,
                            reason      = f"BearBreaker[1H:{h1_trend}] {bb['bot']:.0f}~{bb['top']:.0f}",
                            pattern_key = f"{self.name}_short",
                        )

        return None


class ICTMTFStrategy(BaseStrategy):
    """ICT 멀티타임프레임 전략 (핵심)
    1H 추세 방향 + 15m 컨플루언스 2개 이상 + 5m 확인봉 + NY/London 킬존
    가장 엄격한 진입 조건 → 낮은 빈도, 높은 정확도 목표
    """
    name = "ict_mtf"
    MIN_CONFLUENCE = 3  # 3개 이상 컨플루언스 필요

    def signal(self, kl, h1_kl=None, d1_kl=None, m5_kl=None) -> Optional[TradeSignal]:
        if len(kl) < 50:
            return None

        # 1. Kill Zone 필수 (London 또는 NY만)
        from datetime import datetime, timezone
        last_t = datetime.fromtimestamp(kl[-1]["t"] / 1000, tz=timezone.utc)
        kz = get_kill_zone(last_t)
        if kz not in ("london", "newyork"):
            return None

        # 2. 일봉 시장 국면 + 1H 추세 (모두 필수)
        regime   = get_market_regime(d1_kl) if d1_kl else "ranging"
        h1_trend = get_htf_trend(h1_kl) if h1_kl else "neutral"
        if h1_trend == "neutral":
            return None

        sig = get_ict_signal(kl, h1_kl=h1_kl, d1_kl=d1_kl)
        raw_dir = sig.get("signal")

        # 방향 확정: 국면 + 1H 추세 + 15m 시그널 삼중 일치
        if h1_trend == "bullish" and raw_dir == "long" and _regime_allows(regime, "long"):
            direction = "long"
        elif h1_trend == "bearish" and raw_dir == "short" and _regime_allows(regime, "short"):
            direction = "short"
        else:
            return None

        # 3. 컨플루언스 점수 (3점 이상 필요)
        score = get_confluence_score(kl, h1_kl, direction, sig)
        if score < self.MIN_CONFLUENCE:
            return None

        price = kl[-1]["c"]
        sl    = sig.get("sl")
        tp1   = sig.get("tp1")
        if not sl or not tp1:
            return None
        if not _check_rr(direction, price, sl, tp1, min_rr=2.0):  # MTF는 RR 2.0 이상
            return None

        # 4. 5m 확인봉 (있는 경우)
        if m5_kl and len(m5_kl) >= 3:
            last_m5 = m5_kl[-1]
            if direction == "long":
                if last_m5["c"] < last_m5["o"] and last_m5["c"] < m5_kl[-2]["l"]:
                    return None
            else:
                if last_m5["c"] > last_m5["o"] and last_m5["c"] > m5_kl[-2]["h"]:
                    return None

        return TradeSignal(
            direction   = direction,
            entry       = price,
            sl          = sl,
            tp1         = tp1,
            tp2         = sig.get("tp2"),
            reason      = f"MTF[1H:{h1_trend}][{kz}][conf:{score}] " + sig.get("reason", ""),
            pattern_key = f"{self.name}_{direction}_{kz}",
        )


STRATEGIES = {
    s.name: s
    for s in [
        ICTKillzoneStrategy(),
        ICTOTEStrategy(),
        ICTBreakerStrategy(),
        ICTMTFStrategy(),
    ]
}
