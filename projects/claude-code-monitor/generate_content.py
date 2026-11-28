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

블로그 글은 content/blog/에 저장하고, 같은 내용을 research/content/{날짜}-blog.md에도 남긴다
(워크플로가 research/만 커밋하므로, 자동 발행은 이 사본을 받아 publish_wordpress.py가 처리한다).

인스타 카드뉴스는 **JSON**으로 받는다(2026-11-28). 렌더러(render_final.py)가 그대로 읽어
1080x1350 이미지를 뽑는 구조라, 산문 md 대신 고정 스키마(handle/badge/title_lines 3줄/highlight_word/subtitle/meta/
slides 4장/cta/caption/hashtags)를 검증하고 research/content/{날짜}-instagram.json에 남긴다(git add research/로 자동 커밋 대상).
표지 유형은 A형(매거진 빅타이포), 본문은 3~5줄 설명이고 '~했다/…습니다' 보고서체는 검증에서 막는다(2026-11-28).
Slack 보고와 사람이 읽을 사본은 지금처럼 content/instagram/{날짜}-instagram.md에 JSON을 풀어 쓴다.

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
# 인스타 카드뉴스는 렌더러가 바로 먹는 JSON으로 research/ 아래에 남긴다(워크플로가 research/만 커밋한다).
INSTAGRAM_JSON_NAME = "{date}-instagram.json"
# 표지·본문에서 절대 쓰지 않는 말. 프롬프트(.claude/agents/content-instagram-writer.md 5장)와 같은 목록이다.
BANNED_PHRASES = ("혁신적인", "놀라운", "주목할 만한", "획기적인", "압도적인", "게임 체인저",
                  "새로운 시대", "패러다임", "가능성을 열", "무조건", "역대급")
SLIDE_COUNT = 4  # 표지 + 본문 4장 + CTA = 6장
HANDLE = "청년 재테크 · AI 뉴스 카드"
# 표지 = A형(매거진 빅타이포): 배지 + 3줄 제목 + 주황 박스 강조어 + 부제 + 메타
TITLE_LINE_COUNT = 3
MAX_TITLE_LINE = 12
MAX_HEADLINE = 11  # 띄어쓰기 제외. 78px 큰 글씨로 한 줄에 들어가는 양(약 928px)
MAX_BADGE = 16
MAX_SUBTITLE = 24
MAX_META = 40
# 본문은 한 줄 조각이 아니라 4~5줄 설명(프롬프트 80~170자). 검증은 여유를 둔 경계로 막는다.
BODY_MIN_CHARS = 80
BODY_MAX_CHARS = 190
# '~했다/…습니다' 보고서체 어미는 문장 끝(공백·문장부호·끝)에서만 잡는다. '였다면' 같은 조건형은 통과.
REPORT_ENDING_RE = re.compile(r"[가-힣]{1,8}다(?=[\s.,!?~…)\]\"']|$)")
# 워크플로가 커밋하는 건 research/ 뿐이라(git add research/), 블로그 글은 research/ 아래에도 사본을 남긴다.
# 용도: ① 주간 글의 커밋 기록 ② 워드프레스 자동 발행(publish_wordpress.py)의 입력.
# 업로드는 Actions 밖(Pickle 예약 액션)에서 이 사본을 받아 하므로, Actions 러너의 content/blog는 여전히 커밋하지 않는다.
RESEARCH_CONTENT_DIR = RESEARCH_DIR / "content"
MODEL = "claude-opus-5"
CANDIDATES = 5  # 에이전트가 이 중에서 1개를 고른다
# claude-opus-5는 thinking(adaptive)이 기본으로 켜져 있고 끌 수 없다(thinking {"type":"disabled"}는 400).
# thinking 토큰은 max_tokens 한도에 포함되므로, 한도가 작으면 thinking만 하고 본문 없이 끝난다
# (2026-11-02 실행: content types ['thinking'], 본문 없음 → RuntimeError로 워크플로 실패).
# 그래서 ① thinking을 명시하고(본문만 받는다) ② 한도를 넉넉히 두고 ③ 잘리면 한도를 늘려 1회 재시도한다.
THINKING = {"type": "adaptive", "display": "omitted"}
MAX_TOKENS = {"blog": 16000, "instagram": 12000}  # thinking + 본문 합계 한도
MAX_TOKENS_CAP = 32000

