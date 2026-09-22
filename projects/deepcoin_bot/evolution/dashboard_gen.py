"""
dashboard_gen.py — 대시보드용 JSON 데이터 생성
실행: python evolution/dashboard_gen.py
출력: dashboard/data.json
"""

import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "backtest"))

from data_fetcher import fetch_historical
from ict_engine import get_market_regime, get_htf_trend
from weights import _load as load_weights

DASHBOARD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard")
os.makedirs(DASHBOARD_DIR, exist_ok=True)

SYMBOLS = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "XRP-USDT-SWAP"]


def get_regime_info(sym):
    try:
        d1 = fetch_historical(sym, "1D", 120)
        h1 = fetch_historical(sym, "1H", 7)
        regime   = get_market_regime(d1)
        h1_trend = get_htf_trend(h1)
        price    = d1[-1]["c"] if d1 else None
        return {"regime": regime, "h1_trend": h1_trend, "price": price}
    except Exception as e:
        return {"regime": "unknown", "h1_trend": "unknown", "price": None, "error": str(e)}


def analyze_weights():
    weights = load_weights()
    retire, watch, elite, ok = [], [], [], []

    for key, v in weights.items():
        total   = v.get("total", 0)
        wr      = v.get("win_rate", 0)
        weight  = v.get("weight", 1.0)
        entry   = {"key": key, "total": total, "win_rate": wr, "weight": weight}

        if total < 5:
            continue
        if wr < 20:
            retire.append(entry)
        elif wr >= 45:
            elite.append(entry)
        elif wr < 30:
            watch.append(entry)
        else:
            ok.append(entry)

    retire.sort(key=lambda x: x["win_rate"])
    elite.sort(key=lambda x: -x["win_rate"])
    return {"retire": retire, "watch": watch, "elite": elite, "ok": ok, "all": weights}


def generate_recommendations(regimes, weight_analysis):
    recs = []

    for sym, info in regimes.items():
        ticker = sym.split("-")[0]
        regime = info["regime"]
        h1t    = info["h1_trend"]

        if regime == "bull" and h1t == "bullish":
            recs.append({
                "type": "GO_LONG",
                "asset": ticker,
                "reason": f"{ticker} 일봉 상승장 + 1H 상승추세 일치 → 롱 우선",
                "action": "OTE Long / MTF Long NY 집중"
            })
        elif regime == "bear" and h1t == "bearish":
            recs.append({
                "type": "GO_SHORT",
                "asset": ticker,
                "reason": f"{ticker} 일봉 하락장 + 1H 하락추세 일치 → 숏 우선",
                "action": "OTE Short / Breaker Short 집중"
            })
        elif regime == "ranging":
            recs.append({
                "type": "CAUTION",
                "asset": ticker,
                "reason": f"{ticker} 횡보장 → 신호 축소, 고컨플루언스 셋업만",
                "action": "MTF 전략만 사용 (컨플루언스 3개 이상 필수)"
            })
        else:
            recs.append({
                "type": "MIXED",
                "asset": ticker,
                "reason": f"{ticker} 일봉:{regime} / 1H:{h1t} 불일치 → 관망 권고",
                "action": "진입 보류"
            })

    # 전략 진화 제안
    for e in weight_analysis["retire"][:3]:
        recs.append({
            "type": "RETIRE",
            "asset": e["key"].split("_")[-1] if "_" in e["key"] else "ALL",
            "reason": f"[{e['key']}] 승률 {e['win_rate']:.1f}% ({e['total']}건) — 폐기 권고",
            "action": "해당 패턴 가중치 0.0으로 비활성화"
        })

    for e in weight_analysis["elite"][:3]:
        recs.append({
            "type": "PROMOTE",
            "asset": e["key"].split("_")[-1] if "_" in e["key"] else "ALL",
            "reason": f"[{e['key']}] 승률 {e['win_rate']:.1f}% ({e['total']}건) — 가중치 증가 권고",
            "action": f"현재 {e['weight']}x → 다음 백테스트 후 2.0x 검토"
        })

    return recs


def new_strategy_ideas(regimes, weight_analysis):
    ideas = []
    bull_assets = [s for s, i in regimes.items() if i["regime"] == "bull"]
    bear_assets = [s for s, i in regimes.items() if i["regime"] == "bear"]

    if bull_assets:
        ideas.append({
            "name": "VWAP_Retest_Long",
            "desc": f"{[s.split('-')[0] for s in bull_assets]} 상승장 — VWAP 재테스트 후 롱",
            "basis": "상승장에서 VWAP 이탈 후 복귀 = 고확률 롱 진입점 (ICT 관점: Discount + 거래량 지지)"
        })
    if bear_assets:
        ideas.append({
            "name": "Asian_High_Sweep_Short",
            "desc": f"{[s.split('-')[0] for s in bear_assets]} 하락장 — 아시안 고점 스윕 후 숏",
            "basis": "하락장 아시안 세션 고점 유동성 청소 후 런던/뉴욕에서 숏 (ICT 킬존 + 스윕 조합)"
        })

    # 현재 성공 패턴 기반 아이디어
    elite = weight_analysis.get("elite", [])
    if any("ote_short" in e["key"] for e in elite):
        ideas.append({
            "name": "OTE_Short_Premium_Filter",
            "desc": "OTE Short에 Premium Zone 필터 강화",
            "basis": "현재 OTE Short 47% WR → 진입 시 Premium Zone 상위 30% 이내로 제한하면 WR 60%+ 가능성"
        })
    if any("mtf_long_newyork" in e["key"] for e in elite):
        ideas.append({
            "name": "NY_Session_Long_Only",
            "desc": "MTF Long NY 전용 고확률 전략",
            "basis": "MTF Long NY BTC 80% WR (5건) — 샘플 확보 시 단독 전략으로 분리 가치"
        })

    return ideas


def main():
    print("시장 국면 수집 중...")
    regimes = {}
    for sym in SYMBOLS:
        ticker = sym.split("-")[0]
        print(f"  {ticker}...")
        regimes[sym] = get_regime_info(sym)

    print("가중치 분석 중...")
    weight_analysis = analyze_weights()

    print("추천 생성 중...")
    recommendations = generate_recommendations(regimes, weight_analysis)
    ideas = new_strategy_ideas(regimes, weight_analysis)

    data = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "regimes": regimes,
        "weights": weight_analysis,
        "recommendations": recommendations,
        "new_strategy_ideas": ideas,
        "summary": {
            "total_patterns": len(weight_analysis["all"]),
            "elite_count":    len(weight_analysis["elite"]),
            "retire_count":   len(weight_analysis["retire"]),
            "watch_count":    len(weight_analysis["watch"]),
        }
    }

    out_path = os.path.join(DASHBOARD_DIR, "data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n완료: {out_path}")
    print(f"  전략 패턴: {data['summary']['total_patterns']}개")
    print(f"  엘리트:   {data['summary']['elite_count']}개")
    print(f"  폐기 권고: {data['summary']['retire_count']}개")
    print(f"  관찰 필요: {data['summary']['watch_count']}개")
    for sym, info in regimes.items():
        ticker = sym.split("-")[0]
        print(f"  {ticker}: {info['regime']} / 1H {info['h1_trend']} / ${info.get('price', '?')}")


if __name__ == "__main__":
    main()
