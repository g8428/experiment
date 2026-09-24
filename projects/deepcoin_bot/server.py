# -*- coding: utf-8 -*-
"""Deepcoin Bot v4 - Claude SMC 메인봇 | 거래로그 | 일별수익"""
import os, json, time, threading, sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone, timedelta

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

try:
    from ict_engine import (get_ict_signal, get_htf_trend, get_market_regime,
                             get_ote_signal, get_mtf_signal, get_killzone_signal,
                             get_breaker_signal)
    from smc_engine import find_swings, get_kill_zone, get_asian_range
    get_smc_signal = get_ict_signal  # ICT가 SMC superset
    _SMC_AVAILABLE = True
except ImportError:
    _SMC_AVAILABLE = False
    def get_kill_zone(*a, **kw): return None
    def get_asian_range(*a, **kw): return None
    def get_ict_signal(*a, **kw): return {"signal": None}
    def get_ote_signal(*a, **kw): return {"signal": None}
    def get_mtf_signal(*a, **kw): return {"signal": None}
    def get_killzone_signal(*a, **kw): return {"signal": None}
    def get_breaker_signal(*a, **kw): return {"signal": None}

# 라이브 멀티전략 우선순위 (2026-09-23 6개월 BTC 백테스트 성과순):
# OTE(+164.75%) → MTF(+20.60%) → 킬존NY전용(+25.16%) → Breaker(-26.53%, 최후)
_SIGNAL_CHAIN = [
    ("OTE", lambda kl, h1, d1, m5: get_ote_signal(kl, h1_kl=h1, d1_kl=d1)),
    ("MTF", lambda kl, h1, d1, m5: get_mtf_signal(kl, h1_kl=h1, d1_kl=d1, m5_kl=m5)),
    ("KZ-NY", lambda kl, h1, d1, m5: get_killzone_signal(kl, h1_kl=h1, d1_kl=d1)),
    ("BRK", lambda kl, h1, d1, m5: get_breaker_signal(kl, h1_kl=h1, d1_kl=d1)),
]

def _multi_strategy_signal(kl, h1_kl, d1_kl, m5_kl):
    """우선순위 체인을 순서대로 시도해 가장 먼저 나오는 시그널을 채택.
    반환: (smc_dict, 시그널 낸 전략명 또는 None)
    아무 것도 안 나오면 MTF 결과(OB/FVG 진단 정보 보유)를 모니터링용으로 반환
    — Breaker/OTE는 진단 필드가 항상 0이라 그걸 보여주면 "얼마나 가까운지" 알 수 없음"""
    if not _SMC_AVAILABLE:
        return {"signal": None}, None
    diag = None
    for name, fn in _SIGNAL_CHAIN:
        smc = fn(kl, h1_kl, d1_kl, m5_kl)
        if name == "MTF":
            diag = smc
        if smc.get("signal"):
            return smc, name
    return (diag if diag is not None else smc), None

import sys as _sys_w
_sys_w.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest"))
try:
    from weights import get_weight as _get_weight
    _WEIGHTS_AVAILABLE = True
except ImportError:
    _WEIGHTS_AVAILABLE = False
    def _get_weight(key): return 1.0

# ── 환경변수 ───────────────────────────────────────────────────────
_env = {}
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1); _env[k.strip()] = v.strip()

def _e(k, d=""): return _env.get(k, os.environ.get(k, d))

# ── 딥코인 인증 모듈 ─────────────────────────────────────────────
import hmac, hashlib, base64

DC_BASE = "https://api.deepcoin.com"

def _dc_auth(method, path, body_str=""):
    _now = datetime.now(timezone.utc)
    ts  = _now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{_now.microsecond//1000:03d}Z"
    raw = ts + method.upper() + path + (body_str or "")
    sk  = _e("DEEPCOIN_SECRET_KEY", "").encode()
    sig = base64.b64encode(
              hmac.new(sk, raw.encode(), hashlib.sha256).digest()
          ).decode()
    return {
        "Content-Type":         "application/json",
        "DC-ACCESS-KEY":        _e("DEEPCOIN_API_KEY", ""),
        "DC-ACCESS-SIGN":       sig,
        "DC-ACCESS-TIMESTAMP":  ts,
        "DC-ACCESS-PASSPHRASE": _e("DEEPCOIN_PASSPHRASE", ""),
    }

def _dc_request(method, path, body=None):
    import urllib.request as ur
    body_str = json.dumps(body) if body else ""
    headers  = _dc_auth(method, path, body_str)
    url = DC_BASE + path
    req = ur.Request(url,
        data=body_str.encode() if body_str else None,
        headers=headers, method=method.upper())
    try:
        r = ur.urlopen(req, timeout=8)
        return json.loads(r.read())
    except ur.HTTPError as e:
        return {"code": str(e.code), "msg": e.read().decode(), "data": None}
    except Exception as e:
        return {"code": "err", "msg": str(e), "data": None}


LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_logs", "daily")
_BASE    = os.path.dirname(os.path.abspath(__file__))
_PERSIST = os.path.join(_BASE, "trade_logs", "persist.json")
os.makedirs(LOGS_DIR, exist_ok=True)

# ── 심볼별 계약 사이즈 ────────────────────────────────────────────
_CONTRACT_SZ = {
    "BTC-USDT-SWAP": 0.001,   # 1계약 = 0.001 BTC
    "ETH-USDT-SWAP": 0.01,    # 1계약 = 0.01 ETH
    "XRP-USDT-SWAP": 1.0,     # 1계약 = 1 XRP
}
_ACTIVE_SYMS = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "XRP-USDT-SWAP"]
# 심볼별 가격 소수 자릿수 (TP/SL 주문가 반올림 + 표시)
_PX_DEC = {"BTC-USDT-SWAP": 1, "ETH-USDT-SWAP": 2, "XRP-USDT-SWAP": 4}

def _px_round(px, sym): return round(px, _PX_DEC.get(sym, 1))
def _px_fmt(px, sym):
    if px is None: return "-"
    return f"{px:,.{_PX_DEC.get(sym, 1)}f}"

def _default_st():
    return {
        "running": False, "position": None, "pnl": 0.0, "trades": 0,
        "mode": "sim", "indicators": {}, "can_trade": True, "stop_msg": "",
        "price": 0, "entry": None, "daily": {}, "watch_msg": "대기 중",
        "tp_px": None, "sl_px": None, "signal_score": None, "signal_bias": None,
        "last_close": 0,
    }

# ── 전역 상태 (심볼별) ────────────────────────────────────────────
_bots_st  = {sym: _default_st() for sym in _ACTIVE_SYMS}
_bots_thr = {sym: None for sym in _ACTIVE_SYMS}
_bots_gen = {sym: 0    for sym in _ACTIVE_SYMS}

_logs  = []
_daily = {}
_smc_event_log = {sym: [] for sym in _ACTIVE_SYMS}   # 심볼별 SMC 이벤트 로그 (최근 100건)
_pattern_stats = {}   # 패턴별 승률 통계 {pattern_key: {trades, wins, total_pnl}}

def _persist_load():
    global _logs, _daily, _pattern_stats
    if os.path.exists(_PERSIST):
        try:
            with open(_PERSIST, encoding="utf-8") as f:
                d = json.load(f)
            _logs          = d.get("logs",          [])[-500:]
            _daily         = d.get("daily",         {})
            _pattern_stats = d.get("pattern_stats", {})
            for sym, cb in (d.get("bot_states") or {}).items():
                st = _bots_st.get(sym)
                if not st or not cb.get("pos"): continue
                st.update({
                    "position": cb["pos"], "entry": cb.get("entry", 0.0),
                    "pnl": cb.get("sess_pnl", 0.0), "trades": cb.get("sess_tr", 0),
                    "mode": cb.get("mode", "sim"),
                    "tp_px": cb.get("tp_px"), "sl_px": cb.get("sl_px"),
                    "watch_msg": f"[재시작 복원] {cb['pos'].upper()} @ ${_px_fmt(cb.get('entry',0), sym)}",
                })
            print(f"[persist] 로드: 거래 {len(_logs)}건, 일별 {len(_daily)}일")
        except Exception as e:
            print(f"[persist] 로드 실패: {e}")

def _persist_save():
    try:
        bot_states = {
            sym: {
                "pos":      st.get("position"),
                "entry":    st.get("entry") or 0.0,
                "sess_pnl": st.get("pnl") or 0.0,
                "sess_tr":  st.get("trades") or 0,
                "mode":     st.get("mode", "sim"),
                "tp_px":    st.get("tp_px"),
                "sl_px":    st.get("sl_px"),
            } for sym, st in _bots_st.items()
        }
        with open(_PERSIST, "w", encoding="utf-8") as f:
            json.dump({"logs": _logs[-500:], "daily": _daily,
                       "bot_states": bot_states,
                       "pattern_stats": _pattern_stats}, f, ensure_ascii=False)
    except Exception as e:
        print(f"[persist] 저장 실패: {e}")


