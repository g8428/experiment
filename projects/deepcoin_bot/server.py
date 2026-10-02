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
    from smc_engine import find_swings, get_kill_zone, get_asian_range, find_fvg
    get_smc_signal = get_ict_signal  # ICT가 SMC superset
    _SMC_AVAILABLE = True
except ImportError:
    _SMC_AVAILABLE = False
    def get_kill_zone(*a, **kw): return None
    def get_asian_range(*a, **kw): return None
    def find_fvg(*a, **kw): return ([], [])
    def get_ict_signal(*a, **kw): return {"signal": None}
    def get_ote_signal(*a, **kw): return {"signal": None}
    def get_mtf_signal(*a, **kw): return {"signal": None}
    def get_killzone_signal(*a, **kw): return {"signal": None}
    def get_breaker_signal(*a, **kw): return {"signal": None}

# 라이브 멀티전략 우선순위 (2026-10-01 6개월 재검증 후 조정):
# OTE(+206.42%), MTF(+44.13%)는 6개월 재백테스트에서도 유지 — m15_confirm_n=2(B안,
# 직전 15분봉 확인캔들 재검증)로 노이즈성 신호 안정화.
# 킬존NY전용은 9/23 +25.16%→지금 -33.89%로 역전(숏 승률 17.4%가 주범), Breaker는
# 원래부터 약함(-26.53%→-21.55%, 롱 승률 25%가 주범) — 둘 다 비활성화.
_SIGNAL_CHAIN = [
    ("OTE", lambda kl, h1, d1, m5: get_ote_signal(kl, h1_kl=h1, d1_kl=d1, m15_confirm_n=2)),
    ("MTF", lambda kl, h1, d1, m5: get_mtf_signal(kl, h1_kl=h1, d1_kl=d1, m5_kl=m5, m15_confirm_n=2)),
]

def _multi_strategy_signal(kl, h1_kl, d1_kl, m5_kl):
    """4개 전략을 전부 평가하고, 우선순위 순으로 가장 먼저 시그널을 낸 전략을 채택.
    반환: (채택 smc_dict, 전략명 또는 None, {전략명: 각 결과 dict}) — 결과 dict는
    대시보드에 "각 전략이 지금 왜 안 되는지"를 보여주는 데 쓴다."""
    if not _SMC_AVAILABLE:
        return {"signal": None}, None, {}
    results, chosen, src = {}, None, None
    for name, fn in _SIGNAL_CHAIN:
        try:
            r = fn(kl, h1_kl, d1_kl, m5_kl)
        except Exception as e:
            r = {"signal": None, "reason": f"오류 {e}"}
        results[name] = r
        if chosen is None and r.get("signal"):
            chosen, src = r, name
    if chosen is None:
        chosen = results.get("MTF") or {"signal": None}   # OB/FVG 진단 필드가 있는 결과를 모니터링용으로
    return chosen, src, results

import sys as _sys_w
_sys_w.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest"))
try:
    from weights import get_weight as _get_weight
    _WEIGHTS_AVAILABLE = True
except ImportError:
    _WEIGHTS_AVAILABLE = False
    def _get_weight(key): return 1.0

# ── 일봉+4시간봉 롱 추세돌파 (2026-10-01 재검증에서 채택). 신호 로직은 backtest/strategies_v2.py 재사용 ──
try:
    import trend_live as _TL
    _TL_OK = _TL.AVAILABLE
    _TL_ERR = _TL.IMPORT_ERROR
except Exception as _tl_e:
    _TL = None; _TL_OK = False; _TL_ERR = str(_tl_e)
_trend_saved = {}   # 재시작 복원용: persist.json의 심볼별 추세 포지션 컨텍스트
_xslots_saved = {}  # 재시작 복원용: persist.json의 심볼별 추가 슬롯 목록
_posid_saved = {}   # 재시작 복원용: 심볼별 주 포지션 posId

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
# 딥코인 /deepcoin/market/instruments 실측값 (2026-09-24). 예전엔 ETH 0.01 / XRP 1.0으로
# 잘못 적혀 있어 ETH는 10배 과대, XRP는 10배 과소 사이징이었음 — 반드시 거래소 값과 맞출 것.
_CONTRACT_SZ = {
    "BTC-USDT-SWAP": 0.001,   # ctVal 0.001 BTC, lotSz 1, minSz 1
    "ETH-USDT-SWAP": 0.1,     # ctVal 0.1 ETH,   lotSz 0.1, minSz 0.1
    "XRP-USDT-SWAP": 0.1,     # ctVal 0.1 XRP,   lotSz 1, minSz 100
}
_MIN_SZ = {"BTC-USDT-SWAP": 1, "ETH-USDT-SWAP": 1, "XRP-USDT-SWAP": 100}
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
# 의도 상태 — 워치독이 "사용자가 껐다"와 "죽어서 멈췄다"를 구분하는 기준.
# running=True인데 _bots_st[sym]["running"]이 False면 죽은 것으로 보고 재시작한다.
_bots_want = {sym: {"running": False, "mode": "sim", "restarts": []} for sym in _ACTIVE_SYMS}
_WATCHDOG_MAX_RESTARTS = 5      # 이 횟수 넘게 재시작 반복되면 루프 문제로 보고 포기
_WATCHDOG_WINDOW_SEC   = 1800   # 30분 창

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
                if cb.get("trend_ctx"): _trend_saved[sym] = cb["trend_ctx"]
                if cb.get("extra_slots"): _xslots_saved[sym] = cb["extra_slots"]
                if cb.get("pos_id"): _posid_saved[sym] = cb["pos_id"]
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
                "trend_ctx": st.get("trend_ctx"),
                "extra_slots": st.get("extra_slots") or [],
                "pos_id": st.get("pos_id"),
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
    "rr_min":                 1.2,
    "sl_cap_pct":             2.0,
    "tp_max_pct":             15.0,
    # TP 상한 ATR 배수. tp_max_pct(15%)는 사실상 상한 역할을 못 해서 TP가 3.3 ATR까지 벌어졌다.
    "tp_max_atr_mult":        3.0,
    "tp_max_atr_mult_by_sym": {},
    # TP 앞 역방향 FVG에서 TP를 끊을지 여부
    "tp_fvg_block":           True,
    "tp_min_margin_pct":      0,
    "tp_min_margin_by_sym":   {},
    "sl_cap_pct_by_sym":      {},
    "sl_min_atr_mult":        1.2,
    "sl_min_atr_mult_by_sym": {},
    # 기존 OTE→MTF 체인 사용 여부 (2026-10-01 정직한 백테스트에서 거래당 -0.3~-0.6R — 끄는 걸 권장)
    "legacy_chain_enabled":   True,
    # 일봉+4시간봉 롱 추세돌파. risk_pct는 '1회 손절 시 계좌 손실 %' (기존 체인 risk_pct와 별개)
    "trend": {"enabled": False, "symbols": ["BTC-USDT-SWAP"], "risk_pct": 2.0,
              "allow_short": False, "liq_mult": 2.0,
              "partial_tp_r": 1.0, "partial_tp_frac": 0.3, "partial_be": True},
    # 같은 심볼에서 기존 체인(단타) 포지션을 추가 가상 슬롯으로 동시 보유 (거래소는 방향당 포지션 1개로 합쳐지므로 로컬 슬롯)
    "multi_slot": {"enabled": False, "symbols": ["BTC-USDT-SWAP"], "max_slots": 3},
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
                  "tp_min_margin_pct", "tp_min_margin_by_sym",
                  "sl_cap_pct_by_sym", "sl_min_atr_mult", "sl_min_atr_mult_by_sym",
                  "tp_max_atr_mult", "tp_max_atr_mult_by_sym", "tp_fvg_block",
                  "legacy_chain_enabled", "trend", "multi_slot"):
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

