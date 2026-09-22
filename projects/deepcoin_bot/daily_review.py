"""
daily_review.py — Claude 자율 매매 복기 + 파라미터 자동 튜닝
매일 자정 (KST 00:00) Windows Task Scheduler로 실행

[동작 흐름]
1. persist.json에서 오늘 매매 로그 + 패턴 통계 읽기
2. Claude CLI에게 전체 분석 위임
3. Claude가 내놓은 파라미터 튜닝 JSON을 tuning.json에 저장
4. server.py가 다음 루프에서 tuning.json 자동 반영
"""

import json, os, subprocess, time, re
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).parent
PERSIST_PATH  = BASE / "trade_logs" / "persist.json"
TUNING_PATH   = BASE / "tuning.json"
REVIEW_LOG    = BASE / "trade_logs" / "review_history.jsonl"


# ── 현재 tuning.json 로드 (없으면 기본값) ─────────────────────────
def load_tuning():
    defaults = {
        "leverage":         10,
        "size_pct":         40,
        "cooldown":         900,
        "max_daily_trades": 7,
        "daily_profit_stop": 10.0,
        "daily_loss_stop":  3.0,
        "max_daily_losses": 2,
        "rsi_long_max":     68,
        "rsi_short_min":    32,
        "rr_min":           1.5,
        "sl_cap_pct":       1.5,
        "tp_min_pct":       1.2,
        "enabled_strategies": ["smc", "ema_cross", "bb_reversion", "asian_breakout"],
        "active_symbols":   ["BTC-USDT-SWAP"],
        "ema_cross_tp_atr":  2.5,
        "ema_cross_sl_atr":  1.0,
        "bb_rev_tp_atr":     1.8,
        "bb_rev_sl_atr":     0.8,
        "asian_break_tp_atr": 3.0,
        "asian_break_sl_atr": 1.2,
        "version": 0,
        "last_tuned": None,
    }
    if TUNING_PATH.exists():
        try:
            saved = json.loads(TUNING_PATH.read_text(encoding="utf-8"))
            defaults.update(saved)
        except Exception:
            pass
    return defaults


# ── persist.json에서 최근 N일 매매 로그 로드 ───────────────────────
def load_recent_logs(days=14):
    if not PERSIST_PATH.exists():
        return [], {}
    try:
        data   = json.loads(PERSIST_PATH.read_text(encoding="utf-8"))
        logs   = data.get("logs", [])
        daily  = data.get("daily", {})
        pstats = data.get("pattern_stats", {})
        # 최근 N일 필터
        cutoff = (datetime.now(timezone(timedelta(hours=9)))
                  - timedelta(days=days)).strftime("%Y-%m-%d")
        recent_logs = [l for l in logs if l.get("day", "") >= cutoff]
        recent_daily = {k: v for k, v in daily.items() if k >= cutoff}
        return recent_logs, recent_daily, pstats
    except Exception as e:
        print(f"[review] persist.json 로드 실패: {e}")
        return [], {}, {}


