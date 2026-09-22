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
)


@dataclass
class TradeSignal:
    direction:   str            # "long" | "short"
    entry:       float
    sl:          float
    tp1:         float
    tp2:         Optional[float]
    reason:      str
    pattern_key: str            # 승률 추적용 패턴 키


class BaseStrategy:
    name: str

    def signal(self, kl, h1_kl=None, d1_kl=None) -> Optional[TradeSignal]:
        raise NotImplementedError


class ICTKillzoneStrategy(BaseStrategy):
    """ICT 킬존 전략: Kill Zone 내 BOS + OB/FVG POI 진입"""
    name = "ict_killzone"

    def signal(self, kl, h1_kl=None, d1_kl=None) -> Optional[TradeSignal]:
        if not kl:
            return None
        from datetime import datetime, timezone
        last_t  = datetime.fromtimestamp(kl[-1]["t"] / 1000, tz=timezone.utc)
        kz      = get_kill_zone(last_t)
        if kz not in ("london", "newyork"):
            return None

        sig = get_ict_signal(kl, h1_kl=h1_kl, d1_kl=d1_kl)
        if sig.get("signal") not in ("long", "short"):
            return None

        direction = sig["signal"]
        entry     = kl[-1]["c"]
        sl        = sig.get("sl")
        tp1       = sig.get("tp1")
        tp2       = sig.get("tp2")
        if not sl or not tp1:
            return None

        return TradeSignal(
            direction   = direction,
            entry       = entry,
            sl          = sl,
            tp1         = tp1,
            tp2         = tp2,
            reason      = f"[{kz}] " + sig.get("reason", ""),
            pattern_key = f"{self.name}_{direction}_{kz}",
        )


class ICTOTEStrategy(BaseStrategy):
    """ICT OTE 전략: Sweep 후 OTE zone (0.618~0.786) 재진입"""
    name = "ict_ote"

    def signal(self, kl, h1_kl=None, d1_kl=None) -> Optional[TradeSignal]:
        if len(kl) < 30:
            return None

        price = kl[-1]["c"]
        highs, lows = find_swings(kl, n=3)
        if not highs or not lows:
            return None

        sweep_dir, _ = find_liquidity_sweep(kl, highs, lows)
        if not sweep_dir:
            return None

        if sweep_dir == "bullish" and len(lows) >= 2 and len(highs) >= 1:
            ote = get_ote(lows[-2]["p"], highs[-1]["p"], direction="bullish")
            if ote["low"] <= price <= ote["high"]:
                sl  = round(lows[-1]["p"] * 0.9995, 1)
                tp1 = round(highs[-1]["p"], 1)
                if sl < price < tp1 and (tp1 - price) / max(price - sl, 1e-9) >= 1.5:
                    return TradeSignal(
                        direction   = "long",
                        entry       = price,
                        sl          = sl,
                        tp1         = tp1,
                        tp2         = None,
                        reason      = f"OTE롱 Sweep→되돌림 {ote['low']:.0f}~{ote['high']:.0f}",
                        pattern_key = f"{self.name}_long",
                    )

        elif sweep_dir == "bearish" and len(highs) >= 2 and len(lows) >= 1:
            ote = get_ote(lows[-1]["p"], highs[-2]["p"], direction="bearish")
            if ote["low"] <= price <= ote["high"]:
                sl  = round(highs[-1]["p"] * 1.0005, 1)
                tp1 = round(lows[-1]["p"], 1)
                if sl > price > tp1 and (price - tp1) / max(sl - price, 1e-9) >= 1.5:
                    return TradeSignal(
                        direction   = "short",
                        entry       = price,
                        sl          = sl,
                        tp1         = tp1,
                        tp2         = None,
                        reason      = f"OTE숏 Sweep→되돌림 {ote['low']:.0f}~{ote['high']:.0f}",
                        pattern_key = f"{self.name}_short",
                    )

        return None


class ICTBreakerStrategy(BaseStrategy):
    """ICT Breaker Block 전략: 실패 OB 전환 후 Breaker에서 반응"""
    name = "ict_breaker"

    def signal(self, kl, h1_kl=None, d1_kl=None) -> Optional[TradeSignal]:
        if len(kl) < 30:
            return None

        price = kl[-1]["c"]
        highs, lows = find_swings(kl, n=3)
        if not highs or not lows:
            return None

        bull_bb, bear_bb = find_breaker_blocks(kl, highs, lows)

        # Bullish Breaker 진입 (가격이 Breaker 구간 안)
        for bb in bull_bb:
            if bb["bot"] * 0.999 <= price <= bb["top"] * 1.001:
                sl  = round(bb["bot"] * 0.9995, 1)
                tp1_cands = [h["p"] for h in highs if h["p"] > price]
                if not tp1_cands:
                    continue
                tp1 = round(min(tp1_cands), 1)
                if sl < price < tp1 and (tp1 - price) / max(price - sl, 1e-9) >= 1.5:
                    return TradeSignal(
                        direction   = "long",
                        entry       = price,
                        sl          = sl,
                        tp1         = tp1,
                        tp2         = None,
                        reason      = f"BullBreaker롱 {bb['bot']:.0f}~{bb['top']:.0f}",
                        pattern_key = f"{self.name}_long",
                    )

        # Bearish Breaker 진입
        for bb in bear_bb:
            if bb["bot"] * 0.999 <= price <= bb["top"] * 1.001:
                sl  = round(bb["top"] * 1.0005, 1)
                tp1_cands = [l["p"] for l in lows if l["p"] < price]
                if not tp1_cands:
                    continue
                tp1 = round(max(tp1_cands), 1)
                if sl > price > tp1 and (price - tp1) / max(sl - price, 1e-9) >= 1.5:
                    return TradeSignal(
                        direction   = "short",
                        entry       = price,
                        sl          = sl,
                        tp1         = tp1,
                        tp2         = None,
                        reason      = f"BearBreaker숏 {bb['bot']:.0f}~{bb['top']:.0f}",
                        pattern_key = f"{self.name}_short",
                    )

        return None


STRATEGIES = {
    s.name: s
    for s in [ICTKillzoneStrategy(), ICTOTEStrategy(), ICTBreakerStrategy()]
}
