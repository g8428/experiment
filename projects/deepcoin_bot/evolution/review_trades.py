"""
evolution/review_trades.py — 트레이드 패턴 통계 집계 + 원칙 업데이트 제안

사용:
    python evolution/review_trades.py

출력:
    - evolution/pattern_stats.json (집계 결과 + pending_updates)
    - 콘솔에 요약 + 원칙 업데이트 제안 출력

CLAUDE.md 가이드:
    세션 시작 시 이 스크립트를 실행하고,
    pending_updates 중 MIN_TRADES 이상인 패턴을 STRATEGY.md에 반영한다.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

MIN_TRADES = 5          # 통계 유의성 기준 최소 거래 수
HIGH_WIN   = 0.70       # 이 이상이면 "강화" 제안
LOW_WIN    = 0.30       # 이 이하이면 "제한/금지" 제안
BLOCK_WIN  = 0.20       # 이 이하 + 3거래 이상이면 즉시 금지 고려


def parse_pattern_tables(log_dir: Path) -> dict:
    """모든 daily trade log에서 패턴 학습 통계 테이블 파싱."""
    pattern_totals = {}  # key → {"trades": int, "wins": int, "pnl": float}

    for md_file in sorted(log_dir.glob("*.md")):
        text = md_file.read_text(encoding="utf-8", errors="ignore")

        # 테이블 블록 찾기: "패턴 학습 통계" 이후
        if "패턴 학습 통계" not in text:
            continue

        # 테이블 행 파싱 (| `key` | trades | wins | winrate | pnl |)
        for line in text.splitlines():
            m = re.match(
                r"\|\s*`([^`]+)`\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*[\d.]+%?\s*\|\s*([+\-][\d.]+)%\s*\|",
                line.strip()
            )
            if not m:
                continue
            key, trades, wins, pnl_str = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
            pnl = float(pnl_str)

            if key not in pattern_totals:
                pattern_totals[key] = {"trades": 0, "wins": 0, "pnl": 0.0}
            # 최신 누적값으로 덮어쓰기 (파일은 날짜순으로 정렬됨)
            # 각 파일의 "누적" 값이 최신이므로, 더 큰 trades를 가진 파일 값 채택
            existing = pattern_totals[key]
            if trades >= existing["trades"]:
                pattern_totals[key] = {"trades": trades, "wins": wins, "pnl": round(pnl, 2)}

    return pattern_totals


def compute_win_rates(pattern_totals: dict) -> list:
    """승률 + 분류 계산."""
    results = []
    for key, d in pattern_totals.items():
        t = d["trades"]
        w = d["wins"]
        pnl = d["pnl"]
        wr = round(w / t, 4) if t > 0 else 0.0
        results.append({
            "key": key,
            "trades": t,
            "wins": w,
            "win_rate": wr,
            "pnl": pnl,
        })
    results.sort(key=lambda x: (-x["trades"], -x["win_rate"]))
    return results


def generate_pending_updates(stats: list) -> list:
    """통계적으로 유의미한 패턴의 원칙 업데이트 제안 생성."""
    updates = []
    for s in stats:
        t, wr, key, pnl = s["trades"], s["win_rate"], s["key"], s["pnl"]

        if t >= MIN_TRADES and wr >= HIGH_WIN:
            updates.append({
                "pattern": key,
                "action": "strengthen",
                "reason": f"win_rate={wr*100:.0f}% ({t}trades, PnL {pnl:+.2f}%) -> STRATEGY.md 높은확률 진입조건에 추가",
                "priority": "high",
            })
        elif t >= MIN_TRADES and wr <= LOW_WIN:
            updates.append({
                "pattern": key,
                "action": "restrict",
                "reason": f"win_rate={wr*100:.0f}% ({t}trades, PnL {pnl:+.2f}%) -> STRATEGY.md 주의/금지 조건에 추가",
                "priority": "high",
            })
        elif t >= 3 and wr <= BLOCK_WIN:
            updates.append({
                "pattern": key,
                "action": "watch",
                "reason": f"win_rate={wr*100:.0f}% ({t}trades, PnL {pnl:+.2f}%) -> 5거래 채울때까지 모니터링",
                "priority": "medium",
            })

    return updates


def print_summary(stats: list, pending: list):
    """콘솔 요약 출력."""
    print("\n" + "="*60)
    print("딥코인봇 패턴 통계 리뷰")
    print(f"분석 시각: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*60)

    print(f"\n{'패턴 키':<55} {'거래':>4} {'승률':>6} {'PnL':>8}")
    print("-"*78)
    for s in stats:
        flag = "[OK]" if s["win_rate"] >= HIGH_WIN and s["trades"] >= MIN_TRADES else \
               "[NO]" if s["win_rate"] <= LOW_WIN  and s["trades"] >= MIN_TRADES else \
               "[!!]" if s["win_rate"] <= BLOCK_WIN and s["trades"] >= 3 else "    "
        print(f"{flag} {s['key']:<53} {s['trades']:>4} {s['win_rate']*100:>5.0f}% {s['pnl']:>+7.2f}%")

    if pending:
        print(f"\n{'='*60}")
        print(f"STRATEGY.md 업데이트 제안 ({len(pending)}개)")
        print("="*60)
        for u in pending:
            pri = "[HIGH]" if u["priority"] == "high" else "[MED] "
            print(f"{pri} [{u['action'].upper()}] {u['pattern']}")
            print(f"        -> {u['reason']}")
    else:
        print("\n✓ 현재 업데이트 제안 없음 (데이터 충분하지 않거나 모두 정상 범위)")

    print()


def main():
    base = Path(__file__).parent.parent
    log_dir = base / "trade_logs" / "daily"
    out_path = Path(__file__).parent / "pattern_stats.json"

    if not log_dir.exists():
        print(f"[error] trade_logs 디렉토리 없음: {log_dir}")
        return

    raw = parse_pattern_tables(log_dir)
    stats = compute_win_rates(raw)
    pending = generate_pending_updates(stats)

    result = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_patterns": len(stats),
        "patterns": stats,
        "pending_updates": pending,
        "summary": {
            "total_trades": sum(s["trades"] for s in stats),
            "patterns_with_5plus": sum(1 for s in stats if s["trades"] >= MIN_TRADES),
            "high_win_patterns": sum(1 for s in stats if s["trades"] >= MIN_TRADES and s["win_rate"] >= HIGH_WIN),
            "low_win_patterns":  sum(1 for s in stats if s["trades"] >= MIN_TRADES and s["win_rate"] <= LOW_WIN),
        }
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print_summary(stats, pending)
    print(f"[저장] {out_path}")

    if pending:
        print("\n>>> CLAUDE: pending_updates를 STRATEGY.md 섹션 2에 반영하고")
        print("    버전 올리기 + 진화 이력 추가 후 커밋하세요.\n")


if __name__ == "__main__":
    main()
