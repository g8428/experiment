# Claude Code 소식 모니터 인수인계서 (HANDOVER.md)

> CLAUDE.md는 "지금 어떻게 돌리는가", 이 파일은 "왜 이렇게 됐는가"를 적는다. 결정이 바뀌면 아래 이력에 날짜와 함께 추가한다.

## 1. 용어

| 용어 | 뜻 |
|---|---|
| 리포트 | `research/claude-code-trends-YYYY-MM-DD.md`. 매일 생성, 봇이 master에 커밋 |
| 상태 파일 | `research/state/claude-code-monitor.json`. 항목별 처음 등장일·스타 이력·보도 여부. **이게 없으면 매번 전부 '신규'가 된다** |
| 상위 목록 | `research/state/latest-top.json`. 핵심 3줄·상위 N개·수집 실패. 컨텐츠 생성과 Slack 보고의 입력 |
| 기준선(baseline) | 상태 파일이 비어 있는 첫 실행. 공식 목록·문서 링크는 이때 저장만 하고 다음 실행부터 '새 항목'을 잡는다 |
| 재부상 | 이미 리포트에 실었던 항목인데 스타·언급이 급증해서 다시 싣는 경우 |
| 감시 리스트 | `config.json`의 `watchlist.keywords`. 월요일(KST)마다 점수와 무관하게 바깥 반응을 점검 |

## 2. 파일 역할

```
monitor.py          수집(공식·GitHub·커뮤니티) → 분류 → 점수 → 중복 제거 → 리포트/상태 저장
config.json         수집 범위·쿼리·카테고리·점수 가중치·감시 키워드 (코드 수정 없이 범위 조정)
generate_content.py latest-top.json → 블로그/인스타 초안. 규칙은 .claude/agents/*.md 본문을 그대로 사용
slack_notify.py     #성과보고에 핵심 3줄·수집 실패·감시 경고 + 초안 스레드
fixtures/           --dry-run 검증용 가짜 응답 (실제 소식 아님)
blog/               새 블로그 형식 완성 예시
```

## 3. 결정 이력

### 2026-10-14 — v2 개편: 수집 범위 확대 + 점수제 + 쉬운 블로그

**계기 (사용자 불만 2가지)**
1. "클로드 코드로 영상(모션그래픽)을 만든다, Remotion 공식 스킬이 나왔다" 같은 큰 소식을 모니터가 못 잡았다.
2. 블로그 초안이 너무 어렵다. IT 모르는 일반인용 쉬운 소개글 + SEO가 필요하다.

**v1에서 놓친 원인 (근거)**

| # | 원인 | 근거 |
|---|---|---|
| 1 | 수집원이 GitHub 레포 검색 하나뿐. 공식 릴리스·CHANGELOG·Anthropic 뉴스·공식 스킬 목록·커뮤니티를 전혀 안 봤다. "공식 스킬 출시"는 레포 스타 순위로는 잘 안 보이는 종류의 소식이다 | v1 `monitor.py` 20~26줄 `SEARCH_QUERIES` 5개, 40~46줄 `/search/repositories`만 호출 |
| 2 | 쿼리당 스타순 상위 20개만 받아서 이미 큰 레포만 남는다. 새로 뜨는 레포, Claude 단어가 없는 외부 레포(예: Remotion 쪽 스킬 저장소)는 들어오기 어렵다 | v1 28줄 `TOP_N = 20`, 43줄 `"sort": "stars"`. 10-05·10-12 리포트 상위가 27만~14만 스타 대형 레포 |
| 3 | 이전 실행 기록(`history.json`)이 커밋되지 않아 매번 전 레포가 '신규 진입'으로 찍히고, '스타 급등' 섹션은 한 번도 나오지 않았다. 변화 감지가 사실상 꺼져 있었다 | v1 워크플로가 `git add research/`만 함, `git ls-files`에 history.json 없음. 10-05 리포트 93개, 10-12 리포트 94개 전부 '🆕 신규 진입', 두 리포트 차이는 5개 내외. 두 리포트 모두 '🚀 스타 급등' 섹션 없음 |
| 4 | 영상 관련 신호가 있어도 묻혔다. 카테고리·중요도 없이 스타순 나열이라 | `feicaiclub/video-spec-builder`(영상 분镜 대본→렌더링, ⭐1,020)가 10-05·10-12 리포트 84번째 줄에 있었지만 아무 표시 없음. `remotion`은 research/ 전체에서 0건 |
| 5 | 시작 시점 문제. 파이프라인은 2026-09-27 생겼고 Remotion 공식 스킬 보도는 2026년 1월이다. 변화만 보는 구조라 그 전부터 있던 큰 흐름은 원래 잡을 수 없었다 | 첫 커밋 `99ba3c3`(2026-09-27). 이를 막으려고 주간 감시 리스트를 추가 |

