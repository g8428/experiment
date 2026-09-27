# Claude Code 오픈소스 생태계 조사 (2026-09-27)

---

## 1. GitHub 무료 토큰/크레딧

### 결론

**GitHub 경로에서 Claude를 무료로 쓰는 방법은 현재 없다.** GitHub Models API의 무료 티어에는 Claude가 포함되지 않는다. Anthropic 경로의 무료 옵션이 실질적이다.

### GitHub Copilot Free 티어

- **내용**: 코드 자동완성 2,000회/월 + 채팅 50회/월
- **Claude 포함 여부**: 아니요. 제공 모델은 GPT-4.1, Claude Sonnet 선택 가능하지만 AI 크레딧 소진 시 유료 전환
- **출처**: [GitHub Copilot Pricing 2026 — No Code MBA](https://www.nocode.mba/articles/github-copilot-pricing)

### GitHub AI Credits (2026년 6월 이후 신규 과금 체계)

2026년 6월 1일 GitHub이 사용량 기반 과금으로 전환. 1 AI 크레딧 = $0.01.

| 플랜 | 월 요금 | 크레딧 | 환산 가치 |
|------|--------|--------|---------|
| Free | 무료 | 없음 | — |
| Pro | $10 | 1,500 크레딧 | $15 |
| Pro+ | $39 | 7,000 크레딧 | $70 |
| Max (신규) | $100 | 20,000 크레딧 | $200 |

- **출처**: [GitHub Copilot AI Credits vs Claude Code — DEV Community](https://dev.to/jamilxt/github-copilot-ai-credits-vs-claude-code-the-real-math-on-what-your-ai-coding-costs-now-852)

### GitHub Models API 무료 티어

- **포함 모델**: GPT-4.1, o3-mini, o4-mini, Llama 4, Mistral, DeepSeek-R1, Phi-4 등 13개
- **Claude 포함 여부**: **아니요.** Anthropic 모델 없음
- **무료 한도**: 10 RPM, 50 req/day (고성능 모델 기준), 입력 8K/출력 4K 토큰
- **출처**: [Free GitHub Models API Key — free-model.com](https://www.free-model.com/providers/github-models/)

### Anthropic 직접 경로 — 실용적인 무료 옵션

#### 신규 가입 API 크레딧
- platform.claude.com 계정 생성 시 약 $5 상당의 무료 API 크레딧 제공
- 신용카드 불필요
- **출처**: [Is Claude Code Free? — atomicbot.ai](https://atomicbot.ai/blog/is-claude-code-free)

#### Claude for Open Source 프로그램 (2026년 신청 마감)
- **내용**: Claude Max 20x ($200/월) 6개월 무료 = $1,200 가치
- **자격**: GitHub 스타 5,000개 이상 또는 npm 월 다운로드 100만 이상의 프로젝트 메인테이너
- **대안 트랙**: 위 기준 미충족 시 "생태계 영향도" 서면 설명으로 신청 가능
- **규모**: 최대 10,000명, 2026년 6월 30일 신청 마감 (현재 종료)
- **출처**: [Free Claude Max for open source maintainers — simonwillison.net](https://simonwillison.net/2026/Feb/27/claude-max-oss-six-months/)

#### 무료-프록시 경로 (ToS 유의)
- **GitHub**: [alishahryar1/free-claude-code](https://github.com/alishahryar1/free-claude-code)
- 56개 이상 프로바이더(NVIDIA NIM, Groq, OpenRouter 등)의 무료 티어를 집계해 월 13억 토큰 이상을 라우팅
- Claude 직접 접근은 아니며, 각 프로바이더 무료 한도에 의존
- ToS 리스크 있음, 참고용

---

## 2. Claude Code 필수 오픈소스 스킬/MCP 서버

### 결론

**최우선 설치 3종**: GitHub MCP + Context7 + Sequential Thinking. 여기에 파이썬 개발자라면 Filesystem과 Playwright 추가.

### 공식 레퍼런스 구현 (modelcontextprotocol/servers)

- **GitHub**: [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers)
- **스타**: 90.3k
- **포함 서버**: `filesystem`, `git`, `memory`, `fetch`, `sequential-thinking`, `time`, `everything`(테스트용)
- **설치**: `npx @modelcontextprotocol/server-filesystem` 등 각 서버별 npm 패키지

### 필수 MCP 서버 목록

| 서버 | GitHub/설치 | 스타 | 한 줄 설명 |
|------|------------|------|----------|
| **GitHub MCP** (공식) | [github/github-mcp-server](https://github.com/github/github-mcp-server) / 호스티드 엔드포인트: `https://api.githubcopilot.com/mcp` | 공식 | 레포, 이슈, PR, 코드 검색, Actions를 Claude에서 직접 조작 |
| **Context7** | [upstash/context7](https://github.com/upstash/context7) / `npx @upstash/context7-mcp` | 54k+ | 라이브러리 최신 버전 문서를 컨텍스트에 자동 주입 — 환각 방지 핵심 |
| **Filesystem** | modelcontextprotocol/servers 내 포함 / `npx @modelcontextprotocol/server-filesystem` | (위와 동일) | 로컬 파일 읽기/쓰기 — Claude Code 기본 중의 기본 |
| **Sequential Thinking** | modelcontextprotocol/servers 내 포함 | (위와 동일) | 복잡한 문제를 단계별로 분해해 추론 품질 향상 |
| **Playwright MCP** (MS 공식) | `@playwright/mcp@latest` | 공식 | 실제 브라우저 조작, QA 자동화, 스크래핑 |
| **Memory** | modelcontextprotocol/servers 내 포함 | (위와 동일) | 세션 간 지식 그래프 영속 — 프로젝트 컨텍스트 유지 |
| **Exa MCP** | `exa-mcp-server` | — | 에이전트 최적화 시맨틱 웹 검색 |
| **PostgreSQL** | `@modelcontextprotocol/server-postgres` | — | 자연어 → SQL, DB 스키마 조회 |

- **출처**: [Top 10 Essential MCP Servers for Claude Code — apidog.com](https://apidog.com/blog/top-10-mcp-servers-for-claude-code/), [Best MCP Servers for Claude Code — nimbalyst.com](https://nimbalyst.com/blog/best-claude-code-mcp-servers/)

### 원격(hosted) MCP 엔드포인트 (2026 트렌드)

2026년에는 GitHub, Vercel, Linear, Notion, Supabase, Stripe, Figma, Hugging Face 등이 OAuth 인증 기반 원격 MCP 엔드포인트를 공식 운영. 별도 서버 실행 없이 URL만 설정하면 됨.

---

## 3. 인기 있는 Claude Code 관련 GitHub 리포 (스타 기준)

### 결론

**obra/superpowers**가 스타 기준 최대 성장 프로젝트(~29만). **anthropics/claude-code** 공식 오픈소스화(13만+)가 2026년 최대 이벤트. 큐레이션 리스트는 **hesreallyhim/awesome-claude-code**가 표준.

### 핵심 리포 목록

| 리포 | 스타 | 한 줄 설명 |
|------|------|----------|
| [anthropics/claude-code](https://github.com/anthropics/claude-code) | 131k+ | Claude Code 공식 오픈소스 에이전트 레이어 (TypeScript). 2026년 3월 소스맵 유출 → 공식 오픈소스화 |
| [obra/superpowers](https://github.com/obra/superpowers) | ~291k | Claude Code 플러그인: TDD, 서브에이전트, 브레인스토밍, 코드리뷰 스킬 번들. 2025년 10월 출시 후 최단기 성장 |
| [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) | 54.7k | Claude Code 리소스 최고 큐레이션 목록. 스킬, MCP, 상태바, 툴링 등 분류 |
| [punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers) | 93.9k | MCP 서버 종합 목록 (1,077개+) |
| [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) | 90.3k | Anthropic 공식 MCP 레퍼런스 구현 모노레포 |
| affaan-m/everything-claude-code | 141k | Claude Code 리소스 파이어호스 집계 |
| [upstash/context7](https://github.com/upstash/context7) | 54k | 라이브러리 버전 고정 문서 인젝터 MCP |
| [alishahryar1/free-claude-code](https://github.com/alishahryar1/free-claude-code) | — | 56개 프로바이더 무료 티어 집계 프록시 |

### 2026년 주요 생태계 이벤트

1. **2026-03-31 소스 유출**: Anthropic이 npm 패키지에 .npmignore 누락으로 512,000줄 TypeScript 소스맵 공개 → 공식 오픈소스화로 이어짐
2. **CLAUDE.md 폭발**: Andrej Karpathy의 AI 에이전트 불만 → 커뮤니티가 CLAUDE.md 베스트프랙티스로 대응 → 210k+ 스타 리포 등장
3. **Skills/Hooks/Subagents 구분 확립**: Claude Code가 3개 계층(Skills, Hooks, Subagents)을 공식화, 생태계 표준화

- **출처**: [Claude Code Source Leak — layer5.io](https://layer5.io/blog/engineering/the-claude-code-source-leak-512000-lines-a-missing-npmignore-and-the-fastest-growing-repo-in-github-history/)

---

## 시사점 — 재영이 바로 써먹을 수 있는 것들

재영 프로필: 한국인, 개인 개발자, 파이썬 메인, Claude Code 현재 사용 중 (`projects/deepcoin_bot` 등 운용).

### 즉시 적용 (오늘 바로)

1. **Context7 MCP 설치** — 파이썬 라이브러리(ccxt, pandas, SQLAlchemy 등) 작업 시 환각 방지. `npx @upstash/context7-mcp` 한 줄로 설치, API 키 없이도 무료 사용 가능.
   ```json
   // .mcp.json에 추가
   { "mcpServers": { "context7": { "command": "npx", "args": ["-y", "@upstash/context7-mcp"] } } }
   ```

2. **GitHub MCP 설치** — `projects/deepcoin_bot` 같은 프로젝트에서 이슈 트래킹, PR 리뷰를 Claude에서 직접. 호스티드 엔드포인트(`https://api.githubcopilot.com/mcp`)는 GitHub Copilot 구독 필요; 무료라면 npm 패키지 버전 사용.

3. **Sequential Thinking MCP** — 거래 전략 분석, 멀티스텝 백테스트 설계 등에서 추론 품질 향상. 공식 레퍼런스 구현에 포함.

### 단기 검토 (이번 주)

4. **obra/superpowers 플러그인** — `/plugin install superpowers@claude-plugins-official` 한 줄. TDD 강제 + 서브에이전트 기반 개발 + 코드리뷰 스킬 번들. 파이썬 프로젝트에서 테스트 작성 습관화에 유용. 29만 스타짜리 생태계 검증 완료.

5. **hesreallyhim/awesome-claude-code** 북마크 — 54.7k 스타, 실제 동작하는 도구만 엄선하는 큐레이션 기준으로 유명. 새 도구 탐색 시 첫 번째 참조점.

6. **Memory MCP** — 딥코인봇처럼 장기 운용 프로젝트에서 세션 간 컨텍스트 유지. HANDOVER.md와 병행하면 도메인 기억 손실 최소화.

### 해당 없는 것

- **GitHub Models API**: Claude 없음. 우회할 이유 없음.
- **Claude for Open Source 프로그램**: 2026년 6월 30일 마감. 신청 불가.
- **Anthropic 신규 API 크레딧**: 이미 사용 중이면 기사용.
- **alishahryar1/free-claude-code 프록시**: 현재 실거래 봇(deepcoin_bot)에 연결하기에는 안정성 리스크. 개인 테스트용으로만 참고.

---

*조사일: 2026-09-27 | 작성: researcher 서브에이전트*
