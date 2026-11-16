# Claude Code·AI 도구 소식 모니터 (2026-11-16)

> 공식 발표 · 업계(OpenAI·Google) 발표 · GitHub 신규/급상승 · 커뮤니티(HN/Reddit)를 모아 글감 가치 판정을 통과한 것만 상위 10개 싣는다. 🔥대형 발표(새 제품·새 모델 출시)는 점수와 무관하게 맨 위, 나머지는 점수순. 릴리스 노트는 이번 주기분을 묶어 줄 단위로 판정한다. 이미 다룬 소식은 반응이 급증한 경우(재부상)만 다시 싣는다.

## 오늘의 핵심 3줄

1. [코딩] 🔥대형 발표 공식 [Anthropic 뉴스] Introducing Claude Fable 5.2 and Claude Mythos 5.2 — announcements, models · 2026-11-09 발표 — Our most capable models for daunting technical wo…
2. [기타] 🔥대형 발표 공식 [Anthropic 뉴스] Anthropic launches roadshow for proposed initial public offering — Announcements · 2026-11-10 발표
3. [영상/에이전트] JuneYaooo/rea-video — Reverse-engineer any video, shot by shot: filmed, AI-generated or coded, and how to remak…

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
- **Hacker News** — ProxyError: HTTPSConnectionPool(host='hn.algolia.com', port=443): Max retries exceeded with url: /api/v1/search_by_date?query=claude+code&tags=story&numericFilters=created_at_i%3E1794182789&hitsPerPage=100 (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 For
- **Reddit** — ProxyError: HTTPSConnectionPool(host='www.reddit.com', port=443): Max retries exceeded with url: /r/ClaudeAI/top.json?t=week&limit=50 (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden')))

## 상위 10개 (글감급만, 점수 = 중요도 + 글감 가치)

| # | 점수 | 카테고리 | 소식 | 처음 등장 | 출처 |
|---|---|---|---|---|---|
| 1 | 78 | 코딩 | [[Anthropic 뉴스] Introducing Claude Fable 5.2 and Claude Mythos 5.2](https://www.anthropic.com/claude-fable-and-mythos-5-2) 🆕 | 2026-11-16 | anthropic_news |
| 2 | 75 | 기타 | [[Anthropic 뉴스] Anthropic launches roadshow for proposed initial public offering](https://www.anthropic.com/news/roadshow-launch) 🆕 | 2026-11-16 | anthropic_news |
| 3 | 91 | 영상/에이전트 | [JuneYaooo/rea-video](https://github.com/JuneYaooo/rea-video) 🔁재부상 | 2026-11-09 | github_search |
| 4 | 89 | 영상/디자인/에이전트/코딩 | [lemomo-ai/lemo-opuscar](https://github.com/lemomo-ai/lemo-opuscar) 🔁재부상 | 2026-10-14 | github_search, watchlist |
| 5 | 88 | 영상 | [mromidev/claude-animated-shorts](https://github.com/mromidev/claude-animated-shorts) 🔁재부상 | 2026-11-02 | github_search |
| 6 | 85 | 영상/디자인/에이전트/코딩 | [OpenMontageInc/OpenMontage](https://github.com/OpenMontageInc/OpenMontage) | 2026-11-09 | github_search |
| 7 | 80 | 영상/에이전트/코딩 | [openfilm/openfilm](https://github.com/openfilm/openfilm) 🔁재부상 | 2026-10-26 | github_search |
| 8 | 72 | 디자인 | [heydamir/unslop](https://github.com/heydamir/unslop) 🔁재부상 | 2026-11-02 | github_search |
| 9 | 71 | 영상/에이전트/코딩 | [XiaoyeCodes/code-animation-prompts](https://github.com/XiaoyeCodes/code-animation-prompts) 🆕 | 2026-11-16 | github_search |
| 10 | 70 | 영상/에이전트 | [UnderleveledBuilder/awesome-short-drama-skills](https://github.com/UnderleveledBuilder/awesome-short-drama-skills) 🔁재부상 | 2026-10-26 | github_search |

### 1. [Anthropic 뉴스] Introducing Claude Fable 5.2 and Claude Mythos 5.2

- 링크: https://www.anthropic.com/claude-fable-and-mythos-5-2
- 내용: announcements, models · 2026-11-09 발표 — Our most capable models for daunting technical work, Claude Fable 5.2 and Claude Mythos 5.2 set a new bar in coding, finance, and the sciences.
- 발표일(소스 기준): 2026-11-09
- 원문 발췌: Claude Fable 5.2 and Claude Mythos 5.2, our new models for the hardest technical challenges. Fable 5.2 sets a new bar in coding, finance, and the sciences. / Introducing Claude Fable 5.2 and Claude M…
- 점수 근거: 중요도 43 (공식 +35, 일반 사용자 영향(코딩) +3, 신규 +5)
- 글감 판정: +35 (새 기능 표현(할 수 있게 됨) +5, 대형 발표 +30)

### 2. [Anthropic 뉴스] Anthropic launches roadshow for proposed initial public offering

- 링크: https://www.anthropic.com/news/roadshow-launch
- 내용: Announcements · 2026-11-10 발표
- 발표일(소스 기준): 2026-11-10
- 원문 발췌: Today Anthropic, PBC launched the roadshow for its proposed initial public offering of its Class A common stock. / Anthropic launches roadshow for proposed initial public offering \ Anthropic Skip to…
- 점수 근거: 중요도 40 (공식 +35, 신규 +5)
- 글감 판정: +35 (새 기능 표현(할 수 있게 됨) +5, 대형 발표 +30)

### 3. JuneYaooo/rea-video

- 링크: https://github.com/JuneYaooo/rea-video
- 내용: Reverse-engineer any video, shot by shot: filmed, AI-generated or coded, and how to remake it. Breakdowns in the open VIDEO.md format. 逆向一切视频，逐个镜头看是拍的、AI 生成的还是代码做的，再告诉你怎么复刻；拆解结果按 VIDEO.md 格式输出。
- 스타: 9,175
- 점수 근거: 중요도 45 (스타 +4,405/7일 +25, 일반 사용자 영향(영상/에이전트) +15, 재부상 +5)
- 글감 판정: +46 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 스킬·플러그인·도구 출시 +8, 스타 급증 +12, 유명(스타 9,175) +6, 감시 키워드(remotion, video) +10)

### 4. lemomo-ai/lemo-opuscar

- 링크: https://github.com/lemomo-ai/lemo-opuscar
- 내용: A toolbox of film styles made in code for Claude Code: 99 ready to use, and your own. Each style is a style prompt plus a demo film made entirely in code by Claude Opus 5.5, with no video model. By Lemomo. · 一套用代码做片的风格工具箱：99 种现成风格，也能做出你自己的
- 스타: 16,765
- 점수 근거: 중요도 45 (스타 +2,996/7일 +25, 일반 사용자 영향(영상/디자인/에이전트/코딩) +15, 재부상 +5)
- 글감 판정: +44 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 스킬·플러그인·도구 출시 +8, 스타 급증 +12, 유명(스타 16,765) +6, 감시 키워드(video) +8)

### 5. mromidev/claude-animated-shorts

- 링크: https://github.com/mromidev/claude-animated-shorts
- 내용: Free Claude skill: viral animated story shorts (2D characters in a 3D world) with three.js + Remotion
- 스타: 3,559
- 점수 근거: 중요도 42 (스타 +1,098/7일 +22, 일반 사용자 영향(영상) +15, 재부상 +5)
- 글감 판정: +46 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 스킬·플러그인·도구 출시 +8, 스타 급증 +12, 유명(스타 3,559) +6, 감시 키워드(remotion) +10)

### 6. OpenMontageInc/OpenMontage

- 링크: https://github.com/OpenMontageInc/OpenMontage
- 내용: World's first open-source, agentic video production system. 12 production pipelines, 100+ tools, 700+ agent skill and production-knowledge files. Turn your AI coding assistant into a full video production studio.
- 스타: 80,713
- 점수 근거: 중요도 39 (스타 +1,948/7일 +24, 일반 사용자 영향(영상/디자인/에이전트/코딩) +15)
- 글감 판정: +46 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 스킬·플러그인·도구 출시 +8, 스타 급증 +12, 유명(스타 80,713) +6, 감시 키워드(remotion, video) +10)

### 7. openfilm/openfilm

- 링크: https://github.com/openfilm/openfilm
- 내용: The open source AI video agent: turns any coding agent into a video agent, with an editor to change anything it makes.
- 스타: 7,508
- 점수 근거: 중요도 44 (스타 +2,107/7일 +24, 일반 사용자 영향(영상/에이전트/코딩) +15, 재부상 +5)
- 글감 판정: +36 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 스타 급증 +12, 유명(스타 7,508) +6, 감시 키워드(video) +8)

### 8. heydamir/unslop

- 링크: https://github.com/heydamir/unslop
- 내용: A Claude skill that turns vibecoded, AI-looking UI into a designed interface
- 스타: 16,749
- 점수 근거: 중요도 42 (스타 +4,599/7일 +25, 일반 사용자 영향(디자인) +12, 재부상 +5)
- 글감 판정: +30 (스킬·플러그인·도구 출시 +8, 스타 급증 +12, 유명(스타 16,749) +6, 감시 키워드(design) +4)

### 9. XiaoyeCodes/code-animation-prompts

- 링크: https://github.com/XiaoyeCodes/code-animation-prompts
- 내용: 341 种代码动画风格提示词、196 张参考静帧与离线挑选器，封装为 Claude Code / Codex Skill，支持一键导入与 HTML 视频渲染。
- 스타: 1,117
- 점수 근거: 중요도 39 (스타 +445/7일(추정) +19, 일반 사용자 영향(영상/에이전트/코딩) +15, 신규 +5)
- 글감 판정: +32 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 스킬·플러그인·도구 출시 +8, 스타 증가 +6, 감시 키워드(video) +8)

### 10. UnderleveledBuilder/awesome-short-drama-skills

- 링크: https://github.com/UnderleveledBuilder/awesome-short-drama-skills
- 내용: AI 短剧 · 漫剧 Skill（技能包）精选：剧本、改编、分镜、Seedance / 可灵 / MiniMax 视频提示词，千问、豆包、龙虾 OpenClaw、WorkBuddy、Claude Code、Codex 等智能体可用 | Curated agent skills for AI short drama, micro drama / microdrama, vertical drama and manju (AI comic drama): screenwriting, storyboards, Seedance / Kling / MiniMax video prompts
- 스타: 2,356
- 점수 근거: 중요도 38 (스타 +310/7일 +18, 일반 사용자 영향(영상/에이전트) +15, 재부상 +5)
- 글감 판정: +32 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 스킬·플러그인·도구 출시 +8, 스타 증가 +6, 감시 키워드(video) +8)

## 글감 미달로 뺀 항목 (참고, 중요도순 상위 5)

새 소식이지만 글감 가치가 최소 점수(10) 미만이라 후보에서 뺐다. 기준 조정은 config.json `value_rules`.

- [Claude Code 공식 문서 목차] 새 페이지: claude-models-on-google-cloud-anthropic-managed.md — 글감 +0 (해당 규칙 없음)
- [Claude Code 공식 문서 목차] 새 페이지: code-mode.md — 글감 +0 (해당 규칙 없음)
- Seagey/couch-tv — 글감 +6 (스타 증가 +6)
- INSANE0777/Awwwards-mcp — 글감 +4 (감시 키워드(design) +4)
- wuyoscar/AISafetyHot — 글감 +6 (스타 증가 +6)

## 주간 키워드 감시 리스트 점검

큰 소식이 점수 체계에서 빠지는 것을 막는 안전장치. 키워드에 걸린 항목은 후보 풀에 올려 가산점을 준다. 그래도 바깥 반응이 있는데 최근 7일 리포트에 없으면 ⚠️.

| 키워드 | GitHub(7일 활동, claude 포함) | HN(7일) | Reddit(주간 상위) | 최근 리포트 반영 | 상위 레포 |
|---|---|---|---|---|---|
| remotion | 739 | 실패 | 실패 | 예 | stablyai/orca, Vincentwei1021/video-shotcraft, NanmiCoder/cc-haha |
| video | 1529 | 실패 | 실패 | 예 | ruvnet/RuView, Vincentwei1021/video-shotcraft, lemomo-ai/lemo-opuscar |
| motion graphics | 113 | 실패 | 실패 | ⚠️ 아니오 | Vincentwei1021/anything2explainer, ChatCut-Inc/agent-plugin, zhuyansen/awesome-opus-5.5-video |
| slides | 195 | 실패 | 실패 | ⚠️ 아니오 | alchaincyf/huashu-design, genspark-ai/genoffice, OpenCoworkAI/open-codesign |
| pptx | 59 | 실패 | 실패 | ⚠️ 아니오 | alchaincyf/huashu-design, genspark-ai/genoffice, carnot-tech/jinba-consulting-pptx-skill |
| google workspace | 16 | 실패 | 실패 | ⚠️ 아니오 | taylorwilsdon/google_workspace_mcp, conorbronsdon/gws-mcp-server, Artoxem/workspace-operator |
| design | 1283 | 실패 | 실패 | 예 | nextlevelbuilder/ui-ux-pro-max-skill, cathrynlavery/diagram-design, Nutlope/hallmark |
| excel | 136 | 실패 | 실패 | ⚠️ 아니오 | AgriciDaniel/claude-seo, genspark-ai/genoffice, haris-musa/excel-mcp-server |

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
| Claude Code 공식 문서 목차 | 성공 | 2 | 전체 216개 |
| Claude 플랫폼 문서 목차 | ❌ 실패 | 0 | RuntimeError: 링크 0개 — 페이지 구조 변경 또는 차단 의심 |
| Anthropic 뉴스 | 성공 | 2 | 전체 109개 중 최근 14일·대상 분류 2개 |
| OpenAI 뉴스 | ❌ 실패 | 0 | ProxyError: HTTPSConnectionPool(host='openai.com', port=443): Max retries exceeded with url: /news/rss.xml (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden'))) |
| Google AI 블로그 | ❌ 실패 | 0 | ProxyError: HTTPSConnectionPool(host='blog.google', port=443): Max retries exceeded with url: /technology/ai/rss/ (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden'))) |
| Google DeepMind 블로그 | ❌ 실패 | 0 | ProxyError: HTTPSConnectionPool(host='deepmind.google', port=443): Max retries exceeded with url: /blog/rss.xml (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden'))) |
| GitHub 검색(신규·토픽) | 성공 | 450 | 쿼리 15개 |
| Hacker News | ❌ 실패 | 0 | ProxyError: HTTPSConnectionPool(host='hn.algolia.com', port=443): Max retries exceeded with url: /api/v1/search_by_date?query=claude+code&tags=story&numericFilters=created_at_i%3E1794182789&hitsPerPage=100 (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 For |
| Reddit | ❌ 실패 | 0 | ProxyError: HTTPSConnectionPool(host='www.reddit.com', port=443): Max retries exceeded with url: /r/ClaudeAI/top.json?t=week&limit=50 (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden'))) |
| 대형 발표 원문·국내 기사 | 성공 | 2 | 대형 발표 2개 |

*추적 중이지만 이번에 싣지 않은 항목 327개 (이미 다룸·변화 없음·점수 미달). 생성: 2026-11-16 | projects/claude-code-monitor/monitor.py*
