# Claude Code 소식 모니터

## 목적

Claude Code·AI 도구 관련 큰 소식(공식 발표, 새 스킬, 급상승 오픈소스, 커뮤니티 화제)을 매주 월요일 자동으로 모으고,
그중 하나를 골라 **IT를 잘 모르는 일반인용 쉬운 블로그 소개글**과 인스타 카드뉴스 초안을 만드는 파이프라인.

왜 지금 구조가 됐는지(2026-10-14 v2 개편 배경, v1이 Remotion 영상 소식을 놓친 원인, v2.1 글감 선별 기준)는 `HANDOVER.md` 참고.

## 현재 상태 (2026-11-27)

- master에서 매주 월요일 돌고 있다(10-19 ~ 11-23 리포트).
- **2026-11-27 워드프레스 자동 발행 추가** (사용자 요청 "이제 자동으로 수집해서 블로그 글 쓰는 거를 올려봐"):
  - 블로그 초안을 워드프레스(`earninsu.wordpress.com`, '청년 권씨의 재테크')에 **공개(publish)** 로 올린다. 사용자가 2026-11-27에 "바로 공개하고"라고 정했다(내 제안 기본값은 초안이었는데 사용자가 공개를 택함. `--status draft`는 수동용으로 남아 있다).
  - 업로드는 워크플로가 아니라 **Pickle 예약 액션**(`📮 주간 블로그 글 워드프레스 발행`, 월 19:00 / 화 08:00 KST)이 한다. GitHub App에 `workflows` 권한이 없어 워크플로 파일(스텝 추가)도, 저장소 시크릿(`WORDPRESS_ACCESS_TOKEN`) 등록도 이 환경에서 할 수 없어서다 → 사용자가 아무것도 하지 않아도 되는 쪽으로 정했다.
  - 입력은 Actions가 `git add research/`로 커밋해 둔 `research/content/{날짜}-blog.md`. `generate_content.py`가 content/blog에 쓰면서 같은 내용을 research/ 아래에도 남긴다(커밋 기록 + 발행 입력).
  - 중복 방지는 업로드 전 WordPress REST 조회(같은 슬러그/제목). 월·화 두 번 돌아도 한 번만 올라간다.
- **2026-11-27 손본 것** (사용자 요청 "Reddit 대신 Hacker News로 채워봐", 자세한 원인은 HANDOVER.md "2026-11-27"):
  - Reddit 수집을 **걷어냈다**(`collect_reddit`, `Fetcher`의 OAuth 경로, `REDDIT_*` 상수·환경변수, 감시 표의 Reddit 열, `config.json`의 `reddit_subs`·`reddit_min_score`). 6주 연속 403이었고, OAuth를 켜려면 시크릿 2개와 워크플로 env를 사용자가 계속 관리해야 했다.
  - 대신 `collect_hn`을 늘렸다. 최근 7일 창을 ① 최신순(`search_by_date`) ② 인기순(`search`) 두 경로로 보고, **포인트 `hn_min_points`(50)와 댓글 `hn_min_comments`(10)을 둘 다 넘긴 글만** 후보로 올린다. 같은 글이 두 경로·여러 키워드에 걸려도 한 번만 세도록 수집기 안에서 `objectID` 기준으로 합친다.
  - 리포트에 **"커뮤니티 반응 (Hacker News, 최근 7일)"** 섹션(포인트 순 상위 5개, 링크는 HN 토론)을 넣았다. Reddit 열이 빠진 감시 표 자리를 대신한다. 항목 상세에는 `HN 반응: 포인트 N · 댓글 M`, `latest-top.json`에는 `points`·`comments`·`discussion_url`이 들어간다.
  - **사용자가 따로 할 일은 없다.** Reddit OAuth를 위해 HANDOVER가 안내했던 시크릿 2개·워크플로 env 2줄은 이제 필요 없다(넣었으면 지워도 된다).
- **2026-11-26 손본 것** (자세한 원인은 HANDOVER.md "2026-11-26"):
  - `Claude 플랫폼 문서 목차`가 6주 연속 "링크 0개"로 실패 → 문서가 `docs.claude.com` → `platform.claude.com`으로 이전해서. `config.json` `link_watch.claude_docs`의 URL·패턴을 새 주소로 고쳤다(965개 링크 수집 확인).
  - `generate_content.py`가 thinking 블록만 받아 죽던 문제(11-02 실행) → `claude-opus-5`는 thinking이 기본 켜짐이고 thinking 토큰이 `max_tokens`에 포함된다. thinking을 명시(`adaptive`/`omitted`)하고 한도를 16,000/12,000으로 올렸으며, 본문이 없거나 잘리면 한도를 두 배로 늘려 1회 재시도한다.

