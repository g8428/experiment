"""
모니터 결과에서 소식 1개를 골라 블로그 소개글 + 인스타 카드뉴스를 생성한다 (Anthropic API 직접 호출).

글쓰기 규칙은 이 파일에 두지 않는다. `.claude/agents/content-blog-writer.md`, `content-instagram-writer.md`
본문을 그대로 시스템 프롬프트로 읽어 쓴다 (v1은 이 파일 안에 별도 프롬프트가 있어서 에이전트 파일을 고쳐도
Actions 결과물이 바뀌지 않았다 — HANDOVER.md 참고).

실행:
  python projects/claude-code-monitor/generate_content.py                # research/state/latest-top.json 기준
  python projects/claude-code-monitor/generate_content.py research/claude-code-trends-2026-10-12.md
  python projects/claude-code-monitor/generate_content.py --dry-run      # API 호출 없이 프롬프트만 출력
  python projects/claude-code-monitor/generate_content.py --dry-run --top <폴더>/latest-top.json --fake-blog <응답.md>
      # monitor.py --dump 결과로 프롬프트 확인 + 가짜 블로그 응답으로 SKIP/정상 경로 처리 확인 (파일 안 씀)

글감이 사소하면 블로그 에이전트가 첫 줄에 `SKIP: <사유>`만 출력한다(규칙은 content-blog-writer.md).
그러면 블로그·인스타 파일을 만들지 않고(인스타 호출도 생략) content/YYYY-MM-DD-skip.txt에 사유를 남긴다.
slack_notify.py가 이 파일을 보고 "이번 주는 글감 없음(사유)"를 보낸다. 판단은 기존 블로그 호출 안에서 한다(추가 호출 없음).
의존성: anthropic (dry-run은 불필요)
트레이싱(선택): LANGFUSE_* 환경변수가 있으면 Langfuse로 전송 (shared/utils/langfuse_tracing.py 참고)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:  # 로컬 실행 시 레포 루트 .env 로드 (Langfuse 초기화보다 먼저여야 한다)
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent.parent / ".env")
except ImportError:
    pass

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "shared" / "utils"))
from langfuse_tracing import TRACING_ENABLED, flush, get_client, observe, propagate_attributes, setup_tracing  # noqa: E402

KST = timezone(timedelta(hours=9))
RESEARCH_DIR = ROOT / "research"
TOP_PATH = RESEARCH_DIR / "state" / "latest-top.json"
AGENTS_DIR = ROOT / ".claude" / "agents"
CONTENT_DIR = ROOT / "content"
BLOG_DIR = ROOT / "content" / "blog"
INSTAGRAM_DIR = ROOT / "content" / "instagram"
MODEL = "claude-opus-5"
CANDIDATES = 5  # 에이전트가 이 중에서 1개를 고른다

FACT_RULE = """# 이번 작업의 사실 범위
- 아래 '후보 소식'과 '모니터 리포트'에 적힌 내용만 사실로 쓴다. 그 밖의 수치·날짜·가격·기능은 쓰지 않는다.
- 소식의 날짜는 후보의 published_at(소스에 적힌 발표일)만 쓴다. 리포트 날짜·오늘 날짜를 발표일처럼 쓰지 않는다. 없으면 날짜를 빼거나 "최근"이라고 쓴다.
- 후보의 summary가 짧아 설명이 부족하면, 모르는 부분은 "공식 페이지에서 확인하세요"로 처리한다.
- 출처 목록에는 후보의 url과 리포트에 있는 URL만 넣는다.
- 지금은 API 호출이라 파일을 저장할 수 없다. 완성된 마크다운 전체만 출력하고 다른 말은 붙이지 않는다 (글감이 없으면 `SKIP: <사유>` 한 줄만)."""


def skip_reason(text: str) -> str | None:
    """에이전트 응답의 첫 줄(공백 줄 제외)이 'SKIP:'이면 사유를 돌려준다."""
    for line in text.splitlines():
        if line.strip():
            m = re.match(r"\s*SKIP\s*[:：]\s*(.*)", line)
            return (m.group(1).strip() or "사유 없음") if m else None
    return None


def skip_marker(today: str) -> Path:
    return CONTENT_DIR / f"{today}-skip.txt"  # slack_notify.py가 읽는다 (Actions에서 커밋 안 함)


def write_skip(today: str, reason: str) -> None:
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    skip_marker(today).write_text(reason + "\n", encoding="utf-8")
    print(f"이번 주는 글감 없음: {reason} → {skip_marker(today).relative_to(ROOT)}")


def agent_prompt(name: str) -> str:
    """에이전트 정의 파일에서 YAML 프론트매터를 떼고 본문만 반환."""
    text = (AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    return re.sub(r"\A---\n.*?\n---\n", "", text, count=1, flags=re.S).strip()


def latest_research_file() -> Path:
    files = sorted(RESEARCH_DIR.glob("claude-code-trends-*.md"), reverse=True)
    if not files:
        raise FileNotFoundError("research/ 폴더에 claude-code-trends-*.md 파일이 없습니다.")
    return files[0]


def load_inputs(research_arg: str | None, top_path: Path = TOP_PATH) -> tuple[dict, Path]:
    top = json.loads(top_path.read_text(encoding="utf-8")) if top_path.exists() else {"top": []}
    name = f"claude-code-trends-{top.get('date')}.md"
    if research_arg:
        path = Path(research_arg)
    elif top.get("date") and (top_path.parent / name).exists():  # monitor.py --dump 폴더
        path = top_path.parent / name
    elif top.get("date") and (RESEARCH_DIR / name).exists():
        path = RESEARCH_DIR / name
    else:
        path = latest_research_file()
    return top, path


def build_user_prompt(kind: str, top: dict, research: str, today: str, research_path: Path,
                      blog: str | None = None) -> str:
    cands = json.dumps(top.get("top", [])[:CANDIDATES], ensure_ascii=False, indent=2)
    task = ("블로그 소개글 1편을 써라. 프론트매터의 date는 " + today
            + f", source_report는 {research_path.relative_to(ROOT) if research_path.is_relative_to(ROOT) else research_path}."
            + " 후보가 모두 사소하거나 일반인에게 '그래서 뭐?'인 소식이면 글을 쓰지 말고 첫 줄에 `SKIP: <사유 한 줄>`만 출력한다.")
    if kind == "instagram":
        task = "카드뉴스 1개를 써라. 아래 '같은 소식의 블로그 초안'과 같은 소식을 다루고, 예시·수치·비유는 블로그와 똑같이 쓴다."
        if blog:
            task += f"\n\n# 같은 소식의 블로그 초안 (이 글의 예시·수치를 그대로 쓴다. 여기 없는 수치를 새로 만들지 않는다)\n{blog}"
    return f"""{task}

