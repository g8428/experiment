"""
claude_signal.py — Claude CLI 기반 BTC 기술적 분석 시그널 생성
O'Neil/Minervini 방법론 + technical-analyst/vcp-screener 스킬 프레임워크 적용
signal_scorer.py에서 30분마다 호출됨
"""
import json, subprocess, re, time
from pathlib import Path
from signal_scorer import _fetch, _ema, _rsi, _atr, _williams_r, _stoch_k


def _load_skill(name):
    """~/.claude/commands/<name>.md 핵심 내용 로드"""
    p = Path.home() / ".claude" / "commands" / f"{name}.md"
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


# 스킬 파일 로드 (프롬프트에 방법론으로 주입)
_SKILL_TECH = _load_skill("technical-analyst")
_SKILL_VCP  = _load_skill("vcp-screener")


_PROMPT = """\
You are an expert BTC/USDT perpetual futures trader applying William O'Neil and Mark Minervini methodologies adapted for crypto markets.

## SKILL FRAMEWORKS TO APPLY

### Framework 1: Technical Analyst Skill
""" + _SKILL_TECH + """

### Framework 2: VCP Screener Skill (Minervini methodology — adapt for BTC/crypto)
""" + _SKILL_VCP + """

---

## MANDATORY ANALYSIS REQUIREMENTS

Apply ALL of the following to the price data provided:

### 1. Stage Analysis (O'Neil)
- Stage 1: Basing — price flat, MAs converging
- Stage 2: Uptrend — price > MA50 > MA150/MA200, all MAs rising → LONG zone
- Stage 3: Topping — extended price, distribution, reduce longs
- Stage 4: Downtrend — price < MA50, MAs declining → SHORT zone
- Determine current Stage from Daily EMA alignment

### 2. VCP Pattern Detection (Minervini — adapted to BTC 4H/Daily)
- Check for T1 > T2 > T3 successive range contractions (each ≥20% tighter)
- Volume MUST dry up during each contraction period
- Pivot = breakout above the tightest contraction's high
- Count contraction count (0 if no VCP)

### Framework 3: Smart Money Concepts (SMC) Analysis
Apply ICT/SMC methodology to identify institutional order flow:

**Swing Structure**:
- Identify the last 3-5 significant Swing Highs (SH) and Swing Lows (SL)
- Determine market structure: Higher High/Higher Low (uptrend) or Lower High/Lower Low (downtrend)

**BOS / ChoCh**:
- BOS (Break of Structure): price breaks a swing level in the trend direction
- ChoCh (Change of Character): FIRST break in the OPPOSITE direction — early reversal signal
- State which one occurred and at what price level

**Order Blocks (OB)**:
- Bullish OB: last bearish candle before a bullish BOS — institutional buy zone
- Bearish OB: last bullish candle before a bearish BOS — institutional sell zone
- Identify the most recent unmitigated OB for both directions

**Fair Value Gaps (FVG)**:
- Bullish FVG: gap between candle[i-1].high and candle[i+1].low (unfilled upside imbalance)
- Bearish FVG: gap between candle[i-1].low and candle[i+1].high (unfilled downside imbalance)
- Identify the nearest unfilled FVG above and below current price

**Liquidity**:
- Buy-side liquidity: equal highs above price = stop clusters for shorts (institutional target)
- Sell-side liquidity: equal lows below price = stop clusters for longs (institutional target)
- Liquidity sweep: price briefly takes out a swing level then reverses = high probability reversal

**SMC Entry Logic** (use this to define entry/SL/TP):
- LONG: Bullish ChoCh/BOS + price entering Bullish OB or Bullish FVG + SL below OB bottom
- SHORT: Bearish ChoCh/BOS + price entering Bearish OB or Bearish FVG + SL above OB top
- TP1: nearest opposing FVG or swing level
- TP2: liquidity pool (equal highs for longs / equal lows for shorts)

### 3. Candlestick Pattern Analysis (MANDATORY — must name a pattern)
- Scan last 3-5 candles on 4H timeframe
- Bullish: Hammer, Bullish Engulfing, Morning Star, Bullish Harami, Dragonfly Doji, Three White Soldiers
- Bearish: Shooting Star, Bearish Engulfing, Evening Star, Gravestone Doji, Three Black Crows
- Neutral: Doji, Spinning Top
- State if volume confirms the pattern

### 4. Volume Analysis (MANDATORY — must assess)
- Current volume vs 20-period MA ratio
- Breakout confirmation: volume ≥1.5x MA required for valid breakout
- Volume during consolidation: drying up = healthy base, expanding = distribution
- OBV direction from the provided data
- Volume divergence: price rising + OBV falling = warning sign

### 5. Support / Resistance
- Identify 2 key support and 2 key resistance levels from price structure
- Use swing highs/lows, not just round numbers

### 6. Entry / Exit Definition
- Entry zone: ideal range based on structure + pattern confluence
- TP1: first structural resistance / minimum 1:2 RR
- TP2: extended target
- SL: below structural support (not just ATR-based)
- Invalidation: level that definitively invalidates your thesis

## LANGUAGE REQUIREMENT
The "reasoning" field MUST be written entirely in Korean (한국어). All other fields are numbers or fixed English keywords — do not translate them.

## OUTPUT JSON SCHEMA
Return ONLY this JSON, no markdown fences, no explanation:
{
  "direction": "long" | "short" | "neutral",
  "confidence": "high" | "medium" | "low",
  "stage": "1" | "2" | "3" | "4",
  "vcp_detected": true | false,
  "vcp_contraction_count": <integer 0-4>,
  "candle_pattern": "<pattern name e.g. Hammer, Bearish Engulfing, Doji>",
  "candle_signal": "bullish" | "bearish" | "neutral",
  "volume_trend": "expanding" | "contracting" | "neutral",
  "volume_confirmation": true | false,
  "entry_zone_low": <number>,
  "entry_zone_high": <number>,
  "tp1": <number>,
  "tp2": <number>,
  "sl": <number>,
  "invalidation": <number>,
  "key_support": [<number>, <number>],
  "key_resistance": [<number>, <number>],
  "bos_type": "BOS" | "ChoCh" | null,
  "bos_direction": "bullish" | "bearish" | null,
  "nearest_bull_ob": <price or null>,
  "nearest_bear_ob": <price or null>,
  "nearest_bull_fvg": <price or null>,
  "nearest_bear_fvg": <price or null>,
  "liquidity_above": <price or null>,
  "liquidity_below": <price or null>,
  "bull_prob": <integer 0-100>,
  "bear_prob": <integer 0-100>,
  "neutral_prob": <integer 0-100>,
  "reasoning": "<2-3 sentence summary in Korean (한국어로 작성): Stage, VCP/패턴명, 거래량 상태, 핵심 가격대 포함>"
}
"""