## 파이프라인

```
매주 월요일 09:00 KST (GitHub Actions). 주 1회는 사용자가 의도한 설정이므로 임의로 바꾸지 않는다.
  monitor.py
    수집: Claude Code 릴리스·CHANGELOG / 공식 스킬·플러그인 폴더 / Anthropic 뉴스(JSON 기사 목록)·Claude 제품 목록·공식 문서 목차
          / 업계 RSS(OpenAI·Google AI·DeepMind) / GitHub 신규·토픽 검색 / Hacker News(최근 7일 · 포인트 50+·댓글 10+ / 업계 키워드는 300점 이상)
    → 같은 기사(URL·제목이 같거나 한 제목이 다른 제목을 품음)를 먼저 합치고,
    → 같은 신제품·신모델을 다룬 글(공식·업계 블로그·HN·벤치마크 기사)도 한 항목으로 합침. 고객 사례 글 제외
    → (월요일) 감시 키워드 검색 → 걸린 레포도 후보 풀에 추가
    → 릴리스 묶음: 이번 주기 릴리스·CHANGELOG를 줄 단위로 판정, 글감급 줄만 남김
    → 카테고리 태깅(영상·디자인·문서·오피스·자동화·에이전트·연동·코딩)
    → 중복 제거(research/state/) + 재부상 판정 → 중요도 점수 + 글감 가치(value) → 글감급만 상위 10개
       (🔥대형 발표 = 새 제품·새 모델·상장 등은 점수와 무관하게 맨 위)
    → 대형 발표에 원문 발췌(detail) + 최근 7일 국내 기사 수(kr_news, Google 뉴스 RSS) → 국내 기사 많은 쪽이 먼저
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

(Actions 밖) Pickle 예약 액션 `📮 주간 블로그 글 워드프레스 발행` — 월 19:00 / 화 08:00 KST
  scripts/publish_latest.sh → 발행 전용 클론(/workspace/repos/experiment-publish)을 origin/master로 reset
  publish_wordpress.py → research/content/{날짜}-blog.md(그 주 글, 최근 8일) → 워드프레스 공개 발행
    같은 슬러그 글이 이미 있으면 건너뜀(WP REST 조회) · 올라갔을 때만 사용자에게 제목+링크 알림
```

발행이 장기적으로 Actions 안으로 들어가야 한다면(워크플로 권한이 생기면) "블로그 + 인스타 컨텐츠 생성" 뒤에
`pip install markdown && python projects/claude-code-monitor/publish_wordpress.py --status publish` 스텝과
`WORDPRESS_ACCESS_TOKEN` 시크릿만 추가하면 된다. 스크립트는 그때도 그대로 쓴다(WP 토큰은 env 우선).

## 실행

