"""
smc_engine.py — Smart Money Concepts (SMC) 분석 엔진 (BTC 선물 단타 특화)
LuxAlgo SMC 핵심 개념 Python 구현:
  Swing High/Low → BOS/ChoCh → Order Block → FVG → Liquidity Sweep
  → 진입존 / SL / TP 자동 계산
"""


def find_swings(kl, n=3):
    """스윙 고점/저점 탐지 (좌우 각각 n봉 비교)
    반환: highs=[{i, p, t}], lows=[{i, p, t}]"""
    highs = []; lows = []
    ln = len(kl)
    for i in range(n, ln - n):
        h = kl[i]["h"]; l = kl[i]["l"]
        if all(kl[j]["h"] <= h for j in range(i-n, i+n+1) if j != i):
            highs.append({"i": i, "p": h, "t": kl[i]["t"]})
        if all(kl[j]["l"] >= l for j in range(i-n, i+n+1) if j != i):
            lows.append({"i": i, "p": l, "t": kl[i]["t"]})
    return highs, lows


def find_bos_choch(kl, highs, lows, lookback=5):
    """BOS(Break of Structure) / ChoCh(Change of Character) 탐지
    최근 lookback봉 이내 클로즈가 이전 스윙 고/저 돌파 여부 확인
    BOS:   기존 추세 방향으로 스윙 고/저 돌파 (추세 지속)
    ChoCh: 기존 추세 반대 방향 첫 돌파 (추세 전환 신호)
    반환: {type, direction, level}"""
    if len(highs) < 2 or len(lows) < 2:
        return {"type": None, "direction": None, "level": None}

    # 최근 N봉 클로즈 (현재 포함)
    recent_closes = [k["c"] for k in kl[-lookback:]]

    recent_h = sorted(highs[-3:], key=lambda x: x["i"])
    recent_l = sorted(lows[-3:],  key=lambda x: x["i"])

    uptrend   = (len(recent_h) >= 2 and recent_h[-1]["p"] > recent_h[-2]["p"] and
                 len(recent_l) >= 2 and recent_l[-1]["p"] > recent_l[-2]["p"])
    downtrend = (len(recent_h) >= 2 and recent_h[-1]["p"] < recent_h[-2]["p"] and
                 len(recent_l) >= 2 and recent_l[-1]["p"] < recent_l[-2]["p"])

    # 2번째 최근 스윙 레벨 (1번째는 아직 미돌파 기준선)
    prev_sh = highs[-2]["p"] if len(highs) >= 2 else None
    prev_sl = lows[-2]["p"]  if len(lows)  >= 2 else None

    # 최근 N봉 중 어느 봉이라도 돌파했으면 BOS/ChoCh 인정
    if prev_sh and any(c > prev_sh for c in recent_closes):
        return {"type": "ChoCh" if downtrend else "BOS", "direction": "bullish", "level": prev_sh}
    if prev_sl and any(c < prev_sl for c in recent_closes):
        return {"type": "ChoCh" if uptrend else "BOS",  "direction": "bearish", "level": prev_sl}

    return {"type": None, "direction": None, "level": None}


def find_order_blocks(kl, highs, lows, lookback=40):
    """Order Block 탐지 — 절대 인덱스 기반 (버그 수정)
    Bullish OB: 스윙 저점 직전 마지막 음봉
    Bearish OB: 스윙 고점 직전 마지막 양봉
    반환: (bull_obs, bear_obs) — 유효한 것만"""
    price    = kl[-1]["c"]
    min_idx  = max(0, len(kl) - lookback)
    bull_obs = []; bear_obs = []

    for sl in sorted(lows, key=lambda x: x["i"], reverse=True)[:3]:
        idx = sl["i"]
        if idx < min_idx: continue
        for j in range(idx - 1, max(min_idx, idx - 8), -1):
            if kl[j]["c"] < kl[j]["o"]:  # 음봉
                ob = {"top": kl[j]["o"], "bot": kl[j]["l"],
                      "mid": (kl[j]["o"] + kl[j]["l"]) / 2}
                if price >= ob["bot"]:   # OB 아래로 뚫리지 않은 것만
                    bull_obs.append(ob)
                break

    for sh in sorted(highs, key=lambda x: x["i"], reverse=True)[:3]:
        idx = sh["i"]
        if idx < min_idx: continue
        for j in range(idx - 1, max(min_idx, idx - 8), -1):
            if kl[j]["c"] > kl[j]["o"]:  # 양봉
                ob = {"top": kl[j]["h"], "bot": kl[j]["c"],
                      "mid": (kl[j]["h"] + kl[j]["c"]) / 2}
                if price <= ob["top"]:   # OB 위로 뚫리지 않은 것만
                    bear_obs.append(ob)
                break

    return bull_obs, bear_obs


