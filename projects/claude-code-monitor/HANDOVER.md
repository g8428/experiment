# Claude Code 소식 모니터 인수인계서 (HANDOVER.md)

> CLAUDE.md는 "지금 어떻게 돌리는가", 이 파일은 "왜 이렇게 됐는가"를 적는다. 결정이 바뀌면 아래 이력에 날짜와 함께 추가한다.

## 1. 용어

| 용어 | 뜻 |
|---|---|
| 리포트 | `research/claude-code-trends-YYYY-MM-DD.md`. 매주 월요일 생성, 봇이 master에 커밋 |
| 상태 파일 | `research/state/claude-code-monitor.json`. 항목별 처음 등장일·스타 이력·보도 여부. **이게 없으면 매번 전부 '신규'가 된다** |
| 상위 목록 | `research/state/latest-top.json`. 핵심 3줄·상위 N개·수집 실패. 컨텐츠 생성과 Slack 보고의 입력 |
| 기준선(baseline) | 상태 파일이 비어 있는 첫 실행. 공식 목록·문서 링크는 이때 저장만 하고 다음 실행부터 '새 항목'을 잡는다 |
| 재부상 | 이미 리포트에 실었던 항목인데 스타·언급이 급증해서 다시 싣는 경우 |
| 감시 리스트 | `config.json`의 `watchlist.keywords`. 월요일(KST)마다 바깥 반응을 점검. v2.1부터 키워드에 걸린 항목은 후보 풀에 올려 가산(승격) |
| 글감 가치(value) / 글감급 | `config.json` `value_rules`로 매기는 "블로그 글감이 되는가" 점수. `min_value` 이상이면 글감급 → 후보 자격. 순위 = 중요도 점수 + value |
| 릴리스 묶음 | 이번 주기에 처음 본 Claude Code 릴리스·CHANGELOG를 하나로 묶어 bullet 한 줄씩 판정한 것. 글감급 줄만 후보 |
| SKIP | 블로그 에이전트가 글감이 약하다고 보고 글 대신 출력하는 `SKIP: <사유>` 한 줄. Slack에 "이번 주는 글감 없음(사유)" |

## 2. 파일 역할

