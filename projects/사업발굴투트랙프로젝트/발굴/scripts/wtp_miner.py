#!/usr/bin/env python3
"""
Track A WTP 마이닝 파이프라인
- 키워드 입력 → 네이버카페/쿠팡/블라인드에서 WTP 원문 수집 → track-a 기회카드 초안 저장

사용법:
    python wtp_miner.py "미니 속옷세탁기"
    python wtp_miner.py "미니 속옷세탁기" --max-results 20

의존성:
    pip install duckduckgo-search requests beautifulsoup4
"""

import sys
import re
import json
import datetime
import argparse
from pathlib import Path
from urllib.parse import quote

# Windows 콘솔 UTF-8 설정
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    from duckduckgo_search import DDGS
except ImportError:
    try:
        from ddgs import DDGS
    except ImportError:
        print("[ERROR] ddgs 패키지가 없습니다. 설치: pip install ddgs")
        sys.exit(1)

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("[ERROR] requests/beautifulsoup4 패키지가 없습니다. 설치: pip install requests beautifulsoup4")
    sys.exit(1)

# ── WTP 신호 키워드 (지불의사가 담긴 문장 패턴) ──
WTP_PATTERNS = [
    r'[0-9만천원]+\s*(은|는|이면|정도면|에)\s*(낼|살|구매)',
    r'(살\s*의향|구매\s*의향|구입\s*의향)',
    r'(얼마면|가격만\s*맞으면)',
    r'(진짜\s*살\s*것\s*같|살\s*것\s*같아|살\s*것\s*같다)',
    r'(한\s*달에|매달|정기적으로)\s*[0-9]',
    r'(비싸도|좀\s*비싸더라도)\s*(사겠|살\s*것|구매)',
    r'(이거\s*(있으면|생기면))\s*(얼마든|돈\s*(내겠|낼))',
    r'(가성비|값어치)',
    r'(선물로\s*사고\s*싶|선물\s*추천)',
    r'[0-9]+만원\s*(주고도|내고도)\s*(살|구매)',
]

WTP_RE = [re.compile(p) for p in WTP_PATTERNS]

# ── 검색 대상 사이트 ──
SEARCH_SITES = [
    ("네이버카페",  "site:cafe.naver.com"),
    ("쿠팡리뷰",   "site:coupang.com"),
    ("블라인드",   "site:blind.so OR site:teamblind.com"),
    ("에브리타임", "site:everytime.kr"),
    ("네이버블로그","site:blog.naver.com"),
]


def search_wtp(keyword: str, max_results: int = 15):
    """DuckDuckGo로 커뮤니티 검색 후 WTP 신호 포함 결과 추출."""
    found = []
    ddgs_client = DDGS()

    for site_name, site_filter in SEARCH_SITES:
        # 한국어 리전 우선, 중국 포함 다중 지역 시도
        for region in ["kr-kr", "wt-wt"]:
            query = f"{keyword} {site_filter} 가격 구매 후기 사고싶다"
            print(f"  검색 중: [{site_name}/{region}] {query[:55]}...")

            try:
                results = list(ddgs_client.text(query, max_results=max_results, region=region))
                if results:
                    break  # 결과 있으면 다음 리전 시도 안 함
            except Exception as e:
                print(f"  [WARN] {site_name} 검색 실패: {e}")
                results = []
                continue

        for r in (results or []):
            title = r.get("title", "")
            body  = r.get("body", "")
            url   = r.get("href", "")
            text  = f"{title} {body}"

            # WTP 패턴 매칭
            matched = []
            for pat in WTP_RE:
                m = pat.search(text)
                if m:
                    # 매칭 주변 60자 컨텍스트 추출
                    start = max(0, m.start() - 30)
                    end   = min(len(text), m.end() + 60)
                    snippet = text[start:end].strip()
                    matched.append(snippet)

            if matched:
                found.append({
                    "site":     site_name,
                    "title":    title,
                    "url":      url,
                    "snippets": list(set(matched)),
                    "raw_body": body[:300],
                })

    return found


def extract_price_signals(wtp_results: list[dict]) -> list[str]:
    """WTP 결과에서 금액이 명시된 원문만 추출."""
    price_re = re.compile(r'[0-9,]+\s*(원|만원|천원)')
    signals = []
    for r in wtp_results:
        for snippet in r["snippets"]:
            if price_re.search(snippet):
                signals.append(f'"{snippet.strip()}" — {r["url"]}')
    return signals