{FACT_RULE}

# 후보 소식 (점수순, 이 중 1개만 고른다)
{cands}

# 모니터 리포트 ({research_path.name})
{research}"""


def extract_text(msg) -> str:
    """msg.content[0]이 항상 TextBlock이라고 가정하면 안 된다.
    claude-opus-5는 응답 앞에 ThinkingBlock(.text 속성 없음)을 먼저 반환할 수 있어서,
    content 배열에서 type == 'text'인 블록만 골라 이어붙인다."""
    parts = [block.text for block in msg.content if getattr(block, "type", None) == "text"]
    if not parts:
        raise RuntimeError(f"응답에 text 블록이 없습니다. content types: {[getattr(b, 'type', None) for b in msg.content]}")
    return "\n".join(parts)


@observe(name="generate-blog-post", capture_input=False)  # 입력(리서치 전문)은 하위 generation에 이미 기록됨
def generate_blog_post(client, system: str, user: str) -> str:
    msg = client.messages.create(model=MODEL, max_tokens=6000, system=system,
                                 messages=[{"role": "user", "content": user}])
    return extract_text(msg)


@observe(name="generate-instagram-post", capture_input=False)
def generate_instagram_post(client, system: str, user: str) -> str:
    msg = client.messages.create(model=MODEL, max_tokens=3000, system=system,
                                 messages=[{"role": "user", "content": user}])
    return extract_text(msg)


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:60] or "post"


def front_value(md: str, key: str) -> str | None:
    m = re.search(rf"^{key}:\s*\"?([^\"\n]+)\"?\s*$", md, re.M)
    return m.group(1).strip() if m else None


@observe(name="generate-weekly-content", capture_input=False)  # 1회 실행 = 1 trace
def run(top: dict, research_path: Path, today: str) -> dict:
    import anthropic  # dry-run에서는 필요 없도록 지연 import

    research = research_path.read_text(encoding="utf-8")
    if TRACING_ENABLED:
        get_client().update_current_span(input={"research_file": research_path.name})
    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY env var 자동 사용
    result = {}

    print("블로그 소개글 생성 중...")
    blog = generate_blog_post(client, agent_prompt("content-blog-writer"),
                              build_user_prompt("blog", top, research, today, research_path))
    reason = skip_reason(blog)
    if reason is not None:
        # 글감 가치 낮음 판단: 파일을 만들지 않고 인스타 호출도 건너뛴다 (같은 소식이라 결과가 같다 + 비용 절감)
        write_skip(today, reason)
        result["skip"] = reason
        return result
    if not blog.lstrip().startswith("---"):
        print("블로그: 프론트매터 없는 응답 — 저장하지 않음\n" + blog[:300])
        blog_for_insta = None
    else:
        slug = front_value(blog, "slug") or slugify(front_value(blog, "title") or "claude-code-news")
        BLOG_DIR.mkdir(parents=True, exist_ok=True)
        blog_path = BLOG_DIR / f"{today}-{slugify(slug)}.md"
        blog_path.write_text(blog, encoding="utf-8")
        print(f"블로그 저장: {blog_path}")
        result["blog"] = str(blog_path.relative_to(ROOT))
        blog_for_insta = blog

    print("인스타그램 카드뉴스 생성 중...")
    insta = generate_instagram_post(client, agent_prompt("content-instagram-writer"),
                                    build_user_prompt("instagram", top, research, today, research_path, blog_for_insta))
    if skip_reason(insta) is not None:
        print(f"인스타: SKIP 응답 — 저장하지 않음 ({skip_reason(insta)})")
        return result
    INSTAGRAM_DIR.mkdir(parents=True, exist_ok=True)
    ig_path = INSTAGRAM_DIR / f"{today}-instagram.md"
    ig_path.write_text(insta, encoding="utf-8")
    print(f"인스타 저장: {ig_path}")
    result["instagram"] = str(ig_path.relative_to(ROOT))
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("research", nargs="?", help="리포트 경로 (생략 시 latest-top.json 날짜 또는 최신 리포트)")
    ap.add_argument("--dry-run", action="store_true", help="API 호출 없이 프롬프트만 출력")
    ap.add_argument("--top", type=Path, default=TOP_PATH, help="latest-top.json 경로 (monitor.py --dump 결과 검증용)")
    ap.add_argument("--fake-blog", type=Path, help="--dry-run 전용: 블로그 호출 응답 대신 쓸 파일 (SKIP/정상 경로 확인)")
    args = ap.parse_args(argv)

    today = datetime.now(KST).strftime("%Y-%m-%d")
    top, research_path = load_inputs(args.research, args.top)
    print(f"리서치 파일: {research_path} / 후보 {len(top.get('top', []))}개")

    if not top.get("top"):
        reason = "글감급 후보 없음(규칙 기반 선별)" + (f" — {top['release_summary']}" if top.get("release_summary") else "")
        print("이번 주는 글감급 소식이 없어 컨텐츠 생성을 건너뜁니다 (latest-top.json의 top이 비어 있음).")
        if not args.dry_run:
            write_skip(today, reason)
        else:
            print(f"(dry-run) 저장 안 함 — Slack 보고 예정 문구: 이번 주는 글감 없음({reason})")
        return 0

    if args.dry_run:
        research = research_path.read_text(encoding="utf-8")
        system = agent_prompt("content-blog-writer")
        user = build_user_prompt("blog", top, research, today, research_path)
        print(f"\n=== system (content-blog-writer.md 본문, {len(system):,}자) ===\n{system[:600]}…")
        print(f"\n=== user ({len(user):,}자) ===\n{user[:1500]}…")
        if args.fake_blog:
            fake = args.fake_blog.read_text(encoding="utf-8")
            reason = skip_reason(fake)
            if reason is not None:
                print(f"\n=== 가짜 블로그 응답: SKIP 감지 → 블로그·인스타 파일 미생성, 인스타 호출 생략 ===\n"
                      f"Slack 보고 예정 문구: 이번 주는 글감 없음({reason})")
                return 0
            insta_user = build_user_prompt("instagram", top, research, today, research_path, fake)
            print(f"\n=== 가짜 블로그 응답: 정상 → 저장 예정 slug: {front_value(fake, 'slug')} ===")
            print(f"\n=== instagram user ({len(insta_user):,}자, 블로그 초안 포함) ===\n{insta_user[:700]}…")
        print(f"\n=== instagram system ({len(agent_prompt('content-instagram-writer')):,}자) 로드 OK ===")
        return 0

    setup_tracing()  # Anthropic SDK 호출을 generation(모델/토큰/입출력)으로 자동 수집
    try:
        with propagate_attributes(tags=["claude-code-monitor", "daily-content"], metadata={"research_date": today}):
            run(top, research_path, today)
    finally:
        flush()  # 짧게 끝나는 스크립트라 종료 전 전송 필수
    return 0


if __name__ == "__main__":
    sys.exit(main())
