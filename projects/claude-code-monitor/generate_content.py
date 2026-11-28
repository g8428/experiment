"""
리서치 파일을 읽어 블로그 포스트 + 인스타그램 포스팅을 자동 생성.
Anthropic Python SDK 직접 호출 (Claude Code 없이 Actions/로컬 모두 동작).

실행: python projects/claude-code-monitor/generate_content.py [research_file_path]
의존성: anthropic (pip install anthropic)
트레이싱(선택): LANGFUSE_* 환경변수가 있으면 Langfuse로 전송 (shared/utils/langfuse_tracing.py 참고)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:  # 로컬 실행 시 레포 루트 .env 로드 (Langfuse 초기화보다 먼저여야 한다)
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent.parent / ".env")
except ImportError:
    pass

import anthropic

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "shared" / "utils"))
from langfuse_tracing import TRACING_ENABLED, flush, get_client, observe, propagate_attributes, setup_tracing  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from cards import schema  # noqa: E402

setup_tracing()  # Anthropic SDK 호출을 generation(모델/토큰/입출력)으로 자동 수집

RESEARCH_DIR = ROOT / "research"
BLOG_DIR = ROOT / "content" / "blog"
INSTAGRAM_DIR = ROOT / "content" / "instagram"


def latest_research_file() -> Path:
    files = sorted(RESEARCH_DIR.glob("claude-code-*.md"), reverse=True)
    if not files:
        raise FileNotFoundError(f"research/ 폴더에 claude-code-*.md 파일이 없습니다.")
    return files[0]


def latest_news_file() -> Path | None:
    files = sorted(RESEARCH_DIR.glob("ai-news-*.md"), reverse=True)
    return files[0] if files else None


def extract_text(msg) -> str:
    """msg.content[0]이 항상 TextBlock이라고 가정하면 안 된다.
    claude-opus-5는 응답 앞에 ThinkingBlock(.text 속성 없음)을 먼저 반환할 수 있어서,
    content 배열에서 type == 'text'인 블록만 골라 이어붙인다."""
    parts = [block.text for block in msg.content if getattr(block, "type", None) == "text"]
    if not parts:
        raise RuntimeError(f"응답에 text 블록이 없습니다. content types: {[getattr(b, 'type', None) for b in msg.content]}")
    return "\n".join(parts)


@observe(name="generate-blog-post", capture_input=False)  # 입력(리서치 전문)은 하위 generation에 이미 기록됨
def generate_blog_post(client: anthropic.Anthropic, research: str, today: str) -> str:
    prompt = f"""다음 리서치 파일을 읽고 한국 개발자 커뮤니티(벨로그, 티스토리)용 기술 블로그 포스트를 작성해라.

# 작성 원칙
- 구어체 + 존댓말 혼용 ("~입니다", "~해요" 자연스럽게)
- 기술 용어는 영어 원문 유지, 처음 등장 시 한국어 설명 병기
- 코드 블록: 실제 동작하는 코드만, 인라인 주석 한국어
- 단락: 3~5줄. 긴 단락 금지
- 이모지: 소제목 앞에 1개씩만
- 3,000자 이내
- "혁신적인", "패러다임 전환" 같은 buzzword 금지

# 구조
1. 제목 (클릭 유도 + 키워드, 30자 이내)
2. 한 줄 요약
3. 들어가며 (왜 지금 이 글이 필요한지)
4. 본문 섹션 2~4개 (소제목 + 설명 + 코드/링크/표)
5. 바로 써먹기 (오늘 당장 실행할 3단계 액션)
6. 마치며 (한 문장 + 다음 편 예고)

마크다운 형식으로 전체 포스트만 출력. 설명이나 메타 코멘트 없이.

---

{research}"""

    msg = client.messages.create(
        model="claude-opus-5",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return extract_text(msg)


IG_PROMPT = """다음은 최근 7일 AI 뉴스 수집 파일이다. 이 중 그 주에 가장 화제성 있는 소식 1개(또는 한 이야기로 묶을 수 있는 2개)를 골라 인스타그램 카드뉴스 6~8장(최대 10장) 원고를 **JSON 하나만** 출력해라. 설명·코드펜스 없이 JSON만.
공식 발표(출처에 "공식 발표"가 붙은 항목)를 우선 근거로 삼고, 언론 기사는 보조로만 쓴다.

