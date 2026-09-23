#!/usr/bin/env python3
"""
1688 소싱 확인 스크립트
- 상품명 입력 → 1688 검색 → 가격/MOQ/리드타임 근사치 수집

사용법:
    python sourcing_1688.py "迷你洗衣机 内衣"
    python sourcing_1688.py "迷你洗衣机" --korean "미니 속옷세탁기"

    # 한국어 입력도 가능 (자동 번역 검색어 제안 포함)
    python sourcing_1688.py --korean "미니 속옷세탁기"

의존성:
    pip install duckduckgo-search requests beautifulsoup4
"""

import sys
import re
import json
import argparse
import datetime
from pathlib import Path

# Windows 콘솔 UTF-8 설정
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    from duckduckgo_search import DDGS
except ImportError:
    print("[ERROR] duckduckgo-search 패키지가 없습니다. 설치: pip install duckduckgo-search")
    sys.exit(1)

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("[ERROR] requests/beautifulsoup4 패키지가 없습니다. 설치: pip install requests beautifulsoup4")
    sys.exit(1)

# ── 한국어 → 중국어 키워드 힌트 매핑 (자주 쓰는 것만) ──
KR_TO_CN_HINTS = {
    "미니세탁기": "迷你洗衣机",
    "속옷세탁기": "内衣洗衣机",
    "미니 속옷세탁기": "迷你洗衣机 内衣",
    "셀프벽지": "自粘墙纸",
    "인테리어벽지": "装饰墙纸",
    "키링": "钥匙扣",
    "아크릴키링": "亚克力钥匙扣",
    "피아노키링": "钢琴键盘钥匙扣",
    "포토카드": "小卡",
    "다이소": "大创",
    "말랑이": "解压玩具",
    "스퀴시": "捏捏乐",
}

# ── 가격 추출 패턴 (위안화) ──
PRICE_RE = re.compile(r'[\¥￥]?\s*(\d[\d,.]+)\s*(元|元/个|元/件|/piece|yuan|RMB)', re.IGNORECASE)
PRICE_NUM_RE = re.compile(r'(\d+\.?\d*)\s*~?\s*(\d+\.?\d*)?\s*(元|yuan|rmb|\¥|￥)', re.IGNORECASE)

# ── MOQ 추출 패턴 ──
MOQ_RE = re.compile(r'(最小起订量|MOQ|起订量|起批)[：:\s]*(\d+)\s*(件|个|pcs|pieces)?', re.IGNORECASE)
MOQ_RE2 = re.compile(r'(\d+)\s*(件|个|pcs)\s*(起|起批|起订)', re.IGNORECASE)

# ── 배송 기간 추출 ──
LEAD_RE = re.compile(r'(发货|出货|备货|生产)[：:\s]*(\d+)[~-]?(\d+)?\s*(天|日|工作日)', re.IGNORECASE)


def suggest_chinese_keyword(korean: str) -> str:
    """한국어 키워드에서 1688 검색용 중국어 키워드 제안."""
    # 직접 매핑 확인
    for kr, cn in KR_TO_CN_HINTS.items():
        if kr in korean:
            return cn
    # 매핑 없으면 원본 반환 + 경고
    print(f"  [WARN] '{korean}' 중국어 키워드 매핑 없음. 직접 중국어 키워드 입력 권장.")
    return korean


def parse_price_from_text(text: str) -> dict:
    """텍스트에서 가격 정보 추출."""
    prices = []

    # 패턴 1: "¥12.5" 형식
    for m in PRICE_RE.finditer(text):
        try:
            prices.append(float(m.group(1).replace(",", "")))
        except:
            pass

    # 패턴 2: "5~20元" 형식
    for m in PRICE_NUM_RE.finditer(text):
        try:
            prices.append(float(m.group(1)))
            if m.group(2):
                prices.append(float(m.group(2)))
        except:
            pass

    if not prices:
        return {"min": None, "max": None, "unit": "CNY"}

    return {
        "min": min(prices),
        "max": max(prices),
        "unit": "CNY",
        "krw_min": int(min(prices) * 200),   # 1위안 ≈ 200원 (근사)
        "krw_max": int(max(prices) * 200),
    }


def parse_moq(text: str):
    """최소 주문 수량 추출."""
    for pat in [MOQ_RE, MOQ_RE2]:
        m = pat.search(text)
        if m:
            groups = [g for g in m.groups() if g and g.isdigit()]
            if groups:
                return f"{groups[0]}개"
    return None


def parse_lead_time(text: str):
    """발송 기간 추출."""
    m = LEAD_RE.search(text)
    if m:
        days_start = m.group(2)
        days_end = m.group(3)
        unit = m.group(4)
        if days_end:
            return f"{days_start}~{days_end}{unit}"
        return f"{days_start}{unit}"
    return None


def search_1688(cn_keyword: str, max_results: int = 10) -> list[dict]:
    """DuckDuckGo로 1688 상품 검색."""
    ddgs = DDGS()
    found = []

    queries = [
        f"site:1688.com {cn_keyword}",
        f"1688.com {cn_keyword} 批发 价格",
        f"阿里巴巴 {cn_keyword} 价格 MOQ",
    ]

    for query in queries:
        print(f"  검색: {query[:70]}...")
        try:
            results = list(ddgs.text(query, max_results=max_results, region="zh-cn"))
        except Exception as e:
            print(f"  [WARN] 검색 실패: {e}")
            continue

        for r in results:
            text = f"{r.get('title','')} {r.get('body','')}"
            price = parse_price_from_text(text)
            moq   = parse_moq(text)
            lead  = parse_lead_time(text)

            found.append({
                "title":     r.get("title", ""),
                "url":       r.get("href", ""),
                "body":      r.get("body", "")[:400],
                "price":     price,
                "moq":       moq,
                "lead_time": lead,
            })

    return found


