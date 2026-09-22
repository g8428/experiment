"""
server.py 패치: BB 스캘퍼 → MTF FVG 스캘퍼 (1h 트렌드→15m FVG→1m 진입)
BB는 대시보드 보조 표시용으로 유지
"""
import sys, re
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

with open(r'C:\Users\g8428\deepcoin_bot\server.py', 'r', encoding='utf-8') as f:
    src = f.read()

# ── 1. _scalp_st 초기 dict에 FVG 필드 추가 ─────────────────────────────────
OLD_SCALP_ST = '''_scalp_st = {
    "running": False, "position": None, "pnl": 0.0, "trades": 0,
    "mode": "sim", "indicators": {}, "can_trade": True, "stop_msg": "",
    "price": 0, "entry": None, "daily": {}, "watch_msg": "대기 중",
    "tp_px": None, "sl_px": None,
}'''
NEW_SCALP_ST = '''_scalp_st = {
    "running": False, "position": None, "pnl": 0.0, "trades": 0,
    "mode": "sim", "indicators": {}, "can_trade": True, "stop_msg": "",
    "price": 0, "entry": None, "daily": {}, "watch_msg": "대기 중",
    "tp_px": None, "sl_px": None,
    "trend_1h": None, "fvg_bull": 0, "fvg_bear": 0, "fvg_active": [],
}'''
assert OLD_SCALP_ST in src, "ERROR: _scalp_st 블록을 찾지 못함"
src = src.replace(OLD_SCALP_ST, NEW_SCALP_ST, 1)
print("[1] _scalp_st FVG 필드 추가 OK")

# ── 2. _ind() 다음에 _detect_fvg() 삽입 ────────────────────────────────────
DETECT_FVG = '''

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

'''

# _ind() 함수 끝 이후 삽입 (줄: "        \"bb_mid\":   round(bm, 2),\n    }" 이후)
AFTER_IND = '''        "bb_mid":   round(bm, 2),
    }


# ── 모멘텀 시그널'''
NEW_AFTER_IND = '''        "bb_mid":   round(bm, 2),
    }

''' + DETECT_FVG.strip() + '''


# ── 모멘텀 시그널'''

assert AFTER_IND in src, "ERROR: _ind() 끝 블록을 찾지 못함"
src = src.replace(AFTER_IND, NEW_AFTER_IND, 1)
print("[2] _detect_fvg() 삽입 OK")

# ── 3. _scalp_sig() 전체 제거 (주석으로 남기지 않고 삭제) ────────────────────
OLD_SCALP_SIG_START = "# ── 스캘퍼 시그널 (볼린저밴드 평균회귀 + RSI) ────────────────────"
OLD_ANY_OPEN_POS    = "\ndef _any_open_pos():"
# _scalp_sig 블록 끝은 _any_open_pos 시작 직전
idx_start = src.find(OLD_SCALP_SIG_START)
idx_end   = src.find(OLD_ANY_OPEN_POS, idx_start)
assert idx_start != -1, "ERROR: _scalp_sig 시작을 못 찾음"
assert idx_end   != -1, "ERROR: _any_open_pos 를 못 찾음"
src = src[:idx_start] + src[idx_end+1:]  # +1: 앞의 \n 제거
print("[3] 구 _scalp_sig() 제거 OK")