# ── 공통 한도 설정 (계좌 전체 기준, 3심볼 합산) ─────────────────────
_cfg = {
    "max_daily_trades":  7,
    "daily_profit_stop": 10.0,
    "daily_loss_stop":   25.0,   # risk_pct 10%/트레이드 기준 손실 2회까지 허용
    "max_daily_losses":  3,
}

# ── Claude 봇 설정 (메인 봇) ────────────────────────────────────
_claude_cfg = {
    "leverage":               20,
    "risk_pct":               10.0,
    "size_pct":               40,
    "cooldown":               900,
    "rr_min":                 2.5,
    "sl_cap_pct":             2.0,
    "tp_max_pct":             15.0,
    "tp_min_margin_pct":      0,
    "tp_min_margin_by_sym":   {},
}

# ── tuning.json 자동 반영 ─────────────────────────────────────────
import threading as _thr_mod

_TUNING_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tuning.json")
_tuning_mtime = 0.0
_active_syms_cfg = list(_ACTIVE_SYMS)   # tuning.json active_symbols (기본: 전체)

def _load_tuning():
    """tuning.json 읽어서 _cfg / _claude_cfg 업데이트"""
    global _cfg, _claude_cfg, _tuning_mtime, _active_syms_cfg
    try:
        mtime = os.path.getmtime(_TUNING_PATH)
        if mtime <= _tuning_mtime:
            return
        with open(_TUNING_PATH, encoding="utf-8") as f:
            t = json.load(f)
        for k in ("max_daily_trades", "daily_profit_stop", "daily_loss_stop", "max_daily_losses"):
            if k in t: _cfg[k] = t[k]
        for k in ("leverage", "risk_pct", "size_pct", "cooldown",
                  "rr_min", "sl_cap_pct", "tp_max_pct",
                  "tp_min_margin_pct", "tp_min_margin_by_sym"):
            if k in t: _claude_cfg[k] = t[k]
        if isinstance(t.get("active_symbols"), list):
            _active_syms_cfg = [s for s in t["active_symbols"] if s in _ACTIVE_SYMS]
        _tuning_mtime = mtime
        print(f"[tuning] v{t.get('version',0)} 반영 ({t.get('last_tuned','')})")
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[tuning] 로드 오류: {e}")

_load_tuning()

def _tuning_watcher():
    while True:
        try: _load_tuning()
        except Exception: pass
        import time as _t; _t.sleep(60)

_thr_mod.Thread(target=_tuning_watcher, daemon=True).start()
# ──────────────────────────────────────────────────────────────────


# ── 보조지표 계산 ──────────────────────────────────────────────────
def _ema(cl, n):
    if len(cl) < n: return cl[-1] if cl else 0.0
    k = 2.0/(n+1); e = sum(cl[:n])/n
    for p in cl[n:]: e = p*k + e*(1-k)
    return e

def _rsi(cl, n=14):
    if len(cl) < n+1: return 50.0
    d = [cl[i]-cl[i-1] for i in range(1,len(cl))]
    g = sum(max(x,0) for x in d[-n:])/n
    l = sum(max(-x,0) for x in d[-n:])/n
    return round(100.0 if l==0 else 100-100/(1+g/l), 2)

# ── 딥코인 klines (30초 캐시) ─────────────────────────────────────
_kl_cache = {}
_kl_lock  = threading.Lock()

def _klines(sym="BTC-USDT-SWAP", bar="15m", n=80):
    key = (sym, bar, n)
    with _kl_lock:
        c = _kl_cache.get(key)
        if c and time.time() - c["ts"] < 30:
            return c["data"]
    try:
        import urllib.request
        b = bar.upper() if bar.endswith("h") else bar
        url = (f"https://api.deepcoin.com/deepcoin/market/candles"
               f"?instId={sym}&bar={b}&limit={n}")
        r = urllib.request.urlopen(
            urllib.request.Request(url, headers={"Content-Type":"application/json"}),
            timeout=8)
        resp = json.loads(r.read())
        raw  = resp.get("data", resp) if isinstance(resp, dict) else resp
        kl   = [{"t":int(k[0]),"o":float(k[1]),"h":float(k[2]),
                 "l":float(k[3]),"c":float(k[4]),"v":float(k[5])} for k in raw]
        kl.sort(key=lambda x: x["t"])
        with _kl_lock:
            _kl_cache[key] = {"ts": time.time(), "data": kl}
        return kl
    except:
        with _kl_lock:
            return _kl_cache.get(key, {}).get("data", [])

def _ind(kl):
    """공통 지표: EMA9/21 + RSI + ATR(14) + BB(20,2.0)"""
    if len(kl) < 22: return {}
    hi = [k["h"] for k in kl]
    lo = [k["l"] for k in kl]
    cl = [k["c"] for k in kl]
    # ATR(14)
    tr_list = [max(hi[i]-lo[i], abs(hi[i]-cl[i-1]), abs(lo[i]-cl[i-1]))
               for i in range(1, len(kl))]
    # XRP처럼 가격이 작은 심볼은 소수 2자리 반올림 시 EMA9==EMA21이 되어 필터가 무력화됨 → 6자리
    atr = round(sum(tr_list[-14:])/14, 6)
    # Bollinger Bands(20, 2.0)
    bb20 = cl[-20:]
    bm   = sum(bb20)/20
    bstd = (sum((x-bm)**2 for x in bb20)/20)**0.5
    return {
        "ema9":     round(_ema(cl,9), 6),
        "ema21":    round(_ema(cl,21), 6),
        "rsi":      _rsi(cl,14),
        "price":    cl[-1],
        "atr":      atr,
        "bb_upper": round(bm + 2.0*bstd, 6),
        "bb_lower": round(bm - 2.0*bstd, 6),
        "bb_mid":   round(bm, 6),
    }

# ── FVG (Fair Value Gap) 탐지 + filled 추적 ───────────────────────────────
def _detect_fvg(kl):
    """
    15분봉에서 Fair Value Gap 탐지.
    Bullish FVG : kl[i].low  > kl[i-2].high  → 지지 갭 (롱 기회)
    Bearish FVG : kl[i].high < kl[i-2].low   → 저항 갭 (숏 기회)
    반환: [{"type","low","high","formed_at","filled"}, ...]
    """
    fvgs = []
    for i in range(2, len(kl)):
        if kl[i]["l"] > kl[i-2]["h"]:          # Bullish FVG
            fvgs.append({
                "type":      "bull",
                "low":       round(kl[i-2]["h"], 1),   # 갭 하단
                "high":      round(kl[i]["l"],   1),   # 갭 상단
                "formed_at": kl[i]["t"],
                "filled":    False,
            })
        elif kl[i]["h"] < kl[i-2]["l"]:        # Bearish FVG
            fvgs.append({
                "type":      "bear",
                "low":       round(kl[i]["h"],   1),   # 갭 하단
                "high":      round(kl[i-2]["l"], 1),   # 갭 상단
                "formed_at": kl[i]["t"],
                "filled":    False,
            })
    return fvgs

def _update_fvg_filled(fvgs, current_price):
    """현재가가 FVG 구간에 들어오면 filled=True 마킹"""
    for fg in fvgs:
        if not fg["filled"] and fg["low"] <= current_price <= fg["high"]:
            fg["filled"] = True
    return fvgs


# ── KST 날짜 / 일별 통계 ──────────────────────────────────────────
def _kst_day():
    kst = datetime.now(timezone(timedelta(hours=9)))
    if kst.hour < 21: kst -= timedelta(days=1)   # 거래일 기준: KST 21:00 리셋 (뉴욕 킬존 시작)
    return kst.strftime("%Y-%m-%d")

def _dst(day, mode):
    return _daily.get(day, {}).get(
        mode, {"pnl_pct":0.0,"trades":0,"wins":0,"losses":0})

def _can_trade(mode):
    st = _dst(_kst_day(), mode)
    if mode.endswith("real") and st["trades"] >= _cfg["max_daily_trades"]:
        return False, f"일 최대 {_cfg['max_daily_trades']}회 도달"

    # pnl_pct는 이미 자본 기준으로 기록됨 (_rec에서 size_pct 반영)
    if st["pnl_pct"] >= _cfg["daily_profit_stop"]:
        return False, f"일 자본수익 +{_cfg['daily_profit_stop']:.2f}% 도달"
    if st["pnl_pct"] <= -_cfg["daily_loss_stop"]:
        return False, f"일 자본손실 -{_cfg['daily_loss_stop']:.2f}% 도달"

    # 연속 손절 서킷브레이커: 당일 손절 2회 이상이면 거래 중단
    if st.get("losses", 0) >= _cfg.get("max_daily_losses", 2):
        return False, f"당일 손절 {st['losses']}회 — 서킷브레이커 작동"
    return True, ""