```bash
# 네트워크 없이 전체 흐름 확인 (가짜 응답, 파일 안 씀)
python projects/claude-code-monitor/monitor.py --dry-run --fixtures projects/claude-code-monitor/fixtures/dry_run_sample.json

# 글감 선별 기준 회귀 확인 (2026-10-14 상황 재현)
python projects/claude-code-monitor/monitor.py --dry-run --fixtures projects/claude-code-monitor/fixtures/case1_minor_releases_only.json  # 후보 0개여야 함
python projects/claude-code-monitor/monitor.py --dry-run --fixtures projects/claude-code-monitor/fixtures/case2_big_news_vs_minor.json    # 영상·스킬이 위
python projects/claude-code-monitor/monitor.py --dry-run --fixtures projects/claude-code-monitor/fixtures/case3_mixed_release.json        # 글감급 줄만
python projects/claude-code-monitor/monitor.py --dry-run --fixtures projects/claude-code-monitor/fixtures/case4_big_launch_vs_repos.json   # 🔥대형 발표 2개가 레포보다 위, Duet은 한 칸
python projects/claude-code-monitor/monitor.py --dry-run --fixtures projects/claude-code-monitor/fixtures/case5_competitor_models_dedup.json  # GPT·Gemini 한 칸씩, 고객 사례 글 없음
python projects/claude-code-monitor/monitor.py --dry-run --fixtures projects/claude-code-monitor/fixtures/case6_same_article_sentence_title.json  # 문장형 제목·URL만 다른 같은 기사가 한 칸(2026-11-27 실제 상황)
#   --dump <폴더> 를 붙이면 리포트·latest-top.json을 그 폴더에 저장 → generate_content.py --top 으로 이어서 확인

# 실제 수집 (GITHUB_TOKEN 없어도 동작하지만 검색 rate limit이 낮다)
GITHUB_TOKEN=ghp_xxx python projects/claude-code-monitor/monitor.py
GITHUB_TOKEN=ghp_xxx python projects/claude-code-monitor/monitor.py --watchlist   # 감시 리스트 강제 포함

# 컨텐츠 생성
python projects/claude-code-monitor/generate_content.py --dry-run   # API 호출 없이 프롬프트 확인
python projects/claude-code-monitor/generate_content.py --dry-run --top <dump폴더>/latest-top.json \
    --fake-blog projects/claude-code-monitor/fixtures/fake_blog_skip.md   # SKIP 경로 (fake_blog_ok.md = 정상 경로)
ANTHROPIC_API_KEY=... python projects/claude-code-monitor/generate_content.py

# 워드프레스 발행 (기본 공개. 토큰은 파일 또는 WORDPRESS_ACCESS_TOKEN)
python projects/claude-code-monitor/publish_wordpress.py --dry-run
python projects/claude-code-monitor/publish_wordpress.py
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
| HN 키워드·최소 포인트·최소 댓글 | `community.hn_keywords`, `hn_min_points` (50), `hn_min_comments` (10) |
| HN 업계 키워드·최소 점수 | `community.hn_major_keywords`, `hn_major_min_points` (300) |
| **대형 발표 판정**(출처·패턴·가산점·원문 발췌·국내 기사) | `value_rules.major` (`detail_max`, `detail_chars`, `kr_news_bonus_max`) |
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
  publish_wordpress.py 블로그 초안 → 워드프레스 업로드 (중복 방지·dry-run·status 선택)
  slack_notify.py      Slack 보고
  fixtures/dry_run_sample.json  드라이런용 가짜 응답 (실제 소식 아님)
  fixtures/case*.json           글감 선별 회귀 케이스 ①~⑤ ("__extends__"로 case1을 상속, "__defaults__"로 빈 응답)
  fixtures/fake_blog_*.md       generate_content.py --dry-run --fake-blog 용 가짜 블로그 응답 (SKIP / 정상)
  blog/                새 블로그 형식 완성 예시
  CLAUDE.md / HANDOVER.md

research/
  claude-code-trends-YYYY-MM-DD.md     주간 리포트 (2026-10-12 이전 것은 v1 형식)
  content/YYYY-MM-DD-blog.md          그 주 블로그 글 사본 (워크플로가 커밋 → 예약 액션이 이 파일을 발행)
  claude-code-ecosystem-2026-09-27.md  초기 심층 조사
  state/claude-code-monitor.json       중복 제거·스타 이력 상태 (봇이 커밋, 손대지 말 것)
  state/latest-top.json                오늘의 상위 목록

content/  (Actions에서는 커밋 안 하고 Slack 스레드로만 전달)
  blog/YYYY-MM-DD-{slug}.md          생성 원본 (Actions 러너에만 있고 커밋 안 됨)
  instagram/YYYY-MM-DD-instagram.md
  YYYY-MM-DD-skip.txt       글감 없음(SKIP) 사유. slack_notify.py가 읽음
```

## 워드프레스 발행

생성된 블로그 초안을 `earninsu.wordpress.com`('청년 권씨의 재테크')에 올린다. **기본이 공개 발행**이다(사용자 선택, 2026-11-27).

- 자동: Pickle 예약 액션 `📮 주간 블로그 글 워드프레스 발행` (월 19:00 / 화 08:00 KST).
  `scripts/publish_latest.sh` → 발행 전용 클론을 origin/master로 맞춘 뒤 이 스크립트를 `--status publish`로 부른다.
  (스크립트는 레포 밖 워크스페이스 파일 `/workspace/scripts/publish_latest.sh`다 — 레포를 되돌리는 도구라서 레포 안에 두지 않았다.)
  워크플로가 13~16시로 밀려 도는 경우가 있어 월요일 저녁 1차, 화요일 아침 2차로 돌린다(중복 방지가 있어 두 번 돌아도 한 번만 올라간다).
