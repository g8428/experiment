"""
weights.py — 패턴별 승률 기반 가중치 자동 조정
패턴 키(e.g. ict_breaker_long_BTC) → 포지션 크기 배율 (0.25 ~ 2.0)
"""

import json
import os

WEIGHTS_PATH = os.path.join(os.path.dirname(__file__), "pattern_weights.json")
MIN_TRADES   = 5    # 가중치 반영 최소 거래 수
MIN_WEIGHT   = 0.25
MAX_WEIGHT   = 2.0


def _load():
    if os.path.exists(WEIGHTS_PATH):
        with open(WEIGHTS_PATH) as f:
            return json.load(f)
    return {}


def _save(data):
    with open(WEIGHTS_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_weight(pattern_key: str) -> float:
    """패턴의 현재 가중치 반환 (기본 1.0)"""
    data = _load()
    return data.get(pattern_key, {}).get("weight", 1.0)


def update_weights(trades: list, sym: str = ""):
    """백테스트 trades 결과로 패턴별 승률 갱신 후 가중치 재계산"""
    data = _load()
    stats = {}

    for t in trades:
        key = t.get("pattern_key", "unknown")
        if sym:
            key = f"{key}_{sym.split('-')[0]}"
        if key not in stats:
            stats[key] = {"wins": 0, "total": 0}
        stats[key]["total"] += 1
        if t.get("pnl", 0) > 0:
            stats[key]["wins"] += 1

    for key, s in stats.items():
        total = s["total"]
        win_rate = s["wins"] / total if total > 0 else 0.0

        prev = data.get(key, {"wins": 0, "total": 0, "weight": 1.0})
        # 누적 통계 합산
        cum_wins  = prev.get("wins", 0) + s["wins"]
        cum_total = prev.get("total", 0) + total
        cum_wr    = cum_wins / cum_total if cum_total > 0 else 0.0

        if cum_total >= MIN_TRADES:
            # 승률 → 가중치 매핑
            # WR 80%+ → 2.0 / 60~79% → 1.5 / 45~59% → 1.0 / 30~44% → 0.5 / <30% → 0.25
            if cum_wr >= 0.80:
                weight = 2.0
            elif cum_wr >= 0.60:
                weight = 1.5
            elif cum_wr >= 0.45:
                weight = 1.0
            elif cum_wr >= 0.30:
                weight = 0.5
            else:
                weight = 0.25
        else:
            weight = prev.get("weight", 1.0)

        data[key] = {
            "wins":     cum_wins,
            "total":    cum_total,
            "win_rate": round(cum_wr * 100, 1),
            "weight":   weight,
        }

    _save(data)
    return data


def sync_live_stats(pattern_stats: dict, sym: str = ""):
    """서버 실거래 _pattern_stats를 pattern_weights.json에 반영.
    pattern_stats: {key: {"trades": int, "wins": int, "total_pnl": float}}
    서버가 거래 청산할 때마다 호출 — 실거래 학습 루프의 핵심.
    """
    if not pattern_stats:
        return _load()
    data = _load()

    for key, s in pattern_stats.items():
        full_key = f"{key}_{sym.split('-')[0]}" if sym else key
        live_total = s.get("trades", 0)
        live_wins  = s.get("wins",   0)
        if live_total == 0:
            continue

        prev = data.get(full_key, {"wins": 0, "total": 0, "weight": 1.0})
        # 실거래 누적값은 이미 합산이므로 max로 선택 (이전 백테스트 값과 충돌 방지)
        cum_total = max(prev.get("total", 0), live_total)
        cum_wins  = max(prev.get("wins",  0), live_wins)
        cum_wr    = cum_wins / cum_total if cum_total > 0 else 0.0

        if cum_total >= MIN_TRADES:
            if   cum_wr >= 0.80: weight = 2.0
            elif cum_wr >= 0.60: weight = 1.5
            elif cum_wr >= 0.45: weight = 1.0
            elif cum_wr >= 0.30: weight = 0.5
            else:                weight = 0.25
        else:
            weight = prev.get("weight", 1.0)

        data[full_key] = {
            "wins":     cum_wins,
            "total":    cum_total,
            "win_rate": round(cum_wr * 100, 1),
            "weight":   weight,
        }

    _save(data)
    return data


def print_weights():
    data = _load()
    if not data:
        print("가중치 데이터 없음")
        return
    print(f"\n{'패턴 키':<45} {'거래':>5} {'승률':>7} {'가중치':>7}")
    print("-" * 70)
    for key, v in sorted(data.items()):
        print(f"{key:<45} {v['total']:>5} {v['win_rate']:>6.1f}% {v['weight']:>7.2f}x")
