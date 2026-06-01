"""
경쟁사 인텔리전스 에이전트
────────────────────────────
- 경쟁사 인스타그램 최근 포스팅 수집
- X(트위터) 운동복·출근복 키워드 트렌드 수집
- Claude API로 남성 타겟 인사이트 분석
- Google Sheets에 자동 저장

필요한 GitHub Secrets:
  APIFY_API_TOKEN    - Apify 콘솔 > Settings > API tokens
  ANTHROPIC_API_KEY  - console.anthropic.com
  GOOGLE_CREDENTIALS - 서비스 계정 JSON (문자열로 통째로)
  SPREADSHEET_ID     - Sheets URL의 /d/{ID}/ 부분
"""

import os
import json
from datetime import datetime, date

from apify_client import ApifyClient
import anthropic
import gspread
from google.oauth2.service_account import Credentials


# ══════════════════════════════════════════
# 설정 — 여기만 수정하면 돼
# ══════════════════════════════════════════

# 경쟁사 인스타그램 계정명 (실제 핸들 확인 후 수정)
COMPETITORS = {
    "룰루레몬": "lululemon_kr",
    "젝시믹스": "xexymix",
    "무신사":   "musinsa",
    "STCO":     "stco_official",   # ⚠️ 정확한 계정명 확인 필요
    "유니클로": "uniqlokr",
}

# X 모니터링 키워드 — 남성 운동복
KEYWORDS_WORKOUT = [
    "남성운동복",
    "남자운동복",
    "헬스복 추천",
    "러닝복 남자",
    "남자 스포츠웨어",
    "헬스웨어 추천",
]

# X 모니터링 키워드 — 남성 출근복·애슬레저
KEYWORDS_COMMUTE = [
    "남자출근복",
    "직장인코디 남자",
    "애슬레저 남성",
    "편한출근복 남자",
    "남자 데일리룩 운동",
]

ALL_KEYWORDS = KEYWORDS_WORKOUT + KEYWORDS_COMMUTE

# Apify 수집량 (무료 크레딧 절약 설정)
IG_POSTS_PER_BRAND = 5    # 브랜드당 최근 N개 포스팅
X_POSTS_PER_KEYWORD = 5   # 키워드당 최근 N개 포스트


# ══════════════════════════════════════════
# 인스타그램 수집
# ══════════════════════════════════════════

def collect_instagram(client: ApifyClient) -> list[dict]:
    print("📸 인스타그램 수집 중...")

    run = client.actor("apify/instagram-profile-scraper").call(
        run_input={
            "usernames": list(COMPETITORS.values()),
            "resultsLimit": IG_POSTS_PER_BRAND,
        }
    )

    # 계정명 → 브랜드명 역매핑
    handle_to_brand = {v: k for k, v in COMPETITORS.items()}
    results = []

    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        username = item.get("username", "")
        brand = handle_to_brand.get(username, username)

        for post in item.get("latestPosts", [])[:IG_POSTS_PER_BRAND]:
            results.append({
                "brand":     brand,
                "platform":  "Instagram",
                "caption":   post.get("caption", "")[:300],
                "likes":     post.get("likesCount", 0),
                "comments":  post.get("commentsCount", 0),
                "hashtags":  post.get("hashtags", [])[:10],
                "timestamp": post.get("timestamp", ""),
                "url":       post.get("url", ""),
            })

    print(f"  → {len(results)}개 포스트 수집 완료")
    return results


# ══════════════════════════════════════════
# X (트위터) 수집
# ══════════════════════════════════════════

def collect_x(client: ApifyClient) -> list[dict]:
    print("🐦 X 키워드 수집 중...")
    results = []

    for keyword in ALL_KEYWORDS:
        try:
            run = client.actor("apify/twitter-scraper").call(
                run_input={
                    "searchTerms": [keyword],
                    "maxItems":    X_POSTS_PER_KEYWORD,
                    "lang":        "ko",
                }
            )

            for item in client.dataset(run["defaultDatasetId"]).iterate_items():
                results.append({
                    "keyword":   keyword,
                    "category":  "운동복" if keyword in KEYWORDS_WORKOUT else "출근복",
                    "platform":  "X",
                    "text":      item.get("text", "")[:300],
                    "likes":     item.get("likeCount", 0),
                    "retweets":  item.get("retweetCount", 0),
                    "timestamp": item.get("createdAt", ""),
                    "url":       item.get("url", ""),
                })

        except Exception as e:
            # 특정 키워드 실패 시 전체 중단 방지
            print(f"  ⚠️ '{keyword}' 수집 실패 (스킵): {e}")

    print(f"  → {len(results)}개 포스트 수집 완료")
    return results


# ══════════════════════════════════════════
# Claude API 분석
# ══════════════════════════════════════════