def build_opportunity_card(keyword: str, wtp_results: list[dict], price_signals: list[str]) -> str:
    """Track A 기회 카드 마크다운 생성."""
    today = datetime.date.today().isoformat()
    total_hits = sum(len(r["snippets"]) for r in wtp_results)
    site_counts = {}
    for r in wtp_results:
        site_counts[r["site"]] = site_counts.get(r["site"], 0) + 1

    card = f"""# 기회 카드 — {keyword}

- **기회명:** {keyword}
- **트랙:** A (지속가능)
- **발굴일:** {today}
- **발굴 도구:** WTP 마이닝 자동화 (wtp_miner.py)

---

## WTP 신호 수집 결과

- 총 WTP 신호 수: **{total_hits}개**
- 사이트별 적중: {', '.join(f'{k} {v}건' for k,v in site_counts.items())}

---

## WTP 원문 인용 (금액 언급 포함)

"""
    if price_signals:
        for i, sig in enumerate(price_signals[:10], 1):
            card += f"{i}. {sig}\n"
    else:
        card += "_금액이 명시된 WTP 원문 없음 — 추가 수동 조사 필요_\n"

    card += "\n---\n\n## 전체 WTP 신호 원문\n\n"
    for r in wtp_results[:15]:
        card += f"### [{r['site']}] {r['title'][:60]}\n"
        card += f"URL: {r['url']}\n\n"
        for snip in r["snippets"][:3]:
            card += f"> \"{snip}\"\n\n"

    card += f"""
---

## 미확인 사항

1. **시장 갭 스코어**: 네이버 데이터랩 검색량 vs 공급자 밀도 직접 확인 필요
2. **경쟁 1~2점 리뷰 분석**: 기존 제품의 불만사항 구체화 필요
3. **WTP 금액 범위**: 추출된 원문 기준 최소/최대 WTP 확인 필요

---

## Go/Pivot/Stop 1차 판정

**→ 추가 검증 필요** (WTP 원문 {total_hits}개 수집 — 충분성 판단은 수동으로)

조건: WTP 원문 5개 이상 + 금액 언급 2개 이상 → Go 검토
현재: WTP 원문 {total_hits}개, 금액 언급 {len(price_signals)}개
"""
    return card


def run(keyword: str, max_results: int = 15, output_dir: str = None):
    print(f"\n🔍 WTP 마이닝 시작: [{keyword}]")
    print(f"   최대 결과: {max_results}개 / 사이트")

    wtp_results = search_wtp(keyword, max_results)
    price_signals = extract_price_signals(wtp_results)

    print(f"\n📊 결과: WTP 신호 {sum(len(r['snippets']) for r in wtp_results)}개")
    print(f"   금액 언급: {len(price_signals)}개")

    # 기회 카드 저장
    card_md = build_opportunity_card(keyword, wtp_results, price_signals)
    safe_name = re.sub(r'[^\w가-힣]', '_', keyword)
    today = datetime.date.today().isoformat()
    filename = f"{today}_{safe_name}.md"

    base = Path(output_dir) if output_dir else Path(__file__).parent.parent / "track-a" / "opportunities"
    base.mkdir(parents=True, exist_ok=True)
    out_path = base / filename
    out_path.write_text(card_md, encoding="utf-8")
    print(f"\n✅ 기회 카드 저장: {out_path}")

    # JSON 원본 데이터도 저장
    json_path = base / f"{today}_{safe_name}_raw.json"
    json_path.write_text(
        json.dumps({"keyword": keyword, "results": wtp_results, "price_signals": price_signals},
                   ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"   원본 데이터: {json_path}")

    return {"card_path": str(out_path), "wtp_count": sum(len(r['snippets']) for r in wtp_results), "price_count": len(price_signals)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Track A WTP 마이닝 파이프라인")
    parser.add_argument("keyword", help="검색할 상품/주제 키워드 (예: '미니 속옷세탁기')")
    parser.add_argument("--max-results", type=int, default=15, help="사이트별 최대 검색 결과 수 (기본: 15)")
    parser.add_argument("--output-dir", type=str, default=None, help="기회 카드 저장 디렉터리")
    args = parser.parse_args()

    result = run(args.keyword, args.max_results, args.output_dir)
    print(f"\n🎯 완료: {result}")
