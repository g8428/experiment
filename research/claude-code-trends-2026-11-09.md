# Claude Code·AI 도구 소식 모니터 (2026-11-09)

> 공식 발표 · 업계(OpenAI·Google) 발표 · GitHub 신규/급상승 · 커뮤니티(HN/Reddit)를 모아 글감 가치 판정을 통과한 것만 상위 10개 싣는다. 🔥대형 발표(새 제품·새 모델 출시)는 점수와 무관하게 맨 위, 나머지는 점수순. 릴리스 노트는 이번 주기분을 묶어 줄 단위로 판정한다. 이미 다룬 소식은 반응이 급증한 경우(재부상)만 다시 싣는다.

## 오늘의 핵심 3줄

1. [영상/에이전트] JuneYaooo/rea-video — Reverse-engineer any video, shot by shot: filmed, AI-generated or coded, and how to remak…
2. [영상/디자인/에이전트] Vincentwei1021/video-shotcraft — AI video skill for Claude Code & Codex — cinematic, editable product promos with Remotion…
3. [영상/에이전트] alchaincyf/huashu-art-motion — 艺术动画skill：35种艺术风格、9种解说语法，用代码让画动起来。

## ⚠️ 수집 실패

아래 소스는 이번에 수집하지 못했다. **이 소스에서 나온 소식은 이번 리포트에 빠져 있을 수 있다.**

