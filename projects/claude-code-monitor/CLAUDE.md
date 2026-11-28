# Claude Code 트렌드 모니터

## 목적

GitHub에서 Claude Code 관련 인기 오픈소스 리포를 매주 자동 추적하고,
그 결과를 기반으로 블로그/인스타 컨텐츠를 자동 생성하는 파이프라인.

## 파이프라인

```
[월요일 Actions]
monitor.py (주 1회)
  → research/claude-code-trends-YYYY-MM-DD.md   ── 블로그 입력 (Claude Code 트렌드)
news_collect.py (RSS 10곳, 최근 7일)
  → research/ai-news-YYYY-MM-DD.md              ── 인스타 입력 (AI 뉴스 전반, 제목·링크·200자 요약만)
generate_content.py
  → content/blog/YYYY-MM-DD-*.md
  → content/instagram/YYYY-MM-DD-instagram.json (카드 스펙) + .md (Slack용)
cards/render.py : 이미지 수집(AI/공식 og/위키미디어/GitHub) → cards/out/NN.png (1080×1350)
upload-artifact `ig-cards` (7일, 커밋 안 함)
slack_notify.py : #성과보고 요약(`ig-run:<run id>` 표식) + 스레드에 원고·카드 PNG·캡션
                  + "✅ 반응을 달면 인스타에 게시합니다 (오너만 유효)"

[월·화 매시 claude-code-ig-publish.yml]
ig_publish.py --check : 최근 7일 `ig-run:` 메시지에 오너(SLACK_OWNER_USER_ID)의 ✅가 있나?
  없음/이미 게시 완료 → 조용히 종료
  있음 → ig-cards 다운로드 → ig-media 브랜치에 JPEG 커밋(승인 후에만) → Instagram Graph API 캐러셀 게시
       → 스레드에 "✅ 인스타 게시 완료: <링크>" (실패 시 "❌ 인스타 게시 실패: …" + 로그 URL)
```

카드 JSON 스키마·검증: `cards/schema.py`. 템플릿: `cards/templates/card.html.j2`(Pretendard, photo/figure/end 3종).
브랜드 라벨 기본값 "청년재테크 · AI 뉴스 카드"는 env `IG_BRAND_LABEL` 또는 JSON `brand_label`로 변경.

## 실행

```bash
# 수동 실행
python projects/claude-code-monitor/monitor.py

# 환경변수 (선택 — 없어도 동작, rate limit 낮아짐)
GITHUB_TOKEN=ghp_xxx python projects/claude-code-monitor/monitor.py
```

## 파일 구조

```
projects/claude-code-monitor/
  monitor.py          # GitHub API 트렌드 수집
  news_collect.py     # AI 뉴스 RSS 수집 (FEEDS 상수에서 피드 추가/삭제)
  generate_content.py # 블로그 md + 인스타 카드 JSON 생성
  cards/              # schema.py, images.py, render.py, templates/, sample.json (out/ 은 gitignore)
  slack_notify.py     # #성과보고 + 카드 미리보기
  ig_publish.py       # ✅ 승인 확인 → 인스타 게시
  ig_whoami.py        # IG_USER_ID 찾기 도우미
  tests/              # python -m pytest projects/claude-code-monitor/tests -q
  history.json        # 이전 실행 스타 수 (자동 생성)
  CLAUDE.md           # 이 파일

research/
  claude-code-ecosystem-2026-09-27.md  # 초기 심층 조사
  claude-code-trends-YYYY-MM-DD.md     # 주간 모니터 결과 (블로그 입력)
  ai-news-YYYY-MM-DD.md                # 주간 AI 뉴스 (인스타 입력, 공개돼도 되는 요약만)

content/                               # 원고 본문은 커밋하지 않는다 (Slack 스레드로만)
  blog/YYYY-MM-DD-*.md
  instagram/YYYY-MM-DD-instagram.json  # 카드 스펙 (+ .md: Slack용)
```

