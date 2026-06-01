"""
경쟁사 인텔리전스 에이전트
────────────────────────────
- 경쟁사 인스타그램 최근 포스팅 수집
- X(트위터) 운동복·출근복 키워드 트렌드 수집
- Claude API로 남성 타겟 인사이트 분석
- Google Sheets 저장 + Gmail 뉴스레터 발송

필요한 GitHub Secrets:
  APIFY_API_TOKEN      - Apify 콘솔 > Settings > API tokens
  ANTHROPIC_API_KEY    - console.anthropic.com
  GOOGLE_CREDENTIALS   - 서비스 계정 JSON (문자열로 통째로)
  SPREADSHEET_ID       - Sheets URL의 /d/{ID}/ 부분
  GMAIL_ADDRESS        - 받을 지메일 주소
  GMAIL_APP_PASSWORD   - 구글 앱 비밀번호 (16자리)
"""

import os
import json
import smtplib
from datetime import datetime, date
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from apify_client import ApifyClient
import anthropic
import gspread
from google.oauth2.service_account import Credentials


# ══════════════════════════════════════════
# 설정
# ══════════════════════════════════════════

COMPETITORS = {
    "룰루레몬": "lululemon_kr",
    "젝시믹스": "xexymix",
    "무신사":   "musinsa",
    "STCO":     "stco_official",
    "유니클로": "uniqlokr",
}

KEYWORDS_WORKOUT = [
    "남성운동복", "남자운동복", "헬스복 추천",
    "러닝복 남자", "남자 스포츠웨어", "헬스웨어 추천",
]

KEYWORDS_COMMUTE = [
    "남자출근복", "직장인코디 남자", "애슬레저 남성",
    "편한출근복 남자", "남자 데일리룩 운동",
]

ALL_KEYWORDS = KEYWORDS_WORKOUT + KEYWORDS_COMMUTE

IG_POSTS_PER_BRAND  = 5
X_POSTS_PER_KEYWORD = 5


# ══════════════════════════════════════════
# 헬퍼
# ══════════════════════════════════════════

def parse_date(ts: str) -> str:
    """Apify 타임스탬프 → YYYY-MM-DD"""
    if not ts:
        return ""
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except Exception:
        return ts[:10] if len(ts) >= 10 else ts


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

    handle_to_brand = {v: k for k, v in COMPETITORS.items()}
    results = []

    for item in client.dataset(run.default_dataset_id).iterate_items():
        username = item.get("username", "")
        brand    = handle_to_brand.get(username, username)

        for post in item.get("latestPosts", [])[:IG_POSTS_PER_BRAND]:
            results.append({
                "brand":     brand,
                "platform":  "Instagram",
                "caption":   post.get("caption", "")[:300],
                "likes":     post.get("likesCount", 0),
                "comments":  post.get("commentsCount", 0),
                "hashtags":  post.get("hashtags", [])[:10],
                "post_date": parse_date(post.get("timestamp", "")),  # 실제 게시일
                "url":       post.get("url", ""),
            })

    print(f"  → {len(results)}개 포스트 수집 완료")
    return results


# ══════════════════════════════════════════
# X 수집
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
            for item in client.dataset(run.default_dataset_id).iterate_items():
                results.append({
                    "keyword":   keyword,
                    "category":  "운동복" if keyword in KEYWORDS_WORKOUT else "출근복",
                    "platform":  "X",
                    "text":      item.get("text", "")[:300],
                    "likes":     item.get("likeCount", 0),
                    "retweets":  item.get("retweetCount", 0),
                    "post_date": parse_date(item.get("createdAt", "")),  # 실제 게시일
                    "url":       item.get("url", ""),
                })
        except Exception as e:
            print(f"  ⚠️ '{keyword}' 수집 실패 (스킵): {e}")

    print(f"  → {len(results)}개 포스트 수집 완료")
    return results


# ══════════════════════════════════════════
# Claude 분석
# ══════════════════════════════════════════

def analyze(ig_data: list[dict], x_data: list[dict]) -> str:
    print("🤖 Claude 분석 중...")

    claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = f"""
너는 남성 스포츠 패션 브랜드의 퍼포먼스 마케터야.
오늘 수집된 경쟁사 소셜 데이터를 분석해서 이메일 뉴스레터로 보낼 브리핑을 작성해줘.
주 타겟은 운동과 일상을 넘나드는 20-40대 남성이야.

=== 경쟁사 인스타그램 최근 포스팅 ===
{json.dumps(ig_data, ensure_ascii=False)}

=== X 소비자 반응 ===
{json.dumps(x_data[:30], ensure_ascii=False)}

아래 HTML 형식으로만 작성해줘. 마크다운 쓰지 말고 HTML 태그로만.

<h3>① 오늘의 핵심 인사이트</h3>
<p><b>[인사이트 제목]</b><br>[2-3문장 설명]</p>
(3개 작성)

<h3>② 경쟁사 움직임</h3>
<p><b>[브랜드명]</b>: [한 줄 요약]</p>
(브랜드별)

<h3>③ 남성 소비자 언어</h3>
<p><b>운동복</b>: [실제 소비자 표현·키워드]<br>
<b>출근복</b>: [실제 소비자 표현·키워드]</p>

<h3>④ 공략 포인트</h3>
<p>[경쟁사 갭, 기회 영역 2-3문장]</p>

마케터가 내일 당장 쓸 수 있는 언어로 써줘.
"""

    msg = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    return msg.content[0].text


