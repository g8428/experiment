"""A-rule Ichimoku cloud regime strategy, ready to be called by the bot.

This module is deliberately independent of the live entry chain. It evaluates
one symbol at a time and returns the target state implied by the A definition.
"""

from datetime import datetime, timezone


TENKAN_PERIOD = 9
KIJUN_PERIOD = 26
SENKOU_B_PERIOD = 52
CLOUD_DISPLACEMENT = 26
DAY_MS = 86_400_000


def _midpoint(candles, end, period):
    start = end - period + 1
    if start < 0:
        return None
    window = candles[start:end + 1]
    return (max(float(c["h"]) for c in window) +
            min(float(c["l"]) for c in window)) / 2.0


def _closed_candles(candles, now_ms=None):
    """Return chronologically sorted candles, excluding an unfinished D1 bar."""
    ordered = sorted(candles, key=lambda c: int(c["t"]))
    if not ordered:
        return ordered
    if now_ms is None:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    # Deepcoin candle timestamps are milliseconds; a D1 bar closes 24h later.
    if int(ordered[-1]["t"]) + DAY_MS > now_ms:
        ordered = ordered[:-1]
    return ordered


def evaluate(candles, symbol, position=None, now_ms=None):
    """Evaluate A's current-visible-cloud rule for a symbol.

    Args:
        candles: D1 candles shaped like server._klines output (t/o/h/l/c/v).
        symbol: Exchange instrument identifier, e.g. ``ETH-USDT-SWAP``.
        position: Current position side: ``"long"``, ``"short"``, or None.
        now_ms: Optional UTC epoch milliseconds, useful for deterministic replay.

    Returns a dict with ``signal`` (LONG/SHORT/None), ``action`` (ENTER,
    EXIT, HOLD, or FLAT), and visible cloud levels. A neutral state exits any
    open position; a direct direction change requests a close-and-reverse.
    Decisions use only the latest completed daily close.
    """
    kl = _closed_candles(candles, now_ms=now_ms)
    required = CLOUD_DISPLACEMENT + SENKOU_B_PERIOD
    base = {"symbol": symbol, "strategy": "ICHIMOKU_A", "signal": None,
            "action": "WAIT", "reason": "일봉 데이터 부족", "position": position}
    if len(kl) < required:
        return base

    i = len(kl) - 1
    source_i = i - CLOUD_DISPLACEMENT
    tenkan = _midpoint(kl, source_i, TENKAN_PERIOD)
    kijun = _midpoint(kl, source_i, KIJUN_PERIOD)
    span_a = (tenkan + kijun) / 2.0
    span_b = _midpoint(kl, source_i, SENKOU_B_PERIOD)
    cloud_top, cloud_bottom = max(span_a, span_b), min(span_a, span_b)
    close = float(kl[i]["c"])

    if close > cloud_top:
        target, reason = "LONG", "완결 일봉 종가가 현재 표시 구름 상단 위"
    elif close < cloud_bottom:
        target, reason = "SHORT", "완결 일봉 종가가 현재 표시 구름 하단 아래"
    else:
        target, reason = None, "완결 일봉 종가가 현재 표시 구름 안"

    side = (position or "").lower()
    current = "LONG" if side == "long" else "SHORT" if side == "short" else None
    if target == current:
        action = "HOLD" if target else "FLAT"
    elif target is None:
        action = "EXIT" if current else "FLAT"
    elif current is None:
        action = "ENTER"
    else:
        action = "REVERSE"

    return {"symbol": symbol, "strategy": "ICHIMOKU_A", "signal": target,
            "action": action, "reason": reason, "position": position,
            "close": close, "cloud_top": cloud_top, "cloud_bottom": cloud_bottom,
            "candle_time": int(kl[i]["t"]), "timeframe": "1D"}
