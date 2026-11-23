# Claude Code·AI 도구 소식 모니터 (2026-11-23)

> 공식 발표 · 업계(OpenAI·Google) 발표 · GitHub 신규/급상승 · 커뮤니티(HN/Reddit)를 모아 글감 가치 판정을 통과한 것만 상위 10개 싣는다. 🔥대형 발표(새 제품·새 모델 출시)는 점수와 무관하게 맨 위, 나머지는 점수순. 릴리스 노트는 이번 주기분을 묶어 줄 단위로 판정한다. 이미 다룬 소식은 반응이 급증한 경우(재부상)만 다시 싣는다.

## 오늘의 핵심 3줄

1. [기타] 🔥대형 발표 공식 [Anthropic 뉴스] Anthropic prices initial public offering — Announcements · 2026-11-18 발표
2. [기타] 🔥대형 발표 공식 [Anthropic 뉴스] Anthropic announces closing of initial public offering, including full exercise of underwriters’ option to purchase additional shares, and closing of concurrent private placement — Announcements · 2026-11-20 발표
3. [영상/에이전트] JuneYaooo/rea-video — Reverse-engineer any video, shot by shot: filmed, AI-generated or coded, and how to remak…

## ⚠️ 수집 실패

아래 소스는 이번에 수집하지 못했다. **이 소스에서 나온 소식은 이번 리포트에 빠져 있을 수 있다.**