### 카드 이미지 규칙
- 표지: OpenAI Images(`OPENAI_API_KEY`, 모델 `OPENAI_IMAGE_MODEL` 기본 `gpt-image-1`). 키 없으면 어두운 단색 + 경고(로컬 테스트).
- 본문: `official_og`(공식 발표 og:image) → `wikimedia`(CC/퍼블릭 도메인만, 작성자·라이선스 표기) → `ai`. 언론사 기사 사진은 쓰지 않는다. 오픈소스 소식이면 `repo_og`/`owner_avatar`/`readme_image`. 실패하면 자동으로 AI 폴백.
- Instagram은 JPEG만 공식 지원하므로 게시 직전 PNG를 JPEG로 변환해 `ig-media`에 올린다.

### 로컬 렌더 확인
```bash
pip install pillow playwright jinja2 requests feedparser && playwright install chromium
python projects/claude-code-monitor/cards/render.py projects/claude-code-monitor/cards/sample.json   # cards/out/01~06.png
python projects/claude-code-monitor/news_collect.py --check     # 피드 상태 점검
IG_ACCESS_TOKEN=... python projects/claude-code-monitor/ig_whoami.py   # IG_USER_ID 확인
```

## GitHub Actions 스케줄

Cowork/클라우드 루틴은 GitHub 조회가 안 되어 Actions로 이전했다.
워크플로: `.github/workflows/claude-code-monitor.yml` (VS Code는 GitHub Actions 확장으로 실행 상태 확인)

- 주기: 매주 월요일 오전 9시 (KST), `workflow_dispatch`로 수동 실행 가능
- 단계: `monitor.py` → `news_collect.py` → `generate_content.py`(Anthropic API) → `cards/render.py` → 아티팩트 `ig-cards` → research 커밋(트렌드 + ai-news) → `slack_notify.py`
- `news_collect`·`render`는 `continue-on-error` (실패해도 블로그·research 커밋·Slack 보고는 진행. 렌더 실패 시 `ig-run:` 표식이 없어 게시 대상이 되지 않음)
- 컨텐츠(블로그/인스타 원고)와 카드 이미지는 GitHub `main`에 커밋하지 않는다. Slack 스레드로만 전달. **카드 이미지는 오너 ✅ 승인 후에만** `ig-media` 브랜치(orphan)에 올라간다 (Instagram이 공개 URL을 요구함. 레포가 공개라 승인 전에는 절대 올리지 않음)
- Slack: 웹훅 대신 Bot Token(`chat.postMessage`, 파일 업로드, 반응 조회)

필요한 리포지토리 Secrets (Settings → Secrets and variables → Actions):

| Secret | 설명 |
|--------|------|
| `ANTHROPIC_API_KEY` | 컨텐츠 생성용 |
| `SLACK_BOT_STAFF1_TOKEN` | `xoxb-...` (slack-staff1 봇). 스코프 `chat:write`, `files:write`(카드 업로드), `reactions:read`(✅ 확인), `channels:history`(표식 메시지 조회). 비공개 채널이면 `groups:history` 도 필요. 스코프 추가 후 앱 재설치 |
| `SLACK_CHANNEL_ID` | #성과보고 채널 ID (`C...`). 봇을 채널에 `/invite` 해야 함 |
| `SLACK_OWNER_USER_ID` | 오너 Slack 멤버 ID (`U...`). 이 사람의 ✅만 승인으로 인정 |
| `OPENAI_API_KEY` | 표지·AI 이미지 생성 (Images API) |
| `OPENAI_IMAGE_MODEL` | (선택) 기본 `gpt-image-1` |
| `IG_ACCESS_TOKEN` | Meta 시스템 사용자 토큰 (`instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`) |
| `IG_USER_ID` | 인스타 프로페셔널 계정 ID. `ig_whoami.py` 로 확인 |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_BASE_URL` | (선택) Langfuse 트레이싱. 없으면 자동으로 꺼짐 — `shared/utils/README.md` 참고 |

## 서브에이전트

| 에이전트 | 파일 | 역할 |
|---------|------|------|
| content-blog-writer | `.claude/agents/content-blog-writer.md` | 벨로그/티스토리 블로그 포스트 |
| content-instagram-writer | `.claude/agents/content-instagram-writer.md` | 인스타 카드뉴스 캡션+구성 |

## 참고

- 초기 심층 조사: `research/claude-code-ecosystem-2026-09-27.md`
- GitHub API rate limit: 인증 없이 60 req/h, GITHUB_TOKEN 있으면 5,000 req/h
- 검색 쿼리 수정: `monitor.py`의 `SEARCH_QUERIES` 리스트
