"""
strategy.py — 백테스팅용 전략 래퍼

전략 로직은 전부 ict_engine.py의 get_ote_signal / get_mtf_signal / get_killzone_signal /
get_breaker_signal 에 있다 (라이브 server.py와 같은 함수). 여기서는 그 결과를 TradeSignal로
감싸기만 한다 — 백테스트 숫자 = 실거래 로직의 결과가 되도록 로직을 두 벌 두지 않는다.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dataclasses import dataclass
from typing import Optional
from ict_engine import (
    get_ote_signal, get_mtf_signal, get_killzone_signal, get_breaker_signal,
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
    fn = None
    key_with_kz = False   # pattern_key에 킬존 포함 여부 (weights.py 키 호환용)

    def signal(self, kl, h1_kl=None, d1_kl=None, m5_kl=None,
               m15_confirm_n: int = 0, require_h1_trend: bool = True) -> Optional[TradeSignal]:
        if not kl:
            return None
        sig = self.fn(kl, h1_kl=h1_kl, d1_kl=d1_kl, m5_kl=m5_kl,
                       m15_confirm_n=m15_confirm_n, require_h1_trend=require_h1_trend)
        direction = sig.get("signal")
        if direction not in ("long", "short"):
            return None
        key = f"{self.name}_{direction}"
        if self.key_with_kz:
            key += f"_{sig.get('kz')}"
        return TradeSignal(
            direction   = direction,
            entry       = kl[-1]["c"],
            sl          = sig["sl"],
            tp1         = sig["tp1"],
            tp2         = sig.get("tp2"),
            reason      = sig.get("reason", ""),
            pattern_key = key,
        )


class ICTKillzoneStrategy(BaseStrategy):
    name = "ict_killzone"; fn = staticmethod(get_killzone_signal); key_with_kz = True

class ICTOTEStrategy(BaseStrategy):
    name = "ict_ote"; fn = staticmethod(get_ote_signal)

class ICTBreakerStrategy(BaseStrategy):
    name = "ict_breaker"; fn = staticmethod(get_breaker_signal)

class ICTMTFStrategy(BaseStrategy):
    name = "ict_mtf"; fn = staticmethod(get_mtf_signal); key_with_kz = True


STRATEGIES = {
    s.name: s
    for s in [
        ICTKillzoneStrategy(),
        ICTOTEStrategy(),
        ICTBreakerStrategy(),
        ICTMTFStrategy(),
    ]
}