# ══════════════════════════════════════════
# Gmail 뉴스레터 발송
# ══════════════════════════════════════════

def send_newsletter(analysis: str, ig_count: int, x_count: int, today: str) -> None:
    print("📧 이메일 발송 중...")

    gmail   = os.environ["GMAIL_ADDRESS"]
    app_pw  = os.environ["GMAIL_APP_PASSWORD"]

    html = f"""
<!DOCTYPE html>
<html>
<body style="font-family:'Apple SD Gothic Neo',sans-serif;max-width:620px;margin:0 auto;padding:24px;color:#222;background:#fff;">

  <div style="border-bottom:2px solid #111;padding-bottom:14px;margin-bottom:28px;">
    <p style="margin:0;font-size:12px;color:#888;letter-spacing:1px;">COMPETITIVE INTELLIGENCE</p>
    <h1 style="margin:6px 0 4px;font-size:22px;font-weight:700;">경쟁사 브리핑</h1>
    <p style="margin:0;font-size:13px;color:#666;">{today} &nbsp;·&nbsp; Instagram {ig_count}건 &nbsp;·&nbsp; X {x_count}건</p>
  </div>

  <div style="font-size:15px;line-height:1.8;">
    {analysis}
  </div>

  <div style="margin-top:36px;padding-top:16px;border-top:1px solid #eee;font-size:11px;color:#aaa;">
    자동 발송 &nbsp;·&nbsp; g8428/experiment &nbsp;·&nbsp; {today}
  </div>

</body>
</html>
"""

    msg = MIMEMultipart("alternative")
    msg["Subject"]  = f"📊 경쟁사 브리핑 {today}"
    msg["From"]     = gmail
    msg["To"]       = gmail
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(gmail, app_pw)
        s.send_message(msg)

    print("  → 발송 완료")


# ══════════════════════════════════════════
# Google Sheets 저장
# ══════════════════════════════════════════

def update_sheets(ig_data: list[dict], x_data: list[dict], analysis: str, today: str) -> None:
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

    # 시트 1: 오늘 브리핑
    try:
        ws_brief = sh.worksheet("📌 오늘 브리핑")
    except gspread.WorksheetNotFound:
        ws_brief = sh.add_worksheet("📌 오늘 브리핑", rows=100, cols=2)

    ws_brief.clear()
    ws_brief.update("A1", [
        ["📅 수집일", today],
        ["📦 수집량", f"Instagram {len(ig_data)}건 | X {len(x_data)}건"],
        [""],
        ["🤖 AI 분석", ""],
        [analysis, ""],
    ])

    # 시트 2: 인스타 로그 (게시일 기준)
    try:
        ws_ig = sh.worksheet("📸 인스타 로그")
    except gspread.WorksheetNotFound:
        ws_ig = sh.add_worksheet("📸 인스타 로그", rows=2000, cols=8)
        ws_ig.append_row(["게시일", "수집일", "브랜드", "캡션", "좋아요", "댓글", "해시태그", "URL"])

    for p in ig_data:
        ws_ig.append_row([
            p["post_date"],   # 실제 게시일
            today,            # 수집일
            p["brand"],
            p["caption"],
            p["likes"],
            p["comments"],
            " ".join(f"#{h}" for h in p["hashtags"][:5]),
            p["url"],
        ])

    # 시트 3: X 트렌드 로그
    try:
        ws_x = sh.worksheet("🐦 X 트렌드")
    except gspread.WorksheetNotFound:
        ws_x = sh.add_worksheet("🐦 X 트렌드", rows=2000, cols=8)
        ws_x.append_row(["게시일", "수집일", "카테고리", "키워드", "내용", "좋아요", "리트윗", "URL"])

    for p in x_data:
        ws_x.append_row([
            p["post_date"],   # 실제 게시일
            today,            # 수집일
            p["category"],
            p["keyword"],
            p["text"],
            p["likes"],
            p["retweets"],
            p["url"],
        ])

    print("  → 업데이트 완료")


# ══════════════════════════════════════════
# 실행
# ══════════════════════════════════════════

def main():
    today = date.today().strftime("%Y-%m-%d")
    print(f"\n🚀 경쟁사 인텔리전스 에이전트 [{datetime.now().strftime('%Y-%m-%d %H:%M')}]\n")

    client = ApifyClient(os.environ["APIFY_API_TOKEN"])

    ig_data  = collect_instagram(client)
    x_data   = collect_x(client)
    analysis = analyze(ig_data, x_data)

    update_sheets(ig_data, x_data, analysis, today)
    send_newsletter(analysis, len(ig_data), len(x_data), today)

    print("\n✅ 완료\n")


if __name__ == "__main__":
    main()