FACT_RULE = """# 이번 작업의 사실 범위
- 아래 '후보 소식'과 '모니터 리포트'에 적힌 내용만 사실로 쓴다. 그 밖의 수치·날짜·가격·기능은 쓰지 않는다.
- 소식의 날짜는 후보의 published_at(소스에 적힌 발표일)만 쓴다. 리포트 날짜·오늘 날짜를 발표일처럼 쓰지 않는다. 없으면 날짜를 빼거나 "최근"이라고 쓴다.
- 후보의 detail(원문 페이지 발췌)도 사실 소스다. 대형 발표는 summary가 짧으니 detail에서 무엇·누가·언제부터를 가져온다.
- 후보의 kr_news는 최근 7일 국내 기사 수다. 화제성 판단에만 쓰고 본문에 숫자로 쓰지 않는다.
- summary·detail로도 설명이 부족하면, 모르는 부분은 "공식 페이지에서 확인하세요"로 처리한다.
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
            + " 후보에 \"major\": true(대형 발표: 새 제품·새 모델 출시)가 있으면 그중 하나를 고른다."
            + " 본문은 700~1,100자로 짧게 쓴다."
            + " 후보가 모두 사소하거나 일반인에게 '그래서 뭐?'인 소식이면 글을 쓰지 말고 첫 줄에 `SKIP: <사유 한 줄>`만 출력한다.")
    if kind == "instagram":
        task = ("카드뉴스 1개를 써라. 출력은 에이전트 정의의 6장 스키마를 지킨 JSON 한 덩어리뿐이다"
                "(설명·코드펜스 금지). 아래 '같은 소식의 블로그 초안'과 같은 소식을 다루고, 예시·수치·비유는 블로그와 똑같이 쓴다.")
        if blog:
            task += f"\n\n# 같은 소식의 블로그 초안 (이 글의 예시·수치를 그대로 쓴다. 여기 없는 수치를 새로 만들지 않는다)\n{blog}"
    return f"""{task}

{FACT_RULE}

# 후보 소식 (점수순, 이 중 1개만 고른다)
{cands}

# 모니터 리포트 ({research_path.name})
{research}"""


class ResponseError(RuntimeError):
    """응답에서 쓸 수 있는 본문(text)을 얻지 못했다. retryable이면 한도를 늘려 다시 부르면 될 수 있다."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


def extract_text(msg) -> str:
    """msg.content[0]이 항상 TextBlock이라고 가정하면 안 된다.
    claude-opus-5는 thinking이 기본 켜짐이라 응답 앞에 ThinkingBlock(.text 속성 없음)이 오고,
    thinking이 max_tokens를 다 쓰면 text 블록 없이 끝난다. content 배열에서 type == 'text'인 블록만 이어붙이고,
    본문이 비었거나 잘렸으면 ResponseError로 알린다(호출부가 한도를 늘려 1회 재시도한다)."""
    blocks = list(getattr(msg, "content", None) or [])
    types = [getattr(b, "type", None) for b in blocks]
    stop = getattr(msg, "stop_reason", None)
    parts = [b.text for b in blocks if getattr(b, "type", None) == "text" and getattr(b, "text", "")]
    if not parts:
        raise ResponseError(f"응답에 text 블록이 없습니다 (content types: {types}, stop_reason: {stop})",
                            retryable=stop == "max_tokens")
    text = "\n".join(parts)
    if stop == "max_tokens":
        raise ResponseError(f"응답이 max_tokens에서 잘렸습니다 (본문 {len(text):,}자, content types: {types})",
                            retryable=True)
    return text