추가로, 블로그가 어려웠던 이유: Actions에서 쓰는 `generate_content.py`가 에이전트 파일(`.claude/agents/content-blog-writer.md`)을 읽지 않고 자체 프롬프트("한국 개발자 커뮤니티용 기술 블로그", 리포트 전체를 소재로 3~5개 아이템)를 썼다. 에이전트 파일을 고쳐도 자동 결과물은 안 바뀌는 구조였다.

**바꾼 것과 이유**

- 수집원 확대 (새 시크릿 없이 `GITHUB_TOKEN`과 공개 API만): Claude Code 릴리스·CHANGELOG, 공식 스킬/플러그인 폴더 목록 비교, Anthropic 뉴스·공식 문서 목차(llms.txt) 링크 비교, GitHub 최근 생성/토픽 검색(claude-code, agent-skills, remotion, mcp-server 등), Hacker News(Algolia API), Reddit 공개 JSON.
- 중복 제거 + 재부상: 상태 파일을 `research/state/`에 둬서 기존 봇 커밋 범위(`research/`) 안에서 저장된다. 브랜치 규칙상 봇은 결과물 폴더에만 직접 커밋하므로 `projects/` 아래 대신 여기 둠.
- 점수제: 공식 35 + 스타 증가(7일, 로그) 최대 25 + 언급 최대 20 + 일반 사용자 영향(영상 15·디자인/문서 12·자동화 10…) + 신규/재부상 5. 상위 10개만 싣고 맨 위에 "오늘의 핵심 3줄". 일반 사용자 영향 가중치는 "일반인 블로그 소재"라는 이 파이프라인의 목적을 반영한 것. 가중치는 `config.json`에서 조정.
- 안전장치: 수집 실패는 리포트 상단 "⚠️ 수집 실패"와 Slack에 그대로 표시(조용히 빠지지 않게). 월요일마다 감시 키워드(remotion, video, motion graphics, slides, pptx, google workspace, design, excel) 점검, 바깥 반응이 있는데 최근 7일 리포트에 없으면 ⚠️.
- 스케줄: 주 1회(월) → 매일 09:07 KST. 큰 소식이 일주일 늦게 잡히는 것을 줄이려고. 새 소식이 없으면 컨텐츠 생성은 건너뛴다(API 비용 절감).
- 블로그: 독자를 "IT 모르는 30~50대 직장인"으로 바꾸고 한 글 = 한 소식, 6단 구성, SEO 규칙, 사실 확인 규칙을 `content-blog-writer.md`에 넣었다. `generate_content.py`는 이 파일 본문을 시스템 프롬프트로 그대로 읽는다(규칙의 단일 원본).

**버린 대안**
- X(트위터)·유튜브 수집: API 키·유료 플랜이 필요해 보류 (CLAUDE.md "필요한 시크릿" 참고).
- 블로그 글감 선택을 코드로 고정: 일반인 체감 판단은 모델이 더 잘해서, 상위 5개 후보를 주고 에이전트 규칙으로 1개를 고르게 했다.

**확인 못 한 것 (첫 실행 후 확인)**
- 실제 외부 호출은 한 번도 안 해 봤다(작업 환경에 네트워크·시크릿 없음). 검증은 `--dry-run --fixtures`의 가짜 응답으로만 했다.
- `anthropics/claude-plugins-official` 레포, `code.claude.com/docs/llms.txt`, `docs.claude.com/llms.txt`, anthropic.com/news의 링크 형식이 실제와 맞는지. 틀리면 리포트 '수집 상태'에 실패로 찍힌다.
- Reddit 공개 JSON이 GitHub Actions IP에서 막히는지(막히면 실패로 표시됨 → OAuth 앱 필요).
- 첫 실행은 기준선 저장이라 공식 목록 '새 항목'이 0개로 나오는 게 정상이다.