# ── Claude에게 보낼 분석 프롬프트 생성 ────────────────────────────
def build_prompt(logs, daily, pstats, current_tuning):
    kst_now = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")

    # 패턴별 승률 상위/하위 5개
    pattern_summary = ""
    if pstats:
        sorted_p = sorted(pstats.items(),
                          key=lambda x: (x[1].get("trades", 0) >= 3,
                                         x[1].get("wins", 0) / max(x[1].get("trades", 1), 1)),
                          reverse=True)
        top5    = [(k, v) for k, v in sorted_p if v.get("trades", 0) >= 3][:5]
        bottom5 = [(k, v) for k, v in sorted_p if v.get("trades", 0) >= 3][-5:]
        def fmt(items):
            return "\n".join(
                f"  {k}: {v['wins']}/{v['trades']}승 ({v['wins']/v['trades']*100:.0f}%) "
                f"누적PnL={v['total_pnl']:+.2f}%"
                for k, v in items
            )
        pattern_summary = f"\n[패턴 승률 상위]\n{fmt(top5)}\n[패턴 승률 하위]\n{fmt(bottom5)}"

    # 일별 성과 요약
    daily_summary = ""
    for day in sorted(daily.keys())[-14:]:
        for mode, s in daily[day].items():
            if "real" in mode:
                wr = f"{s['wins']}/{s['trades']}" if s['trades'] > 0 else "0/0"
                daily_summary += f"  {day} [{mode}]: {s['pnl_pct']:+.2f}% ({wr}승) \n"

    # 최근 20개 매매 로그 (실제만)
    real_logs = [l for l in logs if "real" in l.get("mode", "")][-20:]
    log_text  = "\n".join(
        f"  {l.get('ts')} [{l.get('action')}] ${l.get('price',0):,.0f} "
        f"RSI={l.get('rsi')} PnL={l.get('pnl', '-')} "
        f"reason={str(l.get('reason',''))[:80]}"
        for l in real_logs
    )

    # 전체 성과 통계
    total_trades = sum(s.get("trades", 0) for d in daily.values()
                       for s in d.values() if "real" in d)
    total_wins   = sum(s.get("wins",   0) for d in daily.values()
                       for s in d.values() if "real" in d)
    total_pnl    = sum(s.get("pnl_pct", 0) for d in daily.values()
                       for s in d.values() if "real" in d)
    win_rate     = f"{total_wins/total_trades*100:.1f}%" if total_trades > 0 else "N/A"

    prompt = f"""You are a professional quantitative trading system optimizer.
Date: {kst_now}

## 현재 파라미터 (tuning.json)
{json.dumps(current_tuning, ensure_ascii=False, indent=2)}

## 전체 성과 요약 (최근 14일, 실매매)
총 트레이드: {total_trades}회  승률: {win_rate}  누적PnL: {total_pnl:+.2f}%

## 일별 성과
{daily_summary}

## 패턴별 통계 (3회 이상)
{pattern_summary}

## 최근 20개 실매매 로그
{log_text}

---

## 분석 요청

위 데이터를 바탕으로 다음을 수행하라:

1. **문제 진단**: 손실의 주요 원인 3가지를 구체적으로 분석
2. **패턴 인사이트**: 높은 승률 패턴 vs 낮은 승률 패턴의 공통점
3. **파라미터 최적화**: 아래 JSON 형식으로 개선된 파라미터 제시

### 파라미터 조정 가이드
- `leverage`: 최근 PnL이 연속 마이너스면 낮추기 (8~15 범위)
- `size_pct`: 변동성 클 때 낮추기 (20~50 범위)
- `cooldown`: 손절 후 재진입 대기시간 초 (600~1800)
- `daily_loss_stop`: 일 최대 손실 허용 % (2.0~5.0)
- `max_daily_losses`: 연속 손절 후 중단 횟수 (2~4)
- `rsi_long_max`: 롱 진입 허용 RSI 최대값 (60~75)
- `rsi_short_min`: 숏 진입 허용 RSI 최소값 (25~40)
- `rr_min`: 최소 손익비 (1.2~2.5)
- `sl_cap_pct`: SL 최대 거리 % (1.0~2.5)
- `enabled_strategies`: 활성화할 전략 목록 (smc, ema_cross, bb_reversion, asian_breakout)
- `active_symbols`: 매매할 심볼 (BTC-USDT-SWAP, ETH-USDT-SWAP, XRP-USDT-SWAP)
- `ema_cross_tp_atr`: EMA크로스 전략 TP ATR 배수 (1.5~4.0)
- `bb_rev_tp_atr`: BB평균회귀 TP ATR 배수 (1.5~3.0)
- `asian_break_tp_atr`: 아시안브레이크 TP ATR 배수 (2.0~5.0)

### 출력 형식 (JSON만, 설명 없이)
{{
  "diagnosis": ["진단1", "진단2", "진단3"],
  "pattern_insights": "패턴 인사이트 요약 (한국어 2-3문장)",
  "tuning": {{
    "leverage": <number>,
    "size_pct": <number>,
    "cooldown": <number>,
    "max_daily_trades": <number>,
    "daily_profit_stop": <number>,
    "daily_loss_stop": <number>,
    "max_daily_losses": <number>,
    "rsi_long_max": <number>,
    "rsi_short_min": <number>,
    "rr_min": <number>,
    "sl_cap_pct": <number>,
    "tp_min_pct": <number>,
    "enabled_strategies": [...],
    "active_symbols": [...],
    "ema_cross_tp_atr": <number>,
    "ema_cross_sl_atr": <number>,
    "bb_rev_tp_atr": <number>,
    "bb_rev_sl_atr": <number>,
    "asian_break_tp_atr": <number>,
    "asian_break_sl_atr": <number>
  }}
}}"""
    return prompt


