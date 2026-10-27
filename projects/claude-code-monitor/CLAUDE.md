# Claude Code 소식 모니터

## 목적

Claude Code·AI 도구 관련 큰 소식(공식 발표, 새 스킬, 급상승 오픈소스, 커뮤니티 화제)을 매주 월요일 자동으로 모으고,
그중 하나를 골라 **IT를 잘 모르는 일반인용 쉬운 블로그 소개글**과 인스타 카드뉴스 초안을 만드는 파이프라인.

왜 지금 구조가 됐는지(2026-10-14 v2 개편 배경, v1이 Remotion 영상 소식을 놓친 원인, v2.1 글감 선별 기준)는 `HANDOVER.md` 참고.

## 현재 상태 (2026-10-27)

- v2.1은 master에서 매주 월요일 돌고 있다(10-19, 10-26 리포트).
- **v2.2(대형 발표 우선·업계 소식·짧은 글)** 는 `claude/cc-monitor-big-news` 브랜치. 배경은 HANDOVER.md "2026-10-27". 오프라인 fixtures + 실제 anthropic.com/news 페이지로 검증했고, 업계 RSS 주소는 첫 실행에서 확인해야 한다.
- 새 수집원 `claude_products`는 첫 실행이 기준선이라 그때는 '새 제품' 0개가 정상.

## 파이프라인

```
매주 월요일 09:00 KST (GitHub Actions). 주 1회는 사용자가 의도한 설정이므로 임의로 바꾸지 않는다.
  monitor.py
    수집: Claude Code 릴리스·CHANGELOG / 공식 스킬·플러그인 폴더 / Anthropic 뉴스(JSON 기사 목록)·Claude 제품 목록·공식 문서 목차
          / 업계 RSS(OpenAI·Google AI·DeepMind) / GitHub 신규·토픽 검색 / Hacker News(업계 키워드는 300점 이상) / Reddit
    → 새 제품 페이지와 같은 제품을 다룬 글은 한 항목으로 합침
    → (월요일) 감시 키워드 검색 → 걸린 레포도 후보 풀에 추가
    → 릴리스 묶음: 이번 주기 릴리스·CHANGELOG를 줄 단위로 판정, 글감급 줄만 남김
    → 카테고리 태깅(영상·디자인·문서·오피스·자동화·에이전트·연동·코딩)
    → 중복 제거(research/state/) + 재부상 판정 → 중요도 점수 + 글감 가치(value) → 글감급만 상위 10개
       (🔥대형 발표 = 새 제품·새 모델 출시는 점수와 무관하게 맨 위)
    → research/claude-code-trends-YYYY-MM-DD.md   (맨 위 "오늘의 핵심 3줄", 수집 실패 표시)
    → research/state/latest-top.json, research/state/claude-code-monitor.json
    → 월요일엔 "주간 키워드 감시 리스트 점검" 섹션 추가
  generate_content.py   (글감급 후보가 없으면 건너뜀)
    → 규칙: .claude/agents/content-blog-writer.md / content-instagram-writer.md 본문을 그대로 사용
    → content/blog/YYYY-MM-DD-{slug}.md, content/instagram/YYYY-MM-DD-instagram.md  (커밋 안 함)
    → 블로그 응답이 `SKIP: 사유`면 파일 없이 content/YYYY-MM-DD-skip.txt만 남기고 인스타 호출 생략
    → 인스타 호출에는 블로그 초안을 같이 넣어 같은 예시·수치를 쓰게 함
  research/ 커밋 (github-actions[bot], master 직접 — 봇 예외 규칙)
  slack_notify.py → #성과보고: 핵심 3줄·릴리스 묶음 한 줄·수집 실패·감시 경고 + 초안은 스레드 (SKIP이면 "이번 주는 글감 없음(사유)")
```

## 실행