def find_fvg(kl, lookback=20, min_gap_pct=0.02):
    """Fair Value Gap (FVG / Imbalance) 탐지
    Bullish FVG: kl[i-1].high < kl[i+1].low  (상방 미체결 공백)
    Bearish FVG: kl[i-1].low  > kl[i+1].high (하방 미체결 공백)
    반환: (bull_fvgs, bear_fvgs) — 미채워진 것만"""
    price  = kl[-1]["c"]
    b_fvg  = []; d_fvg = []
    n = min(lookback + 2, len(kl) - 1)

    for i in range(2, n):
        k1 = kl[-i-1]; k3 = kl[-i+1]
        gap_bull = k3["l"] - k1["h"]
        gap_bear = k1["l"] - k3["h"]

        if gap_bull > price * min_gap_pct / 100:
            top = k3["l"]; bot = k1["h"]
            if price > bot:   # 현재가가 FVG 바닥 위 — 아직 완전히 채워지지 않음 (지지 구간)
                b_fvg.append({"top": top, "bot": bot, "mid": (top+bot)/2})

        if gap_bear > price * min_gap_pct / 100:
            top = k1["l"]; bot = k3["h"]
            if price < top:   # 현재가가 FVG 상단 아래 — 아직 완전히 채워지지 않음 (저항 구간)
                d_fvg.append({"top": top, "bot": bot, "mid": (top+bot)/2})

    return b_fvg, d_fvg


def find_liquidity(kl, highs, lows):
    """유동성 풀 탐지
    Buy-side (위): 스윙 고점 위 → 숏 포지션의 SL 클러스터
    Sell-side (아래): 스윙 저점 아래 → 롱 포지션의 SL 클러스터
    반환: (buy_liq_prices, sell_liq_prices)"""
    price    = kl[-1]["c"]
    buy_liq  = sorted([h["p"] for h in highs if h["p"] > price])[:3]
    sell_liq = sorted([l["p"] for l in lows  if l["p"] < price], reverse=True)[:3]
    return buy_liq, sell_liq


def find_liquidity_sweep(kl, highs, lows, lookback=8):
    """유동성 청소(Liquidity Sweep) 탐지 — 최근 N봉 이내
    Bullish sweep: 스윙 저점 아래로 찍고 회복 → 매수 기회
    Bearish sweep: 스윙 고점 위로 찍고 하락 → 매도 기회
    반환: (direction, swept_level) or (None, None)"""
    if len(kl) < lookback + 5 or not highs or not lows:
        return None, None

    price  = kl[-1]["c"]
    recent = kl[-lookback:]

    for sl in sorted(lows, key=lambda x: x["i"], reverse=True)[:3]:
        lvl = sl["p"]
        if any(k["l"] < lvl for k in recent) and price > lvl:
            return "bullish", lvl

    for sh in sorted(highs, key=lambda x: x["i"], reverse=True)[:3]:
        lvl = sh["p"]
        if any(k["h"] > lvl for k in recent) and price < lvl:
            return "bearish", lvl

    return None, None


def find_strong_weak(kl, highs, lows, bos):
    """Strong/Weak High & Low 탐지 (ICT 구조 분석)
    Strong High: 불리쉬 BOS 이후 형성된 최신 고점 (지지받는 고점, 재테스트 진입 기회)
    Weak High:   이전/하향 구조 고점 → 스윕 대상 (숏 기회)
    Strong Low:  베어리쉬 BOS 이후 형성된 최신 저점 (저항받는 저점, 숏 진입 기회)
    Weak Low:    이전/상향 구조 저점 → 스윕 대상 (롱 기회)
    반환: {"strong_high", "weak_high", "strong_low", "weak_low"} — float or None"""
    strong_high = weak_high = strong_low = weak_low = None
    bos_dir = bos.get("direction")
    if len(highs) >= 2:
        if bos_dir == "bullish":
            strong_high = highs[-1]["p"]   # 불리쉬 BOS 이후 최신 고점 = Strong
            weak_high   = highs[-2]["p"]   # 이전 고점 = Weak (이미 넘어섬)
        else:
            weak_high   = highs[-1]["p"]   # 베어리쉬 구조: 최신 고점이 더 낮으면 Weak
            strong_high = None
    if len(lows) >= 2:
        if bos_dir == "bearish":
            strong_low = lows[-1]["p"]     # 베어리쉬 BOS 이후 최신 저점 = Strong
            weak_low   = lows[-2]["p"]
        else:
            weak_low   = lows[-1]["p"]     # 불리쉬 구조: 최신 저점이 더 높으면 Weak
            strong_low = None
    return {
        "strong_high": round(strong_high, 1) if strong_high else None,
        "weak_high":   round(weak_high,   1) if weak_high   else None,
        "strong_low":  round(strong_low,  1) if strong_low  else None,
        "weak_low":    round(weak_low,    1) if weak_low    else None,
    }


