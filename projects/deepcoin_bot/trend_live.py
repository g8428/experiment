"""
trend_live.py — 일봉 + 4시간봉 롱 추세돌파 (라이브용)

2026-10-01 전략 재검증(research/전략재검증_2026-10-01.md)에서 살아남은 전략을 라이브에 올린다.
신호 로직은 backtest/strategies_v2.py(RegimeTrend)를 그대로 재사용한다 — 백테스트와 라이브가
같은 코드를 쓰므로 "전략 로직을 두 벌 두지 말 것" 원칙을 지킨다. 이 파일은 그 위에
  · 캔들 수집/캐시 (완결 봉만 사용),
  · 포지션 컨텍스트(추적 손절·타임스탑·레버리지/사이징) 계산
만 얹는다. 주문 전송·상태 저장은 server.py가 한다.

전략 요약
  국면(완결 일봉): 종가>EMA50, EMA20>EMA50, EMA50 5일 기울기>0 이면 '상승' — 상승일 때만 진입
  진입: 일봉 마감 시 20일 고가 돌파 / 4H 마감 시 20봉 고가 돌파 (D1 상승 필터)
  쇼크: 1H ATR%가 최근 90일 97분위 초과 시 신규 진입 금지
  손절: 2×ATR(D1 또는 4H) · 추적: 3×ATR 샹들리에 · 4H 진입은 10일 타임스탑
  판단 시점: 1H 봉이 마감된 직후 1회 (미완성 캔들로 판단하지 않는다)
"""

import math
import os
import sys
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_BT = os.path.join(_HERE, "backtest")
if _BT not in sys.path:
    sys.path.insert(0, _BT)

try:
    import numpy as np
    import pandas as pd
    import engine_v2 as E
    import strategies_v2 as S
    import data_fetcher as DF
    AVAILABLE = True
    IMPORT_ERROR = ""
except Exception as _e:   # pandas/numpy 없음 등 — 서버는 계속 돌고 추세 전략만 비활성
    AVAILABLE = False
    IMPORT_ERROR = str(_e)

TF_MS = {"1H": 3_600_000, "1D": 86_400_000}
H1_DAYS = 100          # 1H 약 2400봉 (쇼크 필터의 90일 분위수 계산용)
D1_BARS = 300
SIGNAL_MAX_AGE_SEC = 1200   # 봉 마감 후 20분이 지난 신호는 폐기 (재시작/쿨다운으로 늦은 진입 방지)
REGIME_LABEL = {1: "상승", -1: "하락", 0: "횡보"}

_lock = threading.Lock()
_cache = {}      # sym -> {"h1": df, "d1": df, "fetched_at": ts, "eval": {...}, "eval_bar": t, "err": str}
_consumed = {}   # sym -> 마지막으로 진입에 쓴(또는 쓰려다 막힌) 신호의 봉 t


# ─────────────────────────── 데이터 ───────────────────────────

def _to_df(kl, tf):
    df = pd.DataFrame(kl).drop_duplicates("t").sort_values("t").reset_index(drop=True)
    df["ct"] = df["t"] + TF_MS[tf]
    return df


def _closed(df, now_ms):
    return df[df["ct"] <= now_ms].reset_index(drop=True)


def _fetch_range_retry(sym, bar, start_ms, end_ms, tries=3):
    last = None
    for _ in range(tries):
        try:
            return DF.fetch_range(sym, bar, start_ms, end_ms)
        except Exception as e:
            last = e
            time.sleep(1.5)
    raise RuntimeError(f"{sym} {bar} 수집 실패: {last}")


def _merge(old_df, new_kl, tf, keep):
    recs = {int(r["t"]): r for r in old_df[["t", "o", "h", "l", "c", "v"]].to_dict("records")}
    for k in new_kl:
        recs[int(k["t"])] = k          # 새로 받은 값이 이긴다 (진행 중이던 봉이 확정값으로 갱신됨)
    return _to_df(list(recs.values()), tf).tail(keep).reset_index(drop=True)


def _refresh(sym, now_ms):
    """1H/1D 캔들을 갱신한다. 첫 호출은 전체, 이후엔 최근 구간만 받아 병합."""
    c = _cache.setdefault(sym, {})
    if "h1" not in c:
        h1 = _fetch_range_retry(sym, "1H", now_ms - H1_DAYS * 86_400_000, now_ms)
        d1 = _fetch_range_retry(sym, "1D", now_ms - D1_BARS * 86_400_000, now_ms)
        c["h1"], c["d1"] = _to_df(h1, "1H"), _to_df(d1, "1D")
    else:
        h1n = _fetch_range_retry(sym, "1H", now_ms - 12 * 3_600_000, now_ms)
        d1n = _fetch_range_retry(sym, "1D", now_ms - 5 * 86_400_000, now_ms)
        c["h1"] = _merge(c["h1"], h1n, "1H", H1_DAYS * 24 + 48)
        c["d1"] = _merge(c["d1"], d1n, "1D", D1_BARS + 10)
    c["fetched_at"] = time.time()


# ─────────────────────────── 신호 계산 (순수 함수) ───────────────────────────

