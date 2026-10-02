"""
리서치 파일을 읽어 블로그 포스트 + 인스타그램 포스팅을 자동 생성.
Anthropic Python SDK 직접 호출 (Claude Code 없이 Actions/로컬 모두 동작).

실행: python projects/claude-code-monitor/generate_content.py [research_file_path]
의존성: anthropic (pip install anthropic)
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic

ROOT = Path(__file__).parent.parent.parent
RESEARCH_DIR = ROOT / "research"
BLOG_DIR = ROOT / "content" / "blog"
INSTAGRAM_DIR = ROOT / "content" / "instagram"


def latest_research_file() -> Path:
    files = sorted(RESEARCH_DIR.glob("claude-code-*.md"), reverse=True)
    if not files:
        raise FileNotFoundError(f"research/ 폴더에 claude-code-*.md 파일이 없습니다.")
    return files[0]


def extract_text(msg) -> str:
    """msg.content[0]이 항상 TextBlock이라고 가정하면 안 된다.
    claude-opus-5는 응답 앞에 ThinkingBlock(.text 속성 없음)을 먼저 반환할 수 있어서,
    content 배열에서 type == 'text'인 블록만 골라 이어붙인다."""
    parts = [block.text for block in msg.content if getattr(block, "type", None) == "text"]
    if not parts:
        raise RuntimeError(f"응답에 text 블록이 없습니다. content types: {[getattr(b, 'type', None) for b in msg.content]}")
    return "\n".join(parts)


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


def generate_instagram_post(client: anthropic.Anthropic, research: str, today: str) -> str:
    prompt = f"""다음 리서치 파일에서 가장 임팩트 있는 내용 1~2개를 골라 개발자 인스타그램 카드뉴스 포스팅을 작성해라.

# 작성 원칙
- 반말 + 친근한 어투 ("알아두면 개이득" 류)
- 숫자로 신뢰 구축: 스타 수, 설치 시간, 무료 여부 명시
- 슬라이드당 텍스트: 50자 이내
- 캡션: 700자 이내
- 이모지: 슬라이드당 1~2개, 캡션에 5개 이내

# 출력 형식
## 슬라이드 구성 (최대 10장)
각 슬라이드:
- [표지] 제목(20자), 서브(숫자 강조), 배경 컨셉
- [본문N] 헤드라인(10자), 설명(2~3줄), 시각 요소 제안
- [마무리] CTA

## 캡션
🔥 첫 줄 (임팩트, 여기서 끊김)

[더보기 후 본문: 핵심 3~5줄 + 액션 1가지]

## 해시태그 (10~15개)
#개발자 #ClaudeCode #AI에이전트 ... (실제 내용에 맞게)

---

{research}"""

    msg = client.messages.create(
        model="claude-opus-5",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return extract_text(msg)


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


def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    research_path = Path(sys.argv[1]) if len(sys.argv) > 1 else latest_research_file()
    print(f"리서치 파일: {research_path}")
    research = research_path.read_text(encoding="utf-8")

    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY env var 자동 사용

    print("블로그 포스트 생성 중...")
    blog = generate_blog_post(client, research, today)
    title_slug = slugify(extract_title(blog))
    BLOG_DIR.mkdir(parents=True, exist_ok=True)
    blog_path = BLOG_DIR / f"{today}-{title_slug}.md"
    blog_path.write_text(blog, encoding="utf-8")
    print(f"블로그 저장: {blog_path}")

    print("인스타그램 포스팅 생성 중...")
    instagram = generate_instagram_post(client, research, today)
    INSTAGRAM_DIR.mkdir(parents=True, exist_ok=True)
    ig_path = INSTAGRAM_DIR / f"{today}-instagram.md"
    ig_path.write_text(instagram, encoding="utf-8")
    print(f"인스타 저장: {ig_path}")

    print("\n=== 컨텐츠 생성 완료 ===")
    print(f"블로그: {blog_path}")
    print(f"인스타: {ig_path}")


if __name__ == "__main__":
    main()
