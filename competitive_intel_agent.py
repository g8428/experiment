"""
경쟁사 인텔리전스 에이전트
────────────────────────────
- 경쟁사 인스타그램 최근 포스팅 수집
- 네이버 블로그·카페·뉴스 키워드 수집
- Claude API로 남성 타겟 인사이트 분석
- Google Sheets 저장 + Gmail 뉴스레터 발송

필요한 GitHub Secrets:
  APIFY_API_TOKEN      - Apify 콘솔 > Settings > API tokens
  ANTHROPIC_API_KEY    - console.anthropic.com
  GOOGLE_CREDENTIALS   - 서비스 계정 JSON (문자열로 통째로)
  SPREADSHEET_ID       - Sheets URL의 /d/{ID}/ 부분
  GMAIL_ADDRESS        - 받을 지메일 주소
  GMAIL_APP_PASSWORD   - 구글 앱 비밀번호 (16자리)
  NAVER_CLIENT_ID      - 네이버 개발자센터 Client ID
  NAVER_CLIENT_SECRET  - 네이버 개발자센터 Client Secret
"""

import os
import json
import smtplib
import requests
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

KEYWORDS_CONSUMER = [
    "남성운동복 추천", "남자운동복 후기",
    "헬스복 추천 남자", "러닝복 남자 추천",
    "남자출근복 코디", "직장인 운동복 남자",
    "애슬레저 남성 추천",
]

KEYWORDS_NEWS = [
    "스포츠패션 남성", "러닝 트렌드",
    "애슬레저 시장", "남성 운동복 브랜드",
    "스포츠웨어 트렌드",
]

IG_POSTS_PER_BRAND  = 5
NAVER_RESULTS_EACH  = 5


# ══════════════════════════════════════════
# 헬퍼
# ══════════════════════════════════════════

def parse_date(ts: str) -> str:
    if not ts:
        return ""
    for fmt in ("%Y%m%d", "%a, %d %b %Y %H:%M:%S +0900"):
        try:
            return datetime.strptime(ts[:len(fmt)], fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return ts[:10] if len(ts) >= 10 else ts

def clean_html(text: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", text).strip()


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
                "caption":   post.get("caption", "")[:300],
                "likes":     post.get("likesCount", 0),
                "comments":  post.get("commentsCount", 0),
                "hashtags":  post.get("hashtags", [])[:10],
                "post_date": parse_date(post.get("timestamp", "")),
                "url":       post.get("url", ""),
            })

    print(f"  → {len(results)}개 포스트 수집 완료")
    return results


# ══════════════════════════════════════════
# 네이버 검색 API 수집
# ══════════════════════════════════════════

def naver_search(query: str, search_type: str, display: int = 5) -> list[dict]:
    url = f"https://openapi.naver.com/v1/search/{search_type}.json"
    headers = {
        "X-Naver-Client-Id":     os.environ["NAVER_CLIENT_ID"],
        "X-Naver-Client-Secret": os.environ["NAVER_CLIENT_SECRET"],
    }
    params = {"query": query, "display": display, "sort": "date"}
    res = requests.get(url, headers=headers, params=params, timeout=10)
    res.raise_for_status()
    return res.json().get("items", [])


def collect_naver() -> list[dict]:
    print("🔍 네이버 블로그·카페·뉴스 수집 중...")
    results = []

    for keyword in KEYWORDS_CONSUMER:
        for search_type, label in [("blog", "블로그"), ("cafearticle", "카페")]:
            try:
                items = naver_search(keyword, search_type, NAVER_RESULTS_EACH)
                for item in items:
                    results.append({
                        "source":    label,
                        "keyword":   keyword,
                        "category":  "소비자반응",
                        "title":     clean_html(item.get("title", "")),
                        "text":      clean_html(item.get("description", ""))[:300],
                        "post_date": parse_date(item.get("postdate") or item.get("datetime", "")),
                        "url":       item.get("link", ""),
                    })
            except Exception as e:
                print(f"  ⚠️ [{label}] '{keyword}' 실패 (스킵): {e}")

    for keyword in KEYWORDS_NEWS:
        try:
            items = naver_search(keyword, "news", NAVER_RESULTS_EACH)
            for item in items:
                results.append({
                    "source":    "뉴스",
                    "keyword":   keyword,
                    "category":  "업계동향",
                    "title":     clean_html(item.get("title", "")),
                    "text":      clean_html(item.get("description", ""))[:300],
                    "post_date": parse_date(item.get("pubDate", "")),
                    "url":       item.get("originallink") or item.get("link", ""),
                })
        except Exception as e:
            print(f"  ⚠️ [뉴스] '{keyword}' 실패 (스킵): {e}")

    print(f"  → {len(results)}건 수집 완료 (블로그+카페+뉴스)")
    return results


