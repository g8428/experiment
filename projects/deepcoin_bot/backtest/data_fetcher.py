"""
data_fetcher.py — Deepcoin API 과거 캔들 데이터 수집 + 파일 캐시
캐시 경로: backtest/cache/{sym}_{bar}_{days}d.json
날짜와 무관하게 캐시를 재사용한다 — 최신 데이터가 필요하면 fetch_historical(refresh=True) 또는 run.py --refresh
"""

import json
import os
import time
import urllib.request

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
API_BASE  = "https://api.deepcoin.com/deepcoin/market/candles"


def _cache_path(sym, bar, cache_key):
    os.makedirs(CACHE_DIR, exist_ok=True)
    safe_sym = sym.replace("/", "-")
    return os.path.join(CACHE_DIR, f"{safe_sym}_{bar}_{cache_key}.json")


def _fetch_page(sym, bar, after_ms=None, limit=300):
    """단일 페이지 캔들 fetch. after_ms 이전(오래된) 데이터 반환."""
    b = bar.upper() if bar.endswith("h") else bar
    url = f"{API_BASE}?instId={sym}&bar={b}&limit={limit}"
    if after_ms:
        url += f"&after={after_ms}"
    req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
    raw  = resp.get("data", resp) if isinstance(resp, dict) else resp
    kl   = [
        {"t": int(k[0]), "o": float(k[1]), "h": float(k[2]),
         "l": float(k[3]), "c": float(k[4]), "v": float(k[5])}
        for k in raw
    ]
    kl.sort(key=lambda x: x["t"])
    return kl


def fetch_range(sym, bar, start_ms, end_ms):
    """특정 기간 캔들 데이터 반환 (ms timestamp). 페이지네이션으로 전체 수집."""
    all_kl  = []
    after   = end_ms
    seen_ts = set()

    while True:
        page = _fetch_page(sym, bar, after_ms=after)
        if not page:
            break
        new = [k for k in page if k["t"] >= start_ms and k["t"] not in seen_ts]
        for k in new:
            seen_ts.add(k["t"])
        all_kl.extend(new)
        oldest = min(k["t"] for k in page)
        if oldest <= start_ms or not new:
            break
        after = oldest
        time.sleep(0.2)

    all_kl.sort(key=lambda x: x["t"])
    return all_kl


def fetch_historical(sym="BTC-USDT-SWAP", bar="15m", days=30, refresh=False):
    """최근 days일치 캔들 데이터 반환.
    캐시는 날짜와 무관하게 재사용 — 명시적으로 refresh=True(--refresh)를 줄 때만 다시 수집한다."""
    path = _cache_path(sym, bar, f"{days}d")

    if os.path.exists(path) and not refresh:
        with open(path, "r") as f:
            return json.load(f)

    now_ms   = int(time.time() * 1000)
    start_ms = now_ms - days * 24 * 3600 * 1000
    kl       = fetch_range(sym, bar, start_ms, now_ms)

    if kl:
        with open(path, "w") as f:
            json.dump(kl, f)

    return kl
