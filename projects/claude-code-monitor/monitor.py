"""
Claude Code·AI 도구 소식 모니터 (v2)

v1은 "GitHub 검색 5개 쿼리 → 스타순 TOP 20" 하나뿐이라 공식 발표·신규 스킬·커뮤니티 화제를 못 잡았다.
v2는 공식 소스 + GitHub(신규·급상승) + 커뮤니티(HN/Reddit)를 모아 중요도 점수로 상위 N개만 리포트에 올린다.
v2.1(2026-10-14)부터 '글감 가치 판정'(config.json value_rules)을 통과한 항목만 후보가 된다. 릴리스 노트는 버전별이 아니라
이번 주기 릴리스를 하나로 묶어 bullet 한 줄씩 판정한다. 감시 키워드에 걸린 항목은 후보 풀에 올려 가산한다.
왜 이렇게 바꿨는지는 HANDOVER.md 참고.

실행:
  python projects/claude-code-monitor/monitor.py                 # 실제 수집 → research/ 저장
  python projects/claude-code-monitor/monitor.py --watchlist     # 요일과 무관하게 주간 감시 리스트 점검 포함
  python projects/claude-code-monitor/monitor.py --dry-run --fixtures projects/claude-code-monitor/fixtures/dry_run_sample.json
      # 네트워크 없이 가짜 응답으로 전체 흐름 확인. 파일을 쓰지 않고 리포트를 화면에 출력
  python projects/claude-code-monitor/monitor.py --dry-run --fixtures projects/claude-code-monitor/fixtures/case2_big_news_vs_minor.json --dump /tmp/x
      # --dump: dry-run 결과(리포트·latest-top.json)를 지정 폴더에 저장 (generate_content.py --top 검증용)

환경변수: GITHUB_TOKEN (Actions 기본 제공. 없어도 동작하지만 검색 rate limit이 낮다)
의존성: requests
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
KST = timezone(timedelta(hours=9))
CONFIG_PATH = HERE / "config.json"
RESEARCH_DIR = ROOT / "research"
STATE_PATH = RESEARCH_DIR / "state" / "claude-code-monitor.json"   # research/ 아래라 봇 커밋 범위 안에 있다
TOP_PATH = RESEARCH_DIR / "state" / "latest-top.json"               # generate_content.py / slack_notify.py 입력
UA = "g8428-experiment-claude-code-monitor/2.0"
GH_REPO_RE = re.compile(r"https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)")


# ─── 네트워크 (fixtures 모드 지원) ───────────────────────────────────────────

class Fetcher:
    """모든 외부 호출은 key를 달고 여기로 들어온다. fixtures 모드면 key로 가짜 응답을 돌려준다."""

    def __init__(self, token: str | None, fixtures: dict | None = None):
        self.token = token
        self.fixtures = fixtures

    def get(self, key: str, url: str, params: dict | None = None, headers: dict | None = None, text: bool = False):
        if self.fixtures is not None:
            if key in self.fixtures:
                return self.fixtures[key]
            # 케이스 fixture를 짧게 쓰도록 접두어별 기본 응답을 허용한다 (예: "search::" → {"items": []})
            for prefix, default in (self.fixtures.get("__defaults__") or {}).items():
                if key.startswith(prefix):
                    return default
            raise RuntimeError(f"fixture 없음: {key}")
        h = {"User-Agent": UA, **(headers or {})}
        resp = requests.get(url, params=params, headers=h, timeout=20)
        resp.raise_for_status()
        return resp.text if text else resp.json()

    def gh(self, key: str, path: str, params: dict | None = None, raw: bool = False):
        headers = {
            "Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return self.get(key, f"https://api.github.com{path}", params, headers, text=raw)

    def pause(self, seconds: float):
        if self.fixtures is None:
            time.sleep(seconds)


class Run:
    """소스별 수집 결과(성공/실패/건수/비고)를 모은다. 실패는 리포트 상단에 그대로 노출된다."""

    def __init__(self):
        self.statuses: list[dict] = []

    def source(self, name: str, label: str, fn, *args):
        try:
            result, count, note = fn(*args)
            self.statuses.append({"name": name, "label": label, "ok": True, "count": count, "note": note})
            return result
        except Exception as e:  # 한 소스가 죽어도 나머지는 계속
            msg = f"{type(e).__name__}: {e}"[:300]
            print(f"  [실패] {label}: {msg}", file=sys.stderr)
            self.statuses.append({"name": name, "label": label, "ok": False, "count": 0, "note": msg})
            return None

    @property
    def failures(self) -> list[dict]:
        return [s for s in self.statuses if not s["ok"]]


# ─── 아이템 공통 ──────────────────────────────────────────────────────────────

def make_item(id_, title, url, summary="", *, official=False, kind="github", source="", stars=None,
              created_at=None, published_at=None, mentions=0, text="") -> dict:
    return {
        "id": id_, "title": title, "url": url, "summary": (summary or "").strip(),
        "official": official, "kind": kind, "sources": [source] if source else [],
        "stars": stars, "created_at": created_at, "published_at": published_at,
        "mentions": mentions, "text": f"{title} {summary} {text}",
    }


def merge(items: dict[str, dict], new: dict):
    old = items.get(new["id"])
    if old is None:
        items[new["id"]] = new
        return
    old["sources"] = sorted(set(old["sources"]) | set(new["sources"]))
    old["official"] = old["official"] or new["official"]
    if new.get("stars") is not None:
        old["stars"] = max(old.get("stars") or 0, new["stars"])
    old["mentions"] += new.get("mentions", 0)
    old["text"] += " " + new["text"]
    for k in ("summary", "created_at", "published_at"):
        if not old.get(k) and new.get(k):
            old[k] = new[k]


def gh_repo_id(url: str | None) -> str | None:
    m = GH_REPO_RE.match(url or "")
    if not m:
        return None
    return f"gh:{m.group(1).lower()}/{m.group(2).lower().removesuffix('.git')}"


def parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def one_line(s: str, n: int = 160) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


# ─── 수집기: 공식 ─────────────────────────────────────────────────────────────

def collect_releases(f: Fetcher, cfg: dict, now: datetime, state: dict):
    """이번 주기에 처음 보는 릴리스만 돌려준다. 이후 bundle_releases()가 하나로 묶어 줄 단위로 판정한다."""
    items, cutoff = [], now - timedelta(days=cfg["lookback_days"])
    seen = set(state.get("releases_seen") or [])
    new_tags = []
    for repo in cfg["official"]["release_repos"]:
        for r in f.gh(f"releases::{repo}", f"/repos/{repo}/releases", {"per_page": 15}):
            pub = parse_dt(r.get("published_at"))
            tag = r.get("tag_name", "")
            if f"{repo}@{tag}" in seen:
                continue  # 지난 주기에 이미 판정한 릴리스
            if pub and pub >= cutoff:
                new_tags.append(f"{repo}@{tag}")
                items.append(make_item(
                    f"release:{repo}@{tag}", f"{repo} {tag} 릴리스", r.get("html_url", ""),
                    one_line(re.sub(r"^\s*[-*]\s*", "", r.get("body") or ""), 300), official=True, kind="official",
                    source="releases", published_at=r.get("published_at"), text=r.get("body", ""),
                ))
                items[-1]["body"] = r.get("body") or ""
    state["releases_seen"] = (list(state.get("releases_seen") or []) + new_tags)[-200:]
    return items, len(items), ""


CHANGELOG_HEAD = re.compile(r"^##\s+\[?v?(\d+\.\d+\.\d+[^\]\s]*)\]?.*$", re.M)


def collect_changelog(f: Fetcher, cfg: dict, state: dict):
    c = cfg["official"]["changelog"]
    text = f.gh(f"changelog::{c['repo']}", f"/repos/{c['repo']}/contents/{c['path']}", raw=True)
    heads = list(CHANGELOG_HEAD.finditer(text))
    if not heads:
        raise RuntimeError("버전 제목(## x.y.z)을 찾지 못함 — CHANGELOG 형식 변경 의심")
    sections = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        sections.append((m.group(1), text[m.end():end].strip()))
    last = state.get("changelog_last")
    state["changelog_last"] = sections[0][0]
    if last is None:
        return [], 0, f"기준선 저장 (최신 {sections[0][0]})"
    new = []
    for ver, body in sections:
        if ver == last:
            break
        new.append(make_item(
            f"changelog:{c['repo']}@{ver}", f"Claude Code {ver} 변경사항",
            f"https://github.com/{c['repo']}/blob/HEAD/{c['path']}",
            one_line(re.sub(r"^\s*[-*]\s*", "", body), 300), official=True, kind="official", source="changelog", text=body,
        ))
        new[-1]["body"] = body
        if len(new) >= 10:
            break
    return new, len(new), f"최신 {sections[0][0]}"


def collect_marketplace(f: Fetcher, cfg: dict, state: dict, m: dict):
    key = f"{m['repo']}/{m['path']}"
    data = f.gh(f"contents::{key}", f"/repos/{m['repo']}/contents/{m['path']}")
    names = sorted(d["name"] for d in data if d.get("type") == "dir")
    dirs = state.setdefault("dirs", {})
    prev = dirs.get(key)
    dirs[key] = names
    if prev is None:
        return [], 0, f"기준선 저장 ({len(names)}개)"
    official = m["repo"].lower().startswith("anthropics/")
    new = [
        make_item(
            f"market:{key}/{n}", f"[{m['label']}] 새 항목: {n}",
            f"https://github.com/{m['repo']}/tree/HEAD/{m['path']}/{n}",
            f"{m['repo']}의 {m['path']}/ 폴더에 '{n}'이(가) 새로 추가됨",
            official=official, kind="official" if official else "github", source="marketplace",
        )
        for n in names if n not in set(prev)
    ]
    return new, len(new), f"전체 {len(names)}개"


def collect_links(f: Fetcher, state: dict, w: dict):
    text = f.get(f"page::{w['name']}", w["url"], text=True)
    links = sorted({w.get("base", "") + m for m in re.findall(w["pattern"], text)})
    if not links:
        raise RuntimeError("링크 0개 — 페이지 구조 변경 또는 차단 의심")
    seen = state.setdefault("links", {})
    prev = seen.get(w["name"])
    seen[w["name"]] = links
    if prev is None:
        return [], 0, f"기준선 저장 ({len(links)}개)"
    fresh = [u for u in links if u not in set(prev)]
    def name(u: str) -> str:
        slug = u.rstrip("/").rsplit("/", 1)[-1]
        return slug.replace("-", " ").title() if w.get("pretty_slug") else slug  # claude-duet → Claude Duet

    new = [
        make_item(f"link:{u}", f"[{w['label']}] 새 페이지: {name(u)}", u,
                  f"{w['label']}에 새 링크가 생김", official=True, kind="official", source=w["name"])
        for u in fresh[:15]
    ]
    note = f"전체 {len(links)}개" + (f", 신규 {len(fresh)}개 중 15개만 반영" if len(fresh) > 15 else "")
    return new, len(new), note


ARTICLE_START_RE = re.compile(r'\{(?:"_id":"[^"]*",)?"_type":"article"')


def collect_articles(f: Fetcher, cfg: dict, now: datetime, a: dict):
    """페이지 안 JSON에 든 기사 객체(제목·슬러그·발표일·분류·요약)를 통째로 읽는다.
    anthropic.com/news는 기사 링크가 href가 아니라 JSON에 있어서, 예전 href 패턴은 메뉴 링크 26개만 잡고 기사는 0개였다.
    기사마다 필드 순서가 달라서(출시 글은 알파벳순) 정규식 대신 JSON으로 읽는다."""
    text = f.get(f"page::{a['name']}", a["url"], text=True).replace('\\"', '"').replace("\\\\", "\\")
    dec, arts = json.JSONDecoder(), {}
    for m in ARTICLE_START_RE.finditer(text):
        try:
            obj, _ = dec.raw_decode(text, m.start())
        except ValueError:
            continue
        slug = (obj.get("slug") or {}).get("current")
        if slug and obj.get("publishedOn") and obj.get("title"):
            arts[slug] = obj
    if not arts:
        raise RuntimeError("기사 0개 — 페이지 구조 변경 또는 차단 의심")
    since = (now - timedelta(days=cfg["lookback_days"])).strftime("%Y-%m-%d")
    keep_types = set(a.get("keep_types") or [])
    items = []
    for slug, o in arts.items():
        date = o["publishedOn"][:10]
        if date < since or (keep_types and o.get("articleType") not in keep_types):
            continue
        cats = o.get("newsCategories") or o.get("category") or o.get("articleType") or "기사"
        cats = ", ".join(cats) if isinstance(cats, list) else cats
        # 출시 글은 /claude-opus-5-5 처럼 루트에, 일반 기사는 /news/... 에 있다. 페이지 안 링크로 판단
        path = f"/{slug}" if f'"/{slug}"' in text and f'/news/{slug}"' not in text else f"/news/{slug}"
        url = a["base"] + path
        summary = f"{cats} · {date} 발표" + (f" — {o['summary']}" if o.get("summary") else "")
        items.append(make_item(f"link:{url}", f"[{a['label']}] {o['title'].strip()}", url, summary,
                               official=True, kind="official", source=a["name"], published_at=date))
    return items, len(items), f"전체 {len(arts)}개 중 최근 {cfg['lookback_days']}일·대상 분류 {len(items)}개"


FEED_ENTRY_RE = re.compile(r"<(item|entry)\b.*?</\1>", re.S)


def _feed_field(block: str, *tags: str) -> str:
    for tag in tags:
        m = re.search(rf"<{tag}\b[^>]*>(?:\s*<!\[CDATA\[)?(.*?)(?:\]\]>\s*)?</{tag}>", block, re.S)
        if m and m.group(1).strip():
            return html.unescape(m.group(1).strip())
    return ""


def collect_feed(f: Fetcher, cfg: dict, now: datetime, fd: dict):
    """업계(경쟁사 포함) 공식 블로그 RSS/Atom. 제목이 '대형 발표' 패턴에 맞는 최근 글만 남긴다 (사례·정책·채용 글 제외)."""
    text = f.get(f"feed::{fd['name']}", fd["url"], text=True)
    blocks = [m.group(0) for m in FEED_ENTRY_RE.finditer(text)]
    if not blocks:
        raise RuntimeError("글 0개 — 피드 주소나 형식 변경 의심")
    patterns = cfg["value_rules"]["major"]["patterns"]
    since = now - timedelta(days=cfg["lookback_days"])
    items = []
    for b in blocks:
        title = _feed_field(b, "title")
        link = _feed_field(b, "link") or (re.search(r'<link\b[^>]*href="([^"]+)"', b) or [None, ""])[1]
        published = parse_feed_date(_feed_field(b, "pubDate", "published", "updated"))
        if not title or not link or (published and published < since):
            continue
        if not any(_rx(p).search(title) for p in patterns):
            continue
        summary = one_line(re.sub(r"<[^>]+>", " ", _feed_field(b, "description", "summary")), 200)
        items.append(make_item(f"feed:{link}", f"[{fd['label']}] {title}", link, summary, kind="industry",
                               source=fd["name"], published_at=published.isoformat() if published else None))
    return items, len(items), f"글 {len(blocks)}개 중 대형 발표 패턴 {len(items)}개"


def fold_launch_coverage(items: dict[str, dict]) -> None:
    """새 제품 페이지와 같은 제품을 다룬 HN·업계·공식 글은 제품 항목 하나로 합친다 (한 소식이 핵심 3줄 두 칸을 먹지 않게)."""
    products = {k: it["title"].rsplit(": ", 1)[-1].lower() for k, it in items.items() if "claude_products" in it["sources"]}
    for pid, name in products.items():
        if len(name) < 4:  # 'tag' 같은 짧은 이름은 엉뚱한 글에 걸린다
            continue
        prod = items[pid]
        for oid in [k for k, o in items.items()
                    if k != pid and o["kind"] in ("community", "industry", "official") and name in o["title"].lower()]:
            o = items.pop(oid)
            prod["mentions"] += o.get("mentions", 0)
            prod["sources"] = sorted(set(prod["sources"]) | set(o["sources"]))
            prod["text"] += " " + o["text"]
            prod["summary"] += f" / 관련 보도: {o['title']} ({o['url']})"
            prod["published_at"] = prod.get("published_at") or o.get("published_at")


def page_text(raw: str, limit: int) -> str:
    """HTML에서 설명(meta description)과 본문 글자만 뽑는다. 블로그 에이전트가 사실 소스로 쓴다."""
    meta = re.search(r'<meta[^>]+(?:name|property)="(?:og:)?description"[^>]+content="([^"]*)"', raw)
    body = re.sub(r"<(script|style|noscript|svg|nav|footer|header)\b.*?</\1>", " ", raw, flags=re.S | re.I)
    body = html.unescape(re.sub(r"<[^>]+>", " ", body))
    text = (html.unescape(meta.group(1)) + " / " if meta else "") + body
    return one_line(text, limit)


def major_name(it: dict) -> str | None:
    """국내 기사 검색어로 쓸 제품·모델 이름. 'Introducing GPT-6 Example' → 'GPT-6 Example'. 문장형 제목이면 None."""
    name = re.sub(r"^\[[^\]]*\]\s*", "", it["title"])
    name = re.sub(r"^(새 페이지:|introducing|announcing)\s*", "", name, flags=re.I)
    name = re.split(r"[:,—–(]| - ", name)[0].strip()
    return name if name and len(name.split()) <= 4 else None


def enrich_majors(f: Fetcher, cfg: dict, top: list[dict]):
    """상위 목록의 대형 발표에 ① 원문 발췌(detail) ② 최근 7일 국내 기사 수(kr_news)를 붙인다.
    ①은 블로그가 '공식 페이지에서 확인하세요'로만 채워지지 않게, ②는 '경쟁 계정들이 다 같이 다루는 소식'을 재는 신호."""
    mj = cfg["value_rules"]["major"]
    majors = [t for t in top if t.get("major")][: mj.get("detail_max", 3)]
    notes, ok = [], 0
    for it in majors:
        try:
            raw = f.get(f"detail::{it['url']}", it["url"], text=True)
            it["detail"] = page_text(raw, mj.get("detail_chars", 1500))
            ok += 1
        except Exception as e:
            notes.append(f"원문 실패({one_line(it['title'], 30)}): {type(e).__name__}")
        name = major_name(it)
        if not name:
            continue
        try:
            rss = f.get(f"krnews::{name}", mj["kr_news_url"], {"q": f'"{name}" when:7d', "hl": "ko", "gl": "KR", "ceid": "KR:ko"},
                        text=True)
            n = len(FEED_ENTRY_RE.findall(rss))
            it["kr_news"] = n
            bonus = min(mj.get("kr_news_bonus_max", 20), n)
            if bonus:
                it["score"] = round(it["score"] + bonus, 1)
                it["importance"] = round(it["importance"] + bonus, 1)
                it["reasons"].append(f"국내 기사 {n}건/7일 +{bonus}")
        except Exception as e:
            notes.append(f"국내 기사 실패({name}): {type(e).__name__}")
    if majors and not ok and notes:
        raise RuntimeError("; ".join(notes))
    top.sort(key=lambda i: (i["major"], i["score"]), reverse=True)  # 국내 반응 큰 대형 발표가 먼저
    return None, ok, "; ".join(notes) or f"대형 발표 {len(majors)}개"


def parse_feed_date(s: str) -> datetime | None:
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        d = parse_dt(s)
    if d and d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


# ─── 수집기: GitHub 검색 ──────────────────────────────────────────────────────

def collect_github(f: Fetcher, cfg: dict, now: datetime):
    gs = cfg["github_search"]
    since = (now - timedelta(days=cfg["new_repo_days"])).strftime("%Y-%m-%d")
    week = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    owners = {o.lower() for o in cfg["official"].get("owners", ["anthropics"])}
    items, failed = [], []
    for q in gs["queries"]:
        try:
            data = f.gh(f"search::{q}", "/search/repositories",
                        {"q": q.format(since=since, week=week), "sort": "stars", "order": "desc",
                         "per_page": gs["per_page"]})
        except Exception as e:
            failed.append(f"{q} ({type(e).__name__})")
            continue
        finally:
            f.pause(2.5)  # 검색 API는 분당 30회 제한
        for it in data.get("items", []):
            if it.get("stargazers_count", 0) < cfg["min_stars_search"]:
                continue
            owner = it["full_name"].split("/")[0].lower()
            items.append(make_item(
                f"gh:{it['full_name'].lower()}", it["full_name"], it["html_url"], it.get("description") or "",
                official=owner in owners, source="github_search", stars=it["stargazers_count"],
                created_at=it.get("created_at"), text=" ".join(it.get("topics") or []),
            ))
    if failed and len(failed) == len(gs["queries"]):
        raise RuntimeError("모든 검색 쿼리 실패: " + "; ".join(failed[:3]))
    note = f"쿼리 {len(failed)}개 실패: " + "; ".join(failed) if failed else f"쿼리 {len(gs['queries'])}개"
    return items, len(items), note


# ─── 수집기: 커뮤니티 ─────────────────────────────────────────────────────────

def collect_hn(f: Fetcher, cfg: dict, now: datetime, counts: dict):
    cm = cfg["community"]
    since = int((now - timedelta(days=7)).timestamp())
    major_min = cm.get("hn_major_min_points", 10**9)
    # 업계 키워드(openai, gemini 등)는 하루에도 글이 많아서 아주 화제가 된 글(major_min 이상)만 본다
    queries = [(kw, cm["hn_min_points"]) for kw in cm["hn_keywords"]]
    queries += [(kw, major_min) for kw in cm.get("hn_major_keywords", []) if kw not in cm["hn_keywords"]]
    items = []
    for kw, min_points in queries:
        data = f.get(f"hn::{kw}", "https://hn.algolia.com/api/v1/search_by_date",
                     {"query": kw, "tags": "story", "numericFilters": f"created_at_i>{since}", "hitsPerPage": 100})
        hits = data.get("hits", [])
        counts[f"hn::{kw}"] = int(data.get("nbHits", len(hits)))
        for h in hits:
            points = int(h.get("points") or 0)
            if points < min_points:
                continue
            disc = f"https://news.ycombinator.com/item?id={h.get('objectID')}"
            url = h.get("url") or disc
            mentions = points + int(h.get("num_comments") or 0)
            source = "hackernews_major" if points >= major_min else "hackernews"
            rid = gh_repo_id(url)
            if rid:
                items.append(make_item(rid, rid[3:], url, h.get("title", ""), source=source, mentions=mentions))
            else:
                items.append(make_item(f"hn:{h.get('objectID')}", h.get("title", ""), url, f"HN 토론: {disc}",
                                       kind="community", source=source, mentions=mentions,
                                       published_at=h.get("created_at")))
    return items, len(items), f"키워드 {len(queries)}개"


def collect_reddit(f: Fetcher, cfg: dict, counts: dict):
    cm = cfg["community"]
    kws = list(dict.fromkeys(cm["hn_keywords"] + cfg["watchlist"]["keywords"]))
    items = []
    for sub in cm["reddit_subs"]:
        data = f.get(f"reddit::{sub}", f"https://www.reddit.com/r/{sub}/top.json", {"t": "week", "limit": 50})
        posts = [c["data"] for c in data.get("data", {}).get("children", [])]
        for kw in kws:
            n = sum(1 for p in posts if kw.lower() in (p.get("title", "") + " " + p.get("selftext", "")).lower())
            counts[f"reddit::{kw}"] = counts.get(f"reddit::{kw}", 0) + n
        for p in posts:
            score = int(p.get("score") or 0)
            if score < cm["reddit_min_score"]:
                continue
            permalink = "https://www.reddit.com" + p.get("permalink", "")
            url = p.get("url_overridden_by_dest") or permalink
            mentions = score + int(p.get("num_comments") or 0)
            rid = gh_repo_id(url)
            if rid:
                items.append(make_item(rid, rid[3:], url, p.get("title", ""), source="reddit", mentions=mentions))
            else:
                items.append(make_item(f"reddit:{p.get('id')}", p.get("title", ""), permalink,
                                       one_line(p.get("selftext", ""), 200), kind="community",
                                       source=f"reddit/r/{sub}", mentions=mentions))
    return items, len(items), f"서브레딧 {len(cm['reddit_subs'])}개"


# ─── 분류·점수·중복 제거 ─────────────────────────────────────────────────────

def kw_match(kw: str, text: str) -> bool:
    kw = kw.lower()
    if not kw.isascii():
        return kw in text
    tail = r"(?![a-z0-9])" if len(kw) <= 3 else ""
    return re.search(rf"(?<![a-z0-9]){re.escape(kw)}{tail}", text) is not None


def categorize(item: dict, cats: dict) -> list[str]:
    text = item["text"].lower()
    found = [c for c, kws in cats.items() if any(kw_match(k, text) for k in kws)]
    return found or ["기타"]


# ─── 글감 가치 판정 (규칙 기반, LLM 호출 없음) ───────────────────────────────
# 2026-10-14 테스트 실행에서 핵심 3줄이 전부 사소한 릴리스(확인창 "2 of 5" 표시 등)였고, 감시 키워드에 걸린
# 영상·문서 소식은 "리포트 미반영"으로 밀렸다. 공식 +35점이 내용과 무관하게 붙었기 때문이다. 이제 내용 자체가
# 글감급(value >= min_value)이어야 후보가 된다. 패턴·가중치·임계값은 전부 config.json value_rules에 있다.

_RX_CACHE: dict[str, re.Pattern] = {}


def _rx(pat: str) -> re.Pattern:
    if pat not in _RX_CACHE:
        _RX_CACHE[pat] = re.compile(pat, re.I | re.M)
    return _RX_CACHE[pat]


def pattern_value(text: str, kind: str, vr: dict) -> tuple[float, list[str]]:
    """positive/negative 그룹별로 패턴이 하나라도 맞으면 weight를 한 번 더한다."""
    total, reasons = 0.0, []
    for group in vr.get("positive", []) + vr.get("negative", []):
        kinds = group.get("applies_to")
        if kinds and kind not in kinds:
            continue
        if any(_rx(p).search(text) for p in group["patterns"]):
            total += group["weight"]
            reasons.append(f"{group['name']} {group['weight']:+g}")
    return total, reasons


def watch_bonus(text_lower: str, cfg: dict) -> tuple[float, list[str]]:
    w = cfg["watchlist"]
    hits = [kw for kw in w["keywords"] if kw_match(kw, text_lower)]
    if not hits:
        return 0.0, []
    by_kw = w.get("promote_bonus_by_keyword", {})
    return max(by_kw.get(kw, w.get("promote_bonus", 0)) for kw in hits), hits


def judge_value(it: dict, cfg: dict) -> None:
    """it에 value / value_reasons / story_grade / needs_check / watch_hits 를 채운다."""
    vr = cfg["value_rules"]
    pop = vr.get("popularity", {})
    text = it["summary"] if it["kind"] == "release_line" else it["text"]
    value, reasons = pattern_value(text, it["kind"], vr)

    for src in it["sources"]:
        b = vr.get("source_bonus", {}).get(src, 0)
        if b:
            value += b; reasons.append(f"출처({src}) +{b}")
            break

    # 대형 발표: 새 제품·새 모델 출시처럼 경쟁 계정들이 다 같이 다루는 소식. 순위에서 GitHub 레포보다 항상 위에 둔다(select_top).
    mj = vr.get("major", {})
    it["major"] = any(
        s in mj.get("sources", []) and (s not in mj.get("pattern_required_sources", [])
                                        or any(_rx(p).search(it["title"]) for p in mj.get("patterns", [])))
        for s in it["sources"])
    if it["major"]:
        value += mj.get("bonus", 0); reasons.append(f"대형 발표 +{mj.get('bonus', 0)}")

    delta, mentions = it.get("star_delta_7d") or 0, it.get("mentions") or 0
    if delta >= pop.get("star_delta_big", 10**9):
        value += pop["star_delta_big_bonus"]; reasons.append(f"스타 급증 +{pop['star_delta_big_bonus']}")
    elif delta >= pop.get("star_delta_mid", 10**9):
        value += pop["star_delta_mid_bonus"]; reasons.append(f"스타 증가 +{pop['star_delta_mid_bonus']}")
    if mentions >= pop.get("mentions_big", 10**9):
        value += pop["mentions_big_bonus"]; reasons.append(f"언급 많음 +{pop['mentions_big_bonus']}")
    if (it.get("stars") or 0) >= pop.get("stars_total_big", 10**9):  # 이미 유명한 도구 (기준선 실행처럼 증가량을 모를 때도 반영)
        value += pop["stars_total_big_bonus"]; reasons.append(f"유명(스타 {it['stars']:,}) +{pop['stars_total_big_bonus']}")

    bonus, hits = watch_bonus(it["text"].lower(), cfg)
    if bonus:
        value += bonus; reasons.append(f"감시 키워드({', '.join(hits)}) +{bonus:g}")

    # 공식이 아닌 항목은 인지도(스타·증가·언급) 최소선을 넘어야 글감급. 감시 키워드 항목은 통과시키되 '확인 필요'.
    mins = pop.get("unofficial_min", {})
    popular = it["official"] or it["major"] or (
        (it.get("stars") or 0) >= mins.get("stars", 0)
        or delta >= mins.get("star_delta_7d", 0)
        or mentions >= mins.get("mentions", 0)
    )
    weak_summary = len((it.get("summary") or "").strip()) < cfg["watchlist"].get("weak_evidence_min_summary", 0)
    grade = value >= vr["min_value"]
    needs_check = False
    if grade and not popular:
        if hits:
            # 후보에는 올리되(승격) 순위는 인지도 있는 항목보다 아래로
            pen = cfg["watchlist"].get("weak_evidence_penalty", 0)
            value += pen
            needs_check = True; reasons.append(f"인지도 낮음(감시 키워드로 승격, 확인 필요) {pen:+g}")
        else:
            grade = False; reasons.append("인지도 미달(공식 아님·스타/언급 적음)")
    if grade and hits and weak_summary:
        needs_check = True; reasons.append("설명 부족(확인 필요)")

    it["value"], it["value_reasons"] = round(value, 1), reasons
    it["story_grade"], it["needs_check"], it["watch_hits"] = grade, needs_check, hits


BULLET_RE = re.compile(r"^(\s*)[-*+]\s+(.*)$")


def release_lines(body: str) -> list[str]:
    """릴리스/CHANGELOG 본문 → bullet 한 줄씩. 들여쓴 이어지는 줄은 앞 bullet에 붙인다. 제목(##)은 버린다."""
    out: list[str] = []
    for raw in (body or "").splitlines():
        m = BULLET_RE.match(raw)
        if m:
            out.append(m.group(2).strip())
        elif out and raw.strip() and not raw.lstrip().startswith("#") and raw.startswith((" ", "\t")):
            out[-1] += " " + raw.strip()
    return [ln for ln in out if ln]


def _norm_line(s: str) -> str:
    s = re.sub(r"\(예시\)\s*", "", s.lower())
    return re.sub(r"[^a-z0-9가-힣$.%/]+", " ", s).strip()


def bundle_releases(items: dict[str, dict], cfg: dict) -> dict:
    """버전별 릴리스·CHANGELOG 항목을 items에서 빼고, 줄 단위로 판정해 글감급 줄만 다시 넣는다.
    반환: 리포트·latest-top.json에 넣을 릴리스 묶음 요약."""
    rb, vr = cfg["value_rules"].get("release_bundle", {}), cfg["value_rules"]
    rel = [k for k, v in items.items() if k.startswith(("release:", "changelog:"))]
    if not rel:
        return {"versions": [], "lines_total": 0, "lines_good": 0, "lines_minor": 0, "text": ""}
    pool: dict[str, dict] = {}
    versions: list[str] = []
    for k in rel:
        it = items.pop(k)
        ver = k.rsplit("@", 1)[-1].lstrip("v")
        if ver not in versions:
            versions.append(ver)
        for ln in release_lines(it.get("body") or ""):
            key = _norm_line(ln)
            if not key:
                continue
            rec = pool.setdefault(key, {"line": ln, "versions": [], "url": it["url"], "published_at": it.get("published_at"),
                                        "sources": set(), "repo": k.split(":", 1)[1].rsplit("@", 1)[0]})
            if ver not in rec["versions"]:
                rec["versions"].append(ver)
            rec["sources"] |= set(it["sources"])
            if it["sources"] == ["releases"]:  # 버전별 릴리스 링크·발표일을 CHANGELOG보다 우선
                rec["url"], rec["published_at"] = it["url"], it.get("published_at") or rec["published_at"]
    judged = []
    for rec in pool.values():
        v, reasons = pattern_value(rec["line"], "release_line", vr)
        judged.append((v, reasons, rec))
    good = sorted((j for j in judged if j[0] >= vr["min_value"]), key=lambda j: j[0], reverse=True)
    picked = good[: rb.get("max_candidates", 3)]
    for v, reasons, rec in picked:
        key = _norm_line(rec["line"])
        vers = ", ".join(sorted(rec["versions"], key=_ver_key))
        short = one_line(re.sub(r"^\(예시\)\s*", "", rec["line"]), 80)
        it = make_item(
            f"relline:{rec['repo'].lower()}:{hashlib.sha1(key.encode()).hexdigest()[:12]}",
            f"Claude Code 업데이트({vers}): {short}",
            rec["url"], rec["line"], official=True, kind="release_line", published_at=rec["published_at"],
        )
        it["sources"] = sorted(rec["sources"])
        it["versions"] = sorted(rec["versions"], key=_ver_key)
        items[it["id"]] = it
    vs = sorted(versions, key=_ver_key)
    span = (f"v{vs[0]}" if len(vs) == 1 else f"v{vs[0]}~v{vs[-1]}") + f", {len(vs)}개"
    minor = len(judged) - len(good)
    if good:
        text = (f"이번 주 릴리스({span}): 글감급 변경 {len(good)}건(후보 {len(picked)}건 올림), 사소한 개선 {minor}건")
    else:
        text = f"이번 주 릴리스({span}): 글감급 변경 없음(사소한 개선 {minor}건)"
    return {"versions": vs, "lines_total": len(judged), "lines_good": len(good), "lines_minor": minor, "text": text,
            "good_lines": [{"line": r["line"], "value": v, "reasons": rs} for v, rs, r in good]}


def _ver_key(v: str):
    return [(0, int(x), "") if x.isdigit() else (1, 0, x) for x in re.split(r"[.\-]", v)]


def star_delta_7d(item: dict, prev: dict | None, now: datetime, cfg: dict) -> tuple[int, bool]:
    """(7일 스타 증가량, 추정치 여부). 이력이 없으면 신규 레포만 생성일 기준으로 추정한다."""
    stars = item.get("stars")
    if stars is None:
        return 0, False
    hist = (prev or {}).get("stars_hist") or []
    if hist:
        target = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        older = [h for h in hist if h[0] <= target]
        base = older[-1][1] if older else hist[0][1]
        return max(0, stars - base), False
    created = parse_dt(item.get("created_at"))
    if created and (now - created).days <= cfg["new_repo_days"]:
        age = max(1.0, (now - created).total_seconds() / 86400)
        return int(stars / age * min(7, age)), True
    return 0, False


def log_scale(x: float, ref: float, cap: float) -> float:
    return 0.0 if x <= 0 else cap * min(1.0, math.log10(1 + x) / math.log10(1 + ref))


def evaluate(items: dict[str, dict], state: dict, cfg: dict, now: datetime, baseline: bool) -> list[dict]:
    sc, today = cfg["scoring"], now.strftime("%Y-%m-%d")
    known = state.setdefault("items", {})
    out = []
    for it in items.values():
        prev = known.get(it["id"])
        it["categories"] = categorize(it, cfg["categories"])
        it["first_seen"] = (prev or {}).get("first_seen", today)
        delta, est = star_delta_7d(it, prev, now, cfg)
        it["star_delta_7d"], it["star_delta_estimated"] = delta, est

        created = parse_dt(it.get("created_at"))
        is_new_repo = bool(created and (now - created).days <= cfg["new_repo_days"])
        is_new = prev is None and (not baseline or it["official"] or is_new_repo or it["kind"] == "community")
        reported = (prev or {}).get("reported") or []
        resurfaced = False
        if reported:
            ls, lm = prev.get("last_reported_stars") or 0, prev.get("last_reported_mentions") or 0
            sd = (it.get("stars") or 0) - ls
            if it.get("stars") is not None and sd >= max(sc["resurface_min_star_delta"], sc["resurface_star_ratio"] * ls):
                resurfaced = True
            if it["mentions"] >= 50 and it["mentions"] >= sc["resurface_mentions_ratio"] * max(lm, 1):
                resurfaced = True

        # 소식으로 볼 만한가: 공식 / 최근 생성 / 급상승 / 커뮤니티 화제 중 하나
        newsworthy = (it["official"] or is_new_repo or delta >= sc["resurface_min_star_delta"]
                      or it["mentions"] > 0 or it["kind"] in ("community", "industry"))
        it["eligible"] = newsworthy and (not reported or resurfaced)
        it["is_new"], it["resurfaced"] = is_new, resurfaced

        reasons, score = [], 0.0
        if it["official"]:
            score += sc["official"]; reasons.append(f"공식 +{sc['official']}")
        g = log_scale(delta, sc["star_growth_ref"], sc["star_growth_max"])
        if g:
            score += g; reasons.append(f"스타 +{delta:,}/7일{'(추정)' if est else ''} +{g:.0f}")
        mscore = log_scale(it["mentions"], sc["mentions_ref"], sc["mentions_max"])
        if mscore:
            score += mscore; reasons.append(f"언급 {it['mentions']:,} +{mscore:.0f}")
        impact = max((sc["impact_by_category"].get(c, 0) for c in it["categories"]), default=0)
        if impact:
            score += impact; reasons.append(f"일반 사용자 영향({'/'.join(it['categories'])}) +{impact}")
        if is_new:
            score += sc["novelty"]; reasons.append(f"신규 +{sc['novelty']}")
        if resurfaced:
            score += sc["resurfaced"]; reasons.append(f"재부상 +{sc['resurfaced']}")
        # 글감 가치(value)를 더한 값이 최종 순위 점수. value 미달이면 아예 후보에서 빠진다(select_top).
        judge_value(it, cfg)
        it["importance"] = round(score, 1)
        it["score"], it["reasons"] = round(score + it["value"], 1), reasons
        out.append(it)
    return out


def select_top(evaluated: list[dict], cfg: dict) -> tuple[list[dict], list[dict]]:
    """(상위 목록, 글감 미달로 뺀 항목). 상위 목록은 eligible(새 소식) 이면서 글감급인 것만."""
    fresh = [i for i in evaluated if i["eligible"]]
    # 대형 발표가 있으면 점수와 무관하게 먼저 (스타 많은 GitHub 레포가 신제품 출시를 이기던 문제)
    top = sorted((i for i in fresh if i["story_grade"]), key=lambda i: (i["major"], i["score"]), reverse=True)[: cfg["top_n"]]
    dropped = sorted((i for i in fresh if not i["story_grade"]), key=lambda i: i["importance"], reverse=True)
    return top, dropped


def pick_headline(top: list[dict], cfg: dict, n: int = 3) -> list[dict]:
    """핵심 3줄. 릴리스 줄은 max_in_headline 칸까지만 (공식 릴리스가 3줄을 독식하던 문제 방지)."""
    cap = cfg["value_rules"].get("release_bundle", {}).get("max_in_headline", n)
    out, held, rel = [], [], 0
    for t in top:
        if t["kind"] == "release_line":
            if rel >= cap:
                held.append(t)
                continue
            rel += 1
        out.append(t)
        if len(out) == n:
            return out
    # 다른 글감이 모자라면 남은 칸은 릴리스 줄로 채운다 (글감급인데 칸이 비는 것보다 낫다)
    return sorted(out + held[: n - len(out)], key=top.index)


def update_state(state: dict, items: list[dict], top: list[dict], now: datetime):
    today = now.strftime("%Y-%m-%d")
    known = state.setdefault("items", {})
    top_ids = {t["id"] for t in top}
    for it in items:
        rec = known.setdefault(it["id"], {"first_seen": it["first_seen"]})
        rec.update({"title": it["title"], "url": it["url"], "last_seen": today, "categories": it["categories"],
                    "kw_text": one_line(it["title"] + " " + it["summary"], 240)})
        if it.get("stars") is not None:
            hist = [h for h in rec.get("stars_hist", []) if h[0] != today] + [[today, it["stars"]]]
            rec["stars_hist"] = hist[-60:]
        if it["id"] in top_ids:
            rec.setdefault("reported", []).append(today)
            rec["last_reported_stars"] = it.get("stars") or 0
            rec["last_reported_mentions"] = it["mentions"]
    cutoff = (now - timedelta(days=120)).strftime("%Y-%m-%d")
    for k in [k for k, v in known.items() if v.get("last_seen", today) < cutoff]:
        del known[k]


def keyword_surges(counts: dict, state: dict, cfg: dict) -> list[dict]:
    cm, hist = cfg["community"], state.setdefault("keyword_counts", {})
    surges = []
    for key, n in counts.items():
        prev = hist.get(key, [])
        avg = sum(prev) / len(prev) if prev else 0
        if prev and n >= cm["surge_min_count"] and n >= cm["surge_ratio"] * max(avg, 1):
            surges.append({"key": key, "count": n, "avg": round(avg, 1)})
        hist[key] = (prev + [n])[-8:]
    return surges


# ─── 주간 키워드 감시 리스트 ─────────────────────────────────────────────────

def watchlist_fetch(f: Fetcher, cfg: dict, now: datetime, counts: dict):
    """감시 키워드별 바깥 반응 조회. 검색에 나온 레포는 후보 풀에 넣을 항목으로도 돌려준다(감시 키워드 승격).
    반환: (rows, failed, extra_items)"""
    week = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    since = int((now - timedelta(days=7)).timestamp())
    owners = {o.lower() for o in cfg["official"].get("owners", ["anthropics"])}
    rows, failed, extra = [], [], []
    for kw in cfg["watchlist"]["keywords"]:
        row = {"kw": kw, "gh": None, "gh_top": [], "hn": None, "reddit": counts.get(f"reddit::{kw}")}
        try:
            d = f.gh(f"watch_gh::{kw}", "/search/repositories",
                     {"q": f'"{kw}" claude pushed:>{week}', "sort": "stars", "order": "desc", "per_page": 3})
            row["gh"] = int(d.get("total_count", 0))
            row["gh_top"] = [i["full_name"] for i in d.get("items", [])[:3]]
            for i in d.get("items", [])[:3]:
                if not i.get("html_url") or (i.get("stargazers_count") or 0) < cfg["min_stars_search"]:
                    continue
                extra.append(make_item(
                    f"gh:{i['full_name'].lower()}", i["full_name"], i["html_url"], i.get("description") or "",
                    official=i["full_name"].split("/")[0].lower() in owners, source="watchlist",
                    stars=i["stargazers_count"], created_at=i.get("created_at"), text=" ".join(i.get("topics") or []),
                ))
        except Exception as e:
            failed.append(f"GitHub '{kw}' ({type(e).__name__})")
        finally:
            f.pause(2.5)
        try:
            d = f.get(f"watch_hn::{kw}", "https://hn.algolia.com/api/v1/search_by_date",
                      {"query": f"{kw} claude", "tags": "story", "numericFilters": f"created_at_i>{since}",
                       "hitsPerPage": 1})
            row["hn"] = int(d.get("nbHits", 0))
        except Exception as e:
            failed.append(f"HN '{kw}' ({type(e).__name__})")
        rows.append(row)
    return rows, failed, extra


def watchlist_finalize(rows: list[dict], state: dict, top: list[dict], now: datetime) -> None:
    """상위 목록이 정해진 뒤 반영 여부·경고를 채운다. update_state() 전에 불러야 '이번 실행'이 반영으로 안 잡힌다."""
    week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    for row in rows:
        kw = row["kw"]
        row["in_top"] = any(kw_match(kw, t["text"].lower()) for t in top)
        row["recent_reported"] = any(
            kw_match(kw, (v.get("kw_text") or "").lower()) and any(d >= week_ago for d in v.get("reported", []))
            for v in state.get("items", {}).values()
        )
        signal = (row["gh"] or 0) >= 5 or (row["hn"] or 0) >= 3 or (row["reddit"] or 0) >= 3
        row["warn"] = signal and not row["in_top"] and not row["recent_reported"]


# ─── 리포트 ───────────────────────────────────────────────────────────────────

def headline(it: dict) -> str:
    tag = "/".join(it["categories"])
    flag = ("🔥대형 발표 " if it.get("major") else "") + ("공식 " if it["official"] else "")
    check = " (확인 필요)" if it.get("needs_check") else ""
    if it["kind"] == "release_line":  # 제목에 이미 줄 내용이 들어 있다
        return f"[{tag}] {flag}{it['title']}{check}"
    return f"[{tag}] {flag}{it['title']}{check} — {one_line(it['summary'], 90) or '설명 없음'}"


def build_report(today: str, cfg: dict, run: Run, top: list[dict], all_items: list[dict], surges: list[dict],
                 watch: tuple | None, baseline: bool, heads: list[dict] | None = None,
                 bundle: dict | None = None, dropped: list[dict] | None = None) -> str:
    heads = top[:3] if heads is None else heads
    L = [f"# Claude Code·AI 도구 소식 모니터 ({today})", "",
         f"> 공식 발표 · 업계(OpenAI·Google) 발표 · GitHub 신규/급상승 · 커뮤니티(HN/Reddit)를 모아 글감 가치 판정을 통과한 것만 상위 {cfg['top_n']}개 싣는다. "
         "🔥대형 발표(새 제품·새 모델 출시)는 점수와 무관하게 맨 위, 나머지는 점수순. "
         "릴리스 노트는 이번 주기분을 묶어 줄 단위로 판정한다. 이미 다룬 소식은 반응이 급증한 경우(재부상)만 다시 싣는다.", ""]
    if baseline:
        L += ["> ℹ️ 첫 실행(기준선 저장). 공식 목록·문서 링크는 이번엔 기준만 저장하고 다음 실행부터 '새 항목'을 잡는다.", ""]

    L += ["## 오늘의 핵심 3줄", ""]
    if heads:
        L += [f"{i}. {headline(t)}" for i, t in enumerate(heads, 1)]
    else:
        L.append(f"이번 주는 글감급 소식이 없습니다 (이미 다룬 항목 제외, 글감 최소 점수 {cfg['value_rules']['min_value']}).")
    L.append("")
    if bundle and bundle.get("text"):
        L += [f"> {bundle['text']}", ""]

    if run.failures:
        L += ["## ⚠️ 수집 실패", "", "아래 소스는 이번에 수집하지 못했다. **이 소스에서 나온 소식은 이번 리포트에 빠져 있을 수 있다.**", ""]
        L += [f"- **{s['label']}** — {s['note']}" for s in run.failures]
        L.append("")
    partial = [s for s in run.statuses if s["ok"] and "실패" in (s["note"] or "")]
    if partial:
        L += ["> 일부 실패: " + " / ".join(f"{s['label']}: {s['note']}" for s in partial), ""]

    L += [f"## 상위 {len(top)}개 (글감급만, 점수 = 중요도 + 글감 가치)", "",
          "| # | 점수 | 카테고리 | 소식 | 처음 등장 | 출처 |", "|---|---|---|---|---|---|"]
    for i, t in enumerate(top, 1):
        mark = " 🔁재부상" if t["resurfaced"] else (" 🆕" if t["is_new"] else "")
        mark += " ⚠️확인 필요" if t.get("needs_check") else ""
        L.append(f"| {i} | {t['score']:.0f} | {'/'.join(t['categories'])} | [{t['title']}]({t['url']}){mark} "
                 f"| {t['first_seen']} | {', '.join(t['sources'])} |")
    L.append("")
    for i, t in enumerate(top, 1):
        L += [f"### {i}. {t['title']}", "",
              f"- 링크: {t['url']}",
              f"- 내용: {one_line(t['summary'], 300) or '설명 없음'}"]
        if t.get("stars") is not None:
            L.append(f"- 스타: {t['stars']:,}")
        if t.get("published_at"):
            L.append(f"- 발표일(소스 기준): {t['published_at'][:10]}")
        if t.get("kr_news") is not None:
            L.append(f"- 국내 기사(최근 7일): {t['kr_news']}건")
        if t.get("detail"):
            L.append(f"- 원문 발췌: {one_line(t['detail'], 200)}")
        L += [f"- 점수 근거: 중요도 {t['importance']:.0f} ({', '.join(t['reasons']) or '없음'})",
              f"- 글감 판정: {t['value']:+.0f} ({', '.join(t['value_reasons']) or '없음'})", ""]

    if dropped:
        L += ["## 글감 미달로 뺀 항목 (참고, 중요도순 상위 5)", "",
              f"새 소식이지만 글감 가치가 최소 점수({cfg['value_rules']['min_value']}) 미만이라 후보에서 뺐다. "
              "기준 조정은 config.json `value_rules`.", ""]
        L += [f"- {one_line(t['title'], 80)} — 글감 {t['value']:+.0f} ({', '.join(t['value_reasons']) or '해당 규칙 없음'})"
              for t in dropped[:5]]
        L.append("")

    if surges:
        L += ["## 커뮤니티 키워드 급증", "", "| 소스::키워드 | 이번 | 직전 평균 |", "|---|---|---|"]
        L += [f"| {s['key']} | {s['count']} | {s['avg']} |" for s in surges]
        L.append("")

    if watch is not None:
        rows, failed = watch
        L += ["## 주간 키워드 감시 리스트 점검", "",
              "큰 소식이 점수 체계에서 빠지는 것을 막는 안전장치. 키워드에 걸린 항목은 후보 풀에 올려 가산점을 준다. "
              "그래도 바깥 반응이 있는데 최근 7일 리포트에 없으면 ⚠️.", "",
              "| 키워드 | GitHub(7일 활동, claude 포함) | HN(7일) | Reddit(주간 상위) | 최근 리포트 반영 | 상위 레포 |",
              "|---|---|---|---|---|---|"]
        for r in rows:
            fmt = lambda v: "실패" if v is None else str(v)  # noqa: E731
            done = "예" if (r["in_top"] or r["recent_reported"]) else ("⚠️ 아니오" if r["warn"] else "아니오")
            L.append(f"| {r['kw']} | {fmt(r['gh'])} | {fmt(r['hn'])} | {fmt(r['reddit'])} | {done} | "
                     f"{', '.join(r['gh_top']) or '-'} |")
        if failed:
            L += ["", "감시 리스트 일부 조회 실패: " + "; ".join(failed)]
        L.append("")

    L += ["## 수집 상태", "", "| 소스 | 결과 | 건수 | 비고 |", "|---|---|---|---|"]
    L += [f"| {s['label']} | {'성공' if s['ok'] else '❌ 실패'} | {s['count']} | {s['note'] or ''} |" for s in run.statuses]
    held = len(all_items) - len(top)
    L += ["", f"*추적 중이지만 이번에 싣지 않은 항목 {held}개 (이미 다룸·변화 없음·점수 미달). "
              f"생성: {today} | projects/claude-code-monitor/monitor.py*"]
    return "\n".join(L) + "\n"


# ─── 메인 ─────────────────────────────────────────────────────────────────────

def load_fixtures(path: Path) -> dict:
    """"__extends__": "다른.json" 이 있으면 그 파일을 먼저 읽고 덮어쓴다 (케이스 fixture를 짧게 유지)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    base = data.pop("__extends__", None)
    if base:
        merged = load_fixtures(path.parent / base)
        merged.update(data)
        return merged
    return data


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Claude Code·AI 도구 소식 모니터")
    ap.add_argument("--dry-run", action="store_true", help="파일을 쓰지 않고 리포트를 화면에 출력")
    ap.add_argument("--fixtures", type=Path, help="가짜 응답 JSON (네트워크 호출 없음)")
    ap.add_argument("--watchlist", action="store_true", help="요일과 무관하게 주간 감시 리스트 점검")
    ap.add_argument("--state", type=Path, default=STATE_PATH)
    ap.add_argument("--config", type=Path, default=CONFIG_PATH)
    ap.add_argument("--dump", type=Path, help="--dry-run 결과(리포트·latest-top.json)를 이 폴더에 저장")
    args = ap.parse_args(argv)

    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    fixtures = load_fixtures(args.fixtures) if args.fixtures else None
    f = Fetcher(os.getenv("GITHUB_TOKEN"), fixtures)
    now = datetime.now(KST)
    if fixtures is not None:
        # fixtures 모드: 실제 상태 파일은 읽지도 쓰지도 않는다. 고정 시각/초기 상태는 fixture가 정한다.
        if fixtures.get("__now__"):
            now = datetime.fromisoformat(fixtures["__now__"]).astimezone(KST)
        state = json.loads(json.dumps(fixtures.get("__state__", {})))
    else:
        state = json.loads(args.state.read_text(encoding="utf-8")) if args.state.exists() else {}
    today = now.strftime("%Y-%m-%d")
    baseline = not state.get("items")
    print(f"[{today}] 모니터 시작 (baseline={baseline}, fixtures={bool(fixtures)})")

    run, items, counts = Run(), {}, {}
    batches = [
        run.source("releases", "Claude Code 릴리스", collect_releases, f, cfg, now, state),
        run.source("changelog", "Claude Code CHANGELOG", collect_changelog, f, cfg, state),
    ]
    for m in cfg["official"]["marketplace_dirs"]:
        batches.append(run.source(f"market:{m['repo']}", m["label"], collect_marketplace, f, cfg, state, m))
    for w in cfg["official"]["link_watch"]:
        batches.append(run.source(w["name"], w["label"], collect_links, f, state, w))
    for a in cfg["official"].get("article_pages", []):
        batches.append(run.source(a["name"], a["label"], collect_articles, f, cfg, now, a))
    for fd in cfg.get("industry_feeds", {}).get("feeds", []):
        batches.append(run.source(fd["name"], fd["label"], collect_feed, f, cfg, now, fd))
    batches.append(run.source("github_search", "GitHub 검색(신규·토픽)", collect_github, f, cfg, now))
    batches.append(run.source("hackernews", "Hacker News", collect_hn, f, cfg, now, counts))
    batches.append(run.source("reddit", "Reddit", collect_reddit, f, cfg, counts))
    for batch in batches:
        for it in batch or []:
            merge(items, it)
    weekly = args.watchlist or now.weekday() == cfg["watchlist"]["weekday_kst"]
    watch = None
    if weekly:  # 감시 키워드 검색 결과도 후보 풀에 넣는다 (예전엔 '리포트 미반영' 경고만 했다)
        rows, wfailed, extra = watchlist_fetch(f, cfg, now, counts)
        for it in extra:
            merge(items, it)
        watch = (rows, wfailed)
    bundle = bundle_releases(items, cfg)
    fold_launch_coverage(items)
    print(f"  수집 아이템 {len(items)}개, 실패 소스 {len(run.failures)}개")
    if bundle["text"]:
        print(f"  {bundle['text']}")

    evaluated = evaluate(items, state, cfg, now, baseline)
    top, dropped = select_top(evaluated, cfg)
    run.source("major_detail", "대형 발표 원문·국내 기사", enrich_majors, f, cfg, top)
    heads = pick_headline(top, cfg)
    surges = keyword_surges(counts, state, cfg)
    if watch:
        watchlist_finalize(watch[0], state, top, now)
    update_state(state, evaluated, top, now)

    report = build_report(today, cfg, run, top, evaluated, surges, watch, baseline, heads, bundle, dropped)
    top_json = {
        "date": today, "baseline": baseline,
        "headline": [headline(t) for t in heads],
        "release_summary": bundle["text"],
        "min_value": cfg["value_rules"]["min_value"],
        "failures": [{"label": s["label"], "note": s["note"]} for s in run.failures],
        "watchlist_warnings": [r["kw"] for r in (watch[0] if watch else []) if r["warn"]],
        "top": [{k: t.get(k) for k in ("id", "title", "url", "summary", "kind", "official", "categories", "stars",
                                        "star_delta_7d", "mentions", "score", "importance", "reasons", "value",
                                        "value_reasons", "needs_check", "watch_hits", "published_at", "versions",
                                        "first_seen", "sources", "resurfaced", "major", "kr_news", "detail")}
                for t in top],
    }

    if args.dry_run:
        print("\n" + report)
        print("=== latest-top.json (미저장) ===")
        print(json.dumps(top_json, ensure_ascii=False, indent=2)[:3000])
        if args.dump:
            args.dump.mkdir(parents=True, exist_ok=True)
            (args.dump / f"claude-code-trends-{today}.md").write_text(report, encoding="utf-8")
            (args.dump / "latest-top.json").write_text(json.dumps(top_json, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"(--dump) {args.dump}에 리포트·latest-top.json 저장")
        return 0

    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    out = RESEARCH_DIR / f"claude-code-trends-{today}.md"
    out.write_text(report, encoding="utf-8")
    args.state.parent.mkdir(parents=True, exist_ok=True)
    args.state.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    TOP_PATH.write_text(json.dumps(top_json, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"리포트: {out}\n상태: {args.state}\n상위 목록: {TOP_PATH}")
    for line in top_json["headline"]:
        print(f"  - {line}")
    if run.failures:
        print("수집 실패: " + ", ".join(s["label"] for s in run.failures))
    return 0


if __name__ == "__main__":
    sys.exit(main())