# JSON 스키마
{
  "cards": [
    {"type": "photo", "kicker": "...", "title": "...", "title_highlight": "title 안의 핵심 단어 1개", "body": "한 줄 부제(생략 가능)",
     "image": {"kind": "ai", "prompt": "..."}},
    {"type": "photo|figure", "kicker": "...", "title": "...", "body": "...",
     "source_url": "근거 링크(수집 파일에 있는 링크, 필수)",
     "image": {"kind": "official_og|wikimedia|ai|repo_og|owner_avatar|readme_image",
               "url": "official_og: 공식 발표 페이지 링크 / wikimedia: Commons 파일 페이지(선택)",
               "prompt": "ai: 장면 묘사 / wikimedia: 영어 검색어",
               "repo": "owner/name (GitHub 계열 kind일 때만)",
               "source_note": "출처: 회사명 공식 발표 처럼 짧게"}},
    {"type": "end", "kicker": "한 줄 정리", "title": "...", "body": "저장 유도 한 줄"}
  ],
  "caption": "...",
  "hashtags": ["#...", "... 10~15개"]
}
- 첫 장은 photo(image.kind=ai), 마지막은 end. 6~8장 권장, 최대 10장.
- photo: 사진이 카드 전체 배경. figure: 어두운 배경 위 흰 박스에 도표/스크린샷/대표 이미지(contain).
- 표지·마무리를 뺀 모든 카드에 source_url(수집 파일에 있는 https 링크)을 남긴다. 카드 하단엔 "출처: 회사명/매체명"만 표기된다.

# 이미지 규칙
- 본문 이미지 우선순위: (1) official_og = 공식 발표 페이지의 대표 이미지(url에 그 페이지 링크) (2) wikimedia = 위키미디어 공용 이미지(CC/퍼블릭 도메인만 자동 선택됨, prompt에 영어 검색어) (3) ai.
- 언론사 기사 사진·이미지는 쓰지 않는다(저작권). 언론 기사만 근거인 카드는 ai로 한다.
- GitHub 계열 kind(repo_og 등)는 오픈소스 소식일 때만 쓰고, 수집 파일에 있는 owner/name만 쓴다.

# 표지(첫 카드) 규칙
- 제목은 기본적으로 "의아함·결과 숨김" 방식: 결과를 감추고 궁금하게("AI한테 원시인 말투 시켰더니 생긴 일"). 리서치에 강한 숫자 근거가 있을 때만 "손실 회피+숫자"("요금 65%를 그냥 버리는 중")를 허용. 공감 상황형은 쓰지 않는다. 내용을 다 말하지 말고 다음 장을 넘기게 만든다. 두 줄 안쪽(\n으로 줄바꿈 가능, 한 줄 9자 안팎).
- 키커는 근거 있는 사회적 증거나 대상 지목("AI 쓰는 직장인 필독", 수집 파일에 있는 수만).
- title_highlight: 제목 안의 부분 문자열 1개(강조색 처리). body는 짧은 부제(생략 가능).
- image.prompt: 제목의 이상한 설정을 그대로 보여 주는 웃기고 과장된 장면(예: 원시인이 노트북으로 진지하게 코딩). 글자·로고 없음, 실존 인물 얼굴 금지.

# 말투·흐름
- 친근한 해요체("~했대요", "~해요", "~입니다" 섞어서). 반말·밈체·과장·딱딱한 보고서체 금지.
- 흐름은 이야기: 훅(질문) -> 무슨 일이야? -> 어떻게 한 거야? -> 근거/실제 결과 -> 주의할 점 -> 저장 유도.
- 본문 카드 키커는 질문형("무슨 일이야?", "어떻게 한 거야?", "주의할 점"). 제목은 10자 안팎, 설명은 60자 안팎 1~2문장.
- 이모지는 마지막 카드에 1개 정도만.
- 캡션 700자 이내, 해요체, 마지막에 자료 출처. 이모지 3개 이내.