def compute(h1_closed, d1_closed, allow_short=False):
    """완결된 1H/1D DataFrame만 받아 마지막 1H 봉 기준으로 신호/상태를 계산한다.
    백테스트(engine_v2 + strategies_v2.RegimeTrend)와 같은 경로 — 테스트에서 동치 검증."""
    if len(h1_closed) < 24 * 40 or len(d1_closed) < 70:
        return {"ok": False, "reason": "데이터 부족", "signal": None}
    data = {"1H": h1_closed, "1D": d1_closed}
    data["4H"] = E.resample(h1_closed, "1H", "4H")
    strat = S.RegimeTrend(allow_short=allow_short)
    strat.prepare(data)
    ctx = E.Ctx(data, "1H")
    i = len(h1_closed) - 1
    reg, adx4, n4 = strat.regime(i, ctx)
    sig = strat.signal(i, ctx)

    nd = ctx.n_closed("1D", i)
    d1 = d1_closed
    levels = {}
    if nd >= 22:
        j = nd - 1
        levels["d1_breakout"] = float(d1["h"].values[j - 20:j].max())
        levels["d1_ema50"] = float(E.ema(d1["c"], 50).values[j])
        levels["d1_atr"] = float(E.atr(d1, 14).values[j])
    h4 = data["4H"]
    n4c = ctx.n_closed("4H", i)
    if n4c >= 22:
        j4 = n4c - 1
        levels["h4_breakout"] = float(h4["h"].values[j4 - 20:j4].max())
        levels["h4_atr"] = float(E.atr(h4, 14).values[j4])
    shock = bool(strat.shock[i])

    out = {
        "ok": True, "bar_t": int(h1_closed["t"].iloc[-1]), "bar_ct": int(h1_closed["ct"].iloc[-1]),
        "bar_close": float(h1_closed["c"].iloc[-1]),
        "regime": None if reg is None else int(reg),
        "regime_label": "-" if reg is None else REGIME_LABEL[int(reg)],
        "adx4": None if adx4 is None else round(float(adx4), 1),
        "shock": shock, "levels": levels, "signal": None, "reason": "",
    }
    if sig:
        ref = float(h1_closed["c"].iloc[-1])
        stop_dist = (ref - sig["sl"]) / ref * sig["dir"]
        out["signal"] = {
            "dir": int(sig["dir"]), "tag": sig.get("tag", ""), "ref": ref,
            "stop_dist": float(stop_dist), "trail_dist": float(sig.get("trail_dist") or 0.0),
            "trail_after_r": float(sig.get("trail_after_r", 1.0)),
            "time_stop_h": sig.get("time_stop"),
        }
        out["reason"] = f"{sig.get('tag')} 돌파 — 손절 {stop_dist*100:.2f}%"
    elif reg is None:
        out["reason"] = "국면 판정 데이터 부족"
    elif shock:
        out["reason"] = "변동성 쇼크 — 신규 진입 금지"
    elif reg != 1:
        out["reason"] = f"일봉 국면 {REGIME_LABEL[int(reg)]} — 롱 진입 안 함 (현금 대기)"
    else:
        out["reason"] = "상승추세 — 돌파 대기"
    return out