- **Claude Code 릴리스** — HTTPError: 403 Client Error: Forbidden for url: https://api.github.com/repos/anthropics/claude-code/releases?per_page=15
- **Claude Code CHANGELOG** — HTTPError: 403 Client Error: Forbidden for url: https://api.github.com/repos/anthropics/claude-code/contents/CHANGELOG.md
- **Anthropic 공식 스킬** — HTTPError: 403 Client Error: Forbidden for url: https://api.github.com/repos/anthropics/skills/contents/skills
- **Claude Code 내장 플러그인** — HTTPError: 403 Client Error: Forbidden for url: https://api.github.com/repos/anthropics/claude-code/contents/plugins
- **공식 플러그인 마켓플레이스 (존재 확인 못 함)** — HTTPError: 403 Client Error: Forbidden for url: https://api.github.com/repos/anthropics/claude-plugins-official/contents/plugins
- **Claude 플랫폼 문서 목차** — RuntimeError: 링크 0개 — 페이지 구조 변경 또는 차단 의심
- **OpenAI 뉴스** — ProxyError: HTTPSConnectionPool(host='openai.com', port=443): Max retries exceeded with url: /news/rss.xml (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden')))
- **Google AI 블로그** — ProxyError: HTTPSConnectionPool(host='blog.google', port=443): Max retries exceeded with url: /technology/ai/rss/ (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden')))
- **Google DeepMind 블로그** — ProxyError: HTTPSConnectionPool(host='deepmind.google', port=443): Max retries exceeded with url: /blog/rss.xml (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden')))
- **Hacker News** — ProxyError: HTTPSConnectionPool(host='hn.algolia.com', port=443): Max retries exceeded with url: /api/v1/search_by_date?query=claude+code&tags=story&numericFilters=created_at_i%3E1793578033&hitsPerPage=100 (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 For
- **Reddit** — ProxyError: HTTPSConnectionPool(host='www.reddit.com', port=443): Max retries exceeded with url: /r/ClaudeAI/top.json?t=week&limit=50 (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden')))

## 상위 10개 (글감급만, 점수 = 중요도 + 글감 가치)

| # | 점수 | 카테고리 | 소식 | 처음 등장 | 출처 |
|---|---|---|---|---|---|
| 1 | 91 | 영상/에이전트 | [JuneYaooo/rea-video](https://github.com/JuneYaooo/rea-video) 🆕 | 2026-11-09 | github_search |
| 2 | 90 | 영상/디자인/에이전트 | [Vincentwei1021/video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft) 🔁재부상 | 2026-10-14 | github_search |
| 3 | 86 | 영상/에이전트 | [alchaincyf/huashu-art-motion](https://github.com/alchaincyf/huashu-art-motion) 🆕 | 2026-11-09 | github_search |
| 4 | 81 | 영상/디자인/에이전트 | [patch-gg/pixelfx](https://github.com/patch-gg/pixelfx) 🔁재부상 | 2026-11-02 | github_search |
| 5 | 79 | 영상 | [mromidev/claude-animated-shorts](https://github.com/mromidev/claude-animated-shorts) | 2026-11-02 | github_search |
| 6 | 78 | 영상/에이전트/코딩 | [openfilm/openfilm](https://github.com/openfilm/openfilm) 🔁재부상 | 2026-10-26 | github_search |
| 7 | 76 | 영상/에이전트/코딩 | [alchaincyf/huashu-motion](https://github.com/alchaincyf/huashu-motion) 🔁재부상 | 2026-10-26 | github_search |
| 8 | 74 | 영상/디자인/에이전트/코딩 | [Leonxlnx/cinetic](https://github.com/Leonxlnx/cinetic) | 2026-10-14 | github_search |
| 9 | 72 | 디자인 | [heydamir/unslop](https://github.com/heydamir/unslop) 🔁재부상 | 2026-11-02 | github_search |
| 10 | 71 | 영상/자동화/에이전트/코딩 | [howznguyen/shorts-kit](https://github.com/howznguyen/shorts-kit) 🆕 | 2026-11-09 | github_search |

### 1. JuneYaooo/rea-video

- 링크: https://github.com/JuneYaooo/rea-video
- 내용: Reverse-engineer any video, shot by shot: filmed, AI-generated or coded, and how to remake it. 逆向一切视频，逐个镜头看是拍的、AI 生成的还是代码做的，再告诉你怎么复刻。
- 스타: 4,445
- 점수 근거: 중요도 45 (스타 +3,012/7일(추정) +25, 일반 사용자 영향(영상/에이전트) +15, 신규 +5)
- 글감 판정: +46 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 스킬·플러그인·도구 출시 +8, 스타 급증 +12, 유명(스타 4,445) +6, 감시 키워드(remotion, video) +10)

### 2. Vincentwei1021/video-shotcraft

- 링크: https://github.com/Vincentwei1021/video-shotcraft
- 내용: AI video skill for Claude Code & Codex — cinematic, editable product promos with Remotion: 124 shot recipe cards, 150 motion previews, beat sync, sound design, Motion Workbench & JianYing (CapCut CN) export.
- 스타: 17,893
- 점수 근거: 중요도 44 (스타 +2,075/7일 +24, 일반 사용자 영향(영상/디자인/에이전트) +15, 재부상 +5)
- 글감 판정: +46 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 스킬·플러그인·도구 출시 +8, 스타 급증 +12, 유명(스타 17,893) +6, 감시 키워드(remotion, video, design) +10)

### 3. alchaincyf/huashu-art-motion

- 링크: https://github.com/alchaincyf/huashu-art-motion
- 내용: 艺术动画skill：35种艺术风格、9种解说语法，用代码让画动起来。
- 스타: 6,539
- 점수 근거: 중요도 42 (스타 +1,354/7일(추정) +23, 일반 사용자 영향(영상/에이전트) +15, 신규 +5)
- 글감 판정: +44 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 스킬·플러그인·도구 출시 +8, 스타 급증 +12, 유명(스타 6,539) +6, 감시 키워드(video) +8)

### 4. patch-gg/pixelfx

- 링크: https://github.com/patch-gg/pixelfx
- 내용: 244 pixel art effects, every one a small piece of code. Plus a Claude Code skill to make your own.
- 스타: 6,080
- 점수 근거: 중요도 45 (스타 +3,530/7일 +25, 일반 사용자 영향(영상/디자인/에이전트) +15, 재부상 +5)
- 글감 판정: +36 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 스킬·플러그인·도구 출시 +8, 스타 급증 +12, 유명(스타 6,080) +6)

### 5. mromidev/claude-animated-shorts

- 링크: https://github.com/mromidev/claude-animated-shorts
- 내용: Free Claude skill: viral animated story shorts (2D characters in a 3D world) with three.js + Remotion
- 스타: 2,422
- 점수 근거: 중요도 39 (스타 +2,241/7일 +24, 일반 사용자 영향(영상) +15)
- 글감 판정: +40 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 스킬·플러그인·도구 출시 +8, 스타 급증 +12, 감시 키워드(remotion) +10)

### 6. openfilm/openfilm

- 링크: https://github.com/openfilm/openfilm
- 내용: The open source AI video agent: turns any coding agent into a video agent, with an editor to change anything it makes.
- 스타: 5,346
- 점수 근거: 중요도 42 (스타 +1,249/7일 +22, 일반 사용자 영향(영상/에이전트/코딩) +15, 재부상 +5)
- 글감 판정: +36 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 스타 급증 +12, 유명(스타 5,346) +6, 감시 키워드(video) +8)

### 7. alchaincyf/huashu-motion

- 링크: https://github.com/alchaincyf/huashu-motion
- 내용: 让你的agent一键直出商业级产品宣传片：会作曲，能指着画面改。Commercial-grade launch films by your coding agent — point at the frame to change it.
- 스타: 2,523
- 점수 근거: 중요도 40 (스타 +516/7일 +20, 일반 사용자 영향(영상/에이전트/코딩) +15, 재부상 +5)
- 글감 판정: +37 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 새 기능 표현(할 수 있게 됨) +5, 스킬·플러그인·도구 출시 +8, 스타 증가 +6, 감시 키워드(video) +8)

### 8. Leonxlnx/cinetic

- 링크: https://github.com/Leonxlnx/cinetic
- 내용: Cinematic launch films and motion design from code, directed by your coding agent.
- 스타: 1,084
- 점수 근거: 중요도 35 (스타 +575/7일 +20, 일반 사용자 영향(영상/디자인/에이전트/코딩) +15)
- 글감 판정: +39 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 새 기능 표현(할 수 있게 됨) +5, 스킬·플러그인·도구 출시 +8, 스타 증가 +6, 감시 키워드(remotion, video, design) +10)

### 9. heydamir/unslop

- 링크: https://github.com/heydamir/unslop
- 내용: A Claude skill that turns vibecoded, AI-looking UI into a designed interface
- 스타: 11,965
- 점수 근거: 중요도 42 (스타 +7,122/7일 +25, 일반 사용자 영향(디자인) +12, 재부상 +5)
- 글감 판정: +30 (스킬·플러그인·도구 출시 +8, 스타 급증 +12, 유명(스타 11,965) +6, 감시 키워드(design) +4)

### 10. howznguyen/shorts-kit

- 링크: https://github.com/howznguyen/shorts-kit
- 내용: Make narrated vertical shorts (TikTok, YouTube Shorts, Reels) with a coding agent and Remotion. 9+ agent skills, 20+ story flows, fact ledger, CC0 SFX.
- 스타: 114
- 점수 근거: 중요도 35 (스타 +114/7일(추정) +15, 일반 사용자 영향(영상/자동화/에이전트/코딩) +15, 신규 +5)
- 글감 판정: +36 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 자동화·새 연동 +8, 스킬·플러그인·도구 출시 +8, 감시 키워드(remotion, video) +10)

## 글감 미달로 뺀 항목 (참고, 중요도순 상위 5)

새 소식이지만 글감 가치가 최소 점수(10) 미만이라 후보에서 뺐다. 기준 조정은 config.json `value_rules`.

- [Anthropic 뉴스] AI for Science expands to foundations and research institutions — 글감 +0 (해당 규칙 없음)
- [Anthropic 뉴스] Expanding our partnership with GSA to bring Claude to all levels… — 글감 +0 (해당 규칙 없음)
- UnderleveledBuilder/awesome-social-media-skills — 글감 +8 (스킬·플러그인·도구 출시 +8)
- stubbi/asm — 글감 +6 (스타 증가 +6)
- GabrieleLozupone/kokon — 글감 +0 (해당 규칙 없음)

## 주간 키워드 감시 리스트 점검

큰 소식이 점수 체계에서 빠지는 것을 막는 안전장치. 키워드에 걸린 항목은 후보 풀에 올려 가산점을 준다. 그래도 바깥 반응이 있는데 최근 7일 리포트에 없으면 ⚠️.

| 키워드 | GitHub(7일 활동, claude 포함) | HN(7일) | Reddit(주간 상위) | 최근 리포트 반영 | 상위 레포 |
|---|---|---|---|---|---|
| remotion | 719 | 실패 | 실패 | 예 | stablyai/orca, OpenMontageInc/OpenMontage, NanmiCoder/cc-haha |
| video | 1451 | 실패 | 실패 | 예 | ruvnet/RuView, OpenMontageInc/OpenMontage, lemomo-ai/lemo-opuscar |
| motion graphics | 79 | 실패 | 실패 | ⚠️ 아니오 | ChatCut-Inc/agent-plugin, zhuyansen/awesome-opus-5.5-video, notivn/AIEV |
| slides | 151 | 실패 | 실패 | ⚠️ 아니오 | alchaincyf/huashu-design, genspark-ai/genoffice, chuspeeism/dashi-ppt-skill |
| pptx | 68 | 실패 | 실패 | 예 | alchaincyf/huashu-design, genspark-ai/genoffice, chuspeeism/dashi-ppt-skill |
| google workspace | 15 | 실패 | 실패 | ⚠️ 아니오 | taylorwilsdon/google_workspace_mcp, maton-ai/api-gateway-skill, conorbronsdon/gws-mcp-server |
| design | 1208 | 실패 | 실패 | 예 | nextlevelbuilder/ui-ux-pro-max-skill, cathrynlavery/diagram-design, Nutlope/hallmark |
| excel | 115 | 실패 | 실패 | ⚠️ 아니오 | genspark-ai/genoffice, haris-musa/excel-mcp-server, sv-grid/sv-grid |

감시 리스트 일부 조회 실패: HN 'remotion' (ProxyError); HN 'video' (ProxyError); HN 'motion graphics' (ProxyError); HN 'slides' (ProxyError); HN 'pptx' (ProxyError); HN 'google workspace' (ProxyError); HN 'design' (ProxyError); HN 'excel' (ProxyError)

## 수집 상태

| 소스 | 결과 | 건수 | 비고 |
|---|---|---|---|
| Claude Code 릴리스 | ❌ 실패 | 0 | HTTPError: 403 Client Error: Forbidden for url: https://api.github.com/repos/anthropics/claude-code/releases?per_page=15 |
| Claude Code CHANGELOG | ❌ 실패 | 0 | HTTPError: 403 Client Error: Forbidden for url: https://api.github.com/repos/anthropics/claude-code/contents/CHANGELOG.md |
| Anthropic 공식 스킬 | ❌ 실패 | 0 | HTTPError: 403 Client Error: Forbidden for url: https://api.github.com/repos/anthropics/skills/contents/skills |
| Claude Code 내장 플러그인 | ❌ 실패 | 0 | HTTPError: 403 Client Error: Forbidden for url: https://api.github.com/repos/anthropics/claude-code/contents/plugins |
| 공식 플러그인 마켓플레이스 (존재 확인 못 함) | ❌ 실패 | 0 | HTTPError: 403 Client Error: Forbidden for url: https://api.github.com/repos/anthropics/claude-plugins-official/contents/plugins |
| Claude 제품 목록(새 제품) | 성공 | 0 | 전체 8개 |
| Claude Code 공식 문서 목차 | 성공 | 0 | 전체 239개 |
| Claude 플랫폼 문서 목차 | ❌ 실패 | 0 | RuntimeError: 링크 0개 — 페이지 구조 변경 또는 차단 의심 |
| Anthropic 뉴스 | 성공 | 3 | 전체 114개 중 최근 14일·대상 분류 3개 |
| OpenAI 뉴스 | ❌ 실패 | 0 | ProxyError: HTTPSConnectionPool(host='openai.com', port=443): Max retries exceeded with url: /news/rss.xml (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden'))) |
| Google AI 블로그 | ❌ 실패 | 0 | ProxyError: HTTPSConnectionPool(host='blog.google', port=443): Max retries exceeded with url: /technology/ai/rss/ (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden'))) |
| Google DeepMind 블로그 | ❌ 실패 | 0 | ProxyError: HTTPSConnectionPool(host='deepmind.google', port=443): Max retries exceeded with url: /blog/rss.xml (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden'))) |
| GitHub 검색(신규·토픽) | 성공 | 450 | 쿼리 15개 |
| Hacker News | ❌ 실패 | 0 | ProxyError: HTTPSConnectionPool(host='hn.algolia.com', port=443): Max retries exceeded with url: /api/v1/search_by_date?query=claude+code&tags=story&numericFilters=created_at_i%3E1793578033&hitsPerPage=100 (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 For |
| Reddit | ❌ 실패 | 0 | ProxyError: HTTPSConnectionPool(host='www.reddit.com', port=443): Max retries exceeded with url: /r/ClaudeAI/top.json?t=week&limit=50 (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden'))) |
| 대형 발표 원문·국내 기사 | 성공 | 0 | 대형 발표 0개 |

*추적 중이지만 이번에 싣지 않은 항목 329개 (이미 다룸·변화 없음·점수 미달). 생성: 2026-11-09 | projects/claude-code-monitor/monitor.py*
