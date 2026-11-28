"""최근 7일 AI 뉴스를 RSS/Atom으로 모아 research/ai-news-YYYY-MM-DD.md 에 저장.

공개 레포에 커밋되므로 제목·날짜·출처·링크·짧은 요약(200자)·대표 이미지 URL만 담는다(기사 본문 전문 금지).
피드가 하나 실패해도 나머지로 진행한다. 공식 발표 피드(official=True)만 og:image를 조회한다
(언론사 기사 사진은 저작권 때문에 대표 이미지도 기록하지 않는다).

실행: python projects/claude-code-monitor/news_collect.py [--days 7] [--check]
  --check : 피드 상태만 점검(파일 저장 안 함)
의존성: feedparser, requests
"""
from __future__ import annotations

import argparse
import html
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import feedparser
import requests

ROOT = Path(__file__).parent.parent.parent
RESEARCH_DIR = ROOT / "research"
UA = {"User-Agent": "Mozilla/5.0 (compatible; claude-code-monitor-news/1.0)"}

# ---- 피드 목록 (쉽게 바꿀 수 있게 상수로). official=True: 회사 공식 발표 (og:image 조회, 카드 근거 우선)
FEEDS = [
    {"name": "OpenAI", "url": "https://openai.com/news/rss.xml", "official": True},
    {"name": "Anthropic", "url": "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_news.xml", "official": True},  # 공식 RSS 없음 -> 서드파티 미러(링크는 anthropic.com),
    {"name": "Google DeepMind", "url": "https://deepmind.google/blog/rss.xml", "official": True},
    {"name": "Google AI", "url": "https://blog.google/technology/ai/rss/", "official": True},
    {"name": "Meta Engineering(ML)", "url": "https://engineering.fb.com/category/ml-applications/feed/", "official": True},  # ai.meta.com/blog는 RSS 없음,
    {"name": "Microsoft AI", "url": "https://www.microsoft.com/en-us/ai/blog/feed/", "official": True},
    {"name": "Hugging Face", "url": "https://huggingface.co/blog/feed.xml", "official": True},
    {"name": "The Verge AI", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "official": False},
    {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "official": False},
    {"name": "AI타임스", "url": "https://www.aitimes.com/rss/allArticle.xml", "official": False},
]
SUMMARY_MAX = 200
MAX_OG_FETCH = 25


def clean_summary(raw: str, limit: int = SUMMARY_MAX) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def entry_datetime(e) -> datetime | None:
    t = e.get("published_parsed") or e.get("updated_parsed")
    return datetime.fromtimestamp(time.mktime(t), timezone.utc) if t else None


def parse_feed(content: bytes, source: str, official: bool) -> list[dict]:
    parsed = feedparser.parse(content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"파싱 실패: {parsed.get('bozo_exception')}")
    items = []
    for e in parsed.entries:
        title, link = (e.get("title") or "").strip(), (e.get("link") or "").strip()
        if not title or not link:
            continue
        summary = e.get("summary") or (e.get("content") or [{}])[0].get("value", "")
        items.append({
            "title": html.unescape(title), "link": link, "date": entry_datetime(e),
            "source": source, "official": official, "summary": clean_summary(summary), "image": "",
        })
    return items


def normalize_title(t: str) -> str:
    return re.sub(r"[\W_]+", "", t.lower())


def dedupe(items: list[dict]) -> list[dict]:
    """제목(정규화) 또는 링크가 같으면 제거. 공식 발표를 우선 남긴다."""
    seen_t, seen_l, out = set(), set(), []
    for it in sorted(items, key=lambda i: (not i["official"],)):  # 안정 정렬: 공식 먼저
        k, l = normalize_title(it["title"]), it["link"].split("#")[0].rstrip("/")
        if k in seen_t or l in seen_l:
            continue
        seen_t.add(k)
        seen_l.add(l)
        out.append(it)
    return out


def filter_recent(items: list[dict], days: int, now: datetime | None = None) -> list[dict]:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    return [i for i in items if i["date"] and i["date"] >= cutoff]


def extract_og_image(page_html: str, base_url: str) -> str:
    for m in re.finditer(r"<meta\s+[^>]*>", page_html, flags=re.I):
        tag = m.group(0)
        if re.search(r"(property|name)=[\"']og:image(:secure_url)?[\"']", tag, flags=re.I):
            c = re.search(r"content=[\"']([^\"']+)[\"']", tag, flags=re.I)
            if c:
                return urljoin(base_url, html.unescape(c.group(1)))
    return ""


def fetch_og_image(url: str) -> str:
    try:
        r = requests.get(url, headers=UA, timeout=15)
        r.raise_for_status()
        return extract_og_image(r.text[:200000], url)
    except Exception:
        return ""


def fetch_feed(feed: dict) -> list[dict]:
    r = requests.get(feed["url"], headers=UA, timeout=20)
    r.raise_for_status()
    return parse_feed(r.content, feed["name"], feed["official"])


def render_md(items: list[dict], today: str, days: int, stats: list[tuple]) -> str:
    lines = [f"# AI 뉴스 수집 ({today})", "", f"> 최근 {days}일 / 피드 RSS 기준 / 제목·링크·요약(200자 이내)만 기록", ""]
    for name, status in stats:
        lines.append(f"- {name}: {status}")
    lines.append("")
    for it in items:
        lines.append(f"## {it['title']}")
        lines.append(f"- 날짜: {it['date'].astimezone(timezone(timedelta(hours=9))).strftime('%Y-%m-%d')}")
        lines.append(f"- 출처: {it['source']}{' (공식 발표)' if it['official'] else ''}")
        lines.append(f"- 링크: {it['link']}")
        if it["summary"]:
            lines.append(f"- 요약: {it['summary']}")
        if it["image"]:
            lines.append(f"- 대표 이미지(og:image): {it['image']}")
        lines.append("")
    return "\n".join(lines)


def collect(days: int = 7) -> tuple[list[dict], list[tuple]]:
    all_items, stats = [], []
    for feed in FEEDS:
        try:
            items = filter_recent(fetch_feed(feed), days)
            all_items += items
            stats.append((feed["name"], f"{len(items)}건"))
        except Exception as e:  # 한 피드 실패가 전체를 막지 않게
            stats.append((feed["name"], f"실패({type(e).__name__}: {str(e)[:80]})"))
    items = sorted(dedupe(all_items), key=lambda i: i["date"], reverse=True)
    fetched = 0
    for it in items:
        if it["official"] and fetched < MAX_OG_FETCH:
            it["image"] = fetch_og_image(it["link"])
            fetched += 1
    return items, stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    items, stats = collect(a.days)
    for name, status in stats:
        print(f"{name}: {status}")
    ok = sum(1 for _, s in stats if not s.startswith("실패"))
    print(f"\n피드 {ok}/{len(stats)} 성공, 중복 제거 후 {len(items)}건")
    if a.check:
        return 0
    if not items:
        print("수집된 뉴스가 없습니다", file=sys.stderr)
        return 1
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    path = RESEARCH_DIR / f"ai-news-{today}.md"
    path.write_text(render_md(items, today, a.days, stats), encoding="utf-8")
    print(f"저장: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