def _rec(mode, action, price, ind, reason, pnl=None, tp_px=None, sl_px=None,
         signal_src=None, smc_ctx=None, sym="BTC-USDT-SWAP", size_pct=None):
    global _pattern_stats
    day = _kst_day()
    ts  = datetime.now(timezone(timedelta(hours=9))).strftime("%m-%d %H:%M")
    _logs.append({"ts":ts,"day":day,"mode":mode,"sym":sym,"action":action,
        "price":price,"e9":ind.get("ema9"),"e21":ind.get("ema21"),
        "rsi":ind.get("rsi"),"atr":ind.get("atr"),"reason":reason,"pnl":pnl,
        "tp_px":tp_px,"sl_px":sl_px,"signal_src":signal_src,
        "smc_ctx": smc_ctx})
    if len(_logs) > 500: _logs.pop(0)
    if pnl is not None:
        _daily.setdefault(day, {}).setdefault(
            mode, {"pnl_pct":0.0,"trades":0,"wins":0,"losses":0})
        s = _daily[day][mode]
        # 자본 기준 P&L = 증거금 수익률(pnl) × 실제 투입 증거금 비율
        if size_pct is None: size_pct = _claude_cfg.get("size_pct", 40)
        cap_pnl  = round(pnl * (size_pct / 100.0), 6)
        s["pnl_pct"] = round(s["pnl_pct"] + cap_pnl, 6)
        s["trades"] += 1
        if pnl > 0: s["wins"]  += 1
        else:       s["losses"] += 1
        # ── 패턴 통계 누적 학습 ─────────────────────────────────
        if smc_ctx and smc_ctx.get("pattern_key"):
            pk = smc_ctx["pattern_key"]
            _pattern_stats.setdefault(pk, {"trades": 0, "wins": 0, "total_pnl": 0.0})
            _pattern_stats[pk]["trades"] += 1
            if pnl > 0: _pattern_stats[pk]["wins"] += 1
            _pattern_stats[pk]["total_pnl"] = round(
                _pattern_stats[pk]["total_pnl"] + pnl, 4)
            # ── 실거래 학습 루프: 패턴 가중치 즉시 동기화 ──────────
            try:
                _get_weight.__module__  # weights 로드 확인
                from weights import sync_live_stats as _sync_w
                _sync_w(_pattern_stats)
            except Exception:
                pass
    save_daily_log(day)
    _persist_save()

# ── 일별 .md 로그 저장 ────────────────────────────────────────────
def _pnl_str(v, d=2):
    if v is None: return "-"
    return f"{'+'if v>0 else ''}{v:.{d}f}%"

def _win_rate(w, l):
    return f"{round(w/(w+l)*100)}%" if (w+l)>0 else "-"