# ── 4. _run_scalp() 전체 교체 ───────────────────────────────────────────────
NEW_RUN_SCALP = '''# ── MTF FVG 스캘퍼 (1h 트렌드 → 15m FVG → 1m 진입) ─────────────────────
def _run_scalp(mode):
    """
    진입 로직 (3단계 MTF 필터):
      1. 1h EMA9/21 → 트렌드 편향 파악
      2. 15m FVG   → 미체결 Fair Value Gap 구간 탐지
      3. 1m RSI+캔들 방향 → 정확한 진입 타이밍
    청산: ATR 기반 TP/SL (캡 적용)
    """
    global _scalp_st
    scalp_mode = "scalp-" + mode
    prev_pos   = _scalp_st.get("position")
    prev_entry = _scalp_st.get("entry") or 0.0
    prev_pnl   = _scalp_st.get("pnl")   or 0.0
    prev_tr    = _scalp_st.get("trades") or 0
    prev_tp    = _scalp_st.get("tp_px")
    prev_sl    = _scalp_st.get("sl_px")
    _scalp_st.update({
        "running": True, "mode": mode, "stop_msg": "",
        "position": prev_pos, "entry": prev_entry,
        "pnl": prev_pnl, "trades": prev_tr,
        "tp_px": prev_tp, "sl_px": prev_sl,
        "trend_1h": None, "fvg_bull": 0, "fvg_bear": 0, "fvg_active": [],
    })
    pos = prev_pos; entry = prev_entry
    tp_px = prev_tp; sl_px = prev_sl
    sess_pnl = prev_pnl; sess_tr = prev_tr
    _last_close = 0.0

    while _scalp_st["running"]:
        # ── MTF 데이터 수집 ─────────────────────────────────────────────
        kl_1h  = _klines(bar="1H",  n=50)
        kl_15m = _klines(bar="15m", n=80)
        kl_1m  = _klines(bar="1m",  n=30)
        if not kl_15m or not kl_1m:
            time.sleep(15); continue

        price = kl_1m[-1]["c"] if kl_1m else 0
        if price == 0:
            time.sleep(15); continue

        # ── 1h 트렌드 편향 ──────────────────────────────────────────────
        trend_1h = None
        e9_1h = e21_1h = 0
        if kl_1h and len(kl_1h) >= 22:
            cl_1h = [k["c"] for k in kl_1h]
            e9_1h  = _ema(cl_1h, 9)
            e21_1h = _ema(cl_1h, 21)
            if   e9_1h > e21_1h * 1.0002: trend_1h = "bull"
            elif e9_1h < e21_1h * 0.9998: trend_1h = "bear"

        # ── 15m ATR + BB (보조지표) ─────────────────────────────────────
        ind_15m = _ind(kl_15m) if len(kl_15m) >= 22 else {}
        atr     = ind_15m.get("atr", price * 0.005)

        # ── 15m FVG 탐지 및 filled 업데이트 ────────────────────────────
        fvgs_all  = _detect_fvg(kl_15m)
        recent    = fvgs_all[-12:]              # 최근 12개
        _update_fvg_filled(recent, price)
        unfilled  = [fg for fg in recent if not fg["filled"]]

        # ── 1m 진입 타이밍 확인 ─────────────────────────────────────────
        ind_1m = {}
        if len(kl_1m) >= 15:
            cl_1m = [k["c"] for k in kl_1m]
            ind_1m = {
                "rsi":      _rsi(cl_1m, 14),
                "last_bull": kl_1m[-1]["c"] > kl_1m[-1]["o"],
                "prev_bull": kl_1m[-2]["c"] > kl_1m[-2]["o"] if len(kl_1m) > 2 else None,
            }

        ok, stop_msg = _can_trade(scalp_mode)
        cooldown_left = max(0, _last_close + 900 - time.time())
        if pos is None and cooldown_left > 0:
            _scalp_st["watch_msg"] = f"쿨다운 {int(cooldown_left//60)}분 {int(cooldown_left%60)}초"

        # ── 진입 로직 ───────────────────────────────────────────────────
        if pos is None and ok and cooldown_left == 0:
            _shared_pos, _shared_bot = _any_open_pos()
            if _shared_pos:
                _scalp_st["watch_msg"] = f"{_shared_bot} 봇 {_shared_pos.upper()} 홀딩 중 — 대기"
                time.sleep(15); continue

            _sd      = load_signal() or {}
            _allowed = _sd.get("allowed_bots", "both")
            _bias    = _sd.get("direction_bias")
            _score   = _sd.get("composite_score", "-")
            if _allowed == "none":
                _scalp_st["watch_msg"] = f"시그널차단[none] score={_score}"
                time.sleep(15); continue

            sig = None; reason = ""; fvg_hit = None
            # 현재가가 속한 미체결 FVG 찾기 (최신 우선)
            for fg in reversed(unfilled):
                if fg["low"] <= price <= fg["high"]:
                    fvg_hit = fg; break

            if fvg_hit and ind_1m:
                rsi_1m     = ind_1m.get("rsi", 50)
                is_bull_1m = ind_1m.get("last_bull", False)

                # ── 롱 진입 조건 ────────────────────────────────────────
                # 1h 상승 or 중립 + 불리시 FVG + 1m 양봉 + RSI<55 + 시그널 편향 OK
                if (fvg_hit["type"] == "bull"
                        and trend_1h in ("bull", None)
                        and is_bull_1m
                        and rsi_1m < 55
                        and _bias != "short"):
                    sig = "long"
                    reason = (f"FVG롱 [1h:{trend_1h or '중립'}] "
                              f"불리시FVG({fvg_hit['low']:.0f}~{fvg_hit['high']:.0f}) "
                              f"1m양봉 RSI={rsi_1m:.1f}")

                # ── 숏 진입 조건 ────────────────────────────────────────
                # 1h 하락 or 중립 + 베어리시 FVG + 1m 음봉 + RSI>45 + 시그널 편향 OK
                elif (fvg_hit["type"] == "bear"
                        and trend_1h in ("bear", None)
                        and not is_bull_1m
                        and rsi_1m > 45
                        and _bias != "long"):
                    sig = "short"
                    reason = (f"FVG숏 [1h:{trend_1h or '중립'}] "
                              f"베어리시FVG({fvg_hit['low']:.0f}~{fvg_hit['high']:.0f}) "
                              f"1m음봉 RSI={rsi_1m:.1f}")

            if not sig:
                u_b = sum(1 for fg in unfilled if fg["type"] == "bull")
                u_e = sum(1 for fg in unfilled if fg["type"] == "bear")
                _scalp_st["watch_msg"] = (
                    f"FVG대기 [1h:{trend_1h or '중립'}] "
                    f"미체결 롱FVG:{u_b} 숏FVG:{u_e} | ${price:,.0f}")

            if sig in ("long", "short"):
                _TP_CAP = 0.010; _SL_CAP = 0.006
                tm = _scalp_cfg["tp_atr_mult"]
                sm = _scalp_cfg["sl_atr_mult"]
                if sig == "long":
                    tp_px = round(price + min(atr * tm, price * _TP_CAP), 1)
                    sl_px = round(price - min(atr * sm, price * _SL_CAP), 1)
                else:
                    tp_px = round(price - min(atr * tm, price * _TP_CAP), 1)
                    sl_px = round(price + min(atr * sm, price * _SL_CAP), 1)

                pos = sig; entry = price
                reason += f" [ATR:{atr:.0f} TP:{tp_px:.0f} SL:{sl_px:.0f}]"
                if mode == "real":
                    _set_leverage(_scalp_cfg["leverage"])
                    side = "buy" if sig == "long" else "sell"
                    ord_r = _place_order(side, sig, tp_px, sl_px, _scalp_cfg["size_pct"])
                    if ord_r.get("code") not in ("0", 0):
                        reason += f" [주문실패:{ord_r.get('msg','')}]"
                _scalp_st["watch_msg"] = reason
                _rec(scalp_mode, f"ENTER_{sig.upper()}", price, ind_15m, reason,
                     tp_px=tp_px, sl_px=sl_px, signal_src="FVG-MTF")

        # ── 청산 로직 ────────────────────────────────────────────────────
        elif pos:
            pct = ((price - entry) / entry * 100 if pos == "long"
                   else (entry - price) / entry * 100)
            hit_sl = (pos == "long"  and sl_px and price <= sl_px) or \
                     (pos == "short" and sl_px and price >= sl_px)
            hit_tp = (pos == "long"  and tp_px and price >= tp_px) or \
                     (pos == "short" and tp_px and price <= tp_px)

            if hit_sl:
                _close_order(pos, mode, _scalp_cfg["size_pct"])
                _rec(scalp_mode, "SL_HIT", price, ind_15m,
                     f"FVG손절 {pct:.2f}%", pnl=round(pct, 4))
                sess_pnl += pct; sess_tr += 1
                pos = None; entry = 0.0; tp_px = None; sl_px = None
                _last_close = time.time()
            elif hit_tp:
                _close_order(pos, mode, _scalp_cfg["size_pct"])
                _rec(scalp_mode, f"CLOSE_{pos.upper()}", price, ind_15m,
                     f"FVG익절 +{pct:.2f}%", pnl=round(pct, 4))
                sess_pnl += pct; sess_tr += 1
                pos = None; entry = 0.0; tp_px = None; sl_px = None
                _last_close = time.time()
            else:
                _scalp_st["watch_msg"] = (
                    f"FVG홀딩 {pos.upper()} @ ${entry:,.0f} "
                    f"({pct:+.2f}%) | TP:${tp_px:,.0f} SL:${sl_px:,.0f}")

        # ── 상태 업데이트 ────────────────────────────────────────────────
        u_b = sum(1 for fg in unfilled if fg["type"] == "bull")
        u_e = sum(1 for fg in unfilled if fg["type"] == "bear")
        _scalp_st.update({
            "position": pos, "price": round(price, 2),
            "entry": round(entry, 2) if pos else None,
            "tp_px": tp_px, "sl_px": sl_px,
            "pnl": round(sess_pnl, 2), "trades": sess_tr,
            "indicators": ind_15m, "can_trade": ok, "stop_msg": stop_msg,
            "daily": _dst(_kst_day(), scalp_mode),
            "trend_1h": trend_1h,
            "fvg_bull": u_b, "fvg_bear": u_e,
            "fvg_active": [
                {"type": fg["type"], "low": fg["low"], "high": fg["high"],
                 "filled": fg["filled"]}
                for fg in recent[-5:]
            ],
        })
        _persist_save()
        time.sleep(15)   # 스캘퍼 15초 주기 (1분봉 기준)
    _scalp_st["running"] = False

'''