def _spawn_bot_thread(sym, mode):
    _bots_st[sym]["running"] = False
    _bots_gen[sym] += 1
    t = threading.Thread(target=_run_claude_bot, daemon=True,
        kwargs={"mode": mode, "gen": _bots_gen[sym], "sym": sym})
    _bots_thr[sym] = t
    t.start()

def _bot_watchdog():
    """20초마다: '가동 의도'인데 루프가 죽어있는 심볼을 감지해 같은 모드로 재시작.
    /api/claude/stop으로 사용자가 직접 끈 건 _bots_want도 같이 꺼지므로 건드리지 않는다.
    같은 심볼이 30분 안에 5번 넘게 재시작되면 루프 자체 문제로 보고 더 시도하지 않는다."""
    while True:
        time.sleep(20)
        now = time.time()
        for sym, want in _bots_want.items():
            if not want["running"] or sym not in _active_syms_cfg:
                continue
            if _bots_st.get(sym, {}).get("running"):
                continue
            want["restarts"] = [t for t in want["restarts"] if now - t < _WATCHDOG_WINDOW_SEC]
            if len(want["restarts"]) >= _WATCHDOG_MAX_RESTARTS:
                continue
            want["restarts"].append(now)
            print(f"[watchdog] {sym} 죽어있음(의도=가동 {want['mode']}) → 재시작 "
                  f"({len(want['restarts'])}/{_WATCHDOG_MAX_RESTARTS} in {_WATCHDOG_WINDOW_SEC//60}분)")
            try:
                _spawn_bot_thread(sym, want["mode"])
            except Exception as e:
                print(f"[watchdog] {sym} 재시작 실패: {e}")