def save_daily_log(day):
    day_logs = [l for l in _logs if l["day"] == day]
    csc = _dst(day, "claude-sim");  crc = _dst(day, "claude-real")

    lines = [
        f"# 거래 일지 — {day} (KST)", "",
        "## 📊 일별 성과", "",
        "| 구분 | PnL | 거래 | 승/패 | 승률 |",
        "|------|-----|------|-------|------|",
        f"| **시뮬** | {_pnl_str(csc['pnl_pct'])} | {csc['trades']}회 "
        f"| {csc['wins']}승 {csc['losses']}패 | {_win_rate(csc['wins'],csc['losses'])} |",
        f"| **실제** | {_pnl_str(crc['pnl_pct'])} | {crc['trades']}회 "
        f"| {crc['wins']}승 {crc['losses']}패 | {_win_rate(crc['wins'],crc['losses'])} |",
        "",
        f"> 일 한도: 수익 +{_cfg['daily_profit_stop']:.0f}% | "
        f"손실 -{_cfg['daily_loss_stop']:.0f}% | 실제 최대 {_cfg['max_daily_trades']}회",
        "", "---", "",
        "## 📋 거래 로그", "",
        "| 시간 | 심볼 | 모드 | 액션 | 가격 | TP | SL | RSI | 이유 | PnL |",
        "|------|------|------|------|------|-----|-----|-----|------|-----|",
    ]
    for l in day_logs:
        sym = l.get("sym", "BTC-USDT-SWAP")
        lines.append(
            f"| {l['ts']} | {sym.split('-')[0]} | {l['mode']} | {l['action']} "
            f"| ${_px_fmt(l['price'], sym)} | ${_px_fmt(l.get('tp_px'), sym)} | ${_px_fmt(l.get('sl_px'), sym)} "
            f"| {l.get('rsi') or '-'} "
            f"| {l['reason']} | {_pnl_str(l['pnl'])} |"
        )
    if not day_logs:
        lines.append("| - | - | - | 거래 없음 | - | - | - | - | - | - |")

    tot_tr  = sum(x["trades"] for x in [csc,crc])
    tot_pnl = round(sum(x["pnl_pct"] for x in [csc,crc]), 4)
    wins    = sum(x["wins"]   for x in [csc,crc])
    losses  = sum(x["losses"] for x in [csc,crc])
    wr      = round(wins/(wins+losses)*100) if (wins+losses)>0 else 0

    lines += ["", "---", "", "## 📝 총평", ""]
    if tot_tr == 0:
        lines.append("거래 없음 — 시그널 조건 미충족 또는 봇 미실행.")
    else:
        lines.append(f"**총 거래:** {tot_tr}회 | **승률:** {wr}% | **종합 PnL:** {_pnl_str(tot_pnl)}")

    # ── 패턴 분석 (누적 학습) ───────────────────────────────────────
    if _pattern_stats:
        lines += ["", "---", "", "## 🎯 패턴 학습 통계 (누적)", ""]
        lines += ["| 패턴 키 | 거래 | 승 | 승률 | 누적PnL |",
                  "|---------|------|-----|------|---------|"]
        sorted_pats = sorted(_pattern_stats.items(),
                             key=lambda x: x[1]["trades"], reverse=True)[:15]
        for pk, ps in sorted_pats:
            tr = ps["trades"]; wi = ps["wins"]
            wr_p = f"{round(wi/tr*100)}%" if tr else "-"
            lines.append(
                f"| `{pk}` | {tr} | {wi} | {wr_p} | {_pnl_str(ps['total_pnl'])} |"
            )
        # 승률 낮은 패턴 경고
        bad_pats = [(pk, ps) for pk, ps in sorted_pats
                    if ps["trades"] >= 3 and ps["wins"] / ps["trades"] < 0.3]
        if bad_pats:
            lines += ["", "### ⚠️ 저승률 패턴 경고 (3회↑, 승률<30%)", ""]
            for pk, ps in bad_pats:
                wr_p = f"{round(ps['wins']/ps['trades']*100)}%"
                lines.append(f"- `{pk}` → {ps['trades']}회 / 승률 {wr_p} / PnL {_pnl_str(ps['total_pnl'])}")

    path = os.path.join(LOGS_DIR, f"{day}_trades.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


# ── 레버리지 설정 + 주문 공통 헬퍼 ──────────────────────────────
def _set_leverage(lev, sym="BTC-USDT-SWAP"):
    lev = str(int(lev))
    for ps in ("long", "short"):
        _dc_request("POST", "/deepcoin/account/set-leverage", {
            "instId": sym, "lever": lev,
            "mgnMode": "isolated", "mrgPosition": "split", "posSide": ps,
        })

def _calc_sz(price, size_pct, lev, sym="BTC-USDT-SWAP"):
    """가용잔고의 size_pct%를 증거금으로 사용하는 계약수 자동 계산"""
    ct_sz = _CONTRACT_SZ.get(sym, 0.001)
    try:
        r = _dc_request("GET", "/deepcoin/account/balances?instType=SWAP")
        if r.get("code") in ("0", 0):
            for a in r.get("data") or []:
                if a.get("ccy") == "USDT":
                    avail = float(a.get("availBal", 0) or 0)
                    if avail <= 0:
                        return 1
                    margin_to_use       = avail * (size_pct / 100.0)
                    margin_per_contract = price * ct_sz / lev
                    sz = max(1, int(margin_to_use / margin_per_contract))
                    print(f"[사이징:{sym}] 잔고=${avail:.2f} size={size_pct}% 증거금=${margin_to_use:.2f} → {sz}계약 (계약당${margin_per_contract:.2f})")
                    return sz
    except Exception as e:
        print(f"[사이징오류:{sym}] {e}")
    return max(1, int(size_pct))

def _place_order(side, pos_side, sz, tp_px=None, sl_px=None, sym="BTC-USDT-SWAP"):
    """시장가 주문 + DeepCoin 서버사이드 TP/SL 동시 설정"""
    body = {
        "instId":      sym,
        "tdMode":      "isolated",
        "mrgPosition": "split",
        "side":        side,
        "posSide":     pos_side,
        "ordType":     "market",
        "sz":          str(max(1, int(sz))),
    }
    if tp_px:
        body["tpTriggerPx"] = str(_px_round(tp_px, sym))
        body["tpOrdPx"]     = "-1"   # 시장가 TP
    if sl_px:
        body["slTriggerPx"] = str(_px_round(sl_px, sym))
        body["slOrdPx"]     = "-1"   # 시장가 SL
    r = _dc_request("POST", "/deepcoin/trade/order", body)
    # top-level code "0"이어도 item-level sCode 체크 (data가 list 또는 dict 모두 대응)
    if r.get("code") in ("0", 0):
        data = r.get("data")
        if isinstance(data, list):
            item = data[0] if data else {}
        elif isinstance(data, dict):
            item = data
        else:
            item = {}
        s_code = str(item.get("sCode", "0"))
        if s_code not in ("0", ""):
            r = {"code": s_code, "msg": item.get("sMsg", "order item error"), "data": None}
        print(f"[주문] {side} {pos_side} sz={sz} → code={r.get('code')} ordId={item.get('ordId','?')}")
    else:
        print(f"[주문실패] {side} {pos_side} → {r}")
    return r

def _close_order(pos_side, mode, sz, sym="BTC-USDT-SWAP"):
    if mode != "real": return
    actual_sz = max(1, int(sz))
    try:
        r = _dc_request("GET", f"/deepcoin/account/positions?instId={sym}&instType=SWAP")
        if r.get("code") in ("0", 0) and r.get("data"):
            for p in r["data"]:
                if p.get("posSide") == pos_side:
                    dc_sz = int(float(p.get("pos", 0) or 0))
                    if dc_sz > 0:
                        actual_sz = dc_sz
                    break
    except Exception:
        pass
    close_side = "sell" if pos_side == "long" else "buy"
    return _dc_request("POST", "/deepcoin/trade/order", {
        "instId": sym, "tdMode": "isolated",
        "mrgPosition": "split", "side": close_side, "posSide": pos_side,
        "ordType": "market", "sz": str(actual_sz),
        "reduceOnly": True,
    })

def _d1_regime_blocks(sig, kl_1d):
    """D1 레짐이 시그널 방향을 막는지 확인. True면 스킵."""
    if not kl_1d or not _SMC_AVAILABLE:
        return False
    try:
        regime = get_market_regime(kl_1d)
        if sig == "short" and regime == "bull":
            return True
        if sig == "long" and regime == "bear":
            return True
    except Exception:
        pass
    return False


# ── Claude 메인 봇 ────────────────────────────────────────────────
def _run_claude_bot(mode, gen=0, sym="BTC-USDT-SWAP"):
    """
    Claude 분석 결과를 직접 매매 트리거로 사용하는 메인 봇.
    gen: 봇 generation — 재시작 시 zombie thread가 즉시 종료되도록 함
    sym: 거래 심볼 (BTC-USDT-SWAP / ETH-USDT-SWAP / XRP-USDT-SWAP)
    """
    st = _bots_st[sym]
    claude_mode = "claude-" + mode

    prev_pos   = st.get("position")
    prev_entry = st.get("entry") or 0.0
    prev_pnl   = st.get("pnl")   or 0.0
    prev_tr    = st.get("trades") or 0
    prev_tp    = st.get("tp_px")
    prev_sl    = st.get("sl_px")

    st.update({"running": True, "mode": mode, "stop_msg": "",
               "position": prev_pos, "entry": prev_entry,
               "pnl": prev_pnl, "trades": prev_tr,
               "tp_px": prev_tp, "sl_px": prev_sl})
    pos = prev_pos; entry = prev_entry
    tp_px = prev_tp; sl_px = prev_sl
    sess_pnl = prev_pnl; sess_tr = prev_tr
    _last_close    = st.get("last_close", 0.0)
    _last_fail_sl  = 0.0   # 직전 SL 터진 가격 레벨 (같은 구조 재진입 차단용)
    _pos_opened_at = 0.0   # 포지션 진입 시각 (DC sync 유예 기간 계산용)
    _entry_ctx     = None  # 진입 당시 SMC 컨텍스트 (패턴 학습용)
    _pos_size_pct  = None  # 진입 시 실제 투입 증거금 비율 (자본 기준 PnL 계산용)
    _ev_log        = _smc_event_log[sym]
    _pf            = lambda v: _px_fmt(v, sym)

    # ── 실제 모드: DeepCoin 포지션 동기화 ─────────────────────────
    if mode == "real" and pos is None:
        try:
            _r = _dc_request("GET", f"/deepcoin/account/positions?instId={sym}&instType=SWAP")
            if _r.get("code") in ("0", 0) and _r.get("data"):
                for _dp in _r["data"]:
                    _dc_sz = int(float(_dp.get("pos", 0) or 0))
                    if _dc_sz > 0:
                        _dc_side = _dp.get("posSide")
                        _dc_avg  = float(_dp.get("avgPx", 0) or 0)
                        _dc_tp   = float(_dp.get("tpTriggerPx", 0) or 0) or None
                        _dc_sl   = float(_dp.get("slTriggerPx", 0) or 0) or None
                        pos = _dc_side; entry = _dc_avg
                        tp_px = _dc_tp; sl_px = _dc_sl
                        st.update({"position": pos, "entry": entry,
                                   "tp_px": tp_px, "sl_px": sl_px,
                                   "watch_msg": f"[DC복원] {_dc_side.upper()} @ ${_pf(_dc_avg)} sz={_dc_sz}"})
                        print(f"[DC복원:{sym}] {_dc_side.upper()} {_dc_sz}계약 @ ${_pf(_dc_avg)}")
                        break
        except Exception as _e:
            print(f"[DC포지션복원] 오류: {_e}")

    _KZ_NAMES = {
        "asian":   "아시안(10~14KST)",
        "london":  "런던(16~19KST)",
        "newyork": "뉴욕(22~01KST)",
    }

    while st["running"] and gen == _bots_gen[sym]:
        kl    = _klines(sym=sym, n=60)
        if not kl: time.sleep(15); continue
        kl_1h = _klines(sym=sym, bar="1H", n=25)
        kl_1d = _klines(sym=sym, bar="1D", n=120)
        kl_5m = _klines(sym=sym, bar="5m", n=20)
        ind   = _ind(kl)
        price = ind.get("price", 0)
        atr   = ind.get("atr", price * 0.01)
        ok, stop_msg = _can_trade(claude_mode)
        st["price"] = _px_round(price, sym)   # continue 발생 시에도 price 반영

        # ── ICT 킬존 & AMD 아시안 레인지 ──────────────────────────
        kz          = get_kill_zone()
        kz_name     = _KZ_NAMES.get(kz, "킬존외")
        asian_rng   = get_asian_range(kl_1h) if kl_1h else None
        asian_tag   = (f" | 아시안레인지 H={_pf(asian_rng['high'])}/L={_pf(asian_rng['low'])}"
                       if asian_rng else "")

        cooldown_left = max(0, _last_close + _claude_cfg["cooldown"] - time.time())

        if pos is None:
            # ── 실시간 멀티전략 (OTE→MTF→킬존NY→Breaker 우선순위) ──
            smc, _sig_src = _multi_strategy_signal(kl, kl_1h, kl_1d, kl_5m)
            # 심볼별 이벤트 로그 업데이트 (최근 이벤트만 추가)
            if _SMC_AVAILABLE:
                new_events = smc.get("events_15m", []) + smc.get("events_1h", [])
                new_events.sort(key=lambda x: x["time_ms"])
                existing_keys = {(e["type"], e["direction"], e["level"], e["label"]) for e in _ev_log}
                for ev in new_events:
                    k = (ev["type"], ev["direction"], ev["level"], ev["label"])
                    if k not in existing_keys:
                        _ev_log.append(ev)
                        existing_keys.add(k)
                _ev_log.sort(key=lambda x: x["time_ms"])
                del _ev_log[:-100]
            s_sig   = smc.get("signal")      # "long" | "short" | None
            s_sl    = smc.get("sl")
            s_tp    = smc.get("tp1")
            s_tp2   = smc.get("tp2")
            smc_rsn = smc.get("reason", "")
            rsi     = ind.get("rsi", 50)
            bb_u    = ind.get("bb_upper", price)
            bb_l    = ind.get("bb_lower", price)
            bb_m    = ind.get("bb_mid",   price)
            ema9    = ind.get("ema9",  price)
            ema21   = ind.get("ema21", price)

            smc_info = (f"SMC:{s_sig or '없음'} BOS:{smc.get('bos_dir','?')} "
                        f"OB=b{smc.get('bull_ob_count',0)}/d{smc.get('bear_ob_count',0)} "
                        f"FVG=b{smc.get('bull_fvg_count',0)}/d{smc.get('bear_fvg_count',0)}")

            # ── 직전 SL 레벨 재진입 차단 (같은 OB에서 반복 손절 방지) ──
            _same_sl = (_last_fail_sl > 0 and s_sl and
                        abs(s_sl - _last_fail_sl) / max(_last_fail_sl, 1) < 0.002)

            # ── 진입 조건 체크 (순서: 일한도 → 킬존 → SMC → 직전SL → RSI → 15m EMA → D1 → 쿨다운 → 5m) ──
            if not ok:
                st["watch_msg"] = f"일 한도: {stop_msg}"
            elif kz not in ("london", "newyork"):
                st["watch_msg"] = f"킬존 외 진입 금지 [{kz_name}]{asian_tag} | {smc_info}"
            elif not s_sig:
                st["watch_msg"] = f"SMC시그널 없음 [{kz_name}]{asian_tag} — {smc_info}"
            elif _same_sl:
                st["watch_msg"] = f"직전 손절 구조 재진입 차단 SL≈${_pf(_last_fail_sl)} | {smc_info}"
            elif s_sig == "long" and rsi > 68:
                st["watch_msg"] = f"RSI과매수({rsi:.1f}) 롱 스킵 | {smc_info}"
            elif s_sig == "short" and rsi < 32:
                st["watch_msg"] = f"RSI과매도({rsi:.1f}) 숏 스킵 | {smc_info}"
            elif s_sig == "long" and ema9 < ema21:
                st["watch_msg"] = f"15m EMA역배열 롱 스킵 (EMA9={_pf(ema9)}<EMA21={_pf(ema21)}) | {smc_info}"
            elif s_sig == "short" and ema9 > ema21:
                st["watch_msg"] = f"15m EMA정배열 숏 스킵 (EMA9={_pf(ema9)}>EMA21={_pf(ema21)}) | {smc_info}"
            elif s_sig and _d1_regime_blocks(s_sig, kl_1d):
                _regime_now = get_market_regime(kl_1d) if (kl_1d and _SMC_AVAILABLE) else "ranging"
                st["watch_msg"] = f"D1레짐({_regime_now}) 역방향 스킵 [{s_sig}] | {smc_info}"
            elif cooldown_left > 0:
                st["watch_msg"] = f"쿨다운 {int(cooldown_left//60)}분 {int(cooldown_left%60)}초 | {smc_info}"
            else:
                # ── 5m 진입 타이밍 확인 ───────────────────────────
                _5m_ok = True
                if kl_5m and len(kl_5m) >= 10:
                    _5m_cl   = [k["c"] for k in kl_5m]
                    _5m_e9   = _ema(_5m_cl, 9)
                    _5m_e21  = _ema(_5m_cl, 21)
                    _5m_bull = kl_5m[-1]["c"] > kl_5m[-1]["o"] and _5m_e9 > _5m_e21
                    _5m_bear = kl_5m[-1]["c"] < kl_5m[-1]["o"] and _5m_e9 < _5m_e21
                    if s_sig == "long"  and not _5m_bull:
                        st["watch_msg"] = f"5m 롱 미확인 (5mEMA9={_pf(_5m_e9)} EMA21={_pf(_5m_e21)}) | {smc_info}"
                        _5m_ok = False
                    elif s_sig == "short" and not _5m_bear:
                        st["watch_msg"] = f"5m 숏 미확인 (5mEMA9={_pf(_5m_e9)} EMA21={_pf(_5m_e21)}) | {smc_info}"
                        _5m_ok = False
                if not _5m_ok:
                    time.sleep(30); continue

                # ── 진입 실행 ────────────────────────────────────
                sig = s_sig  # SMC가 방향 결정
                _lev     = _claude_cfg.get("leverage", 20)
                _TP_CAP  = _claude_cfg.get("tp_max_pct", 15.0) / 100
                _SL_CAP  = _claude_cfg.get("sl_cap_pct", 2.0)  / 100
                # 심볼별 tp_min_margin → 현물 이동폭 환산 (증거금 기준 % ÷ 레버리지)
                _sym_tp_map = _claude_cfg.get("tp_min_margin_by_sym", {})
                _tp_min_margin = _sym_tp_map.get(sym, _claude_cfg.get("tp_min_margin_pct", 0))
                _TP_MIN  = _tp_min_margin / (100.0 * _lev) if _tp_min_margin > 0 else 0.0
                _SL_MIN  = max(atr / price * 0.8, 0.003)   # 최소 SL: ATR×0.8 또는 0.3% 중 큰 값

                # tp2 업그레이드: tp1보다 유리하고 price 대비 2% 이내면 tp1 대신 사용
                _s_tp = s_tp
                if _s_tp and s_tp2:
                    if sig == "long" and s_tp2 > _s_tp:
                        if 0 < (s_tp2 - price) / price <= 0.02:
                            _s_tp = s_tp2
                    elif sig == "short" and s_tp2 < _s_tp:
                        if 0 < (price - s_tp2) / price <= 0.02:
                            _s_tp = s_tp2

                # SL/TP: SMC 구조적 레벨 우선 → 없으면 ATR 기반
                if s_sl and _s_tp:
                    if sig == "long":
                        _tp_dist = min((_s_tp - price) / price, _TP_CAP) if _s_tp > price else atr / price * 2.0
                        raw_sl   = (price - s_sl) / price if s_sl < price else atr / price * 0.8
                        _sl_dist = min(max(raw_sl, _SL_MIN), _SL_CAP)
                    else:
                        _tp_dist = min((price - _s_tp) / price, _TP_CAP) if _s_tp < price else atr / price * 2.0
                        raw_sl   = (s_sl - price) / price if s_sl > price else atr / price * 0.8
                        _sl_dist = min(max(raw_sl, _SL_MIN), _SL_CAP)
                    smc_tag = f"[{_sig_src or 'SMC'}]"
                else:
                    _tp_dist = min(atr / price * 2.0, _TP_CAP)
                    _sl_dist = min(max(atr / price * 0.8, _SL_MIN), _SL_CAP)
                    smc_tag = "[ATR폴백]"

                # TP 목표가 최소 미달이면 진입 스킵 (_TP_MIN=0이면 비활성)
                if _TP_MIN > 0 and _tp_dist < _TP_MIN:
                    st["watch_msg"] = (
                        f"TP목표 짧음 스킵 {smc_tag} TP={_tp_dist*100:.2f}% < 최소{_TP_MIN*100:.0f}%"
                    )
                    time.sleep(30); continue

                # 손익비 불량이면 진입 안 함
                _rr_min = _claude_cfg.get("rr_min", 2.5)
                if _tp_dist < _sl_dist * _rr_min:
                    st["watch_msg"] = (
                        f"손익비 불량 스킵 {smc_tag} TP={_tp_dist*100:.2f}% SL={_sl_dist*100:.2f}%"
                    )
                    time.sleep(30); continue
                if sig == "long":
                    tp_px = _px_round(price * (1 + _tp_dist), sym)
                    sl_px = _px_round(price * (1 - _sl_dist), sym)
                else:
                    tp_px = _px_round(price * (1 - _tp_dist), sym)
                    sl_px = _px_round(price * (1 + _sl_dist), sym)

                # ── SMC 컨텍스트 빌드 (패턴 학습용) ─────────────────
                _poi_type = None
                if "OB재터치" in smc_rsn: _poi_type = "OB재터치"
                elif "FVG진입" in smc_rsn: _poi_type = "FVG진입"
                _ob_cnt  = smc.get("bull_ob_count" if sig=="long" else "bear_ob_count", 0)
                _fvg_cnt = smc.get("bull_fvg_count" if sig=="long" else "bear_fvg_count", 0)
                _bos_t   = smc.get("bos_type") or "없음"
                _has_sw  = smc.get("sweep", False)
                _rr_val  = round(_tp_dist / _sl_dist, 2) if _sl_dist else 0
                _pat_key = (f"{_sig_src or 'SMC'}+{kz or 'no_kz'}+{_bos_t}+{_poi_type or 'no_poi'}"
                            f"+OB{_ob_cnt}+FVG{_fvg_cnt}+{'sweep' if _has_sw else 'no_sweep'}")
                _smc_ctx = {
                    "strategy":    _sig_src or "SMC",
                    "kill_zone":   kz,
                    "bos_type":    _bos_t,
                    "poi_type":    _poi_type,
                    "ob_count":    _ob_cnt,
                    "fvg_count":   _fvg_cnt,
                    "sweep":       _has_sw,
                    "strong_high": smc.get("strong_high"),
                    "weak_high":   smc.get("weak_high"),
                    "strong_low":  smc.get("strong_low"),
                    "weak_low":    smc.get("weak_low"),
                    "rr":          _rr_val,
                    "pattern_key": _pat_key,
                }
                # 패턴 신뢰도 경고 (승률 < 30%, 3회 이상)
                _pk_stat = _pattern_stats.get(_pat_key, {})
                _pk_tr   = _pk_stat.get("trades", 0)
                _pk_wr   = (_pk_stat.get("wins", 0) / _pk_tr * 100) if _pk_tr >= 3 else None
                _pat_warn = f"[패턴경고:{_pk_wr:.0f}%WR/{_pk_tr}회] " if (_pk_wr is not None and _pk_wr < 30) else ""

                conf_tags = (f"RSI={rsi:.1f} EMA={'정' if ema9>=ema21 else '역'} "
                             f"BB={'하단권' if price<=bb_m else '상단권'}")
                sw_tag = ""
                if smc.get("strong_high"): sw_tag += f" StrongH=${_pf(smc['strong_high'])}"
                if smc.get("weak_low"):    sw_tag += f" WeakL=${_pf(smc['weak_low'])}"
                if smc.get("strong_low"):  sw_tag += f" StrongL=${_pf(smc['strong_low'])}"
                if smc.get("weak_high"):   sw_tag += f" WeakH=${_pf(smc['weak_high'])}"
                # 최근 SMC 이벤트 요약 (진입 근거, 이 심볼만)
                recent_ev = _ev_log[-5:]
                ev_summary = " | ".join(
                    f"[{e['label']}]{e['type']}{'↑' if e['direction']=='bullish' else '↓'}@${e['level']}"
                    for e in recent_ev
                ) if recent_ev else "이벤트없음"
                reason = (f"{_pat_warn}SMC{sig.upper()} {smc_tag} {smc_rsn[:50]} "
                          f"| {conf_tags}{sw_tag} "
                          f"| [{kz_name}]{asian_tag} "
                          f"| 근거: {ev_summary} "
                          f"[TP:${_pf(tp_px)} SL:${_pf(sl_px)} RR={_rr_val:.1f}]")

                if mode == "real":
                    _lev_now  = _claude_cfg.get("leverage", 20)
                    _risk_pct = _claude_cfg.get("risk_pct", 10.0)
                    # 동적 사이징: risk_pct % / (SL거리 × 레버리지) → 증거금 비율
                    _dyn_size = min(80.0, _risk_pct / (_sl_dist * _lev_now)) if _sl_dist > 0 else _claude_cfg.get("size_pct", 40)
                    # 적응형 가중치 적용 (백테스트 승률 기반)
                    _wt = _get_weight(_pat_key) if _WEIGHTS_AVAILABLE else 1.0
                    _dyn_size = min(80.0, _dyn_size * _wt)
                    _set_leverage(_lev_now, sym=sym)
                    side  = "buy" if sig == "long" else "sell"
                    _sz   = _calc_sz(price, _dyn_size, _lev_now, sym=sym)
                    print(f"[사이징:{sym}] 리스크{_risk_pct}% SL={_sl_dist*100:.2f}% 레버리지={_lev_now}x 가중치={_wt:.2f} → {_dyn_size:.1f}% 증거금")
                    ord_r = _place_order(side, sig, _sz, tp_px=tp_px, sl_px=sl_px, sym=sym)
                    if ord_r.get("code") not in ("0", 0):
                        reason += f" [주문실패:{ord_r.get('msg','')}]"
                        tp_px = None; sl_px = None
                        st["watch_msg"] = reason
                        time.sleep(60)   # 주문 실패 후 1분 대기 (즉시 재시도 방지)
                    else:
                        pos = sig; entry = price
                        _pos_opened_at = time.time()
                        _pos_size_pct  = _dyn_size
                else:
                    pos = sig; entry = price
                    _pos_opened_at = time.time()
                    _pos_size_pct  = _claude_cfg.get("size_pct", 40)

                if pos:
                    _entry_ctx = _smc_ctx   # 청산 시 패턴 학습에 사용
                    _rec(claude_mode, f"ENTER_{sig.upper()}", price, ind, reason,
                         tp_px=tp_px, sl_px=sl_px, signal_src="Claude", smc_ctx=_smc_ctx, sym=sym)
                    st["watch_msg"] = reason

        elif pos:
            _lev = _claude_cfg.get("leverage", 20)
            # ── Real 모드: DeepCoin 실제 포지션 확인 (진입 후 90초 유예) ──
            if mode == "real" and time.time() - _pos_opened_at > 90:
                try:
                    _pr = _dc_request("GET", f"/deepcoin/account/positions?instId={sym}&instType=SWAP")
                    if _pr.get("code") in ("0", 0):
                        _dc_positions = _pr.get("data") or []
                        _dc_has_pos = any(
                            int(float(p.get("pos", 0) or 0)) > 0 and p.get("posSide") == pos
                            for p in _dc_positions
                        )
                        if not _dc_has_pos:
                            # DeepCoin에 포지션 없음 → 외부 청산 (서버사이드 TP/SL)
                            raw_pct = ((price - entry) / entry * 100 if pos == "long"
                                       else (entry - price) / entry * 100)
                            lev_pct = round(raw_pct * _lev, 4)
                            if tp_px and ((pos == "long" and price >= tp_px * 0.998) or
                                          (pos == "short" and price <= tp_px * 1.002)):
                                action = f"CLOSE_{pos.upper()}"
                                reason = f"DC서버TP ${_pf(tp_px)} 체결확인 {lev_pct:+.2f}% ({_lev}x)"
                                _last_fail_sl = 0.0
                            else:
                                action = "SL_HIT"
                                reason = f"DC서버SL 청산확인 (진입 ${_pf(entry)} → ${_pf(price)}) {lev_pct:+.2f}% ({_lev}x)"
                                _last_fail_sl = sl_px or 0.0
                            _rec(claude_mode, action, price, ind, reason,
                                 pnl=lev_pct, signal_src="Claude", smc_ctx=_entry_ctx,
                                 sym=sym, size_pct=_pos_size_pct)
                            sess_pnl += lev_pct; sess_tr += 1
                            pos = None; entry = 0.0; tp_px = None; sl_px = None
                            _pos_opened_at = 0.0; _entry_ctx = None; _pos_size_pct = None
                            _last_close = time.time()
                            st["last_close"] = _last_close
                            print(f"[DC동기화:{sym}] 외부 청산: {action} {lev_pct:+.2f}%")
                except Exception as _sync_err:
                    print(f"[DC동기화] 오류: {_sync_err}")

            # ── 로컬 TP/SL 체크 (pos가 아직 있으면 실행) ──────────────
            if pos:
                raw_pct = ((price - entry) / entry * 100 if pos == "long"
                           else (entry - price) / entry * 100)
                lev_pct  = round(raw_pct * _lev, 4)
                close_reason = None

                # SL
                if sl_px and ((pos == "long"  and price <= sl_px) or
                              (pos == "short" and price >= sl_px)):
                    close_reason = f"SL ${_pf(sl_px)} 터치 {lev_pct:+.2f}% ({_lev}x)"
                    action = "SL_HIT"

                # TP
                elif tp_px and ((pos == "long"  and price >= tp_px) or
                                (pos == "short" and price <= tp_px)):
                    close_reason = f"TP ${_pf(tp_px)} 달성 {lev_pct:+.2f}% ({_lev}x)"
                    action = f"CLOSE_{pos.upper()}"

                if close_reason:
                    _close_order(pos, mode, _claude_cfg["size_pct"], sym=sym)
                    _rec(claude_mode, action, price, ind, close_reason,
                         pnl=lev_pct, signal_src="Claude", smc_ctx=_entry_ctx,
                         sym=sym, size_pct=_pos_size_pct)
                    sess_pnl += lev_pct; sess_tr += 1
                    if action == "SL_HIT":
                        _last_fail_sl = sl_px
                    else:
                        _last_fail_sl = 0.0
                    pos = None; entry = 0.0; tp_px = None; sl_px = None
                    _pos_opened_at = 0.0; _entry_ctx = None; _pos_size_pct = None
                    _last_close = time.time()
                    st["last_close"] = _last_close
                else:
                    st["watch_msg"] = (
                        f"홀딩 {pos.upper()} @ ${_pf(entry)} "
                        f"| 현재 ${_pf(price)} ({lev_pct:+.2f}%, {_lev}x) "
                        f"| TP ${_pf(tp_px)} SL ${_pf(sl_px)}"
                    )

        # tuning.json active_symbols에서 빠지면 포지션 없을 때 스레드 종료
        if pos is None and sym not in _active_syms_cfg:
            st["watch_msg"] = "active_symbols 제외 — 정지"
            st["position"] = None
            break

        st.update({
            "position": pos, "price": _px_round(price, sym),
            "entry": _px_round(entry, sym) if pos else None,
            "tp_px": tp_px, "sl_px": sl_px,
            "pnl": round(sess_pnl, 2), "trades": sess_tr,
            "indicators": ind, "can_trade": ok, "stop_msg": stop_msg,
            "daily": _dst(_kst_day(), claude_mode),
        })
        _persist_save()

        # ── 날짜 전환 감지 → 자동 review + STRATEGY.md 업데이트 ───
        _new_day = _kst_day()
        if not hasattr(_run_claude_bot, "_last_review_day"):
            _run_claude_bot._last_review_day = _new_day
        if _new_day != _run_claude_bot._last_review_day:
            _run_claude_bot._last_review_day = _new_day
            try:
                import subprocess as _sp
                _rp = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "evolution", "review_trades.py")
                _sp.Popen([__import__("sys").executable, _rp],
                          cwd=os.path.dirname(os.path.abspath(__file__)))
                print(f"[daily-review] {_new_day} 자동 review 실행")
            except Exception as _re:
                print(f"[daily-review] 오류: {_re}")

        time.sleep(30)
    st["running"] = False