def _obv_trend(kl, n=20):
    """간략 OBV 방향: 최근 n봉 누적 거래량 방향"""
    if len(kl) < n + 1: return "neutral"
    obv = 0.0
    for i in range(1, n + 1):
        k = kl[-i]; kp = kl[-i-1]
        if   k["c"] > kp["c"]: obv += k["v"]
        elif k["c"] < kp["c"]: obv -= k["v"]
    return "up" if obv > 0 else ("down" if obv < 0 else "neutral")


def _format_indicators(d_kl, h4_kl, m15_kl):
    """핵심 지표 요약 — Williams %R, Stochastic, OBV, 거래량비율 포함"""
    def ind(kl, label):
        if len(kl) < 22:
            return f"{label}: 데이터 부족"
        cl    = [k["c"] for k in kl]
        price = cl[-1]
        e9    = _ema(cl, 9)
        e21   = _ema(cl, 21)
        e50   = _ema(cl, min(50, len(cl)-1))
        rsi   = _rsi(cl, 14)
        atr   = _atr(kl, 14)
        wR    = _williams_r(kl, 14)
        stoch = _stoch_k(kl, 14)
        # Bollinger Band
        bb20  = cl[-20:]
        bm    = sum(bb20) / 20
        bstd  = (sum((x-bm)**2 for x in bb20) / 20) ** 0.5
        # 거래량
        vols      = [k["v"] for k in kl]
        vol_ma20  = sum(vols[-20:]) / 20
        vol_ratio = round(vols[-1] / vol_ma20, 2) if vol_ma20 else 1.0
        obv_dir   = _obv_trend(kl, min(20, len(kl)-1))
        return (
            f"{label}: price={price:.0f}  EMA9={e9:.0f}  EMA21={e21:.0f}  EMA50={e50:.0f}"
            f"  RSI={rsi:.1f}  WilliamsR={wR:.1f}  Stoch%K={stoch:.1f}"
            f"  ATR={atr:.0f}  BB_upper={bm+2*bstd:.0f}  BB_lower={bm-2*bstd:.0f}"
            f"  Vol/MA20={vol_ratio}x  OBV={obv_dir}"
        )

    lines = ["\n## 핵심 지표 요약"]
    lines.append(ind(d_kl,   "Daily"))
    lines.append(ind(h4_kl,  "4H"))
    lines.append(ind(m15_kl, "15m"))

    if len(d_kl) >= 30:
        highs = [k["h"] for k in d_kl[-90:]]
        lows  = [k["l"] for k in d_kl[-90:]]
        lines.append(f"90일 고점: {max(highs):.0f}  90일 저점: {min(lows):.0f}")

    # VCP 사전 수치 계산 (Python에서 계산해서 Claude에 제공)
    if len(d_kl) >= 30:
        def rng_pct(sl):
            h = max(k["h"] for k in sl); l = min(k["l"] for k in sl)
            m = (h + l) / 2
            return round((h - l) / m * 100, 2) if m else 0.0
        t1 = rng_pct(d_kl[-10:])
        t2 = rng_pct(d_kl[-20:-10])
        t3 = rng_pct(d_kl[-30:-20])
        lines.append(f"\n## VCP 사전 계산 (일봉 고저범위% 수축 확인)")
        lines.append(f"T1(최근10봉)={t1}%  T2(10~20봉전)={t2}%  T3(20~30봉전)={t3}%")
        lines.append(f"수축여부: T1<T2×0.8 = {t1 < t2 * 0.8}  T2<T3×0.9 = {t2 < t3 * 0.9}")

    return "\n".join(lines)