def analyze(ig_data: list[dict], x_data: list[dict]) -> str:
    print("🤖 Claude 분석 중...")

    claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = f"""
너는 남성 스포츠 패션 브랜드의 퍼포먼스 마케터야.
오늘 수집된 경쟁사 소셜 데이터를 분석해서 바로 실무에 쓸 수 있는 인사이트를 뽑아줘.
주 타겟은 운동과 일상을 넘나드는 20-40대 남성이야.

=== 경쟁사 인스타그램 최근 포스팅 ===
{json.dumps(ig_data, ensure_ascii=False)}

=== X 소비자 반응 (운동복·출근복 키워드별) ===
{json.dumps(x_data[:30], ensure_ascii=False)}

다음 형식으로 분석해줘:

## 1. 오늘의 핵심 인사이트 (3가지)
각각 마케터 관점에서 즉시 활용 가능한 내용으로, 근거 포함해서 2-3문장

## 2. 경쟁사 움직임 요약
어느 브랜드가 어떤 메시지·소재·해시태그로 남성 소비자에게 어필하고 있는지

## 3. 남성 소비자 언어 트렌드
- 운동복: 자주 등장하는 표현·니즈·불만
- 출근복: 자주 등장하는 표현·니즈·불만
(실제 소비자 언어 그대로 뽑아줘 — 캠페인 카피에 쓸 수 있게)

## 4. 공략 포인트
경쟁사가 아직 못 잡고 있는 메시지 갭이나 기회 영역

번지르르한 말 말고, 마케터가 내일 당장 쓸 수 있는 언어로 써줘.
"""

    msg = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    return msg.content[0].text


# ══════════════════════════════════════════
# Google Sheets 저장
# ══════════════════════════════════════════

def update_sheets(ig_data: list[dict], x_data: list[dict], analysis: str) -> None:
    print("📊 Sheets 업데이트 중...")

    creds_info = json.loads(os.environ["GOOGLE_CREDENTIALS"])
    creds = Credentials.from_service_account_info(
        creds_info,
        scopes=[
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(os.environ["SPREADSHEET_ID"])
    today = date.today().strftime("%Y-%m-%d")

    # ── 시트 1: 오늘 브리핑 (매일 덮어쓰기) ──
    try:
        ws_brief = sh.worksheet("📌 오늘 브리핑")
    except gspread.WorksheetNotFound:
        ws_brief = sh.add_worksheet("📌 오늘 브리핑", rows=100, cols=2)

    ws_brief.clear()
    ws_brief.update(
        "A1",
        [
            ["📅 업데이트", today],
            ["📦 수집량", f"Instagram {len(ig_data)}건 | X {len(x_data)}건"],
            [""],
            ["🤖 AI 분석 리포트", ""],
            [analysis, ""],
        ],
    )

    # ── 시트 2: 인스타 로그 (날짜별 누적) ──
    try:
        ws_ig = sh.worksheet("📸 인스타 로그")
    except gspread.WorksheetNotFound:
        ws_ig = sh.add_worksheet("📸 인스타 로그", rows=2000, cols=7)
        ws_ig.append_row(["날짜", "브랜드", "캡션", "좋아요", "댓글", "해시태그", "URL"])

    for p in ig_data:
        hashtag_str = " ".join(f"#{h}" for h in p["hashtags"][:5])
        ws_ig.append_row([
            today, p["brand"], p["caption"],
            p["likes"], p["comments"], hashtag_str, p["url"],
        ])

    # ── 시트 3: X 트렌드 로그 (날짜별 누적) ──
    try:
        ws_x = sh.worksheet("🐦 X 트렌드")
    except gspread.WorksheetNotFound:
        ws_x = sh.add_worksheet("🐦 X 트렌드", rows=2000, cols=7)
        ws_x.append_row(["날짜", "카테고리", "키워드", "내용", "좋아요", "리트윗", "URL"])

    for p in x_data:
        ws_x.append_row([
            today, p["category"], p["keyword"],
            p["text"], p["likes"], p["retweets"], p["url"],
        ])

    print("  → Sheets 업데이트 완료")


# ══════════════════════════════════════════
# 실행
# ══════════════════════════════════════════

def main():
    print(f"\n🚀 경쟁사 인텔리전스 에이전트 [{datetime.now().strftime('%Y-%m-%d %H:%M')}]\n")

    client = ApifyClient(os.environ["APIFY_API_TOKEN"])

    ig_data  = collect_instagram(client)
    x_data   = collect_x(client)
    analysis = analyze(ig_data, x_data)

    update_sheets(ig_data, x_data, analysis)

    print("\n" + "─" * 50)
    print(analysis)
    print("─" * 50)
    print("\n✅ 완료\n")


if __name__ == "__main__":
    main()
