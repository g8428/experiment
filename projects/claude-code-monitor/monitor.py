"""
GitHub 트렌딩 모니터 — Claude Code 관련 오픈소스 스타 추적기
매주 월요일 실행. 새로 뜨는 리포 감지 → research/ 저장 → Slack 보고.

실행: python projects/claude-code-monitor/monitor.py
의존성: requests (pip install requests)
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

# ─── 설정 ────────────────────────────────────────────────────────────────────

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # 없어도 동작 (rate limit 낮음)
SEARCH_QUERIES = [
    "claude-code",
    "awesome-claude-code",
    "claude mcp server",
    "anthropic claude skills",
    "CLAUDE.md",
]
MIN_STARS = 100          # 이 이상만 추적
TOP_N = 20               # 쿼리당 상위 N개
OUTPUT_DIR = Path(__file__).parent.parent.parent / "research"
HISTORY_FILE = Path(__file__).parent / "history.json"


# ─── GitHub API ───────────────────────────────────────────────────────────────

def gh_search(query: str) -> list[dict]:
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    url = "https://api.github.com/search/repositories"
    params = {
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": TOP_N,
    }
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json().get("items", [])


def fetch_all_repos() -> dict[str, dict]:
    """쿼리 전체 실행 → full_name 기준 중복 제거 딕셔너리 반환"""
    seen: dict[str, dict] = {}
    for query in SEARCH_QUERIES:
        print(f"  검색 중: {query}")
        try:
            items = gh_search(query)
            for item in items:
                if item["stargazers_count"] >= MIN_STARS:
                    seen[item["full_name"]] = {
                        "full_name": item["full_name"],
                        "html_url": item["html_url"],
                        "description": item.get("description", ""),
                        "stars": item["stargazers_count"],
                        "language": item.get("language", ""),
                        "updated_at": item.get("updated_at", ""),
                        "topics": item.get("topics", []),
                    }
        except requests.HTTPError as e:
            print(f"  경고: {query} 검색 실패 — {e}", file=sys.stderr)
    return seen


# ─── 변경 감지 ────────────────────────────────────────────────────────────────

def load_history() -> dict[str, int]:
    """이전 실행 스타 수 로드 {full_name: stars}"""
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    return {}


def save_history(repos: dict[str, dict]):
    HISTORY_FILE.write_text(
        json.dumps({k: v["stars"] for k, v in repos.items()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def find_changes(current: dict[str, dict], history: dict[str, int]) -> dict:
    new_repos = []
    star_jumps = []

    for name, repo in current.items():
        prev_stars = history.get(name)
        if prev_stars is None:
            new_repos.append(repo)
        else:
            diff = repo["stars"] - prev_stars
            if diff >= 500:  # 일주일 사이 500★ 이상 급등
                star_jumps.append({**repo, "star_diff": diff})

    return {"new": new_repos, "jumps": star_jumps}


# ─── 리포트 생성 ──────────────────────────────────────────────────────────────

def build_report(
    today: str,
    repos: dict[str, dict],
    changes: dict,
) -> str:
    top20 = sorted(repos.values(), key=lambda r: r["stars"], reverse=True)[:20]

    lines = [
        f"# Claude Code 오픈소스 트렌드 모니터 ({today})",
        "",
        f"> 추적 기준: GitHub 검색 쿼리 {len(SEARCH_QUERIES)}개 / 최소 스타 {MIN_STARS}개 이상",
        "",
    ]

    if changes["new"]:
        lines += ["## 🆕 신규 진입 리포", ""]
        for r in sorted(changes["new"], key=lambda x: x["stars"], reverse=True):
            lines.append(f"- [{r['full_name']}]({r['html_url']}) — ⭐ {r['stars']:,} — {r['description']}")
        lines.append("")

    if changes["jumps"]:
        lines += ["## 🚀 이번 주 스타 급등 (500+ 증가)", ""]
        for r in sorted(changes["jumps"], key=lambda x: x["star_diff"], reverse=True):
            lines.append(
                f"- [{r['full_name']}]({r['html_url']}) — ⭐ {r['stars']:,} (+{r['star_diff']:,}) — {r['description']}"
            )
        lines.append("")

    lines += ["## 전체 TOP 20 (스타 기준)", "", "| 리포 | 스타 | 설명 |", "|------|------|------|"]
    for r in top20:
        desc = (r["description"] or "")[:60]
        lines.append(f"| [{r['full_name']}]({r['html_url']}) | {r['stars']:,} | {desc} |")
    lines.append("")
    lines.append(f"*생성: {today} | 스크립트: projects/claude-code-monitor/monitor.py*")

    return "\n".join(lines)


# ─── 메인 ─────────────────────────────────────────────────────────────────────

def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"[{today}] GitHub 트렌드 모니터 시작")

    print("GitHub API 검색 중...")
    repos = fetch_all_repos()
    print(f"  수집된 리포: {len(repos)}개")

    history = load_history()
    changes = find_changes(repos, history)
    save_history(repos)

    report = build_report(today, repos, changes)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"claude-code-trends-{today}.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"리포트 저장: {out_path}")

    # 변경 요약 출력 (Cowork 태스크가 캡처해서 Slack 발송)
    print("\n=== 변경 요약 ===")
    print(f"신규 리포: {len(changes['new'])}개")
    print(f"스타 급등: {len(changes['jumps'])}개")
    if changes["new"]:
        print("신규:")
        for r in changes["new"][:5]:
            print(f"  - {r['full_name']} (⭐{r['stars']:,})")
    if changes["jumps"]:
        print("급등:")
        for r in changes["jumps"][:5]:
            print(f"  - {r['full_name']} (+{r['star_diff']:,})")
    print(f"리포트: {out_path}")


if __name__ == "__main__":
    main()