def evaluate(sym, allow_short=False, force_refresh=False):
    """라이브용: 새 1H 봉이 마감됐을 때만 다시 계산한다(그 사이엔 캐시 반환).
    반환 dict에 "signal"이 있으면 이번 봉에서 막 나온 신호다. 같은 봉의 신호는 consume()된 뒤엔 다시 나오지 않고,
    봉 마감 후 SIGNAL_MAX_AGE_SEC가 지난 신호는 버린다."""
    if not AVAILABLE:
        return {"ok": False, "reason": f"추세 모듈 비활성: {IMPORT_ERROR}", "signal": None}
    now_ms = int(time.time() * 1000)
    with _lock:
        c = _cache.setdefault(sym, {})
        last_closed_t = (now_ms // TF_MS["1H"]) * TF_MS["1H"] - TF_MS["1H"]
        ev = c.get("eval")
        # 새 봉이 마감됐거나, API가 막 마감된 봉을 아직 안 내려줬으면(45초 간격으로) 다시 받는다
        lagging = ev is not None and ev.get("bar_t", 0) < last_closed_t and time.time() - c.get("eval_at", 0) > 45
        stale = force_refresh or ev is None or c.get("eval_for") != last_closed_t or lagging
        if stale:
            try:
                _refresh(sym, now_ms)
                h1c, d1c = _closed(c["h1"], now_ms), _closed(c["d1"], now_ms)
                res = compute(h1c, d1c, allow_short=allow_short)
                c["eval"], c["eval_at"], c["err"] = res, time.time(), ""
                c["eval_for"] = last_closed_t
            except Exception as e:
                c["err"], c["eval_at"] = str(e), time.time()
                if ev is None:
                    return {"ok": False, "reason": f"데이터 수집 실패: {e}", "signal": None}
        res = dict(c.get("eval") or {"ok": False, "reason": "평가 전", "signal": None})
        res["error"] = c.get("err", "")
        res["fetched_at"] = c.get("fetched_at")
        if res.get("signal"):
            age = now_ms / 1000 - res["bar_ct"] / 1000
            if _consumed.get(sym) == res["bar_t"]:
                res["signal"], res["reason"] = None, "이번 봉 신호는 이미 처리됨"
            elif age > SIGNAL_MAX_AGE_SEC:
                res["signal"], res["reason"] = None, f"신호 {int(age/60)}분 경과 — 폐기 (봉 마감 직후에만 진입)"
            elif res["bar_t"] != last_closed_t:
                res["signal"], res["reason"] = None, "신호 봉이 최신 마감 봉이 아님 — 폐기"
        return res


def consume(sym, bar_t):
    """이 봉의 신호를 처리했다(진입했거나, 게이트에 막혔어도 다시 쓰지 않는다)."""
    _consumed[sym] = bar_t


def closed_h1(sym):
    """포지션 관리용: 캐시된 완결 1H 봉 (없으면 None)."""
    c = _cache.get(sym)
    if not c or "h1" not in c:
        return None
    return _closed(c["h1"], int(time.time() * 1000))


# ─────────────────────────── 사이징 / 레버리지 ───────────────────────────

def pick_leverage(stop_dist, max_lev=20, liq_mult=2.0):
    """격리마진에서 청산가(≈1/lev)가 손절폭의 liq_mult배 밖에 있도록 레버리지를 낮춘다.
    예) 손절 5% → 10x (청산 ≈10%), 손절 2% → 20x (청산 ≈5%). 20x 고정이면 손절 5%가 청산(≈5%)보다 멀어
    손절 전에 청산될 수 있다."""
    if stop_dist <= 0:
        return 1
    return int(max(1, min(max_lev, math.floor(1.0 / (liq_mult * stop_dist)))))


def margin_pct(risk_pct, stop_dist, lev, cap=80.0):
    """1회 손절 시 계좌 risk_pct%를 잃도록 하는 증거금 비율(%). 명목가 = 증거금 × lev."""
    if stop_dist <= 0 or lev <= 0:
        return 0.0
    return min(cap, risk_pct / (stop_dist * lev))


# ─────────────────────────── 포지션 컨텍스트 ───────────────────────────

def new_ctx(sig, entry, lev, now=None, size_pct=None):
    """진입 직후 포지션 컨텍스트. 손절은 '신호 시점 종가 대비 거리'를 체결가에 적용(백테스트와 동일)."""
    now = now or time.time()
    d = sig["dir"]
    dist = sig["stop_dist"]
    sl = entry * (1 - d * dist)
    return {
        "v": 1, "tag": sig["tag"], "dir": d, "entry": entry, "init_sl": sl, "sl": sl,
        "R": entry * dist, "stop_dist": dist,
        "trail_dist": sig["trail_dist"], "trail_after_r": sig["trail_after_r"],
        "time_stop_h": sig.get("time_stop_h"), "opened_ts": now,
        "opened_bar_t": int(now * 1000) // TF_MS["1H"] * TF_MS["1H"],
        "best": entry, "last_bar_t": None, "lev": lev, "size_pct": size_pct,
        "trail_on": False,
    }


def manage(ctx, price, now=None, h1=None):
    """30초 루프에서 호출. 새로 마감된 1H 봉으로 추적 손절을 갱신하고(백테스트와 같은 시점),
    현재가로 손절/타임스탑 청산 여부를 판단한다. 반환: (exit_kind|None, 메시지)
    exit_kind: "SL"(최초 손절) | "TRAIL"(추적 손절) | "TIME"(타임스탑)"""
    now = now or time.time()
    d = ctx["dir"]
    if h1 is not None and len(h1):
        t0 = ctx["last_bar_t"] if ctx["last_bar_t"] is not None else ctx["opened_bar_t"] - 1
        new = h1[h1["t"] > t0]
        for t, hi, lo in zip(new["t"].values, new["h"].values, new["l"].values):
            ctx["best"] = max(ctx["best"], float(hi)) if d == 1 else min(ctx["best"], float(lo))
            gain_r = (ctx["best"] - ctx["entry"]) * d / ctx["R"]
            if ctx["trail_dist"] and gain_r >= ctx["trail_after_r"]:
                ch = ctx["best"] - d * ctx["trail_dist"]
                ctx["sl"] = max(ctx["sl"], ch) if d == 1 else min(ctx["sl"], ch)
                ctx["trail_on"] = True
            ctx["last_bar_t"] = int(t)
    if (d == 1 and price <= ctx["sl"]) or (d == -1 and price >= ctx["sl"]):
        kind = "SL" if abs(ctx["sl"] - ctx["init_sl"]) < 1e-12 else "TRAIL"
        return kind, f"{'최초 손절' if kind == 'SL' else '추적 손절'} {ctx['sl']:.6g} 터치"
    ts = ctx.get("time_stop_h")
    if ts and (now - ctx["opened_ts"]) / 3600.0 >= ts:
        return "TIME", f"타임스탑 {ts}시간 경과"
    return None, ""
