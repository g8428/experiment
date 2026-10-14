"""
Claude Code·AI 도구 소식 모니터 (v2)

v1은 "GitHub 검색 5개 쿼리 → 스타순 TOP 20" 하나뿐이라 공식 발표·신규 스킬·커뮤니티 화제를 못 잡았다.
v2는 공식 소스 + GitHub(신규·급상승) + 커뮤니티(HN/Reddit)를 모아 중요도 점수로 상위 N개만 리포트에 올린다.
왜 이렇게 바꿨는지는 HANDOVER.md 참고.

실행:
  python projects/claude-code-monitor/monitor.py                 # 실제 수집 → research/ 저장
  python projects/claude-code-monitor/monitor.py --watchlist     # 요일과 무관하게 주간 감시 리스트 점검 포함
  python projects/claude-code-monitor/monitor.py --dry-run --fixtures projects/claude-code-monitor/fixtures/dry_run_sample.json
      # 네트워크 없이 가짜 응답으로 전체 흐름 확인. 파일을 쓰지 않고 리포트를 화면에 출력

환경변수: GITHUB_TOKEN (Actions 기본 제공. 없어도 동작하지만 검색 rate limit이 낮다)
의존성: requests
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
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
            if key not in self.fixtures:
                raise RuntimeError(f"fixture 없음: {key}")
            return self.fixtures[key]
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

def collect_releases(f: Fetcher, cfg: dict, now: datetime):
    items, cutoff = [], now - timedelta(days=cfg["lookback_days"])
    for repo in cfg["official"]["release_repos"]:
        for r in f.gh(f"releases::{repo}", f"/repos/{repo}/releases", {"per_page": 15}):
            pub = parse_dt(r.get("published_at"))
            if pub and pub >= cutoff:
                tag = r.get("tag_name", "")
                items.append(make_item(
                    f"release:{repo}@{tag}", f"{repo} {tag} 릴리스", r.get("html_url", ""),
                    one_line(re.sub(r"^\s*[-*]\s*", "", r.get("body") or ""), 300), official=True, kind="official",
                    source="releases", published_at=r.get("published_at"), text=r.get("body", ""),
                ))
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
    new = [
        make_item(f"link:{u}", f"[{w['label']}] 새 페이지: {u.rstrip('/').rsplit('/', 1)[-1]}", u,
                  f"{w['label']}에 새 링크가 생김", official=True, kind="official", source=w["name"])
        for u in fresh[:15]
    ]
    note = f"전체 {len(links)}개" + (f", 신규 {len(fresh)}개 중 15개만 반영" if len(fresh) > 15 else "")
    return new, len(new), note


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
    items = []
    for kw in cm["hn_keywords"]:
        data = f.get(f"hn::{kw}", "https://hn.algolia.com/api/v1/search_by_date",
                     {"query": kw, "tags": "story", "numericFilters": f"created_at_i>{since}", "hitsPerPage": 100})
        hits = data.get("hits", [])
        counts[f"hn::{kw}"] = int(data.get("nbHits", len(hits)))
        for h in hits:
            points = int(h.get("points") or 0)
            if points < cm["hn_min_points"]:
                continue
            disc = f"https://news.ycombinator.com/item?id={h.get('objectID')}"
            url = h.get("url") or disc
            mentions = points + int(h.get("num_comments") or 0)
            rid = gh_repo_id(url)
            if rid:
                items.append(make_item(rid, rid[3:], url, h.get("title", ""), source="hackernews", mentions=mentions))
            else:
                items.append(make_item(f"hn:{h.get('objectID')}", h.get("title", ""), url, f"HN 토론: {disc}",
                                       kind="community", source="hackernews", mentions=mentions,
                                       published_at=h.get("created_at")))
    return items, len(items), f"키워드 {len(cm['hn_keywords'])}개"


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
                      or it["mentions"] > 0 or it["kind"] == "community")
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
        it["score"], it["reasons"] = round(score, 1), reasons
        out.append(it)
    return out


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

def watchlist_check(f: Fetcher, cfg: dict, state: dict, top: list[dict], now: datetime, counts: dict):
    week = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    since = int((now - timedelta(days=7)).timestamp())
    week_ago = week
    rows, failed = [], []
    for kw in cfg["watchlist"]["keywords"]:
        row = {"kw": kw, "gh": None, "gh_top": [], "hn": None, "reddit": counts.get(f"reddit::{kw}")}
        try:
            d = f.gh(f"watch_gh::{kw}", "/search/repositories",
                     {"q": f'"{kw}" claude pushed:>{week}', "sort": "stars", "order": "desc", "per_page": 3})
            row["gh"] = int(d.get("total_count", 0))
            row["gh_top"] = [i["full_name"] for i in d.get("items", [])[:3]]
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
        row["in_top"] = any(kw_match(kw, t["text"].lower()) for t in top)
        row["recent_reported"] = any(
            kw_match(kw, (v.get("kw_text") or "").lower()) and any(d >= week_ago for d in v.get("reported", []))
            for v in state.get("items", {}).values()
        )
        signal = (row["gh"] or 0) >= 5 or (row["hn"] or 0) >= 3 or (row["reddit"] or 0) >= 3
        row["warn"] = signal and not row["in_top"] and not row["recent_reported"]
        rows.append(row)
    return rows, failed


# ─── 리포트 ───────────────────────────────────────────────────────────────────

def headline(it: dict) -> str:
    tag = "/".join(it["categories"])
    flag = "공식 " if it["official"] else ""
    return f"[{tag}] {flag}{it['title']} — {one_line(it['summary'], 90) or '설명 없음'}"


def build_report(today: str, cfg: dict, run: Run, top: list[dict], all_items: list[dict], surges: list[dict],
                 watch: tuple | None, baseline: bool) -> str:
    L = [f"# Claude Code·AI 도구 소식 모니터 ({today})", "",
         f"> 공식 발표 · GitHub 신규/급상승 · 커뮤니티(HN/Reddit)를 모아 중요도 점수순 상위 {cfg['top_n']}개만 싣는다. "
         "이미 다룬 소식은 반응이 급증한 경우(재부상)만 다시 싣는다.", ""]
    if baseline:
        L += ["> ℹ️ 첫 실행(기준선 저장). 공식 목록·문서 링크는 이번엔 기준만 저장하고 다음 실행부터 '새 항목'을 잡는다.", ""]

    L += ["## 오늘의 핵심 3줄", ""]
    if top:
        L += [f"{i}. {headline(t)}" for i, t in enumerate(top[:3], 1)]
    else:
        L.append("오늘은 새로 올라온 핵심 소식이 없습니다 (이미 다룬 항목 제외).")
    L.append("")

    if run.failures:
        L += ["## ⚠️ 수집 실패", "", "아래 소스는 이번에 수집하지 못했다. **이 소스에서 나온 소식은 이번 리포트에 빠져 있을 수 있다.**", ""]
        L += [f"- **{s['label']}** — {s['note']}" for s in run.failures]
        L.append("")
    partial = [s for s in run.statuses if s["ok"] and "실패" in (s["note"] or "")]
    if partial:
        L += ["> 일부 실패: " + " / ".join(f"{s['label']}: {s['note']}" for s in partial), ""]

    L += [f"## 상위 {len(top)}개 (중요도 점수순)", "",
          "| # | 점수 | 카테고리 | 소식 | 처음 등장 | 출처 |", "|---|---|---|---|---|---|"]
    for i, t in enumerate(top, 1):
        mark = " 🔁재부상" if t["resurfaced"] else (" 🆕" if t["is_new"] else "")
        L.append(f"| {i} | {t['score']:.0f} | {'/'.join(t['categories'])} | [{t['title']}]({t['url']}){mark} "
                 f"| {t['first_seen']} | {', '.join(t['sources'])} |")
    L.append("")
    for i, t in enumerate(top, 1):
        L += [f"### {i}. {t['title']}", "",
              f"- 링크: {t['url']}",
              f"- 내용: {one_line(t['summary'], 300) or '설명 없음'}"]
        if t.get("stars") is not None:
            L.append(f"- 스타: {t['stars']:,}")
        L += [f"- 점수 근거: {', '.join(t['reasons']) or '없음'}", ""]

    if surges:
        L += ["## 커뮤니티 키워드 급증", "", "| 소스::키워드 | 이번 | 직전 평균 |", "|---|---|---|"]
        L += [f"| {s['key']} | {s['count']} | {s['avg']} |" for s in surges]
        L.append("")

    if watch is not None:
        rows, failed = watch
        L += ["## 주간 키워드 감시 리스트 점검", "",
              "큰 소식이 점수 체계에서 빠지는 것을 막는 안전장치. 바깥 반응이 있는데 최근 7일 리포트에 없으면 ⚠️.", "",
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

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Claude Code·AI 도구 소식 모니터")
    ap.add_argument("--dry-run", action="store_true", help="파일을 쓰지 않고 리포트를 화면에 출력")
    ap.add_argument("--fixtures", type=Path, help="가짜 응답 JSON (네트워크 호출 없음)")
    ap.add_argument("--watchlist", action="store_true", help="요일과 무관하게 주간 감시 리스트 점검")
    ap.add_argument("--state", type=Path, default=STATE_PATH)
    ap.add_argument("--config", type=Path, default=CONFIG_PATH)
    args = ap.parse_args(argv)

    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    fixtures = json.loads(args.fixtures.read_text(encoding="utf-8")) if args.fixtures else None
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
        run.source("releases", "Claude Code 릴리스", collect_releases, f, cfg, now),
        run.source("changelog", "Claude Code CHANGELOG", collect_changelog, f, cfg, state),
    ]
    for m in cfg["official"]["marketplace_dirs"]:
        batches.append(run.source(f"market:{m['repo']}", m["label"], collect_marketplace, f, cfg, state, m))
    for w in cfg["official"]["link_watch"]:
        batches.append(run.source(w["name"], w["label"], collect_links, f, state, w))
    batches.append(run.source("github_search", "GitHub 검색(신규·토픽)", collect_github, f, cfg, now))
    batches.append(run.source("hackernews", "Hacker News", collect_hn, f, cfg, now, counts))
    batches.append(run.source("reddit", "Reddit", collect_reddit, f, cfg, counts))
    for batch in batches:
        for it in batch or []:
            merge(items, it)
    print(f"  수집 아이템 {len(items)}개, 실패 소스 {len(run.failures)}개")

    evaluated = evaluate(items, state, cfg, now, baseline)
    top = sorted((i for i in evaluated if i["eligible"]), key=lambda i: i["score"], reverse=True)[: cfg["top_n"]]
    surges = keyword_surges(counts, state, cfg)
    weekly = args.watchlist or now.weekday() == cfg["watchlist"]["weekday_kst"]
    watch = watchlist_check(f, cfg, state, top, now, counts) if weekly else None
    update_state(state, evaluated, top, now)

    report = build_report(today, cfg, run, top, evaluated, surges, watch, baseline)
    top_json = {
        "date": today, "baseline": baseline,
        "headline": [headline(t) for t in top[:3]],
        "failures": [{"label": s["label"], "note": s["note"]} for s in run.failures],
        "watchlist_warnings": [r["kw"] for r in (watch[0] if watch else []) if r["warn"]],
        "top": [{k: t[k] for k in ("id", "title", "url", "summary", "official", "categories", "stars",
                                    "star_delta_7d", "mentions", "score", "reasons", "first_seen", "sources",
                                    "resurfaced")} for t in top],
    }

    if args.dry_run:
        print("\n" + report)
        print("=== latest-top.json (미저장) ===")
        print(json.dumps(top_json, ensure_ascii=False, indent=2)[:3000])
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