def get_kill_zone(dt_utc=None):
    """ICT Kill Zone 판별 (UTC 기준)
    Asian:   UTC 01~05 (KST 10~14) — Accumulation, 신규 진입 제외
    London:  UTC 07~10 (KST 16~19) — Manipulation/진입 가능
    NY:      UTC 13~16 (KST 22~01) — Distribution/진입 가능
    반환: "asian" | "london" | "newyork" | None (킬존 외)"""
    from datetime import datetime, timezone
    if dt_utc is None:
        dt_utc = datetime.now(timezone.utc)
    h = dt_utc.hour + dt_utc.minute / 60
    if  1 <= h <  5: return "asian"
    if  7 <= h < 10: return "london"
    if 13 <= h < 16: return "newyork"
    return None


def get_asian_range(kl_1h):
    """아시안 세션 고점/저점 추출 (UTC 01~05 / KST 10~14)
    AMD 모델 Accumulation 구간 — 이 범위 이탈이 Manipulation 시작 신호
    반환: {"high": float, "low": float} or None"""
    from datetime import datetime, timezone
    asian_candles = []
    for k in kl_1h:
        t_utc = datetime.fromtimestamp(k["t"] / 1000, tz=timezone.utc)
        if 1 <= t_utc.hour < 5:
            asian_candles.append(k)
    if not asian_candles:
        return None
    return {
        "high": max(c["h"] for c in asian_candles),
        "low":  min(c["l"] for c in asian_candles),
    }


def scan_structure_events(kl, lookback, swing_n=3, label=""):
    """
    kl의 최근 lookback개 캔들을 스캔하여 SMC 이벤트가 발생한 시점을 반환.
    각 이벤트: {time_ms, type, direction, level, detail, label}
    type: "BOS" | "FVG" | "Sweep"
    """
    events = []
    ln     = len(kl)
    start  = max(0, ln - lookback)
    if ln < 10:
        return events

    price   = kl[-1]["c"]
    min_gap = price * 0.02 / 100   # 0.02% 최소 갭
    highs, lows = find_swings(kl, swing_n)
    high_prices = [h["p"] for h in highs]
    low_prices  = [l["p"] for l in lows]

    # ── BOS 이벤트: 스윙 고점/저점이 돌파된 봉 기록 ──────────────
    for sh in highs[:-1]:           # 마지막 스윙은 아직 미돌파 기준선
        level = sh["p"]
        for i in range(sh["i"] + 1, ln):
            if kl[i]["c"] > level:
                if i >= start:
                    events.append({
                        "time_ms": kl[i]["t"], "label": label,
                        "type": "BOS", "direction": "bullish",
                        "level": round(level),
                        "detail": f"고점 ${level:.0f} 상향 돌파"
                    })
                break   # 첫 돌파만 기록

    for sl in lows[:-1]:
        level = sl["p"]
        for i in range(sl["i"] + 1, ln):
            if kl[i]["c"] < level:
                if i >= start:
                    events.append({
                        "time_ms": kl[i]["t"], "label": label,
                        "type": "BOS", "direction": "bearish",
                        "level": round(level),
                        "detail": f"저점 ${level:.0f} 하향 돌파"
                    })
                break

    # ── FVG 이벤트: 3캔들 패턴의 3번째 봉에서 기록 ───────────────
    for i in range(2, ln):
        if i < start:
            continue
        k1 = kl[i - 2]; k3 = kl[i]
        gap_bull = k3["l"] - k1["h"]
        gap_bear = k1["l"] - k3["h"]
        if gap_bull > min_gap:
            events.append({
                "time_ms": k3["t"], "label": label,
                "type": "FVG", "direction": "bullish",
                "level": round((k3["l"] + k1["h"]) / 2),
                "detail": f"상방 갭 ${k1['h']:.0f}~${k3['l']:.0f}"
            })
        if gap_bear > min_gap:
            events.append({
                "time_ms": k3["t"], "label": label,
                "type": "FVG", "direction": "bearish",
                "level": round((k1["l"] + k3["h"]) / 2),
                "detail": f"하방 갭 ${k3['h']:.0f}~${k1['l']:.0f}"
            })

    # ── Sweep 이벤트: 스윙 레벨 이탈 후 회복/하락 봉 기록 ────────
    for i in range(start, ln):
        k = kl[i]
        swept_bull = False
        for lp in low_prices:
            if k["l"] < lp and k["c"] > lp:
                events.append({
                    "time_ms": k["t"], "label": label,
                    "type": "Sweep", "direction": "bullish",
                    "level": round(lp),
                    "detail": f"저점 ${lp:.0f} 스윕 → 회복"
                })
                swept_bull = True
                break
        if not swept_bull:
            for hp in high_prices:
                if k["h"] > hp and k["c"] < hp:
                    events.append({
                        "time_ms": k["t"], "label": label,
                        "type": "Sweep", "direction": "bearish",
                        "level": round(hp),
                        "detail": f"고점 ${hp:.0f} 스윕 → 하락"
                    })
                    break

    # 시간순 정렬, 중복 제거 (같은 type+direction+level은 최신 1개만)
    events.sort(key=lambda x: x["time_ms"])
    seen = {}
    deduped = []
    for e in reversed(events):
        key = (e["type"], e["direction"], e["level"])
        if key not in seen:
            seen[key] = True
            deduped.append(e)
    deduped.reverse()
    return deduped


