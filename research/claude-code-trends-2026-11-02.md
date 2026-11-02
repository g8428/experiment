# Claude Code·AI 도구 소식 모니터 (2026-11-02)

> 공식 발표 · 업계(OpenAI·Google) 발표 · GitHub 신규/급상승 · 커뮤니티(HN/Reddit)를 모아 글감 가치 판정을 통과한 것만 상위 10개 싣는다. 🔥대형 발표(새 제품·새 모델 출시)는 점수와 무관하게 맨 위, 나머지는 점수순. 릴리스 노트는 이번 주기분을 묶어 줄 단위로 판정한다. 이미 다룬 소식은 반응이 급증한 경우(재부상)만 다시 싣는다.

## 오늘의 핵심 3줄

1. [기타] 🔥대형 발표 공식 [Anthropic 뉴스] Anthropic files S-1 with the SEC for proposed initial public offering — announcements · 2026-10-26 발표 — Today, Anthropic, PBC filed a registration statement on F…
2. [문서·오피스/자동화/에이전트] AgriciDaniel/claude-seo — Universal SEO skill for Claude Code. 26 sub-skills + 19 sub-agents covering technical SEO…
3. [영상/디자인/에이전트/코딩] lemomo-ai/lemo-opuscar — A toolbox of film styles made in code for Claude Code: 66 ready to use, and your own. Eac…

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
- **Hacker News** — ProxyError: HTTPSConnectionPool(host='hn.algolia.com', port=443): Max retries exceeded with url: /api/v1/search_by_date?query=claude+code&tags=story&numericFilters=created_at_i%3E1792973251&hitsPerPage=100 (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 For
- **Reddit** — ProxyError: HTTPSConnectionPool(host='www.reddit.com', port=443): Max retries exceeded with url: /r/ClaudeAI/top.json?t=week&limit=50 (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden')))

## 상위 10개 (글감급만, 점수 = 중요도 + 글감 가치)

| # | 점수 | 카테고리 | 소식 | 처음 등장 | 출처 |
|---|---|---|---|---|---|
| 1 | 70 | 기타 | [[Anthropic 뉴스] Anthropic files S-1 with the SEC for proposed initial public offering](https://www.anthropic.com/news/s1-sec) 🆕 | 2026-11-02 | anthropic_news |
| 2 | 91 | 문서·오피스/자동화/에이전트 | [AgriciDaniel/claude-seo](https://github.com/AgriciDaniel/claude-seo) | 2026-10-26 | watchlist |
| 3 | 89 | 영상/디자인/에이전트/코딩 | [lemomo-ai/lemo-opuscar](https://github.com/lemomo-ai/lemo-opuscar) 🔁재부상 | 2026-10-14 | github_search |
| 4 | 82 | 디자인/문서·오피스/에이전트 | [alchaincyf/huashu-design](https://github.com/alchaincyf/huashu-design) | 2026-10-26 | github_search, watchlist |
| 5 | 81 | 영상/에이전트/연동(MCP) | [andyhuo520/digital-human-koubo](https://github.com/andyhuo520/digital-human-koubo) 🆕 | 2026-11-02 | github_search |
| 6 | 76 | 영상/에이전트/연동(MCP) | [heygen-com/hyperframes](https://github.com/heygen-com/hyperframes) | 2026-10-26 | github_search |
| 7 | 74 | 영상/디자인/에이전트 | [patch-gg/pixelfx](https://github.com/patch-gg/pixelfx) 🆕 | 2026-11-02 | github_search |
| 8 | 73 | 영상/에이전트/코딩 | [openfilm/openfilm](https://github.com/openfilm/openfilm) | 2026-10-26 | github_search |
| 9 | 72 | 영상/에이전트 | [UnderleveledBuilder/awesome-short-drama-skills](https://github.com/UnderleveledBuilder/awesome-short-drama-skills) 🔁재부상 | 2026-10-26 | github_search |
| 10 | 72 | 디자인 | [heydamir/unslop](https://github.com/heydamir/unslop) 🆕 | 2026-11-02 | github_search |

### 1. [Anthropic 뉴스] Anthropic files S-1 with the SEC for proposed initial public offering

- 링크: https://www.anthropic.com/news/s1-sec
- 내용: announcements · 2026-10-26 발표 — Today, Anthropic, PBC filed a registration statement on Form S-1 with the U.S. Securities and Exchange Commission relating to its proposed initial public offering of its Class A common stock.
- 발표일(소스 기준): 2026-10-26
- 원문 발췌: Anthropic is an AI safety and research company that's working to build reliable, interpretable, and steerable AI systems. / Anthropic files S-1 with the SEC for proposed initial public offering \ Ant…
- 점수 근거: 중요도 40 (공식 +35, 신규 +5)
- 글감 판정: +30 (대형 발표 +30)

### 2. AgriciDaniel/claude-seo

- 링크: https://github.com/AgriciDaniel/claude-seo
- 내용: Universal SEO skill for Claude Code. 26 sub-skills + 19 sub-agents covering technical SEO, E-E-A-T, schema, GEO/AEO, agent readiness (Lighthouse Agentic Browsing, WebMCP, llms.txt), backlinks, local SEO, e-commerce, international SEO, Google APIs, and PDF/Excel reporting. 9 optional extensions for …
- 스타: 25,525
- 점수 근거: 중요도 37 (스타 +4,381/7일 +25, 일반 사용자 영향(문서·오피스/자동화/에이전트) +12)
- 글감 판정: +54 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 자동화·새 연동 +8, 스킬·플러그인·도구 출시 +8, 스타 급증 +12, 유명(스타 25,525) +6, 감시 키워드(excel) +10)

### 3. lemomo-ai/lemo-opuscar

- 링크: https://github.com/lemomo-ai/lemo-opuscar
- 내용: A toolbox of film styles made in code for Claude Code: 66 ready to use, and your own. Each style is a style prompt plus a demo film made entirely in code by Claude Opus 5.5, with no video model. By Lemomo. · 一套用代码做片的风格工具箱：66 种现成风格，也能做出你自己的
- 스타: 10,581
- 점수 근거: 중요도 45 (스타 +3,031/7일 +25, 일반 사용자 영향(영상/디자인/에이전트/코딩) +15, 재부상 +5)
- 글감 판정: +44 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 스킬·플러그인·도구 출시 +8, 스타 급증 +12, 유명(스타 10,581) +6, 감시 키워드(video) +8)

### 4. alchaincyf/huashu-design

- 링크: https://github.com/alchaincyf/huashu-design
- 내용: Huashu Design 3.0 · 在 agent 里打一句话，拿回能交付的设计：网页 / App 原型 / 可编辑 PPTX / 动画 / 信息图 · 六个候选挑三个方向 · 84 种带样张的风格库 · 越用越懂你的外观账本与设计体检 · HTML-native design skill for Claude Code, Codex, Cursor & any agent
- 스타: 28,399
- 점수 근거: 중요도 36 (스타 +2,074/7일 +24, 일반 사용자 영향(디자인/문서·오피스/에이전트) +12)
- 글감 판정: +46 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 스킬·플러그인·도구 출시 +8, 스타 급증 +12, 유명(스타 28,399) +6, 감시 키워드(pptx, design) +10)

### 5. andyhuo520/digital-human-koubo

- 링크: https://github.com/andyhuo520/digital-human-koubo
- 내용: AI digital-human talking-head videos from one photo: Renoise MCP generation + 5 editing styles + 48 creator-grade packaging components. Agent skill for Claude Code / Codex / OpenClaw / WorkBuddy …
- 스타: 1,639
- 점수 근거: 중요도 43 (스타 +1,639/7일(추정) +23, 일반 사용자 영향(영상/에이전트/연동(MCP)) +15, 신규 +5)
- 글감 판정: +38 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 스킬·플러그인·도구 출시 +8, 스타 급증 +12, 감시 키워드(video) +8)

### 6. heygen-com/hyperframes

- 링크: https://github.com/heygen-com/hyperframes
- 내용: Write HTML. Render video. Built for agents.
- 스타: 77,102
- 점수 근거: 중요도 40 (스타 +4,804/7일 +25, 일반 사용자 영향(영상/에이전트/연동(MCP)) +15)
- 글감 판정: +36 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 스타 급증 +12, 유명(스타 77,102) +6, 감시 키워드(video) +8)

### 7. patch-gg/pixelfx

- 링크: https://github.com/patch-gg/pixelfx
- 내용: 244 pixel art effects, every one a small piece of code. Plus a Claude Code skill to make your own.
- 스타: 2,550
- 점수 근거: 중요도 44 (스타 +2,550/7일(추정) +24, 일반 사용자 영향(영상/디자인/에이전트) +15, 신규 +5)
- 글감 판정: +30 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 스킬·플러그인·도구 출시 +8, 스타 급증 +12)

### 8. openfilm/openfilm

- 링크: https://github.com/openfilm/openfilm
- 내용: The open source AI video agent: turns any coding agent into a video agent, with an editor to change anything it makes.
- 스타: 4,097
- 점수 근거: 중요도 37 (스타 +1,240/7일 +22, 일반 사용자 영향(영상/에이전트/코딩) +15)
- 글감 판정: +36 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 스타 급증 +12, 유명(스타 4,097) +6, 감시 키워드(video) +8)

### 9. UnderleveledBuilder/awesome-short-drama-skills

- 링크: https://github.com/UnderleveledBuilder/awesome-short-drama-skills
- 내용: AI 短剧 · 漫剧 Skill（技能包）精选：剧本、改编、分镜、Seedance / 可灵 / MiniMax 视频提示词，千问、豆包、龙虾 OpenClaw、WorkBuddy、Claude Code、Codex 等智能体可用 | Curated agent skills for AI short drama, micro drama / microdrama, vertical drama and manju (AI comic drama): screenwriting, storyboards, Seedance / Kling / MiniMax video prompts
- 스타: 1,576
- 점수 근거: 중요도 40 (스타 +632/7일 +20, 일반 사용자 영향(영상/에이전트) +15, 재부상 +5)
- 글감 판정: +32 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 스킬·플러그인·도구 출시 +8, 스타 증가 +6, 감시 키워드(video) +8)

### 10. heydamir/unslop

- 링크: https://github.com/heydamir/unslop
- 내용: A Claude skill that turns vibecoded, AI-looking UI into a designed interface
- 스타: 4,843
- 점수 근거: 중요도 42 (스타 +4,843/7일(추정) +25, 일반 사용자 영향(디자인) +12, 신규 +5)
- 글감 판정: +30 (스킬·플러그인·도구 출시 +8, 스타 급증 +12, 유명(스타 4,843) +6, 감시 키워드(design) +4)

## 글감 미달로 뺀 항목 (참고, 중요도순 상위 5)

새 소식이지만 글감 가치가 최소 점수(10) 미만이라 후보에서 뺐다. 기준 조정은 config.json `value_rules`.

- [Anthropic 뉴스] AI for Science expands to foundations and research institutions — 글감 +0 (해당 규칙 없음)
- [Anthropic 뉴스] Expanding our partnership with GSA to bring Claude to all levels… — 글감 +0 (해당 규칙 없음)
- [Anthropic 뉴스] Open call for guest investigators in the life sciences — 글감 +0 (해당 규칙 없음)
- reason-machines/reason-network — 글감 +6 (스타 증가 +6)
- emanuele-em/kanzo — 글감 +6 (스타 증가 +6)

## 주간 키워드 감시 리스트 점검

큰 소식이 점수 체계에서 빠지는 것을 막는 안전장치. 키워드에 걸린 항목은 후보 풀에 올려 가산점을 준다. 그래도 바깥 반응이 있는데 최근 7일 리포트에 없으면 ⚠️.

| 키워드 | GitHub(7일 활동, claude 포함) | HN(7일) | Reddit(주간 상위) | 최근 리포트 반영 | 상위 레포 |
|---|---|---|---|---|---|
| remotion | 711 | 실패 | 실패 | 예 | stablyai/orca, calesthio/OpenMontage, Vincentwei1021/video-shotcraft |
| video | 1339 | 실패 | 실패 | 예 | ruvnet/RuView, calesthio/OpenMontage, Vincentwei1021/video-shotcraft |
| motion graphics | 89 | 실패 | 실패 | ⚠️ 아니오 | zhuyansen/awesome-opus-5.5-video, notivn/AIEV, LeaddeOpenLab/awesome-opus-5-5-video-prompts |
| slides | 152 | 실패 | 실패 | 예 | genspark-ai/genoffice, OpenCoworkAI/open-codesign, taylorwilsdon/google_workspace_mcp |
| pptx | 55 | 실패 | 실패 | 예 | alchaincyf/huashu-design, genspark-ai/genoffice, carnot-tech/jinba-consulting-pptx-skill |
| google workspace | 20 | 실패 | 실패 | ⚠️ 아니오 | taylorwilsdon/google_workspace_mcp, maton-ai/api-gateway-skill, Elnora-AI/elnora-google-workspace |
| design | 1156 | 실패 | 실패 | 예 | nextlevelbuilder/ui-ux-pro-max-skill, asgeirtj/system_prompts_leaks, cathrynlavery/diagram-design |
| excel | 117 | 실패 | 실패 | 예 | AgriciDaniel/claude-seo, genspark-ai/genoffice, haris-musa/excel-mcp-server |

감시 리스트 일부 조회 실패: HN 'remotion' (ProxyError); HN 'video' (ProxyError); HN 'motion graphics' (ProxyError); HN 'slides' (ProxyError); HN 'pptx' (ProxyError); HN 'google workspace' (ProxyError); HN 'design' (ProxyError); HN 'excel' (ProxyError)

## 수집 상태

| 소스 | 결과 | 건수 | 비고 |
|---|---|---|---|
| Claude Code 릴리스 | ❌ 실패 | 0 | HTTPError: 403 Client Error: Forbidden for url: https://api.github.com/repos/anthropics/claude-code/releases?per_page=15 |
| Claude Code CHANGELOG | ❌ 실패 | 0 | HTTPError: 403 Client Error: Forbidden for url: https://api.github.com/repos/anthropics/claude-code/contents/CHANGELOG.md |
| Anthropic 공식 스킬 | ❌ 실패 | 0 | HTTPError: 403 Client Error: Forbidden for url: https://api.github.com/repos/anthropics/skills/contents/skills |
| Claude Code 내장 플러그인 | ❌ 실패 | 0 | HTTPError: 403 Client Error: Forbidden for url: https://api.github.com/repos/anthropics/claude-code/contents/plugins |
| 공식 플러그인 마켓플레이스 (존재 확인 못 함) | ❌ 실패 | 0 | HTTPError: 403 Client Error: Forbidden for url: https://api.github.com/repos/anthropics/claude-plugins-official/contents/plugins |
| Claude 제품 목록(새 제품) | 성공 | 0 | 기준선 저장 (8개) |
| Claude Code 공식 문서 목차 | 성공 | 0 | 전체 239개 |
| Claude 플랫폼 문서 목차 | ❌ 실패 | 0 | RuntimeError: 링크 0개 — 페이지 구조 변경 또는 차단 의심 |
| Anthropic 뉴스 | 성공 | 6 | 전체 107개 중 최근 14일·대상 분류 6개 |
| OpenAI 뉴스 | ❌ 실패 | 0 | ProxyError: HTTPSConnectionPool(host='openai.com', port=443): Max retries exceeded with url: /news/rss.xml (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden'))) |
| Google AI 블로그 | ❌ 실패 | 0 | ProxyError: HTTPSConnectionPool(host='blog.google', port=443): Max retries exceeded with url: /technology/ai/rss/ (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden'))) |
| Google DeepMind 블로그 | ❌ 실패 | 0 | ProxyError: HTTPSConnectionPool(host='deepmind.google', port=443): Max retries exceeded with url: /blog/rss.xml (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden'))) |
| GitHub 검색(신규·토픽) | 성공 | 450 | 쿼리 15개 |
| Hacker News | ❌ 실패 | 0 | ProxyError: HTTPSConnectionPool(host='hn.algolia.com', port=443): Max retries exceeded with url: /api/v1/search_by_date?query=claude+code&tags=story&numericFilters=created_at_i%3E1792973251&hitsPerPage=100 (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 For |
| Reddit | ❌ 실패 | 0 | ProxyError: HTTPSConnectionPool(host='www.reddit.com', port=443): Max retries exceeded with url: /r/ClaudeAI/top.json?t=week&limit=50 (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden'))) |
| 대형 발표 원문·국내 기사 | 성공 | 1 | 대형 발표 1개 |

*추적 중이지만 이번에 싣지 않은 항목 335개 (이미 다룸·변화 없음·점수 미달). 생성: 2026-11-02 | projects/claude-code-monitor/monitor.py*
