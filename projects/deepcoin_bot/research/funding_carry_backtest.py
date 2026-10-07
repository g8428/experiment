"""Deepcoin cash-and-carry simulation using actual spot/swap candles and funding.

Uses 1h candles to approximate fills/marks. Enters just after the first fetched
funding event, then applies subsequent events; exits just after the last event.
This is historical simulation, not a live order or account action.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "backtest" / "cache"
RATE_OUT = ROOT / "research" / "funding_rate_cache_2025-10_to_2026-10.json"
SPOT_OUT = ROOT / "research" / "spot_candle_cache_2025-10_to_2026-10.json"
SYMBOLS = {
    "BTC-USDT-SWAP": "BTC-USDT",
    "ETH-USDT-SWAP": "ETH-USDT",
    "XRP-USDT-SWAP": "XRP-USDT",
}
API = "https://api.deepcoin.com/deepcoin"
TAKER_FEE = 0.0006  # project handover's documented 0.06% Deepcoin taker fee
SLIPPAGE = 0.0001   # 1bp per fill: explicit stress assumption, no historical book data


def utc(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "DeepcoinCarryResearch/1.0"})
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_rates() -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for symbol in SYMBOLS:
        rows: dict[int, dict] = {}
        for page in range(1, 50):
            query = urllib.parse.urlencode({"instId": symbol, "limit": 100, "page": page})
            payload = get_json(f"{API}/v2/market/fund-rate/history?{query}")
            if str(payload.get("code")) != "0":
                raise RuntimeError(f"Funding API error for {symbol}, page {page}: {payload}")
            batch = payload.get("data") or []
            if not batch:
                break
            for item in batch:
                ts = int(item["CreateTime"])
                if ts > 10**12:
                    ts //= 1000
                rows[ts] = {"timestamp": ts, "rate": float(item["rate"])}
            if len(batch) < 100:
                break
        result[symbol] = sorted(rows.values(), key=lambda row: row["timestamp"])
    RATE_OUT.write_text(json.dumps({"source": f"{API}/v2/market/fund-rate/history", "fetched_at_utc": datetime.now(timezone.utc).isoformat(), "rates": result}, indent=2), encoding="utf-8")
    return result


def load_swap(symbol: str) -> list[dict]:
    path = CACHE_DIR / f"{symbol}_1H_1460d.json"
    return sorted(json.loads(path.read_text(encoding="utf-8")), key=lambda row: int(row["t"]))


def fetch_spot(inst_id: str, start_ms: int) -> list[dict]:
    rows: dict[int, dict] = {}
    after: int | None = None
    for _ in range(100):
        params = {"instId": inst_id, "bar": "1H", "limit": 300}
        if after is not None:
            params["after"] = after
        payload = get_json(f"{API}/market/candles?{urllib.parse.urlencode(params)}")
        if str(payload.get("code")) != "0":
            raise RuntimeError(f"Spot candle API error for {inst_id}: {payload}")
        batch = payload.get("data") or []
        if not batch:
            break
        for candle in batch:
            ts = int(candle[0])
            if ts >= start_ms - 3_600_000:
                rows[ts] = {"t": ts, "o": float(candle[1]), "h": float(candle[2]), "l": float(candle[3]), "c": float(candle[4]), "v": float(candle[5])}
        oldest = min(int(candle[0]) for candle in batch)
        if oldest <= start_ms - 3_600_000:
            break
        if after == oldest:
            raise RuntimeError(f"Spot candle pagination stopped advancing for {inst_id}")
        after = oldest
        time.sleep(0.03)
    return sorted(rows.values(), key=lambda row: row["t"])


def basis_pnl_pct(notional: float, qty: float, entry_basis: float, spot_px: float, swap_px: float) -> float:
    return -qty * ((spot_px - swap_px) - entry_basis) / notional * 100.0


def simulate(symbol: str, rates: list[dict], spots: list[dict]) -> dict:
    swaps = load_swap(symbol)
    spot_by_ts = {int(row["t"]): row for row in spots}
    swap_by_ts = {int(row["t"]): row for row in swaps}
    # A few history events are timestamped four seconds after the hour; map
    # them to the 1h candle that was already open at the settlement instant.
    def candle_ts(row: dict) -> int:
        return int(row["timestamp"] * 1000) // 3_600_000 * 3_600_000

    usable = [row for row in rates if candle_ts(row) in spot_by_ts and candle_ts(row) in swap_by_ts]
    if len(usable) < 100:
        raise RuntimeError(f"Insufficient synchronized bars/funding for {symbol}: {len(usable)}")

    # Enter immediately after the first settlement and do not claim its funding.
    entry_rate_event = usable[0]
    entry_ts_ms = candle_ts(entry_rate_event)
    last_ts_ms = candle_ts(usable[-1])
    spot_entry = float(spot_by_ts[entry_ts_ms]["o"])
    swap_entry = float(swap_by_ts[entry_ts_ms]["o"])
    entry_basis = spot_entry - swap_entry
    entry_notional = (spot_entry + swap_entry) / 2.0  # normalize initial matched notional to 1
    qty = 1.0 / entry_notional

    events = [row for row in usable if row["timestamp"] > entry_rate_event["timestamp"]]
    event_by_ts = {candle_ts(row): row for row in events}
    funding = 0.0
    curve: list[tuple[int, float]] = []
    for candle_ts in sorted(ts for ts in spot_by_ts if entry_ts_ms <= ts < last_ts_ms):
        rate_row = event_by_ts.get(candle_ts)
        if rate_row:
            amount = float(rate_row["rate"]) * qty * float(swap_by_ts[candle_ts]["o"])
            funding += amount
        spot_close = float(spot_by_ts[candle_ts]["c"])
        swap_close = float(swap_by_ts[candle_ts]["c"])
        basis_pnl = -qty * ((spot_close - swap_close) - entry_basis)
        curve.append((candle_ts, funding + basis_pnl))

    spot_exit = float(spot_by_ts[last_ts_ms]["o"])
    swap_exit = float(swap_by_ts[last_ts_ms]["o"])
    basis_pnl = -qty * ((spot_exit - swap_exit) - entry_basis)
    exit_notional = qty * (spot_exit + swap_exit) / 2.0
    # Two instruments on entry and two on exit. Apply fee and 1bp slippage to each fill.
    cost_per_fill = TAKER_FEE + SLIPPAGE
    entry_cost = cost_per_fill * 2.0  # two initial legs, normalized by entry notional
    exit_cost = cost_per_fill * 2.0 * exit_notional
    costs = entry_cost + exit_cost
    stress_costs = (0.001 + SLIPPAGE) * 2.0 * (1.0 + exit_notional)
    gross_pct = (funding + basis_pnl) * 100.0
    max_dd = 0.0
    peak = 0.0
    for _, value in curve:
        value -= entry_cost
        peak = max(peak, value)
        max_dd = max(max_dd, peak - value)
    max_dd = max(max_dd, peak - (funding + basis_pnl - costs))
    net_pre_basis_pct = None
    rate_vals = [float(row["rate"]) for row in events]
    return {
        "symbol": symbol,
        "funding_events_received": len(events),
        "start_utc_after_entry": utc(entry_rate_event["timestamp"]),
        "exit_utc": utc(usable[-1]["timestamp"]),
        "synchronized_funding_events": len(usable),
        "spot_entry": spot_entry,
        "swap_entry": swap_entry,
        "entry_basis_pct_of_swap": entry_basis / swap_entry * 100,
        "spot_exit": spot_exit,
        "swap_exit": swap_exit,
        "exit_basis_pct_of_swap": (spot_exit - swap_exit) / swap_exit * 100,
        "funding_cashflow_pct_initial_matched_notional": funding * 100,
        "basis_pnl_pct_initial_matched_notional": basis_pnl * 100,
        "gross_pnl_pct_initial_matched_notional": gross_pct,
        "fees_plus_slippage_0_06pct_fee_per_fill_pct": costs * 100,
        "net_pnl_pct_initial_matched_notional": gross_pct - costs * 100,
        "net_pnl_0_10pct_fee_per_fill_stress_pct": gross_pct - stress_costs * 100,
        "cash_plus_basis_max_drawdown_pct_initial_matched_notional": max_dd * 100,
        "positive_funding_events_pct": 100 * sum(value > 0 for value in rate_vals) / len(rate_vals),
        "funding_rate_mean_per_event_pct": 100 * sum(rate_vals) / len(rate_vals),
        "first_event_excluded": True,
        "assumptions": {
            "historical_swap_and_spot_1h_candles": True,
            "matched_quantity_held_constant": True,
            "project_taker_fee_per_fill": TAKER_FEE,
            "slippage_per_fill_assumption": SLIPPAGE,
            "mark_at_settlement": "swap 1h candle open at funding timestamp",
            "capital_return_denominator": "initial matched notional, not account equity",
            "liquidation_and_margin_allocation_modeled": False,
        },
    }


def main() -> None:
    rates_by_symbol = fetch_rates()
    spots_by_symbol = {}
    for symbol, spot_inst_id in SYMBOLS.items():
        rates = rates_by_symbol[symbol]
        start_ms = min(row["timestamp"] for row in rates) * 1000
        spots_by_symbol[symbol] = fetch_spot(spot_inst_id, start_ms)
    SPOT_OUT.write_text(json.dumps({"source": f"{API}/market/candles", "fetched_at_utc": datetime.now(timezone.utc).isoformat(), "bar": "1H", "candles": spots_by_symbol}, indent=2), encoding="utf-8")
    results = [simulate(symbol, rates_by_symbol[symbol], spots_by_symbol[symbol]) for symbol in SYMBOLS]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"Funding cache: {RATE_OUT}")
    print(f"Spot candle cache: {SPOT_OUT}")


if __name__ == "__main__":
    main()