def summarize_sourcing(results: list[dict], cn_keyword: str, kr_keyword: str = "") -> dict:
    """검색 결과를 소싱 요약으로 정리."""
    all_prices = []
    moqs = []
    leads = []

    for r in results:
        p = r["price"]
        if p["min"] is not None:
            all_prices.append(p["min"])
        if p["max"] is not None:
            all_prices.append(p["max"])
        if r["moq"]:
            moqs.append(r["moq"])
        if r["lead_time"]:
            leads.append(r["lead_time"])

    summary = {
        "keyword_cn": cn_keyword,
        "keyword_kr": kr_keyword,
        "result_count": len(results),
        "price_range_cny": {
            "min": min(all_prices) if all_prices else None,
            "max": max(all_prices) if all_prices else None,
        },
        "price_range_krw": {
            "min": int(min(all_prices) * 200) if all_prices else None,
            "max": int(max(all_prices) * 200) if all_prices else None,
        },
        "moq_samples":  list(set(moqs))[:5],
        "lead_time_samples": list(set(leads))[:5],
        "top_results": results[:5],
    }

    # 마진 계산 (예시: 5배 마진)
    if summary["price_range_krw"]["max"]:
        unit_cost = summary["price_range_krw"]["max"]
        summary["margin_estimate"] = {
            "unit_cost_krw":   unit_cost,
            "selling_price_5x": unit_cost * 5,
            "note": "관세+배송+마케팅 비용 별도. 알리 기준 대략 20~30% 추가."
        }

    return summary


def print_summary(summary: dict):
    """소싱 요약 출력."""
    print(f"\n{'='*50}")
    print(f"📦 소싱 분석 결과: {summary['keyword_kr'] or summary['keyword_cn']}")
    print(f"{'='*50}")
    print(f"검색 결과 수: {summary['result_count']}개")

    p = summary["price_range_cny"]
    pk = summary["price_range_krw"]
    if p["min"] is not None:
        print(f"가격 범위(CNY): ¥{p['min']:.1f} ~ ¥{p['max']:.1f}")
        print(f"가격 범위(KRW): ₩{pk['min']:,} ~ ₩{pk['max']:,} (1위안≈200원 근사)")
    else:
        print("가격 정보: 검색 결과에서 직접 추출 불가 (1688 직접 접속 필요)")

    if summary["moq_samples"]:
        print(f"MOQ 샘플: {', '.join(summary['moq_samples'])}")
    else:
        print("MOQ: 정보 없음 (1688 직접 확인 필요)")

    if summary["lead_time_samples"]:
        print(f"리드타임 샘플: {', '.join(summary['lead_time_samples'])}")
    else:
        print("리드타임: 정보 없음 (1688 직접 확인 필요)")

    if "margin_estimate" in summary:
        m = summary["margin_estimate"]
        print(f"\n💰 마진 추정 (5배 기준):")
        print(f"   단가: ₩{m['unit_cost_krw']:,}")
        print(f"   판매가(5x): ₩{m['selling_price_5x']:,}")
        print(f"   참고: {m['note']}")

    print(f"\n🔗 주요 결과:")
    for r in summary["top_results"][:3]:
        print(f"  - {r['title'][:50]}")
        print(f"    {r['url'][:80]}")


def run(cn_keyword: str, kr_keyword: str = "", max_results: int = 10, save: bool = True) -> dict:
    print(f"\n🔍 1688 소싱 검색 시작")
    print(f"   중국어 키워드: {cn_keyword}")
    if kr_keyword:
        print(f"   한국어 키워드: {kr_keyword}")

    results = search_1688(cn_keyword, max_results)
    summary = summarize_sourcing(results, cn_keyword, kr_keyword)
    print_summary(summary)

    if save:
        today = datetime.date.today().isoformat()
        safe = re.sub(r'[^\w가-힣A-Za-z]', '_', kr_keyword or cn_keyword)
        out_dir = Path(__file__).parent.parent / "track-b" / "sourcing"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{today}_{safe}_sourcing.json"
        out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n✅ 소싱 데이터 저장: {out_path}")
        summary["saved_to"] = str(out_path)

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="1688 소싱 확인 스크립트")
    parser.add_argument("cn_keyword", nargs="?", default=None, help="중국어 검색 키워드 (예: '迷你洗衣机 内衣')")
    parser.add_argument("--korean", "-k", type=str, default="", help="한국어 키워드 (자동으로 중국어 힌트 제안)")
    parser.add_argument("--max-results", type=int, default=10, help="검색 결과 수 (기본: 10)")
    parser.add_argument("--no-save", action="store_true", help="결과 파일 저장 안 함")
    args = parser.parse_args()

    # 키워드 결정
    cn_kw = args.cn_keyword
    kr_kw = args.korean

    if not cn_kw and kr_kw:
        cn_kw = suggest_chinese_keyword(kr_kw)
        print(f"  한국어 → 중국어 변환: '{kr_kw}' → '{cn_kw}'")
    elif not cn_kw:
        print("[ERROR] 중국어 키워드(positional) 또는 --korean 옵션 중 하나는 필요합니다.")
        parser.print_help()
        sys.exit(1)

    result = run(cn_kw, kr_kw, args.max_results, save=not args.no_save)
    print(f"\n🎯 완료")
