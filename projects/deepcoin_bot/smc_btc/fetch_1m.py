"""Deepcoin 1분봉 수집 → backtest/cache/{sym}_1m/YYYY-MM.csv (월별, 이어받기 가능).

python fetch_1m.py [SYM] [START=2024-10]
- 이미 끝난 달의 파일이 있으면 건너뛴다. 진행 중인 달은 매번 다시 받는다.
- 캔들 캐시는 커밋하지 않는다(로컬 전용).
"""
import calendar
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

API = "https://api.deepcoin.com/deepcoin/market/candles"
ROOT = os.path.join(os.path.dirname(__file__), "..", "backtest", "cache")


def page(sym, after_ms, retries=5):
    url = f"{API}?instId={sym}&bar=1m&limit=300&after={after_ms}"
    for k in range(retries):
        try:
            resp = json.loads(urllib.request.urlopen(urllib.request.Request(url), timeout=15).read())
            raw = resp.get("data", resp) if isinstance(resp, dict) else resp
            return sorted((int(r[0]), r[1], r[2], r[3], r[4], r[5]) for r in raw)
        except Exception as e:  # 네트워크/레이트리밋 → 백오프 재시도
            time.sleep(2 * (k + 1))
            err = e
    raise RuntimeError(f"fetch 실패 after={after_ms}: {err}")


def fetch_month(sym, y, m, out_dir):
    start = int(datetime(y, m, 1, tzinfo=timezone.utc).timestamp() * 1000)
    last_day = calendar.monthrange(y, m)[1]
    end = int(datetime(y, m, last_day, 23, 59, tzinfo=timezone.utc).timestamp() * 1000) + 60_000
    now = int(time.time() * 1000)
    done = end <= now
    path = os.path.join(out_dir, f"{y:04d}-{m:02d}.csv")
    if done and os.path.exists(path):
        return 0
    rows, after = {}, min(end, now)
    while True:
        p = page(sym, after)
        if not p:
            break
        for r in p:
            if start <= r[0] < end:
                rows[r[0]] = r
        oldest = p[0][0]
        if oldest <= start or oldest >= after:
            break
        after = oldest
        time.sleep(0.15)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write("t,o,h,l,c,v\n")
        for r in sorted(rows.values()):
            f.write(",".join(str(x) for x in r) + "\n")
    os.replace(tmp, path)
    return len(rows)


def main():
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTC-USDT-SWAP"
    sy, sm = map(int, (sys.argv[2] if len(sys.argv) > 2 else "2024-10").split("-"))
    out_dir = os.path.join(ROOT, f"{sym}_1m")
    os.makedirs(out_dir, exist_ok=True)
    now = datetime.now(timezone.utc)
    y, m = sy, sm
    while (y, m) <= (now.year, now.month):
        t = time.time()
        n = fetch_month(sym, y, m, out_dir)
        print(f"{y}-{m:02d}: {n} 봉 ({time.time()-t:.0f}s)" if n else f"{y}-{m:02d}: 캐시 있음", flush=True)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    print("완료", flush=True)


if __name__ == "__main__":
    main()