# ── Claude CLI 실행 ────────────────────────────────────────────────
def run_claude(prompt):
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=180,
            encoding="utf-8", errors="replace"
        )
        if result.returncode != 0:
            return None, f"Claude CLI 오류: {result.stderr[:300]}"
        resp = json.loads(result.stdout)
        raw  = resp.get("result", "")
        m    = re.search(r'\{[\s\S]+\}', raw)
        if not m:
            return None, f"JSON 추출 실패: {raw[:200]}"
        return json.loads(m.group()), None
    except subprocess.TimeoutExpired:
        return None, "Claude CLI timeout (180s)"
    except Exception as e:
        return None, str(e)


# ── tuning.json 저장 ──────────────────────────────────────────────
def save_tuning(review_result, current_version):
    new_tuning = review_result.get("tuning", {})
    new_tuning["version"]    = current_version + 1
    new_tuning["last_tuned"] = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")

    TUNING_PATH.write_text(
        json.dumps(new_tuning, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # 복기 히스토리 기록
    history_entry = {
        "date":             new_tuning["last_tuned"],
        "version":          new_tuning["version"],
        "diagnosis":        review_result.get("diagnosis", []),
        "pattern_insights": review_result.get("pattern_insights", ""),
        "tuning":           new_tuning,
    }
    with open(REVIEW_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(history_entry, ensure_ascii=False) + "\n")

    return new_tuning


# ── 메인 ──────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*60}")
    print(f"[daily_review] 시작: {datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M KST')}")
    print(f"{'='*60}")

    # 1. 데이터 로드
    logs, daily, pstats = load_recent_logs(days=14)
    current_tuning = load_tuning()
    print(f"[1] 로그 {len(logs)}개, 일별 {len(daily)}일, 패턴 {len(pstats)}개 로드")

    if not logs and not daily:
        print("[!] 매매 기록 없음 → 복기 스킵")
        return

    # 2. 프롬프트 생성
    prompt = build_prompt(logs, daily, pstats, current_tuning)
    print(f"[2] 프롬프트 생성 ({len(prompt):,}자) → Claude 분석 요청...")

    # 3. Claude 실행
    t0     = time.time()
    result, err = run_claude(prompt)
    elapsed = time.time() - t0

    if err:
        print(f"[!] Claude 실패: {err}")
        return

    print(f"[3] Claude 응답 ({elapsed:.1f}초)")

    # 4. 파라미터 먼저 저장 (출력 오류와 무관하게)
    new_tuning = save_tuning(result, current_tuning.get("version", 0))

    # 5. 결과 출력
    print("\n[결과] 진단:")
    for i, d in enumerate(result.get("diagnosis", []), 1):
        print(f"  {i}. {d}")

    print(f"\n[인사이트] {result.get('pattern_insights', '-')}")
    print(f"\n[OK] tuning.json 저장 (v{new_tuning['version']})")

    # 변경된 파라미터 표시
    changed = {k: v for k, v in new_tuning.items()
               if k in current_tuning and current_tuning[k] != v
               and k not in ("version", "last_tuned")}
    if changed:
        print("\n[fix] 변경된 파라미터:")
        for k, v in changed.items():
            print(f"  {k}: {current_tuning[k]} → {v}")
    else:
        print("\n  (파라미터 변경 없음)")

    print(f"\n[done] {datetime.now(timezone(timedelta(hours=9))).strftime('%H:%M KST')}")


if __name__ == "__main__":
    main()