def _ema_s(cl, n):
    """smc_engine 내부용 EMA 계산"""
    if len(cl) < n: return cl[-1] if cl else 0.0
    k = 2.0 / (n + 1); e = sum(cl[:n]) / n
    for p in cl[n:]: e = p * k + e * (1 - k)
    return e


def get_smc_signal(kl, swing_n=3, h1_kl=None):
    """SMC 종합 분석 → 진입 시그널 + SL/TP 자동 계산
    SMC 진입 원칙:
      Long:  Bullish BOS/ChoCh or Bullish Sweep + Bullish OB 존재
             SL = OB 하단 아래, TP1 = 최근 Bearish FVG or 스윙 고점
      Short: Bearish BOS/ChoCh or Bearish Sweep + Bearish OB 존재
             SL = OB 상단 위,  TP1 = 최근 Bullish FVG or 스윙 저점
    반환: dict {signal, entry_low, entry_high, sl, tp1, tp2, ...}"""
    if len(kl) < 30:
        return {"signal": None, "reason": "데이터 부족"}

    # ── 1H EMA 추세 필터 ──────────────────────────────────────────
    # 1H EMA9 < EMA21이면 하락 추세 → LONG 차단
    # 1H EMA9 > EMA21이면 상승 추세 → SHORT 차단
    h1_trend = None   # "bullish" | "bearish" | None
    if h1_kl and len(h1_kl) >= 21:
        h1_cl = [k["c"] for k in h1_kl]
        h1_ema9  = _ema_s(h1_cl, 9)
        h1_ema21 = _ema_s(h1_cl, 21)
        if h1_ema9 > h1_ema21 * 1.0002:   # 0.02% 마진으로 노이즈 제거
            h1_trend = "bullish"
        elif h1_ema9 < h1_ema21 * 0.9998:
            h1_trend = "bearish"

    price = kl[-1]["c"]
    highs, lows = find_swings(kl, swing_n)
    if not highs or not lows:
        return {"signal": None, "reason": "스윙 탐지 실패"}

    bos              = find_bos_choch(kl, highs, lows)
    b_obs, d_obs     = find_order_blocks(kl, highs, lows)
    b_fvg, d_fvg     = find_fvg(kl, lookback=20)
    sweep_dir, sweep_lvl = find_liquidity_sweep(kl, highs, lows)
    buy_liq, sell_liq    = find_liquidity(kl, highs, lows)
    sw               = find_strong_weak(kl, highs, lows, bos)

    result = {
        "signal": None, "entry_low": None, "entry_high": None,
        "sl": None, "tp1": None, "tp2": None,
        "bos_type": bos["type"], "bos_dir": bos["direction"],
        "bull_ob_count": len(b_obs), "bear_ob_count": len(d_obs),
        "bull_fvg_count": len(b_fvg), "bear_fvg_count": len(d_fvg),
        "sweep": bool(sweep_dir), "sweep_dir": sweep_dir, "sweep_lvl": sweep_lvl,
        "buy_liq": buy_liq, "sell_liq": sell_liq,
        "strong_high": sw["strong_high"], "weak_high":  sw["weak_high"],
        "strong_low":  sw["strong_low"],  "weak_low":   sw["weak_low"],
        "reason": f"조건 미충족 BOS={bos['type'] or '없음'} OB(롱{len(b_obs)}/숏{len(d_obs)}) FVG(롱{len(b_fvg)}/숏{len(d_fvg)})"
    }

    # ── Long setup ──────────────────────────────────────────────
    long_trigger = bos["direction"] == "bullish" or sweep_dir == "bullish"
    # 1H 하락 추세면 LONG 차단 (추세 역행 방지)
    if long_trigger and h1_trend == "bearish":
        result["reason"] = f"1H하락추세(EMA역배열) LONG차단 | BOS={bos['type'] or '없음'}"
        long_trigger = False
    if long_trigger and b_obs:
        ob  = b_obs[0]
        sl  = round(ob["bot"] * 0.9995, 1)

        # TP1: 현재가 위의 가장 가까운 Bearish FVG 하단 or 스윙 고점
        tp1 = None
        above_dfvg = [f for f in d_fvg if f["bot"] > price]
        if above_dfvg:
            tp1 = round(min(above_dfvg, key=lambda x: x["bot"])["bot"], 1)
        if not tp1:
            above_sh = [h for h in highs if h["p"] > price]
            if above_sh:
                tp1 = round(min(above_sh, key=lambda x: x["p"])["p"], 1)

        # 1H 구조 레벨 보강: tp1이 없거나 1% 미만이면 1H 스윙 고점으로 업그레이드
        if h1_kl and len(h1_kl) >= 10:
            h1_highs, _ = find_swings(h1_kl, swing_n)
            above_h1 = [h["p"] for h in h1_highs if h["p"] > price]
            if above_h1:
                h1_tp = round(min(above_h1), 1)
                if not tp1 or (tp1 - price) / price < 0.01:
                    tp1 = h1_tp

        tp2 = round(buy_liq[0], 1) if buy_liq else None

        # ── POI 진입 조건: 가격이 OB 구간 또는 Bull FVG 구간에 있어야 함 ──
        # OB 재터치: 가격이 OB 하단~상단 안에 있음 (±0.15% 허용)
        at_ob = ob["bot"] * 0.9985 <= price <= ob["top"] * 1.0015
        # Bull FVG 재진입: 가격이 미채워진 Bull FVG 구간 안에 있음
        at_bfvg = any(f["bot"] * 0.9985 <= price <= f["top"] * 1.0015 for f in b_fvg)
        poi_tag = "OB재터치" if at_ob else ("FVG진입" if at_bfvg else None)

        if poi_tag and tp1 and sl < price < tp1:
            sl_d  = price - sl
            tp1_d = tp1 - price
            if sl_d > 0 and tp1_d / sl_d >= 1.5:   # 최소 1:1.5 RR
                result.update({
                    "signal": "long",
                    "entry_low":  round(ob["bot"], 1),
                    "entry_high": round(ob["top"], 1),
                    "sl": sl, "tp1": tp1, "tp2": tp2,
                    "reason": (f"SMC롱 {bos['type'] or '스윕'} [{poi_tag}] "
                               f"OB={ob['bot']:.0f}~{ob['top']:.0f} "
                               f"SL={sl:.0f} TP1={tp1:.0f} "
                               f"RR={tp1_d/sl_d:.1f}")
                })
        elif not poi_tag and b_obs:
            # POI 아직 미도달 → 이유 업데이트
            result["reason"] = (f"롱POI대기 OB={ob['bot']:.0f}~{ob['top']:.0f} "
                                f"BullFVG={len(b_fvg)}개 | 현재${price:.0f}→OB복귀대기")

    # ── Short setup ─────────────────────────────────────────────
    short_trigger = bos["direction"] == "bearish" or sweep_dir == "bearish"
    # 1H 상승 추세면 SHORT 차단 (추세 역행 방지)
    if short_trigger and h1_trend == "bullish":
        if result["signal"] is None:
            result["reason"] = f"1H상승추세(EMA정배열) SHORT차단 | BOS={bos['type'] or '없음'}"
        short_trigger = False
    if short_trigger and d_obs and result["signal"] is None:
        ob  = d_obs[0]
        sl  = round(ob["top"] * 1.0005, 1)

        # TP1: 현재가 아래의 가장 가까운 Bullish FVG 상단 or 스윙 저점 (버그 수정: d_fvg → b_fvg)
        tp1 = None
        below_bfvg = [f for f in b_fvg if f["top"] < price]
        if below_bfvg:
            tp1 = round(max(below_bfvg, key=lambda x: x["top"])["top"], 1)
        if not tp1:
            below_sl = [l for l in lows if l["p"] < price]
            if below_sl:
                tp1 = round(max(below_sl, key=lambda x: x["p"])["p"], 1)

        # 1H 구조 레벨 보강: tp1이 없거나 1% 미만이면 1H 스윙 저점으로 업그레이드
        if h1_kl and len(h1_kl) >= 10:
            _, h1_lows = find_swings(h1_kl, swing_n)
            below_h1 = [l["p"] for l in h1_lows if l["p"] < price]
            if below_h1:
                h1_tp = round(max(below_h1), 1)
                if not tp1 or (price - tp1) / price < 0.01:
                    tp1 = h1_tp

        tp2 = round(sell_liq[0], 1) if sell_liq else None

        # ── POI 진입 조건: 가격이 OB 구간 또는 Bear FVG 구간에 있어야 함 ──
        at_ob_s  = ob["bot"] * 0.9985 <= price <= ob["top"] * 1.0015
        at_dfvg  = any(f["bot"] * 0.9985 <= price <= f["top"] * 1.0015 for f in d_fvg)
        poi_tag_s = "OB재터치" if at_ob_s else ("FVG진입" if at_dfvg else None)

        if poi_tag_s and tp1 and sl > price > tp1:
            sl_d  = sl - price
            tp1_d = price - tp1
            if sl_d > 0 and tp1_d / sl_d >= 1.5:   # 최소 1:1.5 RR
                result.update({
                    "signal": "short",
                    "entry_low":  round(ob["bot"], 1),
                    "entry_high": round(ob["top"], 1),
                    "sl": sl, "tp1": tp1, "tp2": tp2,
                    "reason": (f"SMC숏 {bos['type'] or '스윕'} [{poi_tag_s}] "
                               f"OB={ob['bot']:.0f}~{ob['top']:.0f} "
                               f"SL={sl:.0f} TP1={tp1:.0f} "
                               f"RR={tp1_d/sl_d:.1f}")
                })
        elif not poi_tag_s and d_obs:
            result["reason"] = (f"숏POI대기 OB={ob['bot']:.0f}~{ob['top']:.0f} "
                                f"BearFVG={len(d_fvg)}개 | 현재${price:.0f}→OB복귀대기")

    # ── 멀티 타임프레임 이벤트 스캔 ─────────────────────────────
    events_15m = scan_structure_events(kl,    lookback=60, swing_n=swing_n, label="15m")
    events_1h  = scan_structure_events(h1_kl, lookback=20, swing_n=swing_n, label="1h") if h1_kl and len(h1_kl) >= 10 else []
    result["events_15m"] = events_15m
    result["events_1h"]  = events_1h

    return result


def score_smc(h4_kl):
    """SMC 강도 스코어 → 0~15점 (방향 중립)
    구조가 명확할수록 고점 (상승/하락 동등)"""
    if len(h4_kl) < 40:
        return 5

    price        = h4_kl[-1]["c"]
    highs, lows  = find_swings(h4_kl, n=2)
    bos          = find_bos_choch(h4_kl, highs, lows)
    b_obs, d_obs = find_order_blocks(h4_kl, highs, lows)
    b_fvg, d_fvg = find_fvg(h4_kl, lookback=20)
    sweep_dir, _ = find_liquidity_sweep(h4_kl, highs, lows)

    s = 0
    if bos["type"]: s += 4
    near_b = any(ob["bot"] * 0.999 <= price <= ob["top"] * 1.001 for ob in b_obs)
    near_d = any(ob["bot"] * 0.999 <= price <= ob["top"] * 1.001 for ob in d_obs)
    if near_b or near_d: s += 4
    fvg_cnt = len(b_fvg) + len(d_fvg)
    s += min(4, fvg_cnt * 2)
    if sweep_dir: s += 3

    return min(15, s)