def _format_candles(kl, label, n=20):
    """캔들 데이터를 텍스트로 포맷"""
    lines = [f"\n## {label} (최근 {min(n, len(kl))}봉)"]
    lines.append("시간(UTC ms) | Open | High | Low | Close | Vol")
    for k in kl[-n:]:
        lines.append(f"{k['t']} | {k['o']:.0f} | {k['h']:.0f} | {k['l']:.0f} | {k['c']:.0f} | {k['v']:.1f}")
    return "\n".join(lines)


def _parse_result(raw: str):
    """Claude 응답에서 JSON 추출"""
    m = re.search(r'\{[\s\S]+\}', raw)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return None


def analyze() -> dict:
    """
    Claude CLI로 BTC 기술적 분석 실행 (O'Neil/Minervini + 캔들 + 거래량 포함).
    반환: 분석 결과 dict 또는 {"error": ...}
    """
    d_kl   = _fetch("1D", 100)
    h4_kl  = _fetch("4H", 80)
    m15_kl = _fetch("15m", 60)

    if not d_kl or not h4_kl or not m15_kl:
        return {"error": "klines fetch 실패"}

    data_text = (
        _format_indicators(d_kl, h4_kl, m15_kl)
        + _format_candles(d_kl,   "Daily", n=30)
        + _format_candles(h4_kl,  "4H",    n=24)
        + _format_candles(m15_kl, "15m",   n=20)
    )

    full_prompt = _PROMPT + "\n\n## 가격 데이터\n" + data_text

    try:
        result = subprocess.run(
            ["claude", "-p", full_prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace"
        )
        if result.returncode != 0:
            return {"error": f"claude CLI 오류: {result.stderr[:200]}"}

        resp = json.loads(result.stdout)
        raw  = resp.get("result", "")
        data = _parse_result(raw)
        if not data:
            return {"error": f"JSON 파싱 실패: {raw[:200]}"}

        required = ["direction", "entry_zone_low", "entry_zone_high", "tp1", "tp2", "sl"]
        if not all(k in data for k in required):
            return {"error": f"필드 누락: {[k for k in required if k not in data]}"}

        total = data.get("bull_prob", 0) + data.get("bear_prob", 0) + data.get("neutral_prob", 0)
        if total > 0 and total != 100:
            data["bull_prob"]    = round(data.get("bull_prob", 0) / total * 100)
            data["bear_prob"]    = round(data.get("bear_prob", 0) / total * 100)
            data["neutral_prob"] = 100 - data["bull_prob"] - data["bear_prob"]

        data["analyzed_at"] = time.strftime("%Y-%m-%d %H:%M", time.localtime())
        return data

    except subprocess.TimeoutExpired:
        return {"error": "claude CLI timeout (120s)"}
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    print("[claude_signal] BTC 분석 시작 (O'Neil/Minervini + 캔들 + 거래량)...")
    r = analyze()
    if "error" in r:
        print(f"실패: {r['error']}")
    else:
        print(f"방향:    {r['direction']}  (신뢰: {r['confidence']})")
        print(f"Stage:   {r.get('stage')}  VCP={r.get('vcp_detected')} ({r.get('vcp_contraction_count')}회 수축)")
        print(f"캔들:    {r.get('candle_pattern')} → {r.get('candle_signal')}")
        print(f"거래량:  트렌드={r.get('volume_trend')}  확인={r.get('volume_confirmation')}")
        print(f"진입존:  ${r['entry_zone_low']:,.0f} ~ ${r['entry_zone_high']:,.0f}")
        print(f"TP1/TP2: ${r['tp1']:,.0f} / ${r['tp2']:,.0f}")
        print(f"SL:      ${r['sl']:,.0f}  무효화=${r.get('invalidation'):,.0f}")
        print(f"시나리오: 롱{r.get('bull_prob')}% / 숏{r.get('bear_prob')}% / 중립{r.get('neutral_prob')}%")
        print(f"근거:    {r.get('reasoning', '')}")