_thr_mod.Thread(target=_bot_watchdog, daemon=True).start()
# ──────────────────────────────────────────────────────────────────


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
    """ATR(14) + 현재가 — SL/TP ATR 폴백과 최소 SL 계산에만 쓴다.
    (EMA/RSI/BB는 전략 함수 밖의 별도 필터였고 백테스트에 없던 것이라 제거됨)"""
    if len(kl) < 15: return {}
    hi = [k["h"] for k in kl]; lo = [k["l"] for k in kl]; cl = [k["c"] for k in kl]
    tr_list = [max(hi[i]-lo[i], abs(hi[i]-cl[i-1]), abs(lo[i]-cl[i-1]))
               for i in range(1, len(kl))]
    return {"price": cl[-1], "atr": round(sum(tr_list[-14:]) / 14, 6)}


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
         signal_src=None, smc_ctx=None, sym="BTC-USDT-SWAP", size_pct=None, partial=False):
    global _pattern_stats
    day = _kst_day()
    ts  = datetime.now(timezone(timedelta(hours=9))).strftime("%m-%d %H:%M")
    _logs.append({"ts":ts,"day":day,"mode":mode,"sym":sym,"action":action,
        "price":price,"atr":ind.get("atr"),"reason":reason,"pnl":pnl,
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
        if not partial:   # 반익절은 일 P&L만 반영 — 거래수/승패/패턴통계는 최종 청산에서 1회
            s["trades"] += 1
            if pnl > 0: s["wins"]  += 1
            else:       s["losses"] += 1
        # ── 패턴 통계 누적 학습 ─────────────────────────────────
        if not partial and smc_ctx and smc_ctx.get("pattern_key"):
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
        "| 시간 | 심볼 | 모드 | 액션 | 가격 | TP | SL | 전략 | 이유 | PnL |",
        "|------|------|------|------|------|-----|-----|------|------|-----|",
    ]
    for l in day_logs:
        sym = l.get("sym", "BTC-USDT-SWAP")
        lines.append(
            f"| {l['ts']} | {sym.split('-')[0]} | {l['mode']} | {l['action']} "
            f"| ${_px_fmt(l['price'], sym)} | ${_px_fmt(l.get('tp_px'), sym)} | ${_px_fmt(l.get('sl_px'), sym)} "
            f"| {(l.get('smc_ctx') or {}).get('strategy', '-')} "
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
                    sz = max(_MIN_SZ.get(sym, 1), int(margin_to_use / margin_per_contract))
                    print(f"[사이징:{sym}] 잔고=${avail:.2f} size={size_pct}% 증거금=${margin_to_use:.2f} → {sz}계약 (계약당${margin_per_contract:.4f})")
                    return sz
    except Exception as e:
        print(f"[사이징오류:{sym}] {e}")
    return _MIN_SZ.get(sym, 1)

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

def _dc_positions(sym):
    """거래소 보유 포지션 목록(pos>0). split 모드라 주문 1건 = posId 1개(각자 TP/SL). 조회 실패 시 None."""
    try:
        r = _dc_request("GET", f"/deepcoin/account/positions?instId={sym}&instType=SWAP")
        if r.get("code") in ("0", 0):
            return [p for p in (r.get("data") or []) if int(float(p.get("pos", 0) or 0)) > 0]
    except Exception:
        pass
    return None

def _find_pos(plist, side, pid=None):
    for p in plist or []:
        if p.get("posSide") == side and (pid is None or p.get("posId") == pid):
            return p
    return None

def _new_pid(sym, side, before_pids):
    """주문 직후 새로 생긴 posId 탐지 (주문 전 posId 집합과 비교)."""
    for _ in range(4):
        time.sleep(1.5)
        for p in _dc_positions(sym) or []:
            if p.get("posSide") == side and p.get("posId") not in before_pids:
                return p.get("posId")
    return None

def _close_pid(sym, side, pid, mode, frac=1.0):
    """포지션(posId) 단위 시장가 청산 — split 모드는 closePosId 없으면 'NotEnoughPositionToClose'로 실패한다.
    pid=None이면 해당 방향 첫 포지션. frac<1이면 일부만.
    반환: True=청산됨(이미 없으면 True), None=수량 부족으로 생략, False=실패(재시도 필요)."""
    if mode != "real": return True
    pl = _dc_positions(sym)
    if pl is None: return False
    p = _find_pos(pl, side, pid)
    if not p: return True
    have = int(float(p["pos"]))
    n = have if frac >= 1 else int(have * frac)
    if n < 1 or (frac < 1 and have - n < 1): return None
    r = _dc_request("POST", "/deepcoin/trade/order", {
        "instId": sym, "tdMode": "isolated", "mrgPosition": "split",
        "side": "sell" if side == "long" else "buy", "posSide": side,
        "ordType": "market", "sz": str(n), "closePosId": p["posId"],
    })
    item = r.get("data") if isinstance(r.get("data"), dict) else {}
    ok = r.get("code") in ("0", 0) and str(item.get("sCode", "0")) in ("0", "")
    if not ok:
        print(f"[청산실패:{sym}] {side} pid={p['posId']} n={n} → {r}")
    return ok

# ── Claude 메인 봇 ────────────────────────────────────────────────
def _run_claude_bot(mode, gen=0, sym="BTC-USDT-SWAP"):
    """
    Claude 분석 결과를 직접 매매 트리거로 사용하는 메인 봇.
    gen: 봇 generation — 재시작 시 zombie thread가 즉시 종료되도록 함
    sym: 거래 심볼 (BTC-USDT-SWAP / ETH-USDT-SWAP / XRP-USDT-SWAP)
    """
    st = _bots_st[sym]
    claude_mode = "claude-" + mode

    # 로컬에 남은 포지션 상태는 같은 모드(sim↔sim)일 때만 이어받는다.
    # real은 항상 거래소 조회로 복원 — 시뮬 포지션이 persist를 타고 real로 넘어와
    # "거래소에 없음 → 청산됨"으로 가짜 기록되던 사고(2026-09-23 BTC) 재발 방지.
    _carry = (st.get("mode") == mode) and mode != "real"
    prev_pos   = st.get("position") if _carry else None
    prev_entry = (st.get("entry") or 0.0) if _carry else 0.0
    prev_pnl   = st.get("pnl")   or 0.0
    prev_tr    = st.get("trades") or 0
    prev_tp    = st.get("tp_px") if _carry else None
    prev_sl    = st.get("sl_px") if _carry else None

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
    _trend_ctx     = None  # 추세돌파 포지션 컨텍스트 (추적 손절·타임스탑·레버리지). None이면 기존 체인 포지션
    _pos_lev       = None  # 이 포지션의 실제 레버리지 (추세 전략은 손절폭에 따라 거래별로 다름)

    # ── 실제 모드: DeepCoin 포지션 동기화 ─────────────────────────
    _pos_id = None  # 주 포지션의 거래소 posId (split 모드: 주문 1건 = posId 1개, 청산도 posId 단위)
    _xclaimed = {x.get("pid") for x in (_xslots_saved.get(sym) or []) if x.get("pid")}
    if mode == "real" and pos is None:
        try:
            _dcl_all = _dc_positions(sym) or []
            _cands = [p for p in _dcl_all if p.get("posId") not in _xclaimed]
            _cands.sort(key=lambda p: p.get("posId") != _posid_saved.get(sym))   # 저장된 주 posId 우선
            for _dp in _cands:
                _dc_sz = int(float(_dp.get("pos", 0) or 0))
                if _dc_sz > 0:
                    _dc_side = _dp.get("posSide")
                    _dc_avg  = float(_dp.get("avgPx", 0) or 0)
                    _dc_tp   = float(_dp.get("tpTriggerPx", 0) or 0) or None
                    _dc_sl   = float(_dp.get("slTriggerPx", 0) or 0) or None
                    pos = _dc_side; entry = _dc_avg; _pos_id = _dp.get("posId")
                    tp_px = _dc_tp; sl_px = _dc_sl
                    # 추세돌파 포지션이면 저장된 컨텍스트(추적 손절 등)를 복원 — 진입가가 1% 이내로 일치할 때만
                    _sv = _trend_saved.get(sym)
                    if _sv and _dc_avg and abs(_sv.get("entry", 0) - _dc_avg) / _dc_avg < 0.01:
                        _trend_ctx = _sv
                        _pos_lev = _sv.get("lev")
                        _pos_opened_at = _sv.get("opened_ts", 0.0)
                        _pos_size_pct = _sv.get("size_pct")
                        _entry_ctx = {"strategy": "TREND-" + str(_sv.get("tag", "")),
                                      "pattern_key": f"TREND+{_sv.get('tag','')}+{sym.split('-')[0]}"}
                        _dc_sl = _sv.get("sl") or _dc_sl   # 추적 손절 반영
                    st.update({"position": pos, "entry": entry, "pos_id": _pos_id,
                               "tp_px": tp_px, "sl_px": _dc_sl,
                               "watch_msg": f"[DC복원] {_dc_side.upper()} @ ${_pf(_dc_avg)} sz={_dc_sz}"
                                            + (" [추세 컨텍스트 복원]" if _trend_ctx else "")})
                    sl_px = _dc_sl
                    print(f"[DC복원:{sym}] {_dc_side.upper()} {_dc_sz}계약 @ ${_pf(_dc_avg)} pid={_pos_id}"
                          + (f" 추세 컨텍스트 복원(sl={_dc_sl})" if _trend_ctx else ""))
                    break
        except Exception as _e:
            print(f"[DC포지션복원] 오류: {_e}")

    # ── 추가 슬롯 (같은 심볼 단타 동시 보유). split 모드라 슬롯마다 거래소 posId·TP/SL이 따로 있다 ──
    _xs = []
    for _s in (_xslots_saved.get(sym) or []):
        if mode == "real" and not _find_pos(_dc_positions(sym), _s.get("side"), _s.get("pid")):
            continue
        if _s.get("mode", mode) != mode:
            continue
        _xs.append(_s)
    if _xs:
        print(f"[슬롯복원:{sym}] 추가 슬롯 {len(_xs)}개 복원")

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

        # ── 추가 슬롯 관리: 로컬 SL/TP 판정 + 거래소 외부 청산 동기화 ──────
        for _x in list(_xs):
            _xd  = 1 if _x["side"] == "long" else -1
            _xlp = round((price - _x["entry"]) / _x["entry"] * 100 * _xd * _x["lev"], 4)
            _xact, _xwhy = None, None
            _xpl = _dc_positions(sym) if mode == "real" else None
            if mode == "real" and _xpl is not None and time.time() - _x["opened_ts"] > 90 and not _find_pos(_xpl, _x["side"], _x.get("pid")):
                _xact, _xwhy = "SL_HIT" if _xlp < 0 else f"CLOSE_{_x['side'].upper()}", f"슬롯 외부 청산 확인(거래소 포지션 없음) {_xlp:+.2f}% ({_x['lev']}x)"
            elif _x.get("sl") and ((_xd == 1 and price <= _x["sl"]) or (_xd == -1 and price >= _x["sl"])):
                _xact, _xwhy = "SL_HIT", f"슬롯 SL ${_pf(_x['sl'])} 터치 {_xlp:+.2f}% ({_x['lev']}x)"
            elif _x.get("tp") and ((_xd == 1 and price >= _x["tp"]) or (_xd == -1 and price <= _x["tp"])):
                _xact, _xwhy = f"CLOSE_{_x['side'].upper()}", f"슬롯 TP ${_pf(_x['tp'])} 달성 {_xlp:+.2f}% ({_x['lev']}x)"
            if _xact:
                if "외부 청산" not in _xwhy and not _close_pid(sym, _x["side"], _x.get("pid"), mode):
                    print(f"[슬롯청산실패:{sym}] 다음 루프 재시도")
                    continue
                _rec(claude_mode, _xact, price, ind, f"[슬롯{_x['n']}] {_xwhy}",
                     pnl=_xlp, signal_src="Claude", smc_ctx=_x.get("ctx"), sym=sym, size_pct=_x["size_pct"])
                sess_pnl += _xlp; sess_tr += 1
                _last_fail_sl = (_x.get("sl") or 0.0) if _xact == "SL_HIT" else 0.0
                _xs.remove(_x)
                _last_close = time.time(); st["last_close"] = _last_close

        _ms         = _claude_cfg.get("multi_slot") or {}
        _multi_on   = bool(_ms.get("enabled") and sym in (_ms.get("symbols") or []))
        _max_slots  = int(_ms.get("max_slots", 3))
        _slots_used = (1 if pos else 0) + len(_xs)
        _can_slot   = _slots_used < _max_slots
        _as_extra   = bool(pos and _multi_on and _can_slot)
        _enter_prim = bool(pos is None and (not _xs or _can_slot))
        _pos_before = pos   # 이번 루프에 새로 진입한 주 포지션은 같은 루프에서 홀딩 판정하지 않는다

        if _enter_prim or _as_extra:
            # ── 추세돌파 (일봉+4시간봉, 롱). 1H 봉이 마감된 직후에만 판단 — 미완성 캔들로 판단하지 않는다 ──
            _tcfg     = _claude_cfg.get("trend") or {}
            _trend_on = bool(_TL_OK and _tcfg.get("enabled") and sym in (_tcfg.get("symbols") or [])
                             and not _as_extra)   # 추가 슬롯은 단타 전용
            _legacy_on = bool(_claude_cfg.get("legacy_chain_enabled", True))
            _tres, _tsig = None, None
            if _trend_on:
                try:
                    _tres = _TL.evaluate(sym, allow_short=bool(_tcfg.get("allow_short", False)))
                except Exception as _te:
                    _tres = {"ok": False, "reason": f"추세 평가 오류 {_te}", "signal": None}
                _tsig = _tres.get("signal")
                st["trend"] = {k: _tres.get(k) for k in ("ok", "bar_t", "bar_ct", "bar_close", "regime", "regime_label",
                                                         "adx4", "shock", "levels", "signal", "reason", "error")}
            elif not _TL_OK and _tcfg.get("enabled"):
                st["trend"] = {"ok": False, "reason": f"추세 모듈 비활성: {_TL_ERR}"}

            # ── 기존 멀티전략 체인 (OTE→MTF). 끄면(legacy_chain_enabled=false) 평가하지 않는다 ──
            if _legacy_on:
                smc, _sig_src, _chain = _multi_strategy_signal(kl, kl_1h, kl_1d, kl_5m)
            else:
                smc, _sig_src, _chain = {"signal": None, "reason": "기존 체인 비활성"}, None, {}
            st["chain"] = {n: {"signal": r.get("signal"), "reason": r.get("reason", "")}
                           for n, r in _chain.items()}
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
            _chain_brief = " | ".join(f"{n}:{(r.get('reason') or '-')[:16]}" for n, r in _chain.items())

            # ── 직전 SL 레벨 재진입 차단 (같은 구조에서 반복 손절 방지) ──
            _same_sl = (_last_fail_sl > 0 and s_sl and
                        abs(s_sl - _last_fail_sl) / max(_last_fail_sl, 1) < 0.002)

            # ── 추세돌파 진입 (게이트: 일 한도 · 쿨다운만. 손절폭이 크므로 기존 SL상한/RR/TP 게이트는 쓰지 않는다) ──
            _trend_handled = False
            if _tsig and ok and cooldown_left <= 0:
                _trend_handled = True
                _TL.consume(sym, _tres["bar_t"])   # 성공/실패와 무관하게 이 봉 신호는 한 번만 시도
                _sd      = _tsig["stop_dist"]
                _t_lev   = _TL.pick_leverage(_sd, max_lev=_claude_cfg.get("leverage", 20),
                                             liq_mult=float(_tcfg.get("liq_mult", 2.0)))
                _t_risk  = float(_tcfg.get("risk_pct", 2.0))
                _t_marg  = _TL.margin_pct(_t_risk, _sd, _t_lev)
                sig      = "long" if _tsig["dir"] == 1 else "short"
                _t_sl    = _px_round(price * (1 - _tsig["dir"] * _sd), sym)
                reason = (f"추세돌파 {sig.upper()} [{_tsig['tag']}] 일봉국면={_tres.get('regime_label')} "
                          f"| 손절 {_sd*100:.2f}% 레버리지 {_t_lev}x 증거금 {_t_marg:.1f}% (계좌리스크 {_t_risk}%) "
                          f"| 추적 {_tsig['trail_dist']:.6g} [SL:${_pf(_t_sl)}]")
                _ok_entry = True
                _t_pid = None
                if mode == "real":
                    _tpl0 = _dc_positions(sym)
                    _tbefore = {p.get("posId") for p in (_tpl0 or [])}
                    _set_leverage(_t_lev, sym=sym)
                    _t_sz = _calc_sz(price, _t_marg, _t_lev, sym=sym)
                    print(f"[추세진입:{sym}] {sig} 손절{_sd*100:.2f}% lev={_t_lev}x 증거금{_t_marg:.2f}% → {_t_sz}계약")
                    ord_r = _place_order("buy" if sig == "long" else "sell", sig, _t_sz,
                                         tp_px=None, sl_px=_t_sl, sym=sym)
                    if ord_r.get("code") not in ("0", 0):
                        _ok_entry = False
                        reason += f" [주문실패:{ord_r.get('msg','')}]"
                        st["watch_msg"] = reason
                        time.sleep(60)
                    else:
                        _t_pid = _new_pid(sym, sig, _tbefore)
                if _ok_entry:
                    pos = sig; entry = price; sl_px = _t_sl; tp_px = None; _pos_id = _t_pid
                    _pos_opened_at = time.time(); _pos_lev = _t_lev; _pos_size_pct = _t_marg
                    _trend_ctx = _TL.new_ctx(_tsig, entry, _t_lev, size_pct=_t_marg)
                    _trend_ctx["sl"] = _trend_ctx["init_sl"] = sl_px
                    _entry_ctx = {"strategy": "TREND-" + _tsig["tag"], "kill_zone": None,
                                  "pattern_key": f"TREND+{_tsig['tag']}+{sym.split('-')[0]}",
                                  "rr": None, "regime": _tres.get("regime_label")}
                    _rec(claude_mode, f"ENTER_{sig.upper()}", price, ind, reason, tp_px=None, sl_px=sl_px,
                         signal_src="Trend", smc_ctx=_entry_ctx, sym=sym)
                    st["watch_msg"] = reason
            elif _tsig and not ok:
                st["watch_msg"] = f"[추세 {_tsig['tag']}] 신호 있음 — 일 한도: {stop_msg}"

            # ── 리스크 게이트만 (시그널 필터는 전략 함수 안에 있음): 일한도 → 시그널 → 직전SL → 쿨다운 ──
            if _trend_handled:
                pass
            elif not ok:
                st["watch_msg"] = f"일 한도: {stop_msg}"
            elif not s_sig:
                _tmsg = f"[추세] {_tres.get('reason')}" if _tres else ""
                if _legacy_on:
                    st["watch_msg"] = f"시그널 없음 [{kz_name}]{asian_tag} — {_chain_brief}" + (f" | {_tmsg}" if _tmsg else "")
                else:
                    st["watch_msg"] = _tmsg or "시그널 없음 (기존 체인 비활성, 추세 전략 대기)"
            elif _same_sl:
                st["watch_msg"] = f"[{_sig_src}] 직전 손절 구조 재진입 차단 SL≈${_pf(_last_fail_sl)}"
            elif cooldown_left > 0:
                st["watch_msg"] = f"[{_sig_src} {s_sig}] 쿨다운 {int(cooldown_left//60)}분 {int(cooldown_left%60)}초"
            else:
                # ── 진입 실행 ────────────────────────────────────
                sig = s_sig  # SMC가 방향 결정
                _lev     = _claude_cfg.get("leverage", 20)
                _TP_CAP  = _claude_cfg.get("tp_max_pct", 15.0) / 100
                # 심볼별 SL 상한 (없으면 전역 sl_cap_pct) — XRP처럼 변동성 큰 종목만 더 타이트하게
                _sl_cap_map = _claude_cfg.get("sl_cap_pct_by_sym", {})
                _SL_CAP  = _sl_cap_map.get(sym, _claude_cfg.get("sl_cap_pct", 2.0)) / 100
                # 심볼별 tp_min_margin → 현물 이동폭 환산 (증거금 기준 % ÷ 레버리지)
                _sym_tp_map = _claude_cfg.get("tp_min_margin_by_sym", {})
                _tp_min_margin = _sym_tp_map.get(sym, _claude_cfg.get("tp_min_margin_pct", 0))
                _TP_MIN  = _tp_min_margin / (100.0 * _lev) if _tp_min_margin > 0 else 0.0
                # 최소 SL: ATR×배율 또는 0.3% 중 큰 값. 배율은 심볼별로 다르게 (변동성 큰 종목만 낮춰서
                # 구조적 저점/고점이 좁아도 ATR이 억지로 넓히는 폭을 줄인다 — 백테스트는 이 ATR 확장이
                # 없고 구조 레벨 그대로 쓰므로, 배율을 낮출수록 라이브가 백테스트에 가까워진다)
                _sl_mult_map = _claude_cfg.get("sl_min_atr_mult_by_sym", {})
                _sl_mult = _sl_mult_map.get(sym, _claude_cfg.get("sl_min_atr_mult", 1.2))
                _SL_MIN  = max(atr / price * _sl_mult, 0.0035)
                # TP 상한(ATR 배수): 구조 레벨은 최대 15시간치 스윙에서 나오는데 SL은 15분 ATR 기준이라
                # 시간축이 안 맞는다. 15분봉에서 도달 가능한 거리로 TP를 묶는다 (0이면 비활성).
                _tp_atr_mult_map = _claude_cfg.get("tp_max_atr_mult_by_sym", {})
                _tp_atr_mult = _tp_atr_mult_map.get(sym, _claude_cfg.get("tp_max_atr_mult", 3.0))
                _TP_ATR_CAP = (atr / price * _tp_atr_mult) if _tp_atr_mult > 0 else 1e9

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
                        _tp_dist = min((_s_tp - price) / price, _TP_CAP, _TP_ATR_CAP) if _s_tp > price else atr / price * 2.0
                        raw_sl   = (price - s_sl) / price if s_sl < price else atr / price * _sl_mult
                        _sl_dist = min(max(raw_sl, _SL_MIN), _SL_CAP)
                    else:
                        _tp_dist = min((price - _s_tp) / price, _TP_CAP, _TP_ATR_CAP) if _s_tp < price else atr / price * 2.0
                        raw_sl   = (s_sl - price) / price if s_sl > price else atr / price * _sl_mult
                        _sl_dist = min(max(raw_sl, _SL_MIN), _SL_CAP)
                    smc_tag = f"[{_sig_src or 'SMC'}]"
                else:
                    _tp_dist = min(atr / price * 2.0, _TP_CAP, _TP_ATR_CAP)
                    _sl_dist = min(max(atr / price * _sl_mult, _SL_MIN), _SL_CAP)
                    smc_tag = "[ATR폴백]"

                # SL 상한이 하한보다 좁으면 ATR 확대가 통째로 무효화된다(min(max(raw,floor),cap) 순서상
                # cap이 항상 이김). 노이즈 밖으로 빼려던 SL이 조용히 노이즈 안으로 돌아오므로 진입을 막는다.
                if _SL_CAP < _SL_MIN:
                    st["watch_msg"] = (
                        f"SL상한<하한 스킵 {smc_tag} cap={_SL_CAP*100:.2f}% < min={_SL_MIN*100:.2f}%"
                    )
                    time.sleep(30); continue

                # TP 앞 역방향 FVG(미체결 갭) 절단: 롱이면 위쪽 하락FVG, 숏이면 아래쪽 상승FVG가 1차 벽이다.
                # 그 너머를 TP로 잡으면 벽에서 되돌림 맞고 SL까지 끌려간다(09-30 BTC 건이 정확히 이 케이스).
                if _claude_cfg.get("tp_fvg_block", True):
                    try:
                        _b_fvg, _d_fvg = find_fvg(kl)
                    except Exception:
                        _b_fvg, _d_fvg = [], []
                    _tp_raw_px = price * (1 + _tp_dist) if sig == "long" else price * (1 - _tp_dist)
                    if sig == "long":
                        _walls = [f["bot"] for f in _d_fvg if price < f["bot"] < _tp_raw_px]
                        if _walls:
                            _tp_dist = max((min(_walls) * 0.999 - price) / price, 0.0)
                            smc_tag += "[FVG절단]"
                    else:
                        _walls = [f["top"] for f in _b_fvg if _tp_raw_px < f["top"] < price]
                        if _walls:
                            _tp_dist = max((price - max(_walls) * 1.001) / price, 0.0)
                            smc_tag += "[FVG절단]"

                # 비용 바닥: TP가 왕복 수수료(≈0.12%)를 유의미하게 못 넘으면 먹을 게 없다.
                # FVG 벽이 코앞이라 TP가 눌린 경우가 여기서 걸린다 — RR이 아니라 이게 진짜 차단 기준.
                if _TP_MIN > 0 and _tp_dist < _TP_MIN:
                    st["watch_msg"] = (
                        f"TP<비용바닥 스킵 {smc_tag} TP={_tp_dist*100:.2f}% < {_TP_MIN*100:.2f}%"
                    )
                    time.sleep(30); continue

                # RR 하한은 느슨하게 둔다. 무편향 랜덤워크에서 TP 선도달 확률은 SL/(SL+TP)라
                # RR이 높든 낮든 기대값은 같다 — RR 자체는 엣지를 만들지 않는다. 높은 RR을 요구하면
                # TP가 먼 신호만 통과시키게 되는데, 그게 TP_HIT 0건/SL_HIT 12건을 만든 원인이었다.
                # 진짜 바닥은 수수료이고 그건 위 _TP_MIN이 담당한다.
                _rr_min = _claude_cfg.get("rr_min", 1.2)
                if _tp_dist < _sl_dist * _rr_min:
                    _rr_now = (_tp_dist / _sl_dist) if _sl_dist else 0
                    st["watch_msg"] = (
                        f"손익비 불량 스킵 {smc_tag} TP={_tp_dist*100:.2f}% SL={_sl_dist*100:.2f}% "
                        f"RR={_rr_now:.2f}<{_rr_min}"
                    )
                    time.sleep(30); continue
                _sv_tp, _sv_sl = tp_px, sl_px   # 추가 슬롯 진입 시 주 포지션의 tp/sl 로컬 변수를 보존
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
                            f"+OB{_ob_cnt}+FVG{_fvg_cnt}+{'sweep' if _has_sw else 'no_sweep'}"
                            f"+{sym.split('-')[0]}")
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

                conf_tags = f"KZ={kz_name}"
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

                _ent_ok, _ent_size, _ent_sz, _ent_pid = False, None, None, None
                _ent_lev = _claude_cfg.get("leverage", 20)
                _has_dc_side = False
                if mode == "real":
                    _lev_now  = _claude_cfg.get("leverage", 20)
                    # 같은 방향 포지션이 이미 있으면 그 레버리지를 그대로 쓴다(방향 단위 설정이라 바꾸면 기존 포지션에 영향)
                    _pl0 = _dc_positions(sym)
                    if _pl0 is None:
                        st["watch_msg"] = "거래소 포지션 조회 실패 — 진입 보류"
                        tp_px, sl_px = _sv_tp, _sv_sl
                        time.sleep(30); continue
                    _before_pids = {p.get("posId") for p in _pl0}
                    _same = _find_pos(_pl0, sig)
                    _has_dc_side = _same is not None
                    try:
                        if _has_dc_side and _same.get("lever"): _lev_now = int(float(_same["lever"]))
                    except Exception:
                        pass
                    _ent_lev = _lev_now
                    _risk_pct = _claude_cfg.get("risk_pct", 10.0)
                    # 동적 사이징: risk_pct % / (SL거리 × 레버리지) → 증거금 비율
                    _dyn_size = min(80.0, _risk_pct / (_sl_dist * _lev_now)) if _sl_dist > 0 else _claude_cfg.get("size_pct", 40)
                    # 적응형 가중치 적용 (백테스트 승률 기반)
                    _wt = _get_weight(_pat_key) if _WEIGHTS_AVAILABLE else 1.0
                    _dyn_size = min(80.0, _dyn_size * _wt)
                    if not _has_dc_side:
                        _set_leverage(_lev_now, sym=sym)
                    side  = "buy" if sig == "long" else "sell"
                    _sz   = _calc_sz(price, _dyn_size, _lev_now, sym=sym)
                    print(f"[사이징:{sym}] 리스크{_risk_pct}% SL={_sl_dist*100:.2f}% 레버리지={_lev_now}x 가중치={_wt:.2f} → {_dyn_size:.1f}% 증거금")
                    ord_r = _place_order(side, sig, _sz, tp_px=tp_px, sl_px=sl_px, sym=sym)
                    if ord_r.get("code") not in ("0", 0):
                        reason += f" [주문실패:{ord_r.get('msg','')}]"
                        st["watch_msg"] = reason
                        if _as_extra: tp_px, sl_px = _sv_tp, _sv_sl
                        else:         tp_px = None; sl_px = None
                        time.sleep(60)   # 주문 실패 후 1분 대기 (즉시 재시도 방지)
                    else:
                        _ent_ok, _ent_size, _ent_sz = True, _dyn_size, _sz
                        _ent_pid = _new_pid(sym, sig, _before_pids)
                else:
                    _ent_ok, _ent_size, _ent_sz = True, _claude_cfg.get("size_pct", 40), 0

                if _ent_ok and _as_extra:
                    _used = {x["n"] for x in _xs}
                    _n = next(i for i in range(1, 10) if i not in _used)
                    _xs.append({"n": _n, "side": sig, "entry": price, "sz": int(_ent_sz or 0), "pid": _ent_pid,
                                "tp": tp_px, "sl": sl_px, "lev": _ent_lev, "size_pct": _ent_size,
                                "opened_ts": time.time(), "mode": mode, "ctx": _smc_ctx})
                    _rec(claude_mode, f"ENTER_{sig.upper()}", price, ind, f"[슬롯{_n}] " + reason,
                         tp_px=tp_px, sl_px=sl_px, signal_src="Claude", smc_ctx=_smc_ctx, sym=sym)
                    st["watch_msg"] = f"[슬롯{_n}] " + reason
                    tp_px, sl_px = _sv_tp, _sv_sl
                elif _ent_ok:
                    pos = sig; entry = price; _pos_id = _ent_pid
                    _pos_opened_at = time.time()
                    _pos_size_pct  = _ent_size
                    _pos_lev       = _ent_lev if mode == "real" else None
                    _entry_ctx = _smc_ctx   # 청산 시 패턴 학습에 사용
                    _rec(claude_mode, f"ENTER_{sig.upper()}", price, ind, reason,
                         tp_px=tp_px, sl_px=sl_px, signal_src="Claude", smc_ctx=_smc_ctx, sym=sym)
                    st["watch_msg"] = reason

        if _pos_before:
            _lev = _pos_lev or _claude_cfg.get("leverage", 20)   # 추세 포지션은 거래별 레버리지
            # ── Real 모드: DeepCoin 실제 포지션 확인 (진입 후 90초 유예) ──
            if mode == "real" and time.time() - _pos_opened_at > 90:
                try:
                    _spl = _dc_positions(sym)
                    if _spl is not None:
                        _dc_has_pos = _find_pos(_spl, pos, _pos_id) is not None
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
                            pos = None; entry = 0.0; tp_px = None; sl_px = None; _pos_id = None
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

                # 추세돌파 포지션: 마감된 1H 봉으로 추적 손절 갱신 → 현재가로 손절/타임스탑 판단 (거래소엔 최초 손절만 걸려 있음)
                if _trend_ctx:
                    try:
                        _tm = _TL.evaluate(sym, allow_short=bool((_claude_cfg.get("trend") or {}).get("allow_short", False)))
                        st["trend"] = {k: _tm.get(k) for k in ("ok", "bar_t", "bar_ct", "bar_close", "regime", "regime_label",
                                                               "adx4", "shock", "levels", "reason", "error")}
                    except Exception as _te:
                        print(f"[추세갱신:{sym}] 오류 {_te}")
                    _tkind, _tmsg = _TL.manage(_trend_ctx, price, h1=_TL.closed_h1(sym))
                    _tcfg = _claude_cfg.get("trend") or {}
                    _ptr = _tcfg.get("partial_tp_r")
                    if not _tkind and _TL.partial_due(_trend_ctx, price, _ptr):
                        _pf_frac = float(_tcfg.get("partial_tp_frac", 0.3))
                        _pres = _close_pid(sym, pos, _pos_id, mode, frac=_pf_frac)
                        _trend_ctx["partial_done"] = True   # 실패/수량부족이어도 재시도 폭주 방지
                        if _pres:
                            _psz = _pos_size_pct
                            _rec(claude_mode, "PARTIAL_TP", price, ind,
                                 f"반익절 {int(_pf_frac*100)}% @ {_ptr}R ${_pf(price)} {lev_pct:+.2f}% ({_lev}x)",
                                 pnl=lev_pct * _pf_frac, signal_src="Claude", smc_ctx=_entry_ctx,
                                 sym=sym, size_pct=_psz, partial=True)
                            _TL.apply_partial(_trend_ctx, _pf_frac, be=bool(_tcfg.get("partial_be", True)))
                            _pos_size_pct = _trend_ctx["size_pct"]
                    sl_px = _px_round(_trend_ctx["sl"], sym)
                    if _tkind:
                        close_reason = f"{_tmsg} {lev_pct:+.2f}% ({_lev}x)"
                        action = {"SL": "SL_HIT", "TRAIL": "TRAIL_EXIT", "TIME": "TIME_EXIT"}[_tkind]
                # SL
                elif sl_px and ((pos == "long"  and price <= sl_px) or
                              (pos == "short" and price >= sl_px)):
                    close_reason = f"SL ${_pf(sl_px)} 터치 {lev_pct:+.2f}% ({_lev}x)"
                    action = "SL_HIT"

                # TP
                elif tp_px and ((pos == "long"  and price >= tp_px) or
                                (pos == "short" and price <= tp_px)):
                    close_reason = f"TP ${_pf(tp_px)} 달성 {lev_pct:+.2f}% ({_lev}x)"
                    action = f"CLOSE_{pos.upper()}"

                if close_reason:
                    if not _close_pid(sym, pos, _pos_id, mode):
                        print(f"[청산실패:{sym}] 다음 루프 재시도")
                        time.sleep(30); continue
                    _rec(claude_mode, action, price, ind, close_reason,
                         pnl=lev_pct, signal_src="Claude", smc_ctx=_entry_ctx,
                         sym=sym, size_pct=_pos_size_pct)
                    sess_pnl += lev_pct; sess_tr += 1
                    if action == "SL_HIT":
                        _last_fail_sl = sl_px
                    else:
                        _last_fail_sl = 0.0
                    pos = None; entry = 0.0; tp_px = None; sl_px = None; _pos_id = None
                    _pos_opened_at = 0.0; _entry_ctx = None; _pos_size_pct = None
                    _last_close = time.time()
                    st["last_close"] = _last_close
                else:
                    _src_tag = f"[{_entry_ctx['strategy']}] " if _entry_ctx and _entry_ctx.get("strategy") else ""
                    _trail_tag = " (추적중)" if _trend_ctx and _trend_ctx.get("trail_on") else ""
                    st["watch_msg"] = (
                        f"{_src_tag}홀딩 {pos.upper()} @ ${_pf(entry)} "
                        f"| 현재 ${_pf(price)} ({lev_pct:+.2f}%, {_lev}x) "
                        f"| TP ${_pf(tp_px)} SL ${_pf(sl_px)}{_trail_tag}"
                    )

        if pos is None:
            _trend_ctx = None; _pos_lev = None   # 어떤 경로로 청산됐든 추세 컨텍스트 정리

        # tuning.json active_symbols에서 빠지면 포지션 없을 때 스레드 종료
        if pos is None and not _xs and sym not in _active_syms_cfg:
            st["watch_msg"] = "active_symbols 제외 — 정지"
            st["position"] = None
            break

        st.update({
            "position": pos, "price": _px_round(price, sym),
            "entry": _px_round(entry, sym) if pos else None,
            "tp_px": tp_px, "sl_px": sl_px, "trend_ctx": _trend_ctx, "extra_slots": list(_xs), "pos_id": _pos_id,
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
            out = {}
            for s, st in _bots_st.items():
                d = dict(st)
                w = _bots_want.get(s, {})
                d["want_running"] = w.get("running", False)
                d["watchdog_restarts_30m"] = len(w.get("restarts", []))
                out[s] = d
            self._j(out)
        elif p == "/api/claude/config":   self._j(_claude_cfg)
        elif p == "/api/trend":
            # 일봉+4시간봉 추세돌파 상태 (심볼별 국면·돌파 레벨·신호·포지션 컨텍스트)
            tc = _claude_cfg.get("trend") or {}
            out = {"available": _TL_OK, "error": _TL_ERR if not _TL_OK else "", "cfg": tc,
                   "legacy_chain_enabled": bool(_claude_cfg.get("legacy_chain_enabled", True)), "syms": {}}
            for _s, _st in _bots_st.items():
                out["syms"][_s] = {
                    "enabled": bool(tc.get("enabled") and _s in (tc.get("symbols") or [])),
                    "eval": _st.get("trend"), "ctx": _st.get("trend_ctx"),
                    "position": _st.get("position"), "price": _st.get("price"),
                    "entry": _st.get("entry"), "sl_px": _st.get("sl_px"),
                }
            self._j(out)
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

        elif p == "/api/fills":
            # 거래소 실제 주문 이력 (체결 완료분) — 봇 내부 로그가 아니라 딥코인 원장이 기준
            n = min(int(qs.get("n", ["50"])[0]), 100)
            r = _dc_request("GET", f"/deepcoin/trade/orders-history?instType=SWAP&limit={n}")
            if str(r.get("code")) != "0":
                self._j({"ok": False, "code": r.get("code"), "msg": r.get("msg"), "orders": []}); return
            out = []
            for o in r.get("data") or []:
                if o.get("state") != "filled":
                    continue
                sym  = o.get("instId", "")
                side, ps = o.get("side"), o.get("posSide")
                avg  = float(o.get("avgPx") or 0); sz = float(o.get("accFillSz") or 0)
                lev  = float(o.get("lever") or 0) or None
                pnl  = float(o.get("pnl") or 0); fee = float(o.get("fee") or 0)
                ct   = _CONTRACT_SZ.get(sym, 1.0)
                margin = (sz * ct * avg / lev) if (lev and avg) else None
                is_close = (side == "sell" and ps == "long") or (side == "buy" and ps == "short")
                ts_ms = int(o.get("fillTime") or o.get("uTime") or 0)
                kst = datetime.fromtimestamp(ts_ms / 1000, tz=timezone(timedelta(hours=9))) if ts_ms else None
                out.append({
                    "ts": kst.strftime("%m-%d %H:%M") if kst else "-",
                    "ts_ms": ts_ms, "sym": sym, "ordId": o.get("ordId"),
                    "action": ("CLOSE_" if is_close else "OPEN_") + (ps or "").upper(),
                    "px": avg, "sz": sz, "lever": lev, "ordType": o.get("ordType"),
                    "pnl": pnl, "fee": fee,
                    "margin_pct": round((pnl - fee) / margin * 100, 2) if (margin and is_close) else None,
                })
            out.sort(key=lambda x: x["ts_ms"], reverse=True)
            self._j({"ok": True, "orders": out})
        elif p == "/api/logs":
            n = int(qs.get("n",["60"])[0])
            self._j(list(reversed(_logs[-n:])))
        elif p == "/api/daily":  self._j(_daily)
        elif p == "/api/gates":
            # 전략 밖 리스크 게이트 상태 (선택 심볼) — 라이브 루프의 진입 게이트와 1:1
            sym = qs.get("sym", ["BTC-USDT-SWAP"])[0]
            if sym not in _bots_st: sym = "BTC-USDT-SWAP"
            _st = _bots_st[sym]
            ok, msg = _can_trade("claude-" + _st.get("mode", "real"))
            cooldown_left = max(0, _st.get("last_close", 0) + _claude_cfg["cooldown"] - time.time())
            day = _dst(_kst_day(), "claude-" + _st.get("mode", "real"))
            self._j({
                "sym": sym,
                "gates": [
                    {"name": "일 한도", "pass": ok,
                     "value": msg or f"손익 {day['pnl_pct']:+.2f}% / 거래 {day['trades']}회 / 손절 {day['losses']}회"},
                    {"name": "쿨다운", "pass": cooldown_left <= 0,
                     "value": f"잔여 {int(cooldown_left//60)}분 {int(cooldown_left%60)}초" if cooldown_left > 0 else "없음"},
                    {"name": "킬존(참고)", "pass": True,
                     "value": {"london":"런던","newyork":"뉴욕","asian":"아시안"}.get(get_kill_zone(), "킬존외") + " — MTF·킬존NY 전략만 영향"},
                ],
                "limits": {"rr_min": _claude_cfg.get("rr_min"), "sl_cap_pct": _claude_cfg.get("sl_cap_pct"),
                           "tp_max_pct": _claude_cfg.get("tp_max_pct"),
                           "tp_min_margin": _claude_cfg.get("tp_min_margin_by_sym", {}).get(sym, _claude_cfg.get("tp_min_margin_pct", 0))},
            })
        elif p == "/api/regime":
            # 심볼별 일봉 시장국면 + 1H 추세 (라이브 _klines 캐시 재사용, 30초 캐시)
            out = {}
            for sym in _bots_st:
                try:
                    kl_1d = _klines(sym=sym, bar="1D", n=120)
                    kl_1h = _klines(sym=sym, bar="1H", n=25)
                    out[sym] = {
                        "regime":   get_market_regime(kl_1d) if kl_1d else "unknown",
                        "h1_trend": get_htf_trend(kl_1h) if kl_1h else "unknown",
                        "price":    kl_1d[-1]["c"] if kl_1d else None,
                    }
                except Exception as e:
                    out[sym] = {"regime": "unknown", "h1_trend": "unknown", "price": None, "error": str(e)}
            self._j(out)
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
                _bots_want[_sym] = {"running": True, "mode": mode, "restarts": []}
                _spawn_bot_thread(_sym, mode)
                started.append(_sym)
            self._j({"ok": True, "msg": f"Claude봇({mode}) 시작", "syms": started,
                     "skipped_not_active": skipped})

        elif p == "/api/claude/stop":
            req_syms = b.get("syms", list(_bots_st))
            if isinstance(req_syms, str): req_syms = [req_syms]
            for _sym in req_syms:
                if _sym in _bots_st: _bots_st[_sym]["running"] = False
                if _sym in _bots_want: _bots_want[_sym]["running"] = False
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