# ══════════════════════════════════════════
# Claude 분석
# ══════════════════════════════════════════

def analyze(ig_data: list[dict], naver_data: list[dict]) -> str:
    print("🤖 Claude 분석 중...")

    claude    = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    blog_cafe = [d for d in naver_data if d["source"] in ("블로그", "카페")]
    news      = [d for d in naver_data if d["source"] == "뉴스"]

    prompt = f"""
너는 남성 스포츠 패션 브랜드의 퍼포먼스 마케터야.
오늘 수집된 데이터를 분석해서 이메일 뉴스레터용 브리핑을 HTML로 작성해줘.
주 타겟은 운동과 일상을 넘나드는 20-40대 남성이야.

=== 경쟁사 인스타그램 ===
{json.dumps(ig_data, ensure_ascii=False)}

=== 네이버 블로그·카페 (소비자 반응) ===
{json.dumps(blog_cafe[:20], ensure_ascii=False)}

=== 네이버 뉴스 (업계 동향) ===
{json.dumps(news[:10], ensure_ascii=False)}

아래 HTML 형식으로만 작성해. 마크다운이나 코드펜스 절대 쓰지 말 것. HTML 태그만.

<h3>① 오늘의 핵심 인사이트</h3>
<p><b>[제목]</b><br>[2-3문장]</p>
(3개)

<h3>② 경쟁사 움직임</h3>
<p><b>[브랜드]</b>: [한 줄 요약]</p>

<h3>③ 소비자 언어 (블로그·카페)</h3>
<p><b>운동복</b>: [실제 소비자 표현·키워드]<br>
<b>출근복</b>: [실제 소비자 표현·키워드]</p>

<h3>④ 업계 동향 (뉴스)</h3>
<p>[주목할 뉴스 2-3건, 한 줄씩]</p>

<h3>⑤ 공략 포인트</h3>
<p>[경쟁사 갭, 기회 영역 2-3문장]</p>

각 섹션 간결하게. 마케터가 내일 당장 쓸 수 있는 언어로.
"""

    msg = claude.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )

    result = msg.content[0].text
    result = result.replace("```html", "").replace("```", "").strip()
    return result


# ══════════════════════════════════════════
# Gmail 뉴스레터 발송
# ══════════════════════════════════════════