```bash
# 네트워크 없이 전체 흐름 확인 (가짜 응답, 파일 안 씀)
python projects/claude-code-monitor/monitor.py --dry-run --fixtures projects/claude-code-monitor/fixtures/dry_run_sample.json

# 글감 선별 기준 회귀 확인 (2026-10-14 상황 재현)
python projects/claude-code-monitor/monitor.py --dry-run --fixtures projects/claude-code-monitor/fixtures/case1_minor_releases_only.json  # 후보 0개여야 함
python projects/claude-code-monitor/monitor.py --dry-run --fixtures projects/claude-code-monitor/fixtures/case2_big_news_vs_minor.json    # 영상·스킬이 위
python projects/claude-code-monitor/monitor.py --dry-run --fixtures projects/claude-code-monitor/fixtures/case3_mixed_release.json        # 글감급 줄만
python projects/claude-code-monitor/monitor.py --dry-run --fixtures projects/claude-code-monitor/fixtures/case4_big_launch_vs_repos.json   # 🔥대형 발표 2개가 레포보다 위, Duet은 한 칸
#   --dump <폴더> 를 붙이면 리포트·latest-top.json을 그 폴더에 저장 → generate_content.py --top 으로 이어서 확인

# 실제 수집 (GITHUB_TOKEN 없어도 동작하지만 검색 rate limit이 낮다)
GITHUB_TOKEN=ghp_xxx python projects/claude-code-monitor/monitor.py
GITHUB_TOKEN=ghp_xxx python projects/claude-code-monitor/monitor.py --watchlist   # 감시 리스트 강제 포함

# 컨텐츠 생성
python projects/claude-code-monitor/generate_content.py --dry-run   # API 호출 없이 프롬프트 확인
python projects/claude-code-monitor/generate_content.py --dry-run --top <dump폴더>/latest-top.json \
    --fake-blog projects/claude-code-monitor/fixtures/fake_blog_skip.md   # SKIP 경로 (fake_blog_ok.md = 정상 경로)
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
| 공식 소스(레포·폴더·페이지) | `official.*` (`article_pages` = JSON 기사 목록, `link_watch` = 새 링크 감지) |
| 업계(경쟁사) 블로그 RSS | `industry_feeds.feeds` |
| HN 업계 키워드·최소 점수 | `community.hn_major_keywords`, `hn_major_min_points` (300) |
| **대형 발표 판정**(출처·패턴·가산점) | `value_rules.major` |
| 카테고리 키워드 | `categories` |
| 점수 가중치·재부상 기준 | `scoring` |
| 감시 키워드·요일 | `watchlist.keywords`, `watchlist.weekday_kst` |
| 감시 키워드 승격 가산점 | `watchlist.promote_bonus` (기본 10), 키워드별 `promote_bonus_by_keyword` (design 4, video 8) |
| "확인 필요" 기준·감점 | `watchlist.weak_evidence_min_summary` (설명 30자 미만), `weak_evidence_penalty` (−8) |
| **글감 최소 점수(임계값)** | `value_rules.min_value` (기본 10). 올리면 엄격, 내리면 느슨 |
| 글감으로 치는 것 / 감점하는 것 | `value_rules.positive` / `value_rules.negative` (패턴 정규식 + weight, `applies_to`로 적용 대상 제한) |
| 출처 자체 가산(공식 스킬 폴더·Anthropic 뉴스) | `value_rules.source_bonus` |
| 인기 가산·비공식 인지도 최소선 | `value_rules.popularity` (`unofficial_min`: 스타 300 / 7일 +100 / 언급 50 중 하나) |
| 릴리스 줄 후보 수·핵심 3줄 칸 수 | `value_rules.release_bundle.max_candidates` (3), `max_in_headline` (1) |
| 리포트에 싣는 개수 | `top_n` |

리포트의 "글감 미달로 뺀 항목" 섹션에 무엇이 왜 빠졌는지 나오니, 기준을 조정할 때 그걸 보고 패턴·가중치를 고친다.

## 파일 구조

```
projects/claude-code-monitor/
  monitor.py           수집·점수·리포트
  config.json          수집 범위·점수·감시 키워드
  generate_content.py  블로그/인스타 초안 (에이전트 파일을 프롬프트로 사용)
  slack_notify.py      Slack 보고
  fixtures/dry_run_sample.json  드라이런용 가짜 응답 (실제 소식 아님)
  fixtures/case*.json           글감 선별 회귀 케이스 ①②③④ ("__extends__"로 case1을 상속, "__defaults__"로 빈 응답)
  fixtures/fake_blog_*.md       generate_content.py --dry-run --fake-blog 용 가짜 블로그 응답 (SKIP / 정상)
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
  YYYY-MM-DD-skip.txt       글감 없음(SKIP) 사유. slack_notify.py가 읽음
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
| content-blog-writer | `.claude/agents/content-blog-writer.md` | 일반인용 쉬운 소개글 + SEO (한 글 한 소식, 700~1,100자). 블로그 규칙의 단일 원본. 주제 고르는 기준(대형 발표 우선)·SKIP·사실 고정 규칙 포함 |
| content-instagram-writer | `.claude/agents/content-instagram-writer.md` | 쉬운 말 카드뉴스 5~6장. 블로그 초안과 같은 예시·수치, SKIP 규칙 |

## 참고

- GitHub API rate limit: 검색은 인증 시 분당 30회 → 쿼리 사이 2.5초 쉼. 일반 API는 인증 시 시간당 5,000회
- 소스 하나가 실패해도 나머지는 계속하고, 실패는 리포트 "⚠️ 수집 실패"와 Slack에 표시된다