def complete(client, kind: str, system: str, user: str) -> str:
    """모델 호출 + 본문 추출. thinking이 한도를 다 쓰면 max_tokens를 두 배로 늘려 한 번 더 부른다."""
    budget = MAX_TOKENS[kind]
    for attempt in (1, 2):
        msg = client.messages.create(model=MODEL, max_tokens=budget, system=system, thinking=THINKING,
                                     messages=[{"role": "user", "content": user}])
        try:
            text = extract_text(msg)
        except ResponseError as e:
            if not e.retryable or attempt == 2:
                raise
            nxt = min(budget * 2, MAX_TOKENS_CAP)
            print(f"{kind}: {e} → max_tokens {budget:,}에서 {nxt:,}로 올려 재시도")
            budget = nxt
            continue
        out_tokens = getattr(getattr(msg, "usage", None), "output_tokens", None)
        print(f"{kind}: 응답 {len(text):,}자" + (f" (출력 토큰 {out_tokens:,})" if out_tokens else ""))
        return text
    raise RuntimeError("도달하지 않는 경로")  # 위 루프가 항상 return 또는 raise


@observe(name="generate-blog-post", capture_input=False)  # 입력(리서치 전문)은 하위 generation에 이미 기록됨
def generate_blog_post(client, system: str, user: str) -> str:
    return complete(client, "blog", system, user)


@observe(name="generate-instagram-post", capture_input=False)
def generate_instagram_post(client, system: str, user: str) -> str:
    return complete(client, "instagram", system, user)


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:60] or "post"


def parse_instagram_json(text: str) -> dict:
    """응답에서 JSON 객체만 뽑아 파싱한다(코드펜스나 앞뒤 설명이 붙어도 된다)."""
    body = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip(), count=1, flags=re.S)
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("JSON 객체를 찾지 못했습니다")
    return json.loads(body[start:end + 1])


def report_style_hits(text: str) -> list[str]:
    """'~했다/…습니다' 보고서체로 끝나는 구간. 대화체 '~해요/~거든요' 규칙(에이전트 0장)을 강제한다."""
    return [m.group(0) for m in REPORT_ENDING_RE.finditer(text)]