- **Claude Code 릴리스** — HTTPError: 403 Client Error: Forbidden for url: https://api.github.com/repos/anthropics/claude-code/releases?per_page=15
- **Claude Code CHANGELOG** — HTTPError: 403 Client Error: Forbidden for url: https://api.github.com/repos/anthropics/claude-code/contents/CHANGELOG.md
- **Anthropic 공식 스킬** — HTTPError: 403 Client Error: Forbidden for url: https://api.github.com/repos/anthropics/skills/contents/skills
- **Claude Code 내장 플러그인** — HTTPError: 403 Client Error: Forbidden for url: https://api.github.com/repos/anthropics/claude-code/contents/plugins
- **공식 플러그인 마켓플레이스 (존재 확인 못 함)** — HTTPError: 403 Client Error: Forbidden for url: https://api.github.com/repos/anthropics/claude-plugins-official/contents/plugins
- **Claude 플랫폼 문서 목차** — RuntimeError: 링크 0개 — 페이지 구조 변경 또는 차단 의심
- **OpenAI 뉴스** — ProxyError: HTTPSConnectionPool(host='openai.com', port=443): Max retries exceeded with url: /news/rss.xml (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden (agent proxy: no rule or network setting allows this host)')))
- **Google AI 블로그** — ProxyError: HTTPSConnectionPool(host='blog.google', port=443): Max retries exceeded with url: /technology/ai/rss/ (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden (agent proxy: no rule or network setting allows this host)')))
- **Google DeepMind 블로그** — ProxyError: HTTPSConnectionPool(host='deepmind.google', port=443): Max retries exceeded with url: /blog/rss.xml (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden (agent proxy: no rule or network setting allows this host)')))
- **Hacker News** — ProxyError: HTTPSConnectionPool(host='hn.algolia.com', port=443): Max retries exceeded with url: /api/v1/search_by_date?query=claude+code&tags=story&numericFilters=created_at_i%3E1794787620&hitsPerPage=100 (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 For
- **Reddit** — ProxyError: HTTPSConnectionPool(host='www.reddit.com', port=443): Max retries exceeded with url: /r/ClaudeAI/top.json?t=week&limit=50 (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden (agent proxy: no rule or network setting allows this host)')))

## 상위 10개 (글감급만, 점수 = 중요도 + 글감 가치)

| # | 점수 | 카테고리 | 소식 | 처음 등장 | 출처 |
|---|---|---|---|---|---|
| 1 | 85 | 기타 | [[Anthropic 뉴스] Anthropic prices initial public offering](https://www.anthropic.com/news/anthropic-prices-initial-public-offering) 🆕 | 2026-11-23 | anthropic_news |
| 2 | 60 | 기타 | [[Anthropic 뉴스] Anthropic announces closing of initial public offering, including full exercise of underwriters’ option to purchase additional shares, and closing of concurrent private placement](https://www.anthropic.com/news/ipo-close) 🆕 | 2026-11-23 | anthropic_news |
| 3 | 91 | 영상/에이전트 | [JuneYaooo/rea-video](https://github.com/JuneYaooo/rea-video) 🔁재부상 | 2026-11-09 | github_search |
| 4 | 83 | 영상/에이전트 | [latent-spaces/brag](https://github.com/latent-spaces/brag) 🔁재부상 | 2026-10-14 | github_search |
| 5 | 81 | 영상/디자인/에이전트 | [shinyobjectz/raea](https://github.com/shinyobjectz/raea) 🆕 | 2026-11-23 | github_search |
| 6 | 78 | 영상/디자인/에이전트 | [emilkowalski/skills](https://github.com/emilkowalski/skills) | 2026-11-16 | github_search |
| 7 | 78 | 영상/디자인/에이전트 | [patch-gg/pixelfx](https://github.com/patch-gg/pixelfx) 🔁재부상 | 2026-11-02 | github_search |
| 8 | 74 | 영상/자동화/에이전트 | [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill) | 2026-10-14 | github_search |
| 9 | 68 | 영상/자동화/에이전트/연동(MCP) | [EL4CTEO/blender-skills](https://github.com/EL4CTEO/blender-skills) | 2026-10-19 | github_search |
| 10 | 68 | 자동화/에이전트/연동(MCP) | [bookwjitchieni1986/blender-ai-mcp-addon](https://github.com/bookwjitchieni1986/blender-ai-mcp-addon) 🆕 | 2026-11-23 | github_search |

### 1. [Anthropic 뉴스] Anthropic prices initial public offering

- 링크: https://www.anthropic.com/news/anthropic-prices-initial-public-offering
- 내용: Announcements · 2026-11-18 발표
- 발표일(소스 기준): 2026-11-18
- 원문 발췌: Today Anthropic, PBC priced its initial public offering of its Class A common stock. / Anthropic prices initial public offering \ Anthropic Skip to main content Related articles Anthropic announces c…
- 점수 근거: 중요도 40 (공식 +35, 신규 +5)
- 글감 판정: +45 (요금·모델·정책(일반 사용자 영향 큼) +15, 대형 발표 +30)

### 2. [Anthropic 뉴스] Anthropic announces closing of initial public offering, including full exercise of underwriters’ option to purchase additional shares, and closing of concurrent private placement

- 링크: https://www.anthropic.com/news/ipo-close
- 내용: Announcements · 2026-11-20 발표
- 발표일(소스 기준): 2026-11-20
- 원문 발췌: Today Anthropic, PBC announced the closing of its initial public offering of an aggregate of 1,127,000,000 shares of its Class A common stock at a public offering price of $83.00 per share, including…
- 점수 근거: 중요도 40 (공식 +35, 신규 +5)
- 글감 판정: +20 (설정·환경변수·옵션 추가 -10, 대형 발표 +30)

### 3. JuneYaooo/rea-video

- 링크: https://github.com/JuneYaooo/rea-video
- 내용: Reverse-engineer any video, shot by shot: filmed, AI-generated or coded, and how to remake it. Breakdowns in the open VIDEO.md format. 逆向一切视频，逐个镜头看是拍的、AI 生成的还是代码做的，再告诉你怎么复刻；拆解结果按 VIDEO.md 格式输出。
- 스타: 12,237
- 점수 근거: 중요도 45 (스타 +2,913/7일 +25, 일반 사용자 영향(영상/에이전트) +15, 재부상 +5)
- 글감 판정: +46 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 스킬·플러그인·도구 출시 +8, 스타 급증 +12, 유명(스타 12,237) +6, 감시 키워드(remotion, video) +10)

### 4. latent-spaces/brag

- 링크: https://github.com/latent-spaces/brag
- 내용: You built it. Now brag. Turn the project you just created into a short, shareable launch video with one command.
- 스타: 22,250
- 점수 근거: 중요도 40 (스타 +624/7일 +20, 일반 사용자 영향(영상/에이전트) +15, 재부상 +5)
- 글감 판정: +43 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 새 기능 표현(할 수 있게 됨) +5, 스킬·플러그인·도구 출시 +8, 스타 증가 +6, 유명(스타 22,250) +6, 감시 키워드(video) +8)

### 5. shinyobjectz/raea

- 링크: https://github.com/shinyobjectz/raea
- 내용: Render Anything Engine: tell your AI what to make. Videos, motion graphics, 3D and games as React and TypeScript, rendered on your own GPU. Rust + Bevy, macOS, Linux and Windows.
- 스타: 4,258
- 점수 근거: 중요도 41 (스타 +845/7일(추정) +21, 일반 사용자 영향(영상/디자인/에이전트) +15, 신규 +5)
- 글감 판정: +40 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 스킬·플러그인·도구 출시 +8, 스타 증가 +6, 유명(스타 4,258) +6, 감시 키워드(video, motion graphics, design) +10)

### 6. emilkowalski/skills

- 링크: https://github.com/emilkowalski/skills
- 내용: Skills for Designers and Engineers.
- 스타: 58,866
- 점수 근거: 중요도 38 (스타 +1,589/7일 +23, 일반 사용자 영향(영상/디자인/에이전트) +15)
- 글감 판정: +40 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 스킬·플러그인·도구 출시 +8, 스타 급증 +12, 유명(스타 58,866) +6, 감시 키워드(design) +4)

### 7. patch-gg/pixelfx

- 링크: https://github.com/patch-gg/pixelfx
- 내용: 244 pixel art effects, every one a small piece of code. Plus a Claude Code skill to make your own.
- 스타: 8,752
- 점수 근거: 중요도 42 (스타 +1,121/7일 +22, 일반 사용자 영향(영상/디자인/에이전트) +15, 재부상 +5)
- 글감 판정: +36 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 스킬·플러그인·도구 출시 +8, 스타 급증 +12, 유명(스타 8,752) +6)

### 8. mvanhorn/last30days-skill

- 링크: https://github.com/mvanhorn/last30days-skill
- 내용: AI agent skill that researches any topic across Reddit, X, YouTube, HN, Polymarket, and the web - then synthesizes a grounded summary
- 스타: 72,697
- 점수 근거: 중요도 40 (스타 +4,893/7일 +25, 일반 사용자 영향(영상/자동화/에이전트) +15)
- 글감 판정: +34 (자동화·새 연동 +8, 스킬·플러그인·도구 출시 +8, 스타 급증 +12, 유명(스타 72,697) +6)

### 9. EL4CTEO/blender-skills

- 링크: https://github.com/EL4CTEO/blender-skills
- 내용: Professional Blender 5.3 workflows as Agent Skills for Claude Code, Codex, Gemini CLI, Copilot and Cursor: modeling, UVs, PBR, baking, rigging, animation, export and QA.
- 스타: 2,703
- 점수 근거: 중요도 38 (스타 +1,459/7일 +23, 일반 사용자 영향(영상/자동화/에이전트/연동(MCP)) +15)
- 글감 판정: +30 (업무에 새로 쓸 수 있는 일(영상·문서·슬라이드·엑셀·디자인) +10, 스킬·플러그인·도구 출시 +8, 스타 급증 +12)

### 10. bookwjitchieni1986/blender-ai-mcp-addon

- 링크: https://github.com/bookwjitchieni1986/blender-ai-mcp-addon
- 내용: AI assistant and MCP server for Blender: visual chat, scene tools, multi-agent workflows. Works with ChatGPT/GPT, Claude, Gemini, Ollama, OpenCode. Blender AI addon, copilot for 3D, bpy Python scripting, MCP integration.
- 스타: 2,746
- 점수 근거: 중요도 40 (스타 +2,746/7일(추정) +25, 일반 사용자 영향(자동화/에이전트/연동(MCP)) +10, 신규 +5)
- 글감 판정: +28 (자동화·새 연동 +8, 스킬·플러그인·도구 출시 +8, 스타 급증 +12)

## 글감 미달로 뺀 항목 (참고, 중요도순 상위 5)

새 소식이지만 글감 가치가 최소 점수(10) 미만이라 후보에서 뺐다. 기준 조정은 config.json `value_rules`.

- hridaya423/phonedriver — 글감 +8 (자동화·새 연동 +8)
- DuskBotAI/duskbot — 글감 +0 (해당 규칙 없음)
- lemonadesaltbagel/sill — 글감 +0 (해당 규칙 없음)
- dansugc/reverse-engineer-marketing — 글감 +6 (스타 증가 +6)
- morganlinton/BeautifulRust — 글감 +8 (스킬·플러그인·도구 출시 +8)

## 주간 키워드 감시 리스트 점검

큰 소식이 점수 체계에서 빠지는 것을 막는 안전장치. 키워드에 걸린 항목은 후보 풀에 올려 가산점을 준다. 그래도 바깥 반응이 있는데 최근 7일 리포트에 없으면 ⚠️.

| 키워드 | GitHub(7일 활동, claude 포함) | HN(7일) | Reddit(주간 상위) | 최근 리포트 반영 | 상위 레포 |
|---|---|---|---|---|---|
| remotion | 775 | 실패 | 실패 | 예 | stablyai/orca, Vincentwei1021/video-shotcraft, NanmiCoder/cc-haha |
| video | 1560 | 실패 | 실패 | 예 | ruvnet/RuView, Vincentwei1021/video-shotcraft, lemomo-ai/lemo-opuscar |
| motion graphics | 108 | 실패 | 실패 | 예 | nexu-io/openmotion, Vincentwei1021/anything2explainer, ChatCut-Inc/agent-plugin |
| slides | 200 | 실패 | 실패 | ⚠️ 아니오 | alchaincyf/huashu-design, genspark-ai/genoffice, OpenCoworkAI/open-codesign |
| pptx | 72 | 실패 | 실패 | ⚠️ 아니오 | alchaincyf/huashu-design, genspark-ai/genoffice, carnot-tech/jinba-consulting-pptx-skill |
| google workspace | 22 | 실패 | 실패 | ⚠️ 아니오 | sandbox-quantum/switch, taylorwilsdon/google_workspace_mcp, fivetaku/nopal |
| design | 1280 | 실패 | 실패 | 예 | nextlevelbuilder/ui-ux-pro-max-skill, cathrynlavery/diagram-design, alchaincyf/huashu-design |
| excel | 119 | 실패 | 실패 | ⚠️ 아니오 | genspark-ai/genoffice, haris-musa/excel-mcp-server, sv-grid/sv-grid |

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
| Claude Code 공식 문서 목차 | 성공 | 0 | 전체 216개 |
| Claude 플랫폼 문서 목차 | ❌ 실패 | 0 | RuntimeError: 링크 0개 — 페이지 구조 변경 또는 차단 의심 |
| Anthropic 뉴스 | 성공 | 4 | 전체 110개 중 최근 14일·대상 분류 4개 |
| OpenAI 뉴스 | ❌ 실패 | 0 | ProxyError: HTTPSConnectionPool(host='openai.com', port=443): Max retries exceeded with url: /news/rss.xml (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden (agent proxy: no rule or network setting allows this host)'))) |
| Google AI 블로그 | ❌ 실패 | 0 | ProxyError: HTTPSConnectionPool(host='blog.google', port=443): Max retries exceeded with url: /technology/ai/rss/ (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden (agent proxy: no rule or network setting allows this host)'))) |
| Google DeepMind 블로그 | ❌ 실패 | 0 | ProxyError: HTTPSConnectionPool(host='deepmind.google', port=443): Max retries exceeded with url: /blog/rss.xml (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden (agent proxy: no rule or network setting allows this host)'))) |
| GitHub 검색(신규·토픽) | 성공 | 450 | 쿼리 15개 |
| Hacker News | ❌ 실패 | 0 | ProxyError: HTTPSConnectionPool(host='hn.algolia.com', port=443): Max retries exceeded with url: /api/v1/search_by_date?query=claude+code&tags=story&numericFilters=created_at_i%3E1794787620&hitsPerPage=100 (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 For |
| Reddit | ❌ 실패 | 0 | ProxyError: HTTPSConnectionPool(host='www.reddit.com', port=443): Max retries exceeded with url: /r/ClaudeAI/top.json?t=week&limit=50 (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden (agent proxy: no rule or network setting allows this host)'))) |
| 대형 발표 원문·국내 기사 | 성공 | 2 | 대형 발표 2개 |

*추적 중이지만 이번에 싣지 않은 항목 329개 (이미 다룸·변화 없음·점수 미달). 생성: 2026-11-23 | projects/claude-code-monitor/monitor.py*