- 수동/확인:
  ```bash
  python3 projects/claude-code-monitor/publish_wordpress.py --dry-run        # 올릴 글·중복 여부만 확인
  python3 projects/claude-code-monitor/publish_wordpress.py                  # 공개 발행
  python3 projects/claude-code-monitor/publish_wordpress.py --file <경로> --status draft   # 특정 파일을 초안으로
  python3 projects/claude-code-monitor/publish_wordpress.py --image downloads/blog.png --image-alt "설명"   # 대표·본문 이미지
  python3 projects/claude-code-monitor/publish_wordpress.py --update-post-id 50 --image downloads/blog.png  # 이미 올라간 글에 이미지
  ```
- 이미지(2026-11-27 추가): `--image`는 `/sites/{site}/media/new`로 올려 첫 장을 대표 이미지(`featured_image`)로 걸고 `[이미지 제안: …]` 자리를 치환한다. 여러 번 주면 순서대로. `--image-prompt "<영어 프롬프트>"`는 셸의 `images` 명령으로 먼저 만든다(프롬프트 작성은 부르는 쪽이 한다). `[이미지 제안: …]`·`[내부 링크 제안: …]` 메모는 발행 시 지워진다. 이미 올라간 글은 `--update-post-id`, 대표 이미지만 비어 있는 글은 `--fill-missing-image`. 테스트: `python3 -m unittest projects/claude-code-monitor/test_publish_wordpress.py`.
- 대상: `research/content/` 우선, 없으면 `content/blog/`에서 날짜가 가장 최근인 글. **최근 8일(`--max-age-days`) 안의 글만** 자동 발행한다(오래된 글이 뒤늦게 올라가지 않게). 날짜가 있는 파일명(`YYYY-MM-DD-*.md`)만 대상.
- 중복 방지: 업로드 전 WordPress REST로 최근 글을 받아 **같은 슬러그 또는 같은 제목**이 있으면 건너뛴다(휴지통은 없는 것으로 본다). 그래서 월·화 두 번 돌아도 한 번만 올라간다.
- 토큰: `WORDPRESS_ACCESS_TOKEN` 환경변수 → 없으면 토큰 파일(`WORDPRESS_TOKEN_FILE`, 기본 `/workspace/.pickle-secrets/wordpress-earninsu.json`, 권한 600). **토큰은 로그·커밋·PR에 쓰지 않는다.**
- 업로드 이력: `/workspace/state/wordpress-published.json` (`WORDPRESS_STATE_FILE`로 변경). 레포 밖에 두는 이유는 예약 액션이 매번 `git reset --hard`로 레포를 되돌리기 때문이고, 판단은 항상 WordPress 쪽 실제 글로 한다(이력은 기록용).
- **블로그 사이트는 아직 공개 전(coming soon) 상태다**(2026-11-27 기준 `is_coming_soon: true`, `launch_status: unlaunched`). 글은 publish 상태로 올라가지만 방문자에게는 "곧 공개됩니다"가 보인다. 사이트 공개는 사용자 결정이라 손대지 않는다.
- 블로그 본문은 `markdown` 패키지로 HTML 변환한다(확장: extra·sane_lists·nl2br·toc). `pip install markdown` 필요(requirements.txt에 추가).

## Secrets

이미 쓰는 것 (Settings → Secrets and variables → Actions):

| Secret | 설명 |
|--------|------|
| `GITHUB_TOKEN` | Actions 기본 제공. 등록 불필요 |
| `ANTHROPIC_API_KEY` | 컨텐츠 생성용 |
| `SLACK_BOT_STAFF1_TOKEN` | `xoxb-...` (slack-staff1 봇), 스코프 `chat:write` |
| `SLACK_CHANNEL_ID` | #성과보고 채널 ID (`C...`). 봇을 채널에 `/invite` 해야 함 |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_BASE_URL` | (선택) Langfuse 트레이싱 |

v2 추가 수집원은 모두 공개 API라 **새 시크릿 없이** 동작한다(Hacker News는 Algolia 공개 API, 키 불필요).
Reddit을 걷어내면서 `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET` 시크릿과 워크플로 env 2줄은 더 이상 쓰지 않는다(2026-11-27).

아래는 범위를 더 넓히려면 필요한 것(지금 코드에는 없음):

| 필요한 시크릿 | 쓰임 | 언제 필요 |
|---|---|---|
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
- `claude-opus-5`는 thinking(adaptive)이 기본 켜짐이고 끌 수 없다(`thinking {"type":"disabled"}`는 400). thinking 토큰이 `max_tokens`에 포함되므로 한도가 작으면 본문 없이 끝난다 → `generate_content.py`는 thinking을 `omitted`로 명시하고 한도를 16,000(블로그)/12,000(인스타)로 주며, 본문이 없거나 잘리면 두 배(최대 32,000)로 1회 재시도한다