```
monitor.py          수집(공식·GitHub·커뮤니티) → 분류 → 점수 → 중복 제거 → 리포트/상태 저장
config.json         수집 범위·쿼리·카테고리·점수 가중치·감시 키워드 (코드 수정 없이 범위 조정)
generate_content.py latest-top.json → 블로그/인스타 초안. 규칙은 .claude/agents/*.md 본문을 그대로 사용. 블로그 사본은 research/content/에도 저장
publish_wordpress.py research/content/의 그 주 글 → 워드프레스 공개 발행(중복 방지). 기본이 publish(사용자 선택)
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
- 스케줄: 주 1회(월) 유지. 사용자가 의도한 설정이다. (개편 때 매일로 바꿨다가 사용자 요청으로 되돌림, 2026-10-14. 사용자 승인 없이 스케줄을 바꾸지 말 것.) 새 소식이 없으면 컨텐츠 생성은 건너뛴다(API 비용 절감).
- 블로그: 독자를 "IT 모르는 30~50대 직장인"으로 바꾸고 한 글 = 한 소식, 6단 구성, SEO 규칙, 사실 확인 규칙을 `content-blog-writer.md`에 넣었다. `generate_content.py`는 이 파일 본문을 시스템 프롬프트로 그대로 읽는다(규칙의 단일 원본).

**버린 대안**
- X(트위터)·유튜브 수집: API 키·유료 플랜이 필요해 보류 (CLAUDE.md "필요한 시크릿" 참고).
- 블로그 글감 선택을 코드로 고정: 일반인 체감 판단은 모델이 더 잘해서, 상위 5개 후보를 주고 에이전트 규칙으로 1개를 고르게 했다.

**확인 못 한 것 (첫 실행 후 확인)**
- (2026-10-14 테스트 실행 run 38508748996에서 실제 호출 확인됨. 'Claude 플랫폼 문서 목차'는 링크 0개, Reddit은 403으로 실패 표시됨)
- 실제 외부 호출은 한 번도 안 해 봤다(작업 환경에 네트워크·시크릿 없음). 검증은 `--dry-run --fixtures`의 가짜 응답으로만 했다.
- `anthropics/claude-plugins-official` 레포, `code.claude.com/docs/llms.txt`, `docs.claude.com/llms.txt`, anthropic.com/news의 링크 형식이 실제와 맞는지. 틀리면 리포트 '수집 상태'에 실패로 찍힌다.
- Reddit 공개 JSON이 GitHub Actions IP에서 막히는지(막히면 실패로 표시됨 → OAuth 앱 필요).
- 첫 실행은 기준선 저장이라 공식 목록 '새 항목'이 0개로 나오는 게 정상이다.

### 2026-10-14 — v2.1: 글감 선별 기준 (사소한 릴리스가 핵심 3줄을 독식하던 문제)

**계기 (테스트 실행 Actions run 38508748996 결과)**
- 오늘의 핵심 3줄이 전부 anthropics/claude-code 릴리스(v2.1.286, v2.1.299, v2.1.292)였고, 상위 10개도 전부 릴리스였다.
- 블로그 글감으로 "확인창에 '5개 중 2개' 숫자가 표시된다"(v2.1.286 첫 줄 "Added a count such as "2 of 5" to the permission prompt")가 뽑혔다.
- 반대로 감시 키워드 remotion·motion graphics·pptx·google workspace·excel은 바깥 반응이 잡혔는데 "⚠️ 리포트 미반영"으로만 끝났다. 상태 파일에 `Vincentwei1021/video-shotcraft`(Remotion 영상 스킬, ⭐11,772) 같은 항목이 있었지만 상위에 못 올라왔다.
- 사용자 기준 문장: **"단순히 화면 개편 이런 건 너무 별로다. 대대적인 기능 업데이트도 아니고 혁신적인 스킬이 나온 것도 아니다."**

**원인 (근거)**
| # | 원인 | 근거 |
|---|---|---|
| 1 | 공식 +35점이 내용과 무관하게 붙었다. 사소한 릴리스도 35+α로 시작해 GitHub 소식을 이겼다 | 리포트 상위 10개 점수 근거가 전부 "공식 +35, 일반 사용자 영향 +10~15, 신규 +5" |
| 2 | 릴리스 본문 전체로 카테고리를 매겨서 한 줄이라도 'video'·'design'이 있으면 영상/디자인 가산(+15/+12)을 받았다 | v2.1.286이 [영상/자동화/에이전트/연동/코딩]으로 태깅, 55점 1위 |
| 3 | 릴리스가 버전별로 따로 올라가 12개 버전이 상위 10칸을 다 차지했다 | 상위 10개 = v2.1.286~v2.1.299 |
| 4 | 감시 리스트는 경고만 하고 점수·후보에는 아무 영향이 없었다 | v2 `watchlist_check()`가 상위 목록이 정해진 *뒤* 실행 |

**바꾼 것**
- `config.json` `value_rules`: 글감 가치(value)를 규칙으로 판정. positive(업무에 새로 쓸 수 있는 일 +10, 자동화·연동 +8, 스킬·플러그인 출시 +8, 새 기능 표현 +5, 요금·모델·정책 +15) / negative(화면 표시·문구·단축키·알림 −12, 설정·환경변수·옵션 −10, 버그 수정·안정성·소폭 성능 −15, 내부·개발자 전용 −10). 출처 가산(공식 스킬 폴더 새 항목·Anthropic 뉴스 +12), 인기 가산(7일 스타 +1000 → +12 등). **value ≥ `min_value`(10)인 항목만 후보**(상위 목록·핵심 3줄·블로그 후보). 순위 = 중요도 + value.
- 릴리스 묶음: 이번 주기에 처음 본 릴리스(+CHANGELOG)를 하나로 묶어 What's changed bullet 한 줄씩 판정, 글감급 줄만 후보(최대 3줄, 핵심 3줄에는 1칸까지 — 다른 글감이 모자라면 채움). 글감급이 없으면 리포트·Slack에 "이번 주 릴리스: 글감급 변경 없음(사소한 개선 N건)" 한 줄만. 이미 판정한 릴리스 태그는 상태 파일 `releases_seen`에 남겨 다음 주에 다시 세지 않는다.
- 감시 키워드 승격: 키워드에 걸린 항목은 가산(+10, 뜻이 넓은 design +4·video +8), 감시 검색에서 처음 나온 레포도 후보 풀에 넣는다. 인지도(스타 300·7일 +100·언급 50 중 하나)가 모자라거나 설명이 짧으면 "확인 필요" 표시 + 순위 감점(−8). 감시 키워드에 안 걸린 비공식 항목은 인지도 미달이면 탈락.
- 블로그·인스타 에이전트: 글감이 사소하면 글 대신 `SKIP: <사유>` 한 줄. `generate_content.py`가 감지해 파일을 안 만들고 인스타 호출도 생략, `content/YYYY-MM-DD-skip.txt` → Slack "이번 주는 글감 없음(사유)". 사실 고정 규칙(소스에 없는 위치·날짜·수치·동작 금지, 날짜는 소스 발표일만), 이미지는 `[이미지 제안: …]`, 인스타는 블로그 초안을 함께 받아 같은 예시·수치를 쓴다.
- 새 LLM 호출·모델·스케줄·워크플로 입력·Slack 전송 방식은 바꾸지 않았다 (사용자 설정).

**버린 대안**
- *LLM으로 글감 가치를 따로 판정*: 정확하겠지만 새 유료 호출(비용 구조 변경)이라 사용자 승인 사항. 규칙 기반 1차 거르기 + 기존 블로그 호출 안의 SKIP 판단으로 대신했다.
- *공식 가산점(+35)만 낮추기*: 사소한 릴리스가 덜 이기긴 하지만, "Haiku 새 모델·요금" 같은 큰 공식 변경까지 같이 묻힌다. 내용(줄 단위)으로 가르는 쪽을 택했다.
- *릴리스를 통째로 수집에서 제외*: 요금·모델·새 기능 같은 ④·① 글감이 릴리스 노트에서 나온다. 묶어서 줄 단위로 거르는 쪽을 택했다.
- *감시 키워드 항목을 무조건 핵심 3줄에 고정*: 'design'·'video'처럼 넓은 키워드는 엉뚱한 레포도 걸린다. 가산점 + 글감 판정을 똑같이 통과해야 오르게 했다.

**오프라인 재평가 (오늘 실제 데이터, 근사)**
- 상태 파일·latest-top.json에는 릴리스 본문이 300자까지만, 레포는 생성일·언급 수 없이 남아 있어 근사치다(스타 증가량 0으로 둠).
- 결과: 릴리스 12개 → 글감급 2줄(Claude Haiku 5.5 새 기본 모델·요금, Claude Mods), 사소한 개선 13줄. 확인창 "2 of 5"는 −12로 탈락.
- 새 핵심 3줄: ① Claude Haiku 5.5 (릴리스 v2.1.293) ② Vincentwei1021/video-shotcraft (Remotion 영상 스킬) ③ rehan-remade/universal-modder. 상위 10개에 OpenMontage·motion-video-kit·googleworkspace/cli·frontend-slides 등 영상·문서 소식이 들어온다.

**확인 못 한 것**
- 규칙은 영어 릴리스 노트 문구 기준으로 만들었다. 새 표현이 나오면 `value_rules` 패턴에 추가해야 한다(리포트 "글감 미달로 뺀 항목"에서 확인).
- 실제 실행에서 감시 검색 결과가 후보에 몇 개나 들어오는지, `min_value` 10이 적당한지는 다음 월요일 실행 결과로 조정해야 한다.

### 2026-10-27 — v2.2: 대형 발표 우선 + 업계 소식 수집 + 짧은 글

**계기 (사용자 피드백)**
1. "블로그 글이 너어무 길다. 카드뉴스도 줄여."
2. "주제가 너무 쓰잘데기 없다. 한 가지 큼직한 주제에 집중해야 한다." 2026-10-26 리포트 핵심 3줄이 lemo-opuscar·huashu-motion·RuView(중국어 영상 레포 등)였다.
3. "지난주 Claude Duet이 나왔다고 경쟁 계정들이 다 같이 홍보하는데 여기선 1도 없었다. GPT Terra 나온 것도 못 발견했다."

**원인 (근거)**
| # | 원인 | 근거 |
|---|---|---|
| 1 | Anthropic 뉴스 수집이 처음부터 기사를 하나도 못 읽고 있었다. anthropic.com/news는 기사 목록이 href가 아니라 페이지 안 JSON(`"slug":{"current":...}`)에 있어서, href 패턴은 메뉴·분류 링크 26개만 잡았다 | 10-26 리포트 '수집 상태' "Anthropic 뉴스 성공 0건, 전체 26개". 상태 파일 `links.anthropic_news` 26개가 전부 /news/policy, /news/product 같은 메뉴 링크. 같은 페이지 JSON에는 기사 88개(제목·발표일·분류 포함) |
| 2 | 신제품 출시 글은 anthropic.com/news 기사 목록에 없을 수 있다. Duet은 10-21 공개됐는데 그 페이지 JSON 기사 목록엔 없고, 사이트 메뉴에 `claude.com/product/claude-duet` 링크로만 있었다 | 2026-10-27 페이지 확인. 최근 기사는 연구·정책 글뿐 |
| 3 | 경쟁사(OpenAI·Google) 소식을 보는 수집원이 아예 없었다. HN 키워드도 claude code·anthropic·remotion 등 5개뿐 | config.json `community.hn_keywords` |
| 4 | 순위가 "스타 급증 + 영상 카테고리" 점수라 스타 많은 레포가 공식 발표(35점)를 이겼다 | 10-26 상위 10개 전부 GitHub 레포, 85~89점 |

GPT Terra: 확인해 보니 실제 공개된 건 GPT-5.6 Terra(2026-07)다. 파이프라인 시작(09-27) 전이라 원래 잡을 수 없었다. GPT-6 Terra는 2026-10-27 기준 공식 발표를 찾지 못했다(소문 단계). 다만 원인 3 때문에 앞으로의 경쟁사 신모델도 못 잡는 구조였던 건 맞다.

**바꾼 것**
- `collect_articles`: anthropic.com/news의 JSON 기사 목록(제목·발표일·분류)을 읽는다. 최근 `lookback_days` 안 + `articleType` news만(연구 논문 제외).
- `claude_products` 링크 감시: 사이트 메뉴의 `claude.com/product/*`에 새 페이지가 생기면 신제품. **첫 실행은 기준선이라 Duet은 소급해서 잡히지 않는다.**
- `industry_feeds`: OpenAI 뉴스·Google AI 블로그·DeepMind 블로그 RSS. 제목이 대형 발표 패턴(introducing·launch·새 모델·출시 등)에 맞는 글만.
- HN `hn_major_keywords`(claude·openai·chatgpt·gpt·gemini): 300점 이상만 → 출처 `hackernews_major`.
- `value_rules.major`: 위 출처의 대형 발표는 +30이고, **순위에서 점수와 무관하게 맨 위**(select_top 정렬 키 `(major, score)`). 리포트·Slack에 🔥대형 발표 표시.
- `fold_launch_coverage`: 새 제품 페이지와 같은 이름을 다룬 HN·업계 글은 한 항목으로 합친다(한 소식이 핵심 3줄 두 칸을 먹지 않게).
- 블로그: 1,500~2,500자 → **700~1,100자**, 섹션 ⑥ 한 줄 요약 삭제, FAQ 3→2, 이미지 제안 1~2개. 주제 고르는 기준을 "① 대형 발표(경쟁사 포함) ② 공식 기능·스킬 ③ 유명 오픈소스(대형 발표 없을 때만)"로 바꿨다.
- 인스타: 최대 10장 → **5~6장**, 슬라이드 35자, 캡션 300자, 해시태그 6~8개.
- `generate_content.py`: max_tokens 6000/3000 → 3000/2000(짧아진 글 기준, 비용 감소). 프롬프트에 major 우선·길이 한 줄.
- 회귀 케이스 ④ `fixtures/case4_big_launch_vs_repos.json` 추가. case1·dry_run_sample은 새 수집원 키(page::claude_products, feed::, JSON 기사)를 넣었다(기대 결과는 그대로).

**버린 대안**
- *Google News RSS로 "경쟁 계정들이 다루는 화제" 직접 측정*: 같은 소식이 매체 수만큼 중복으로 들어와 묶는 로직이 따로 필요하다. 이번엔 공식 블로그 RSS + HN 고득점으로 대신했다. 그래도 놓치면 다음 후보.
- *X·유튜브·인스타 경쟁 계정 직접 감시*: 유료 API·키가 필요(사용자 승인 사항).
- *대형 발표에 점수만 크게 주기*: 스타 점수 상한과 계속 줄다리기가 된다. 정렬 우선순위로 분리했다.

**같은 날 추가 (사용자 "다 해")**
- `collect_articles`를 정규식 → JSON 객체 통째 읽기로 바꿨다. 출시 글(예: "Introducing Claude Opus 5.5")은 필드 순서가 알파벳순이라 정규식이 놓쳤다. 88개 → 110개. 놓쳤던 것 중에 "Anthropic files S-1 with the SEC for proposed IPO"(10-26), "Donating Agent Skills to the Agentic AI Foundation"(10-22)이 있었다. 출시 글은 `/claude-opus-5-5`처럼 루트 경로라 페이지 안 링크로 경로를 정한다.
- `source_bonus.anthropic_news` 12 → 0: 기사 수집을 고치니 사무소 개소·이사 선임 같은 회사 소식이 2주에 7개 들어와 후보를 채웠다. 출시·새 모델·상장(IPO) 글만 major로 +30.
- `enrich_majors`: 상위 대형 발표(최대 3개)에 ① 원문 페이지 발췌 1,500자(`detail`) ② Google 뉴스 한국어 RSS로 최근 7일 국내 기사 수(`kr_news`, 1건당 +1점, 최대 +20)를 붙인다. ①은 블로그가 "공식 페이지에서 확인하세요"로만 채워지던 문제, ②는 "경쟁 계정들이 다 같이 다루는 소식"을 재는 신호다. 대형 발표끼리는 국내 기사가 많은 쪽이 먼저.
- `generate_content.py` 사실 범위에 detail을 소스로 추가, kr_news는 본문에 숫자로 쓰지 않게 했다.

**이 브랜치 실제 실행 결과 (2026-10-30, Actions run 40989617677, watchlist=true)**
- 핵심 3줄: ① GPT-6.1 Terra(국내 기사 58건) ② Gemini 4 Carbon(16건) ③ Anthropic S-1(IPO). 10-26의 중국어 영상 레포 3줄과 비교하면 경쟁 계정들이 다루는 주제로 바뀌었다.
- 수집 상태: OpenAI RSS(글 1,337개)·DeepMind RSS·Google AI 블로그·Google 뉴스 RSS·Anthropic 기사(107개) 모두 성공. 원문 발췌는 openai.com이 HTTP 오류로 실패, 나머지 성공.
- 카드뉴스는 6장·캡션 약 270자·해시태그 7개로 새 기준에 맞았다. 원문 발췌 덕에 공식 수치가 들어갔다.
- **문제 2개를 찾아 고쳤다**: (1) 같은 소식이 출처별로 따로 올라감 — GPT(HN+RSS), Gemini(HN+DeepMind+벤치마크 기사)가 상위 10칸 중 5칸. → `fold_same_story`로 일반화(기준 항목 우선순위 `fold_anchor_order`, 이름 포함 또는 같은 URL이면 합침). (2) OpenAI 고객 사례 글("CodeRabbit helps… with GPT-6.1")이 모델 이름 패턴에 걸려 6~9위. → `major.exclude_patterns`. 회귀 케이스 ⑤ `case5_competitor_models_dedup.json`이 이 상황을 재현한다.
- 실행이 브랜치에 남긴 봇 커밋(리포트·상태)은 revert했다. 머지되면 월요일 정기 실행이 이 소식들을 '이미 다룸'으로 건너뛰기 때문이다.

**확인 못 한 것**
- (해결) 업계 RSS·Google 뉴스 주소는 위 실제 실행에서 모두 성공 확인.
- 블로그 초안 전체 길이는 Slack에 앞부분만 올라가서 확인하지 못했다. 다음 실행에서 content/blog 파일 길이를 확인할 것.
- anthropic.com/news JSON 구조는 2026-10-27 실제 페이지로 확인했다. 구조가 바뀌면 "기사 0개" 실패로 찍힌다.
- 원문 발췌는 HTML 글자를 그대로 잘라 쓴다. JS로만 그려지는 페이지면 발췌가 메뉴 글자 위주일 수 있다.

### 2026-11-26 — 6주 연속 실패한 수집원 2개 + thinking 실패 수정

**계기**
- 사용자 요청: "트렌드모니터 관련 에러와 막힌 소스를 미리 손봐 달라". 10-14부터 11-23까지 일곱 번의 리포트에 매번 같은 두 소스가 실패로 찍혀 있었고, 11-02 실행은 컨텐츠 생성 단계에서 워크플로가 죽었다.

**원인 (근거)**

| # | 증상 | 원인 | 근거 |
|---|---|---|---|
| 1 | `Claude 플랫폼 문서 목차` — `RuntimeError: 링크 0개` (10-14, 10-19, 10-26, 11-02, 11-09, 11-16, 11-23) | 개발자 문서가 `docs.claude.com` → `platform.claude.com`으로 이전. `docs.claude.com/llms.txt`는 여전히 200으로 응답하지만 안의 링크가 전부 `platform.claude.com/docs/en/*.md`라서 옛 패턴(`\((https://docs\.claude\.com/[^)\s]+)\)`)이 한 개도 못 잡았다 | 2026-11-26 실제 응답 확인: 109KB, 링크 966개(영어 965 + `llms-full.txt` 1), `docs.claude.com` 링크 0개 |
| 2 | `Reddit` — `HTTPError: 403 Client Error: Blocked for url: https://www.reddit.com/r/ClaudeAI/top.json` | Reddit이 데이터센터 IP를 네트워크 단위로 막는다. UA·엔드포인트 문제가 아니다 | 403 본문이 "You've been blocked by network security. To continue, log in to your Reddit account or use your developer token". 프로젝트 UA와 브라우저 UA, `www`/`old`/`api.reddit.com`, `.json`/`.rss` 모두 403 또는 429 |
| 3 | 11-02 실행: `RuntimeError: 응답에 text 블록이 없습니다. content types: ['thinking']` → 워크플로 실패 | `claude-opus-5`는 adaptive thinking이 기본 켜짐이고 끌 수 없다. thinking 토큰도 `max_tokens`에 포함되므로, 한도(3,000)를 thinking이 다 쓰면 text 블록 없이 `stop_reason: max_tokens`로 끝난다 | 응답 47초 만에 종료된 traceback, `stop_reason` 미기록. Anthropic 문서 "Thinking"·"Troubleshooting thinking"의 `stop_reason: max_tokens` 항목 |

**바꾼 것**
- `config.json` `link_watch.claude_docs`: URL `https://platform.claude.com/llms.txt`, 패턴 `\((https://(?:platform|docs)\.claude\.com/docs/en/[^)\s]+)\)`(영어 문서만). 2026-11-26 실제 수집 965개 확인. **첫 실행은 기준선 저장이라 그 주에는 '새 페이지' 0개가 정상**이다.
- `collect_links` 이름 규칙: `.md`를 떼고, `overview`·`quickstart`·`home`·`intro` 같은 흔한 이름은 상위 폴더를 붙인다(`…/agent-skills/overview.md` → `Agent Skills / Overview`). claude_code_docs도 같은 규칙이라 제목이 `example-new-page` → `example new page`로 보인다(항목 id는 URL이라 중복 제거에 영향 없음).
- Reddit OAuth(선택): `REDDIT_CLIENT_ID`·`REDDIT_CLIENT_SECRET`이 있으면 `www.reddit.com/api/v1/access_token`(client_credentials)로 토큰을 받아 `oauth.reddit.com/r/{sub}/top`을 쓴다. 없으면 지금처럼 공개 JSON을 시도하고, 401/403/429면 "Reddit이 이 실행 환경의 IP를 막았습니다 … 시크릿을 넣으면 OAuth로 수집합니다 (r/… HTTP 403)"로 적는다. **아직 할 일:** Actions에서 쓰려면 ① 저장소 시크릿에 두 값 추가 ② `.github/workflows/claude-code-monitor.yml` monitor 스텝 `env`에 `REDDIT_CLIENT_ID`·`REDDIT_CLIENT_SECRET` 두 줄 추가. ②는 이때 연결된 GitHub App에 `workflows` 권한이 없어 커밋하지 못했다(권한을 주면 다음에 같이 커밋할 수 있다).
- `generate_content.py`: `thinking={"type":"adaptive","display":"omitted"}` 명시(본문만 받는다), `max_tokens` 블로그 16,000·인스타 12,000, `stop_reason: max_tokens`이거나 text 블록이 없으면 한도를 두 배(최대 32,000)로 1회 재시도. 두 번째도 잘리면 `ResponseError`로 명확히 실패해 반쪽 글을 저장하지 않는다. `extract_text`는 text 블록만 이어붙이고(기존 유지) 진단에 `stop_reason`을 넣는다.
- `Fetcher.get`이 `self.session`을 쓰도록 바꿨다(기본값 `requests` 모듈 → 동작 동일). OAuth 경로를 가짜 세션으로 테스트하기 위해서다.
- fixtures `dry_run_sample`·`case1`의 `page::claude_docs`·상태 링크를 새 URL 형식으로 갱신(패턴이 되돌아가면 fixture에서 바로 드러난다).

**버린 대안**
- *Reddit을 RSS(`top/.rss`)로 전환*: 429(레이트리밋)였고 RSS에는 점수·selftext가 없어 `reddit_min_score`(100) 필터와 키워드 집계가 약해진다. 게다가 같은 IP 차단 계열이라 Actions에서 될 보장이 없다.
- *UA 위장·공개 미러(pullpush 등)*: 브라우저 UA로도 403이었고 pullpush.io도 403(Cloudflare). Reddit이 공식적으로 안내하는 경로는 로그인/개발자 토큰뿐이다.
- *`max_tokens`만 낮추기/올리기*: 낮추면 더 자주 잘리고, 올리기만 하면 재시도 없이 같은 실패가 남는다. 잘림 감지 + 재시도를 같이 넣었다. `effort`를 낮춰 thinking을 줄이는 방법은 글 품질·비용 기준을 바꾸는 일이라 사용자 판단으로 남겼다.

**검증 (2026-11-26, 로컬)**
- `py_compile` 통과. fixtures ①~⑤ + dry_run_sample 6개 모두 exit 0, 수정 전 출력과 diff는 문서 제목 한 줄(`example new page`)뿐.
- 실제 네트워크로 `claude_docs` 수집: 965개, 전부 `platform.claude.com/docs/en/…md`. 새 링크 1개만 남긴 상태로 '새 페이지' 감지·제목 규칙 확인.
- Reddit: 자격증명 없이 실제 403 → 안내 메시지 확인. OAuth 경로는 가짜 세션으로 토큰 발급→`oauth.reddit.com`→Bearer 헤더→항목·키워드 집계까지 확인.
- `generate_content.py`: thinking만 온 응답→재시도→정상, 두 번 다 잘림→에러, text 여러 블록→thinking 제외, tool_use만→재시도 불가 에러. (`--dry-run` 프롬프트·SKIP 경로도 확인)

**확인 못 한 것**
- 실제 Reddit OAuth 호출(자격증명 없음), 실제 Anthropic 호출(API 키 없음). 16,000이 적정한지는 다음 실행 로그의 "응답 N자 (출력 토큰 N)"으로 확인할 것.
- Reddit을 계속 쓸지 여부는 사용자 결정(앱 생성 + 시크릿 2개). 넣지 않으면 리포트에 실패 한 줄이 계속 남는다(의도된 표시).

### 2026-11-26 — 확인만 하고 고치지 않은 것
- **월요일 리포트가 두 번 생성된다.** 같은 날짜 리포트를 ①클라우드 세션(커밋 작성자 `Claude <noreply@anthropic.com>`, 09:09~09:12 KST)과 ②GitHub Actions(예정 09:00 KST, 실제 13:19~16:10 KST)가 각각 만든다. Actions 스케줄 실행이 cron(00:00 UTC)보다 4~7시간 늦게 시작해서(00:00 UTC는 GitHub 스케줄이 가장 몰리는 시각) ②가 ①의 결과·상태 파일을 덮어쓴다. Anthropic API 호출도 두 번이다. ①이 무엇으로 도는지(파이 스케줄 태스크·Cowork 등)는 이 레포 밖이라 확인하지 못했다. 스케줄 변경은 사용자 승인 사항이라 손대지 않았다.
- **원격 브랜치 3개**: `claude/charming-tesla-cypq91`은 master에 완전히 포함, `claude/agent-dev-references`(PR #2)·`claude/cc-monitor-big-news`(PR #1)는 내용이 master에 squash 머지됨. 셋 다 지워도 되는 상태지만 삭제는 사용자 결정.

### 2026-11-27 — Reddit 제거, Hacker News로 교체

**계기**
- 사용자 요청: "Reddit 대신 Hacker News로 채워봐". 2026-11-26에 Reddit OAuth(선택)를 넣어 두었지만, 쓰려면 사용자가 직접 ① Reddit 앱 생성 ② 저장소 시크릿 2개 추가 ③ 워크플로 env 2줄 추가(workflows 권한 필요)를 해야 했다. 도구 하나 때문에 사용자에게 계속 관리 부담이 남고, 시크릿을 넣지 않으면 리포트에 실패 한 줄이 영원히 남는다.
- Hacker News는 Algolia 공개 API(`hn.algolia.com/api/v1/search`, `search_by_date`)라 키가 필요 없고, 2026-10-27 이후 `hackernews_major`(업계 300점 이상)로 이미 잘 동작하고 있었다.

**바꾼 것**
- Reddit 수집을 전부 걷어냈다: `collect_reddit()`, `Fetcher`의 `reddit_client_id/secret`·`reddit_token()`·`reddit_oauth`, `REDDIT_UA`/`REDDIT_BLOCK_HINT`, `main()`의 `REDDIT_*` env 전달, 감시 표의 `Reddit(주간 상위)` 열과 `row["reddit"]`(경고 신호에서도 뺐다), `config.json` `reddit_subs`/`reddit_min_score`, fixture의 `reddit::*` 키.
- `collect_hn` 확장 — Reddit이 하던 '서브레딧별 인기 글' 자리를 HN이 대신하도록:
  - 최근 7일 창을 ① 최신순(`search_by_date`, 100건) ② 인기순(`search`, 100건) 두 번 본다. ①의 `nbHits`는 예전처럼 '이번 주 그 키워드 글 수'(키워드 급증·감시 판정용)로 쓰고, ②는 인기순 목록에 밀린 고득점 글을 보탠다.
  - **포인트 `hn_min_points`(50)와 댓글 `hn_min_comments`(10)을 둘 다 넘은 글만** 후보. 댓글 기준을 둔 이유: 댓글 0개짜리 링크는 '토론'이 아니다. Algolia `numericFilters`로 한 번, 코드에서 한 번 더 건다.
  - 같은 글이 두 경로·여러 키워드에 걸려도 **한 번만** 센다(수집기 안에서 `objectID` 기준 합치, mentions를 두 번 더하지 않는다).
  - 항목에 `points`·`comments`·`discussion_url`을 넣고, 커뮤니티 글 요약을 `HN N점 · 댓글 M개`로 바꿨다(예전 `HN 토론: <url>`).
- `judge_value`의 '설명 부족(확인 필요)' 판정에서 HN 글(`kind=community`)은 뺐다. 예전 요약이 `HN 토론: <url>`로 30자를 넘겼는데 `HN 400점 · 댓글 120개`로 줄자 HN 글이 전부 '확인 필요'로 찍혔다. HN 글은 제목이 곧 내용이라 요약 길이는 근거가 아니다.
- 리포트: Reddit 열이 빠진 감시 표 자리에 **"커뮤니티 반응 (Hacker News, 최근 7일)"** 섹션(포인트 순 상위 5개, 링크는 HN 토론)을 넣었다. 항목 상세에는 `HN 반응: 포인트 N · 댓글 M개`. `latest-top.json`의 top 항목에 `points`·`comments`·`discussion_url` 추가(기존 키는 그대로라 `generate_content.py`·`slack_notify.py`는 손대지 않았다).
- 워크플로 파일은 **바꾸지 않았다**. Reddit env 2줄은 master에 들어가지 않았고(workflows 권한), 이제 필요도 없다. 로컬에 미커밋으로 남아 있던 그 2줄도 되돌렸다.

**검증 (2026-11-27, 로컬)**
- `py_compile` 통과. fixture 6종(dry_run_sample ①~⑤) 전부 exit 0. 2026-11-26 버전과 출력 diff는 의도한 것만: Reddit 3건이 빠지고 HN 인기순 글 2건이 들어오면서 상위 6 → 5개, HN 요약 문구, 새 HN 섹션, 문구(HN/Reddit → Hacker News).
- 실제 네트워크 `--dry-run`(GITHUB_TOKEN 없이): **실패 소스 0개, 수집 297건, Hacker News 36건 수집**(키워드 10개 · 포인트 50+/댓글 10+, 건수는 실행 시점에 따라 달라진다). HN이 상위 10개 중 4건(Anthropic IPO·GPT-6/6.2 관련)과 새 '커뮤니티 반응' 섹션 상위 5개를 채웠다.
- `--dry-run --watchlist`로 감시 표 5열(Reddit 열 빠짐) 렌더링 확인.

**확인 못 한 것**
- Actions(인증된 `GITHUB_TOKEN`)에서의 실행은 못 돌렸다. 로컬에서는 `gh auth token` 값이 GitHub API에 401로 거절되고 익명 호출만 통과해, GitHub 검색 15개 중 6개가 레이트리밋으로 실패했다(레이트리밋이지 코드 문제가 아니다 — Actions에서는 토큰이 붙어 정상).
- 50포인트·10댓글이 적정한지는 몇 주 돌려 봐야 한다. 후보가 너무 적으면 `config.json` `community.hn_min_points`/`hn_min_comments`를 내리면 된다.
- 남은 품질 이슈(이번에 고치지 않음): 같은 소식이 HN과 OpenAI RSS에 동시에 올라와 상위에 두 칸을 차지하는 경우가 있다(예: `GPT-6 models demonstrate intrinsic protein-design capabilities`). `fold_same_story`는 제목에서 제품·모델 이름(4단어 이내)을 뽑아 합치는데, 긴 문장형 제목은 이름이 안 뽑혀 합쳐지지 않는다. URL이 같은 경우까지 합치도록 넓히는 게 다음 후보.

### 2026-11-27 — 워드프레스 자동 발행 (글이 실제 블로그에 올라감)

**계기**
- 사용자 요청: "이제 자동으로 수집해서 블로그 글 쓰는 거를 올려봐". 지금까지 블로그 초안은 `content/blog/`에만 생기고 Slack 스레드로 전달될 뿐, 블로그에는 사람이 직접 복사해 붙여야 했다.

**사용자가 정한 것 / 내가 판단한 것**
- **사용자 결정: "바로 공개하고"** — 자동 발행의 기본 상태는 `publish`(공개). 내가 제안한 기본값은 `draft`(초안)였고, 사용자가 공개를 택했다. `--status draft`는 수동용으로 남겨 뒀다. 공개로 돌리면 그 주 글이 사용자 확인 없이 블로그에 올라가고, 검색·구독자에게 노출된다는 점은 이 결정에 포함된 것으로 본다.
- 내 판단 ① 업로드는 **Pickle 예약 액션**(`📮 주간 블로그 글 워드프레스 발행`)이 맡는다. 워크플로 안에서 올리는 쪽이 더 단순하지만, 이 환경의 GitHub App에 `workflows` 권한이 없어 ① 워크플로 파일 수정(스텝 추가)이 remote에서 거부되고 ② `actions/secrets` 등록도 403(`Resource not accessible by integration`)이다. 사용자가 github.com 웹에서 시크릿 등록 + YAML 붙여넣기를 해야 하는 방식은 "자동으로 되게 해"라는 요구와 맞지 않아, **사용자가 아무것도 하지 않아도 되는** 예약 액션 쪽으로 정했다.
- 내 판단 ② 예약 실행은 **발행 전용 클론**(`/workspace/repos/experiment-publish`)만 `git fetch && git reset --hard`로 되돌린다. 작업 사본(`/workspace/repos/experiment`)을 되돌리면 그때 다른 작업 중인 변경이 날아가기 때문. `git clean`은 쓰지 않는다.
- 내 판단 ③ 자동 발행은 **최근 8일 안의 글만** 대상으로 한다(`--max-age-days`, 기본 8). 이 제한이 없으면 Actions가 SKIP인 주에 10월 글 같은 옛 글이 뒤늦게 공개될 수 있다.

**바꾼 것**
- `publish_wordpress.py` 신규: 프론트매터(title·slug·meta_description·tags) 파싱 → 마크다운 HTML 변환(`markdown`) → WordPress REST `posts/new` 업로드. `--dry-run`, `--status draft|publish`(기본 publish), `--file`, `--max-age-days`. 토큰은 `WORDPRESS_ACCESS_TOKEN` 우선, 없으면 토큰 파일(기본 `/workspace/.pickle-secrets/wordpress-earninsu.json`). 토큰은 로그에 찍지 않는다.
- 중복 방지: 업로드 전 `/sites/{site}/posts/?status=any`로 최근 글을 받아 **같은 슬러그 또는 같은 제목**이면 건너뛴다(휴지통은 제외). 월 19:00·화 08:00 두 번 돌아도 한 번만 올라간다.
- `generate_content.py`: 블로그 글을 `content/blog/`에 쓰면서 같은 내용을 `research/content/{날짜}-blog.md`에도 저장. 워크플로가 `git add research/`만 하므로 이 사본이 커밋되어 발행 입력이 된다(동시에 주간 글의 커밋 기록).
- `requirements.txt`에 `markdown` 추가. `scripts/publish_latest.sh`(워크스페이스, 레포 밖)는 발행 전용 클론을 최신 master로 맞추고 스크립트를 호출한다.

**검증 (2026-11-27, 로컬)**
- `py_compile` 통과. `monitor.py --dry-run`(fixture 전체)·`generate_content.py --dry-run` 회귀 확인.
- 예시 글(2026-11-16 인스타 카드뉴스 원문, 제목에 `[테스트]`)으로 **실제 공개 발행**: ID 48 → `https://earninsu.wordpress.com/2026/11/27/test-wp-auto-publish-check/` (HTTP 200 확인). 같은 파일로 다시 실행 → "건너뜀: 이미 올린 글입니다 (ID 48…)" 확인. 확인 후 휴지통으로 옮겨(status `trash`, 페이지 404) 블로그에 테스트 글이 남지 않게 했다.
- `--dry-run`은 업로드 없이 대상·중복 여부만 출력하고 exit 0.

**확인 못 한 것 / 남은 것**
- 워크플로 수동 실행(`actions/workflows/.../dispatches`)은 `actions:write` 권한이 없어 403일 가능성이 크다(이번에 시도해 본 결과는 PR 본문 참고).
- Actions에서 생성→커밋→예약 액션이 발행하는 전체 흐름은 **월요일 첫 실행**에서 처음 돈다. 그 전까지는 위의 예시 글로 발행·중복 방지·휴지통만 확인했다.
- 나중에 워크플로 권한이 생기면 "블로그 + 인스타 컨텐츠 생성" 스텝 뒤에 `pip install markdown && python projects/claude-code-monitor/publish_wordpress.py --status publish` 스텝과 `WORDPRESS_ACCESS_TOKEN` 시크릿을 넣어 Actions 안에서 바로 발행할 수 있다(스크립트는 그대로 쓴다).