# 사실 규칙
- 숫자·사실은 수집 파일에 있는 값만. 근거가 있을 때 설명 문장 안에 자연스럽게. 추측·창작 금지.
- 모든 사실에 출처를 남긴다(source_url, 캡션 끝에 출처 회사명/매체명).

---

"""


def parse_json_text(text: str):
    """모델 응답에서 JSON 객체를 꺼낸다(코드펜스·앞뒤 잡설 허용)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("JSON 객체를 찾지 못함")
    return json.loads(text[start : end + 1])


@observe(name="generate-instagram-post", capture_input=False)
def generate_instagram_post(client: anthropic.Anthropic, research: str, today: str) -> dict:
    """카드 JSON 스펙(검증 완료)을 반환. 파싱/검증 실패 시 1회 재시도 후 RuntimeError."""
    messages = [{"role": "user", "content": IG_PROMPT + research}]
    last_err = ""
    for attempt in (1, 2):
        msg = client.messages.create(model="claude-opus-5", max_tokens=4096, messages=messages)
        text = extract_text(msg)
        try:
            return schema.validate(parse_json_text(text))
        except (ValueError, schema.SpecError) as e:  # JSONDecodeError도 ValueError
            last_err = str(e)
            print(f"인스타 JSON 오류(시도 {attempt}/2): {last_err}")
            messages = messages + [
                {"role": "assistant", "content": text},
                {"role": "user", "content": f"JSON이 올바르지 않아요: {last_err}\n스키마에 맞게 JSON 하나만 다시 출력해라."},
            ]
    raise RuntimeError(f"인스타 카드 JSON 생성 실패(2회 시도): {last_err}")


def slugify(text: str) -> str:
    import re
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:60]


def extract_title(blog_md: str) -> str:
    for line in blog_md.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "claude-code-trends"


@observe(name="generate-weekly-content", capture_input=False)  # 1회 실행 = 1 trace
def run(research_path: Path, today: str) -> dict:
    research = research_path.read_text(encoding="utf-8")
    if TRACING_ENABLED:
        get_client().update_current_span(input={"research_file": research_path.name})

    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY env var 자동 사용

    print("블로그 포스트 생성 중...")
    blog = generate_blog_post(client, research, today)
    title_slug = slugify(extract_title(blog))
    BLOG_DIR.mkdir(parents=True, exist_ok=True)
    blog_path = BLOG_DIR / f"{today}-{title_slug}.md"
    blog_path.write_text(blog, encoding="utf-8")
    print(f"블로그 저장: {blog_path}")

    print("인스타그램 포스팅 생성 중...")
    news_path = latest_news_file()  # 인스타 카드는 AI 뉴스 전반(블로그는 Claude Code 리서치 그대로)
    if news_path:
        print(f"인스타 입력(AI 뉴스): {news_path}")
        ig_input = news_path.read_text(encoding="utf-8")
    else:
        print("ai-news 파일 없음 -> Claude Code 리서치로 대체")
        ig_input = research
    spec = generate_instagram_post(client, ig_input, today)
    INSTAGRAM_DIR.mkdir(parents=True, exist_ok=True)
    (INSTAGRAM_DIR / f"{today}-instagram.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    ig_path = INSTAGRAM_DIR / f"{today}-instagram.md"  # Slack 스레드용 (JSON에서 생성)
    ig_path.write_text(schema.to_markdown(spec), encoding="utf-8")
    print(f"인스타 저장: {ig_path}")

    print("\n=== 컨텐츠 생성 완료 ===")
    print(f"블로그: {blog_path}")
    print(f"인스타: {ig_path}")
    return {"blog": str(blog_path.relative_to(ROOT)), "instagram": str(ig_path.relative_to(ROOT))}


def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    research_path = Path(sys.argv[1]) if len(sys.argv) > 1 else latest_research_file()
    print(f"리서치 파일: {research_path}")

    try:
        with propagate_attributes(tags=["claude-code-monitor", "weekly-content"], metadata={"research_date": today}):
            run(research_path, today)
    finally:
        flush()  # 짧게 끝나는 스크립트라 종료 전 전송 필수


if __name__ == "__main__":
    main()