def validate_instagram(data: dict) -> list[str]:
    """렌더러가 그대로 쓸 수 있는지 검사한다. 문제가 있으면 사람이 읽을 수 있는 목록으로 돌려준다."""
    if not isinstance(data, dict):
        return ["최상위가 JSON 객체가 아닙니다"]
    problems: list[str] = []
    for key in ("badge", "subtitle", "meta", "cover_visual", "caption"):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"{key}가 비었습니다")
    if len(str(data.get("badge") or "")) > MAX_BADGE:
        problems.append(f"badge가 {len(str(data.get('badge')))}자입니다 ({MAX_BADGE}자 이내)")
    if len(str(data.get("subtitle") or "")) > MAX_SUBTITLE:
        problems.append(f"subtitle가 {len(str(data.get('subtitle')))}자입니다 ({MAX_SUBTITLE}자 이내)")
    if len(str(data.get("meta") or "")) > MAX_META:
        problems.append(f"meta가 {len(str(data.get('meta')))}자입니다 ({MAX_META}자 이내)")
    if len(str(data.get("caption") or "")) > 400:
        problems.append(f"caption이 {len(str(data.get('caption')))}자입니다 (300자 이내)")

    # 표지 A형: 3줄 제목 + 그 안의 강조어 하나
    title_lines = data.get("title_lines")
    if not isinstance(title_lines, list) or len(title_lines) != TITLE_LINE_COUNT:
        problems.append(f"title_lines는 정확히 {TITLE_LINE_COUNT}줄이어야 합니다")
        title_lines = []
    for i, line in enumerate(title_lines, start=1):
        if not isinstance(line, str) or not line.strip():
            problems.append(f"title_lines {i}번째 줄이 비었습니다")
        elif len(line.replace("\n", "")) > MAX_TITLE_LINE:
            problems.append(f"title_lines {i}번째 줄이 {len(line)}자입니다 ({MAX_TITLE_LINE}자 이내)")
    highlight_word = data.get("highlight_word")
    title_text = " ".join(str(x) for x in title_lines)
    if not isinstance(highlight_word, str) or not highlight_word.strip():
        problems.append("highlight_word가 비었습니다")
    elif highlight_word not in title_text:
        problems.append("highlight_word는 title_lines 안에 있는 글자여야 합니다")
    elif not 2 <= len(highlight_word) <= 7:
        problems.append(f"highlight_word가 {len(highlight_word)}자입니다 (2~7자)")

    slides = data.get("slides")
    if not isinstance(slides, list) or len(slides) != SLIDE_COUNT:
        problems.append(f"slides는 정확히 {SLIDE_COUNT}개여야 합니다 (지금 {len(slides) if isinstance(slides, list) else '없음'})")
        slides = []
    for i, slide in enumerate(slides, start=2):
        if not isinstance(slide, dict):
            problems.append(f"{i}장이 객체가 아닙니다")
            continue
        if slide.get("mode") not in ("fullbleed", "card"):
            problems.append(f"{i}장 mode는 fullbleed 또는 card여야 합니다 (지금 {slide.get('mode')!r})")
        for key in ("kicker", "headline", "body", "visual_hint"):
            if not isinstance(slide.get(key), str) or not slide[key].strip():
                problems.append(f"{i}장 {key}가 비었습니다")
        headline_len = len(str(slide.get("headline") or "").replace("\n", "").replace(" ", ""))
        if headline_len > MAX_HEADLINE:
            problems.append(f"{i}장 headline이 {headline_len}자입니다 ({MAX_HEADLINE}자 이내, 띄어쓰기 제외)")
        body_len = len(str(slide.get("body") or ""))
        if body_len < BODY_MIN_CHARS:
            problems.append(f"{i}장 body가 {body_len}자입니다 (3~5줄·{BODY_MIN_CHARS}자 이상)")
        if body_len > BODY_MAX_CHARS:
            problems.append(f"{i}장 body가 {body_len}자입니다 (3~5줄·{BODY_MAX_CHARS}자 이내)")
        hl = slide.get("headline_highlight")
        if hl is not None and (not isinstance(hl, str) or hl not in str(slide.get("headline") or "")):
            problems.append(f"{i}장 headline_highlight는 headline 안에 있는 글자여야 합니다")

    cta = data.get("cta")
    cta_headline = str(cta.get("headline") or "") if isinstance(cta, dict) else ""
    if not isinstance(cta, dict) or not cta_headline.strip():
        problems.append("cta.headline이 비었습니다")
    hashtags = data.get("hashtags")
    if not isinstance(hashtags, list) or not 4 <= len(hashtags) <= 10 or not all(
            isinstance(t, str) and t.startswith("#") for t in hashtags):
        problems.append("hashtags는 '#'로 시작하는 4~10개 목록이어야 합니다")

    text = " ".join([title_text, str(data.get("subtitle") or ""), str(data.get("caption") or "")] + [
        f"{s.get('kicker', '')} {s.get('headline', '')} {s.get('body', '')}"
        for s in slides if isinstance(s, dict)])
    banned = [w for w in BANNED_PHRASES if w in text]
    if banned:
        problems.append("금지어: " + ", ".join(banned))

    # 말투: 표지·본문·CTA는 '~해요'체. 캡션은 사람이 다듬는 자리라 검사에서 뺀다.
    tone_texts = [("표지 제목", title_text), ("표지 부제", str(data.get("subtitle") or "")),
                  ("CTA", f"{cta_headline} {cta.get('body', '') if isinstance(cta, dict) else ''}")]
    for i, slide in enumerate(slides, start=2):
        if isinstance(slide, dict):
            tone_texts.append((f"{i}장", f"{slide.get('kicker', '')} {slide.get('headline', '')} {slide.get('body', '')}"))
    for label, value in tone_texts:
        hits = report_style_hits(value)
        if hits:
            problems.append(f"{label} 말투: '{hits[0]}' 같은 보고서체 — '~해요/~거든요'로 바꿔 주세요")
    return problems


def _instagram_or_problems(text: str) -> tuple[dict, list[str]]:
    """응답 문자열 → (데이터, 문제 목록). 파싱이 깨져도 예외를 밖으로 던지지 않는다."""
    try:
        data = parse_instagram_json(text)
    except (ValueError, json.JSONDecodeError) as e:
        return {}, [f"JSON 파싱 실패: {e}"]
    return data, validate_instagram(data)