# ── HTTP 핸들러 ───────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _j(self, d, st=200):
        b = json.dumps(d, ensure_ascii=False).encode()
        self.send_response(st)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length", len(b))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try: self.wfile.write(b)
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError): pass
    def _h(self, html):
        b = html.encode(); self.send_response(200)
        self.send_header("Content-Type","text/html; charset=utf-8")
        self.send_header("Content-Length", len(b))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.end_headers(); self.wfile.write(b)
    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n)) if n else {}
    def do_OPTIONS(self):
        self.send_response(200)
        for h,v in [("Access-Control-Allow-Origin","*"),
                    ("Access-Control-Allow-Methods","GET,POST,OPTIONS"),
                    ("Access-Control-Allow-Headers","Content-Type")]:
            self.send_header(h, v)
        self.end_headers()

    def do_GET(self):
        try:
            self._do_GET()
        except Exception as e:
            try: self._j({"error": str(e)}, 500)
            except Exception: pass

    def _do_GET(self):
        p  = urlparse(self.path).path
        qs = parse_qs(urlparse(self.path).query)
        if p in ("/", "/index.html"):
            idx = os.path.join(os.path.dirname(os.path.abspath(__file__)),"index.html")
            with open(idx, encoding="utf-8") as f: self._h(f.read())
        elif p == "/api/status":
            ak = _e("DEEPCOIN_API_KEY","")
            self._j({"api_key_set":bool(ak and ak!="your_api_key_here"),
                "claude_running":any(s["running"] for s in _bots_st.values()),
                "running_syms":[s for s, st in _bots_st.items() if st["running"]],
                "active_symbols":_active_syms_cfg,
                "time":time.strftime("%Y-%m-%d %H:%M:%S"),
                "config":_cfg})
        elif p == "/api/claude/status":
            qs = parse_qs(urlparse(self.path).query)
            _sym = qs.get("sym", ["BTC-USDT-SWAP"])[0]
            self._j(_bots_st.get(_sym, _bots_st["BTC-USDT-SWAP"]))
        elif p == "/api/bots/status":
            self._j({s: dict(st) for s, st in _bots_st.items()})
        elif p == "/api/claude/config":   self._j(_claude_cfg)
        elif p == "/api/ticker":
            try:
                import urllib.request
                sym = qs.get("symbol",["BTC-USDT-SWAP"])[0]
                url = (f"https://api.deepcoin.com/deepcoin/market/tickers"
                       f"?instId={sym}&instType=SWAP")
                r = urllib.request.urlopen(
                    urllib.request.Request(url, headers={"Content-Type":"application/json"}),
                    timeout=3)
                resp = json.loads(r.read())
                d = (resp.get("data") or [{}])[0]
                last   = float(d.get("last") or 0)
                open24 = float(d.get("open24h") or last or 1)
                chg = round((last - open24) / open24 * 100, 2) if open24 else 0
                self._j({"last": last, "change": chg})
            except Exception as e:
                self._j({"last": 0, "change": 0, "error": str(e)})

        elif p == "/api/klines":
            bar = qs.get("interval",["15m"])[0]
            lim = int(qs.get("limit",["100"])[0])
            sym = qs.get("symbol",["BTC-USDT-SWAP"])[0]
            self._j(_klines(sym, bar, lim))

        elif p == "/api/indicators":
            bar = qs.get("interval",["15m"])[0]
            sym = qs.get("symbol",["BTC-USDT-SWAP"])[0]
            kl  = _klines(sym=sym, bar=bar, n=80)
            if len(kl) < 22:
                self._j({"ema9":[],"ema21":[],"rsi":[],"atr":[],"bb_upper":[],"bb_lower":[],"bb_mid":[],"ts":[]}); return
            hi = [k["h"] for k in kl]; lo = [k["l"] for k in kl]
            cl = [k["c"] for k in kl]; ts = [k["t"] for k in kl]
            e9s=[]; e21s=[]; rs=[]; atrs=[]; bbus=[]; bbls=[]; bbms=[]
            for i in range(21, len(cl)):
                sub_kl = kl[:i+1]
                sub_hi = hi[:i+1]; sub_lo = lo[:i+1]; sub_cl = cl[:i+1]
                e9s.append(round(_ema(sub_cl,9),2))
                e21s.append(round(_ema(sub_cl,21),2))
                rs.append(_rsi(sub_cl,14))
                tr_list = [max(sub_hi[j]-sub_lo[j], abs(sub_hi[j]-sub_cl[j-1]),
                               abs(sub_lo[j]-sub_cl[j-1])) for j in range(1,len(sub_kl))]
                atrs.append(round(sum(tr_list[-14:])/14, 2) if len(tr_list)>=14 else 0)
                bb20 = sub_cl[-20:]; bm = sum(bb20)/20
                bstd = (sum((x-bm)**2 for x in bb20)/20)**0.5
                bbus.append(round(bm+2*bstd,2)); bbls.append(round(bm-2*bstd,2))
                bbms.append(round(bm,2))
            self._j({"ema9":e9s,"ema21":e21s,"rsi":rs,"atr":atrs,
                     "bb_upper":bbus,"bb_lower":bbls,"bb_mid":bbms,"ts":ts[21:]})

        elif p == "/api/fvg":
            # 15분봉 기준 최근 FVG 목록 + filled 상태 (실시간)
            sym     = qs.get("symbol",["BTC-USDT-SWAP"])[0]
            kl_fvg  = _klines(sym=sym, bar="15m", n=80)
            kl_1h_f = _klines(sym=sym, bar="1H",  n=50)
            cur_px  = kl_fvg[-1]["c"] if kl_fvg else 0
            fvgs_f  = _detect_fvg(kl_fvg) if kl_fvg else []
            recent_f = fvgs_f[-15:]
            _update_fvg_filled(recent_f, cur_px)
            trend_str = None
            if kl_1h_f and len(kl_1h_f) >= 22:
                cl_f = [k["c"] for k in kl_1h_f]
                e9f = _ema(cl_f, 9); e21f = _ema(cl_f, 21)
                if   e9f > e21f * 1.0002: trend_str = "bull"
                elif e9f < e21f * 0.9998: trend_str = "bear"
                else: trend_str = "neutral"
            self._j({
                "trend_1h": trend_str,
                "fvgs": [{"type": fg["type"], "low": fg["low"], "high": fg["high"],
                          "filled": fg["filled"],
                          "formed_at": fg["formed_at"]} for fg in recent_f],
                "unfilled_bull": sum(1 for fg in recent_f if fg["type"]=="bull" and not fg["filled"]),
                "unfilled_bear": sum(1 for fg in recent_f if fg["type"]=="bear" and not fg["filled"]),
                "current_price": cur_px,
            })
        elif p == "/api/logs":
            n = int(qs.get("n",["60"])[0])
            self._j(list(reversed(_logs[-n:])))
        elif p == "/api/daily":  self._j(_daily)
        elif p == "/api/debrief":
            sym   = qs.get("sym", qs.get("symbol", ["BTC-USDT-SWAP"]))[0]
            if sym not in _bots_st: sym = "BTC-USDT-SWAP"
            _st   = _bots_st[sym]
            kl    = _klines(sym=sym, n=60)
            kl_1h = _klines(sym=sym, bar="1H", n=25)
            ind   = _ind(kl) if kl else {}
            kl_1d = _klines(sym=sym, bar="1D", n=120)
            smc   = get_ict_signal(kl, h1_kl=kl_1h, d1_kl=kl_1d) if (_SMC_AVAILABLE and kl) else {"signal": None}

            price  = ind.get("price", 0)
            rsi    = ind.get("rsi", 50)
            bb_u   = ind.get("bb_upper", price)
            bb_l   = ind.get("bb_lower", price)
            bb_m   = ind.get("bb_mid",   price)
            ema9   = ind.get("ema9",  price)
            ema21  = ind.get("ema21", price)
            atr    = ind.get("atr",   0)
            s_sig  = smc.get("signal")
            rsi_ok = not ((s_sig == "long" and rsi > 68) or (s_sig == "short" and rsi < 32))
            bb_ok  = not ((s_sig == "long"  and ema9 < ema21) or
                          (s_sig == "short" and ema9 > ema21))
            cooldown_left = max(0, _st.get("last_close", 0) + _claude_cfg["cooldown"] - time.time())
            kz_now = get_kill_zone()

            filters = [
                {"name": "킬존",        "pass": kz_now in ("london","newyork"), "value": kz_now or "킬존외"},
                {"name": "SMC 시그널",  "pass": bool(s_sig),        "value": s_sig or "없음"},
                {"name": "RSI 필터",    "pass": rsi_ok,              "value": f"{rsi:.1f}"},
                {"name": "BB+EMA 필터", "pass": bb_ok,               "value": f"${_px_fmt(price, sym)} mid=${_px_fmt(bb_m, sym)} EMA{'정배열' if ema9>=ema21 else '역배열'}"},
                {"name": "쿨다운",      "pass": cooldown_left <= 0,  "value": f"잔여 {int(cooldown_left//60)}분 {int(cooldown_left%60)}초" if cooldown_left > 0 else "완료"},
            ]

            self._j({
                "sym": sym,
                "smc": {
                    "signal":         s_sig,
                    "bos_dir":        smc.get("bos_dir"),
                    "sl":             smc.get("sl"),
                    "tp1":            smc.get("tp1"),
                    "reason":         smc.get("reason", ""),
                    "bull_ob_count":  smc.get("bull_ob_count", 0),
                    "bear_ob_count":  smc.get("bear_ob_count", 0),
                    "bull_fvg_count": smc.get("bull_fvg_count", 0),
                    "bear_fvg_count": smc.get("bear_fvg_count", 0),
                    "sweep":          smc.get("sweep", False),
                },
                "indicators": {
                    "price": round(price,2), "rsi": round(rsi,1),
                    "ema9":  round(ema9,1),  "ema21": round(ema21,1),
                    "bb_upper": round(bb_u,1), "bb_lower": round(bb_l,1),
                    "bb_mid": round(bb_m,1), "atr": round(atr,1),
                },
                "filters":   filters,
                "watch_msg": _st.get("watch_msg", ""),
                "position":  _st.get("position"),
                "entry":     _st.get("entry"),
                "tp_px":     _st.get("tp_px"),
                "sl_px":     _st.get("sl_px"),
                "smc_events":  sorted(
                    smc.get("events_15m", []) + smc.get("events_1h", []),
                    key=lambda x: x["time_ms"], reverse=True
                )[:20],
                "smc_log": list(reversed(_smc_event_log[sym][-20:])),
            })
        elif p == "/api/pattern-stats":
            # 패턴별 학습 통계 (승률 순 정렬)
            stats = []
            for pk, ps in _pattern_stats.items():
                tr = ps["trades"]; wi = ps["wins"]
                stats.append({
                    "pattern": pk,
                    "trades":  tr,
                    "wins":    wi,
                    "win_rate": round(wi / tr * 100, 1) if tr else 0,
                    "total_pnl": ps["total_pnl"],
                    "warning": tr >= 3 and (wi / tr) < 0.3,
                })
            stats.sort(key=lambda x: x["trades"], reverse=True)
            self._j({"count": len(stats), "stats": stats})
        elif p == "/api/config":        self._j(_cfg)
        elif p == "/api/balance":
            r = _dc_request("GET", "/deepcoin/account/balances?instType=SWAP")
            if str(r.get("code")) == "0":
                assets = {a["ccy"]: {"avail": a.get("availEq") or a.get("availBal","0"),
                                     "total": a.get("eq") or a.get("bal","0")}
                          for a in (r.get("data") or []) if a.get("ccy")}
                self._j({"ok": True, "assets": assets})
            else:
                self._j({"ok": False, "code": r.get("code"), "msg": r.get("msg")})
        elif p == "/api/positions":
            sym = qs.get("symbol", ["BTC-USDT-SWAP"])[0]
            r = _dc_request("GET", f"/deepcoin/account/positions?instId={sym}&instType=SWAP")
            if str(r.get("code")) == "0":
                self._j({"ok": True, "positions": r.get("data", [])})
            else:
                self._j({"ok": False, "code": r.get("code"), "msg": r.get("msg")})
        elif p == "/api/log-files":
            files = sorted(os.listdir(LOGS_DIR), reverse=True) if os.path.exists(LOGS_DIR) else []
            self._j([f for f in files if f.endswith(".md")])
        elif p.startswith("/api/log/"):
            fname = os.path.basename(p[9:])
            fpath = os.path.join(LOGS_DIR, fname)
            if os.path.exists(fpath):
                with open(fpath, encoding="utf-8") as f:
                    self.send_response(200)
                    b = f.read().encode()
                    self.send_header("Content-Type","text/plain; charset=utf-8")
                    self.send_header("Content-Length", len(b))
                    self.send_header("Access-Control-Allow-Origin","*")
                    self.end_headers(); self.wfile.write(b)
            else: self._j({"error":"not found"},404)
        else: self._j({"error":"not found"}, 404)


    def do_POST(self):
        try:
            self._do_POST()
        except Exception as e:
            try: self._j({"error": str(e)}, 500)
            except Exception: pass

    def _do_POST(self):
        p = urlparse(self.path).path; b = self._body()

        if p == "/api/claude/start":
            mode = b.get("mode", "sim")
            # 요청한 심볼 목록 (없으면 tuning.json active_symbols)
            req_syms = b.get("syms", _active_syms_cfg)
            if isinstance(req_syms, str): req_syms = [req_syms]
            started, skipped = [], []
            for _sym in req_syms:
                if _sym not in _bots_st: continue
                if _sym not in _active_syms_cfg:
                    skipped.append(_sym); continue
                _bots_st[_sym]["running"] = False
                _bots_gen[_sym] += 1
                _t = threading.Thread(target=_run_claude_bot, daemon=True,
                    kwargs={"mode": mode, "gen": _bots_gen[_sym], "sym": _sym})
                _bots_thr[_sym] = _t
                _t.start()
                started.append(_sym)
            self._j({"ok": True, "msg": f"Claude봇({mode}) 시작", "syms": started,
                     "skipped_not_active": skipped})

        elif p == "/api/claude/stop":
            req_syms = b.get("syms", list(_bots_st))
            if isinstance(req_syms, str): req_syms = [req_syms]
            for _sym in req_syms:
                if _sym in _bots_st: _bots_st[_sym]["running"] = False
            self._j({"ok":True,"msg":"Claude봇 중지","syms":req_syms})

        elif p == "/api/claude/config":
            for k in ("leverage","size_pct","cooldown"):
                if k in b: _claude_cfg[k] = int(b[k])
            for k in ("risk_pct","rr_min","sl_cap_pct","tp_max_pct","tp_min_margin_pct"):
                if k in b: _claude_cfg[k] = float(b[k])
            self._j({"ok":True,"config":_claude_cfg})

        elif p == "/api/config":
            # 공통 한도 설정
            for k in ("max_daily_trades","daily_profit_stop","daily_loss_stop"):
                if k in b:
                    _cfg[k] = int(b[k]) if k == "max_daily_trades" else float(b[k])
            self._j({"ok":True,"config":_cfg})

        elif p == "/api/reset-daily":
            # 오늘 거래일 통계 즉시 리셋 (메모리 + persist)
            global _daily
            day = _kst_day()
            mode = b.get("mode", "claude-real")
            if day in _daily and mode in _daily[day]:
                before = _daily[day][mode].copy()
                _daily[day][mode] = {"pnl_pct": 0.0, "trades": 0, "wins": 0, "losses": 0}
            else:
                before = {}
                _daily.setdefault(day, {})[mode] = {"pnl_pct": 0.0, "trades": 0, "wins": 0, "losses": 0}
            _persist_save()
            self._j({"ok": True, "day": day, "mode": mode,
                     "before": before, "after": _daily[day][mode]})

        elif p == "/api/save-log":
            day = b.get("day", _kst_day())
            path = save_daily_log(day)
            self._j({"ok":True,"day":day,"path":path})

        else: self._j({"error":"not found"}, 404)

if __name__ == "__main__":
    _persist_load()
    # 환경변수 PORT가 .env보다 우선 (테스트 서버를 다른 포트에 띄우기 위함)
    port = int(os.environ.get("PORT") or _e("PORT", "5000"))
    ThreadingHTTPServer.allow_reuse_address = False   # 운영 서버와 같은 포트에 겹쳐 붙는 사고 방지
    srv  = ThreadingHTTPServer(("0.0.0.0",port), Handler)
    print(f"\n{'='*52}\n  Deepcoin Bot — Claude SMC 메인봇\n  http://localhost:{port}\n  Stop: Ctrl+C\n{'='*52}\n")
    try: srv.serve_forever()
    except KeyboardInterrupt:
        _persist_save()
        print("Stopped")
