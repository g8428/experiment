# Claude Code 소식 모니터

## 목적

Claude Code·AI 도구 관련 큰 소식(공식 발표, 새 스킬, 급상승 오픈소스, 커뮤니티 화제)을 매주 월요일 자동으로 모으고,
그중 하나를 골라 **IT를 잘 모르는 일반인용 쉬운 블로그 소개글**과 인스타 카드뉴스 초안을 만드는 파이프라인.

왜 지금 구조가 됐는지(2026-10-14 v2 개편 배경, v1이 Remotion 영상 소식을 놓친 원인)는 `HANDOVER.md` 참고.

## 현재 상태 (2026-10-14)

- v2 코드는 `claude/charming-tesla-cypq91` 브랜치에 있고 아직 master에 머지되지 않았다. **Actions 스케줄은 master의 워크플로로 돈다** → 머지 전까지는 v1(주 1회)이 계속 돈다.
- v2는 로컬 `--dry-run --fixtures`(가짜 응답)로만 검증했다. 실제 외부 호출은 첫 수동 실행에서 확인해야 한다.
- 첫 실행은 기준선 저장(공식 목록·문서 링크 '새 항목' 0개가 정상).

## 파이프라인

```
매주 월요일 09:00 KST (GitHub Actions). 주 1회는 사용자가 의도한 설정이므로 임의로 바꾸지 않는다.
  monitor.py
    수집: Claude Code 릴리스·CHANGELOG / 공식 스킬·플러그인 폴더 / Anthropic 뉴스·공식 문서 목차
          / GitHub 신규·토픽 검색 / Hacker News / Reddit
    → 카테고리 태깅(영상·디자인·문서·오피스·자동화·에이전트·연동·코딩)
    → 중복 제거(research/state/) + 재부상 판정 → 중요도 점수 → 상위 10개
    → research/claude-code-trends-YYYY-MM-DD.md   (맨 위 "오늘의 핵심 3줄", 수집 실패 표시)
    → research/state/latest-top.json, research/state/claude-code-monitor.json
    → 월요일엔 "주간 키워드 감시 리스트 점검" 섹션 추가
  generate_content.py   (새 소식이 없으면 건너뜀)
    → 규칙: .claude/agents/content-blog-writer.md / content-instagram-writer.md 본문을 그대로 사용
    → content/blog/YYYY-MM-DD-{slug}.md, content/instagram/YYYY-MM-DD-instagram.md  (커밋 안 함)
  research/ 커밋 (github-actions[bot], master 직접 — 봇 예외 규칙)
  slack_notify.py → #성과보고: 핵심 3줄·수집 실패·감시 경고 + 초안은 스레드
```

## 실행

```bash
# 네트워크 없이 전체 흐름 확인 (가짜 응답, 파일 안 씀)
python projects/claude-code-monitor/monitor.py --dry-run --fixtures projects/claude-code-monitor/fixtures/dry_run_sample.json

# 실제 수집 (GITHUB_TOKEN 없어도 동작하지만 검색 rate limit이 낮다)
GITHUB_TOKEN=ghp_xxx python projects/claude-code-monitor/monitor.py
GITHUB_TOKEN=ghp_xxx python projects/claude-code-monitor/monitor.py --watchlist   # 감시 리스트 강제 포함

# 컨텐츠 생성
python projects/claude-code-monitor/generate_content.py --dry-run   # API 호출 없이 프롬프트 확인
ANTHROPIC_API_KEY=... python projects/claude-code-monitor/generate_content.py
```

수동 실행(Actions): GitHub → Actions → "Claude Code 트렌드 모니터 & 컨텐츠 생성" → Run workflow
(`watchlist` 체크 = 감시 리스트 포함, `skip_content` 체크 = API 비용 없이 수집만).
`gh` CLI: `gh workflow run claude-code-monitor.yml -f watchlist=true -f skip_content=true`

## 설정 바꾸기

모두 `config.json`에서 한다 (코드 수정 불필요).

| 바꾸고 싶은 것 | 키 |
|---|---|
| GitHub 검색 쿼리·토픽 | `github_search.queries` |
| 공식 소스(레포·폴더·페이지) | `official.*` |
| 카테고리 키워드 | `categories` |
| 점수 가중치·재부상 기준 | `scoring` |
| 감시 키워드·요일 | `watchlist` |
| 리포트에 싣는 개수 | `top_n` |

## 파일 구조

```
projects/claude-code-monitor/
  monitor.py           수집·점수·리포트
  config.json          수집 범위·점수·감시 키워드
  generate_content.py  블로그/인스타 초안 (에이전트 파일을 프롬프트로 사용)
  slack_notify.py      Slack 보고
  fixtures/dry_run_sample.json  드라이런용 가짜 응답 (실제 소식 아님)
  blog/                새 블로그 형식 완성 예시
  CLAUDE.md / HANDOVER.md

research/
  claude-code-trends-YYYY-MM-DD.md     주간 리포트 (2026-10-12 이전 것은 v1 형식)
  claude-code-ecosystem-2026-09-27.md  초기 심층 조사
  state/claude-code-monitor.json       중복 제거·스타 이력 상태 (봇이 커밋, 손대지 말 것)
  state/latest-top.json                오늘의 상위 목록

content/  (Actions에서는 커밋 안 하고 Slack 스레드로만 전달)
  blog/YYYY-MM-DD-{slug}.md
  instagram/YYYY-MM-DD-instagram.md
```

## Secrets

이미 쓰는 것 (Settings → Secrets and variables → Actions):

| Secret | 설명 |
|--------|------|
| `GITHUB_TOKEN` | Actions 기본 제공. 등록 불필요 |
| `ANTHROPIC_API_KEY` | 컨텐츠 생성용 |
| `SLACK_BOT_STAFF1_TOKEN` | `xoxb-...` (slack-staff1 봇), 스코프 `chat:write` |
| `SLACK_CHANNEL_ID` | #성과보고 채널 ID (`C...`). 봇을 채널에 `/invite` 해야 함 |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_BASE_URL` | (선택) Langfuse 트레이싱 |

v2 추가 수집원은 모두 공개 API라 **새 시크릿 없이** 동작하도록 만들었다. 아래는 범위를 더 넓히려면 필요한 것(지금 코드에는 없음):

| 필요한 시크릿 | 쓰임 | 언제 필요 |
|---|---|---|
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | Reddit OAuth API | Actions에서 Reddit 공개 JSON이 403으로 막힐 때 |
| `X_BEARER_TOKEN` | X(트위터) 검색 | 해외 화제를 더 빨리 잡고 싶을 때 (유료 플랜 필요할 수 있음, 확인 못 함) |
| `YOUTUBE_API_KEY` | 유튜브 영상 화제 | "클로드로 영상 만들기" 같은 시연 영상 추적 |

## 서브에이전트

| 에이전트 | 파일 | 역할 |
|---------|------|------|
| content-blog-writer | `.claude/agents/content-blog-writer.md` | 일반인용 쉬운 소개글 + SEO (한 글 한 소식). 블로그 규칙의 단일 원본 |
| content-instagram-writer | `.claude/agents/content-instagram-writer.md` | 쉬운 말 카드뉴스 |

## 참고

- GitHub API rate limit: 검색은 인증 시 분당 30회 → 쿼리 사이 2.5초 쉼. 일반 API는 인증 시 시간당 5,000회
- 소스 하나가 실패해도 나머지는 계속하고, 실패는 리포트 "⚠️ 수집 실패"와 Slack에 표시된다