# 기존 _run_scalp() 찾아서 교체
OLD_RUN_SCALP_START = "# ── BB 스캘퍼 봇 (볼린저밴드 평균회귀 | ATR TP/SL) ────────────────"
OLD_CLAUDE_BOT_START = "\n\n# ── Claude 메인 봇"
idx_s = src.find(OLD_RUN_SCALP_START)
idx_e = src.find(OLD_CLAUDE_BOT_START, idx_s)
assert idx_s != -1, "ERROR: _run_scalp 시작을 못 찾음"
assert idx_e != -1, "ERROR: Claude 봇 시작을 못 찾음"
src = src[:idx_s] + NEW_RUN_SCALP + src[idx_e+2:]  # +2: \n\n 제거
print("[4] _run_scalp() 교체 OK")

# ── 5. /api/fvg 엔드포인트 추가 ────────────────────────────────────────────
OLD_API_LOGS = "        elif p == \"/api/logs\":"
NEW_API_FVG_AND_LOGS = '''        elif p == "/api/fvg":
            # 15분봉 기준 최근 FVG 목록 + filled 상태 (실시간)
            kl_fvg  = _klines(bar="15m", n=80)
            kl_1h_f = _klines(bar="1H",  n=50)
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
        elif p == "/api/logs":'''

assert OLD_API_LOGS in src, "ERROR: /api/logs 엔드포인트를 못 찾음"
src = src.replace(OLD_API_LOGS, NEW_API_FVG_AND_LOGS, 1)
print("[5] /api/fvg 엔드포인트 추가 OK")

# ── 6. 버전 문자열 업데이트 ────────────────────────────────────────────────
src = src.replace(
    '"""Deepcoin Bot v3 - 모멘텀(ATR TP/SL) + BB 스캘퍼 | 거래로그 | 일별수익"""',
    '"""Deepcoin Bot v4 - 모멘텀(ATR TP/SL) + MTF FVG 스캘퍼(1h→15m→1m) | 거래로그 | 일별수익"""'
)
src = src.replace(
    "  모멘텀(EMA+RSI+ATR) + BB 스캘퍼 + 자동 스코어링",
    "  모멘텀(EMA+RSI+ATR) + MTF FVG 스캘퍼(1h→15m→1m) + 자동 스코어링"
)
print("[6] 버전 문자열 업데이트 OK")

# ── 저장 ───────────────────────────────────────────────────────────────────
with open(r'C:\Users\g8428\deepcoin_bot\server.py', 'w', encoding='utf-8') as f:
    f.write(src)
print("\n✅ server.py 패치 완료!")
print(f"   총 라인 수: {len(src.splitlines())}")