def instagram_markdown(data: dict, today: str) -> str:
    """JSON을 사람이 읽는 카드뉴스 대본으로 풀어 쓴다(Slack 스레드·수동 검수용)."""
    slides = data["slides"]
    title_lines = data.get("title_lines") or []
    lines = [f"# 인스타 카드뉴스 {today}", "",
             f"- 표지 배지: {data.get('badge', '-')}",
             f"- 표지 제목: **{' / '.join(title_lines)}** (강조: {data.get('highlight_word', '-')})",
             f"- 부제: {data.get('subtitle', '-')}  ({data.get('hook_type', '-')})",
             f"- 메타: {data.get('meta', '-')}",
             f"- 표지 그림: {data.get('cover_visual', '-')}"]
    for i, slide in enumerate(slides, start=2):
        lines += ["", f"## {i}. {slide.get('kicker', '')}", f"**{slide.get('headline', '')}**",
                  slide.get("body", ""), f"[그림: {slide.get('visual_hint', '')}]"]
    cta = data.get("cta") or {}
    lines += ["", f"## {len(slides) + 2}. CTA", f"**{cta.get('headline', '')}**", cta.get("body", ""),
              "", "## 캡션", data.get("caption", ""), "", " ".join(data.get("hashtags", []))]
    return "\n".join(lines) + "\n"


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
        # 커밋 대상(research/)에 발행용 사본을 남긴다 — 원문 그대로(프론트매터 포함)
        RESEARCH_CONTENT_DIR.mkdir(parents=True, exist_ok=True)
        publish_path = RESEARCH_CONTENT_DIR / f"{today}-blog.md"
        publish_path.write_text(blog, encoding="utf-8")
        print(f"발행용 사본: {publish_path.relative_to(ROOT)}")
        result["blog_publish_copy"] = str(publish_path.relative_to(ROOT))
        blog_for_insta = blog

    print("인스타그램 카드뉴스 생성 중...")
    insta_user = build_user_prompt("instagram", top, research, today, research_path, blog_for_insta)
    insta = generate_instagram_post(client, agent_prompt("content-instagram-writer"), insta_user)
    if skip_reason(insta) is not None:
        print(f"인스타: SKIP 응답 — 저장하지 않음 ({skip_reason(insta)})")
        return result

    data, problems = _instagram_or_problems(insta)
    if problems:
        # 렌더러가 바로 쓸 수 없는 JSON은 커밋하지 않는다. 무엇이 틀렸는지 알려 한 번만 교정 요청한다.
        print("인스타 JSON 검증 실패: " + "; ".join(problems) + " → 1회 교정 요청")
        repair_user = (insta_user + f"\n\n# 직전 출력 (고칠 대상)\n{insta[:8000]}"
                       + "\n\n# 고칠 점\n- " + "\n- ".join(problems)
                       + "\n\n위 문제만 고친 JSON 전체를 다시 출력한다. 에이전트 정의의 스키마를 지키고, 설명·코드펜스 금지.")
        data, problems = _instagram_or_problems(
            generate_instagram_post(client, agent_prompt("content-instagram-writer"), repair_user))
    if problems:
        print("인스타: 교정 후에도 JSON이 규격에 안 맞아 저장하지 않습니다 — " + "; ".join(problems))
        result["instagram_error"] = problems
        return result

    data["handle"] = HANDLE  # 계정 헤더는 모델이 쓰게 두지 않고 고정한다
    INSTAGRAM_DIR.mkdir(parents=True, exist_ok=True)
    ig_path = INSTAGRAM_DIR / f"{today}-instagram.md"
    ig_path.write_text(instagram_markdown(data, today), encoding="utf-8")
    print(f"인스타 저장: {ig_path}")
    result["instagram"] = str(ig_path.relative_to(ROOT))
    # 렌더러 입력 — 워크플로가 research/만 커밋하므로 여기 둬야 다음 단계가 받는다
    RESEARCH_CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = RESEARCH_CONTENT_DIR / INSTAGRAM_JSON_NAME.format(date=today)
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"인스타 JSON: {json_path.relative_to(ROOT)}")
    result["instagram_json"] = str(json_path.relative_to(ROOT))
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