def send_newsletter(analysis: str, ig_data: list[dict],
                    naver_data: list[dict], today: str) -> None:
    print("📧 이메일 발송 중...")

    gmail  = os.environ["GMAIL_ADDRESS"]
    app_pw = os.environ["GMAIL_APP_PASSWORD"]

    # 경쟁사 인스타 링크
    ig_links = "".join(
        f'<li><a href="{p["url"]}" style="color:#0066cc;text-decoration:none;">'
        f'{p["brand"]} ({p["post_date"]})</a></li>'
        for p in ig_data if p.get("url")
    )

    # 네이버 상위 15건 링크
    naver_links = "".join(
        f'<li><a href="{p["url"]}" style="color:#0066cc;text-decoration:none;">'
        f'[{p["source"]}] {p["title"][:45]}</a></li>'
        for p in naver_data[:15] if p.get("url")
    )

    html = f"""
<!DOCTYPE html>
<html>
<body style="font-family:'Apple SD Gothic Neo',sans-serif;max-width:620px;
             margin:0 auto;padding:24px;color:#222;background:#fff;">

  <div style="border-bottom:2px solid #111;padding-bottom:14px;margin-bottom:28px;">
    <p style="margin:0;font-size:11px;color:#888;letter-spacing:1.5px;">COMPETITIVE INTELLIGENCE</p>
    <h1 style="margin:6px 0 4px;font-size:22px;font-weight:700;">경쟁사 브리핑</h1>
    <p style="margin:0;font-size:13px;color:#666;">
      {today} &nbsp;·&nbsp;
      Instagram {len(ig_data)}건 &nbsp;·&nbsp;
      네이버 블로그·카페·뉴스 {len(naver_data)}건
    </p>
  </div>

  <div style="font-size:15px;line-height:1.85;">
    {analysis}
  </div>

  <div style="margin-top:32px;padding-top:20px;border-top:1px solid #eee;">
    <p style="font-size:12px;font-weight:700;color:#555;margin:0 0 8px;">
      📎 경쟁사 인스타그램</p>
    <ul style="font-size:12px;line-height:2;padding-left:16px;margin:0 0 16px;">
      {ig_links}
    </ul>
    <p style="font-size:12px;font-weight:700;color:#555;margin:0 0 8px;">
      📰 참고 블로그·카페·뉴스</p>
    <ul style="font-size:12px;line-height:2;padding-left:16px;margin:0;">
      {naver_links}
    </ul>
  </div>

  <div style="margin-top:28px;padding-top:16px;border-top:1px solid #eee;
              font-size:11px;color:#bbb;">
    자동 발송 · g8428/experiment · {today}
  </div>

</body>
</html>
"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📊 경쟁사 브리핑 {today}"
    msg["From"]    = gmail
    msg["To"]      = gmail
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(gmail, app_pw)
        s.send_message(msg)

    print("  → 발송 완료")


# ══════════════════════════════════════════
# Google Sheets 저장
# ══════════════════════════════════════════

def update_sheets(ig_data: list[dict], naver_data: list[dict],
                  analysis: str, today: str) -> None:
    print("📊 Sheets 업데이트 중...")

    creds = Credentials.from_service_account_info(
        json.loads(os.environ["GOOGLE_CREDENTIALS"]),
        scopes=[
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(os.environ["SPREADSHEET_ID"])

    # 오늘 브리핑
    try:
        ws_b = sh.worksheet("📌 오늘 브리핑")
    except gspread.WorksheetNotFound:
        ws_b = sh.add_worksheet("📌 오늘 브리핑", rows=100, cols=2)
    ws_b.clear()
    ws_b.update("A1", [
        ["📅 수집일", today],
        ["📦 수집량", f"Instagram {len(ig_data)}건 | 네이버 {len(naver_data)}건"],
        [""],
        ["🤖 AI 분석", ""],
        [analysis, ""],
    ])

    # 인스타 로그 — 배치 전송
    try:
        ws_ig = sh.worksheet("📸 인스타 로그")
    except gspread.WorksheetNotFound:
        ws_ig = sh.add_worksheet("📸 인스타 로그", rows=2000, cols=8)
        ws_ig.append_row(["게시일", "수집일", "브랜드", "캡션", "좋아요", "댓글", "해시태그", "URL"])
    ig_rows = [
        [
            p["post_date"], today, p["brand"], p["caption"],
            p["likes"], p["comments"],
            " ".join(f"#{h}" for h in p["hashtags"][:5]),
            p["url"],
        ]
        for p in ig_data
    ]
    if ig_rows:
        ws_ig.append_rows(ig_rows)

    # 네이버 로그 — 배치 전송
    try:
        ws_n = sh.worksheet("🔍 네이버 로그")
    except gspread.WorksheetNotFound:
        ws_n = sh.add_worksheet("🔍 네이버 로그", rows=2000, cols=8)
        ws_n.append_row(["게시일", "수집일", "출처", "카테고리", "키워드", "제목", "내용", "URL"])
    naver_rows = [
        [
            p["post_date"], today, p["source"], p["category"],
            p["keyword"], p["title"], p["text"], p["url"],
        ]
        for p in naver_data
    ]
    if naver_rows:
        ws_n.append_rows(naver_rows)

    print("  → 업데이트 완료")


# ══════════════════════════════════════════
# 실행
# ══════════════════════════════════════════

def main():
    today = date.today().strftime("%Y-%m-%d")
    print(f"\n🚀 경쟁사 인텔리전스 에이전트 [{datetime.now().strftime('%Y-%m-%d %H:%M')}]\n")

    apify = ApifyClient(os.environ["APIFY_API_TOKEN"])

    ig_data    = collect_instagram(apify)
    naver_data = collect_naver()
    analysis   = analyze(ig_data, naver_data)

    update_sheets(ig_data, naver_data, analysis, today)
    send_newsletter(analysis, ig_data, naver_data, today)

    print("\n✅ 완료\n")


if __name__ == "__main__":
    main()
