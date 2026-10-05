# Claude Code 생태계, 지금 뭐가 뜨고 있나

> GitHub 상위 90여 개 Claude Code 리포를 훑어보니, 흐름이 4가지로 정리됩니다: **토큰 절약 / 메모리 / 스킬 / 멀티 에이전트**.

## 🔍 들어가며

Claude Code를 쓰다 보면 비슷한 벽에 부딪힙니다. 세션이 끊기면 맥락이 날아가고, 토큰은 금방 소진되고, 결과물 품질은 들쑥날쑥하죠.

재밌는 건 커뮤니티가 이 문제들을 각자 해결해서 오픈소스로 풀고 있다는 점입니다. 2026년 10월 기준 트렌드 스캔 결과를 정리해봤어요. 제품 소개가 아니라, **내 설정에 당장 붙일 수 있는 것** 위주로 골랐습니다.

## 💸 토큰 비용 줄이기

가장 체감이 빠른 영역입니다. 세 가지 접근이 보여요.

| 리포 | 접근 방식 | 효과 |
|------|----------|------|
| [rtk-ai/rtk](https://github.com/rtk-ai/rtk) | CLI proxy로 명령어 출력 압축 | 60~90% 절감 |
| [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) | 프롬프트를 최소 토큰으로 변환 | 약 65% 절감 |
| [drona23/claude-token-efficient](https://github.com/drona23/claude-token-efficient) | CLAUDE.md 한 장으로 출력 간결화 | 설치 불필요 |

rtk는 Rust 단일 바이너리라 의존성이 없습니다. `git diff`, `ls -R` 같은 명령 출력이 컨텍스트를 잡아먹는 걸 proxy 레벨에서 막아줘요.

가장 가벼운 건 세 번째입니다. CLAUDE.md에 규칙 몇 줄 추가하는 것만으로 응답 verbosity(장황함)가 줄어듭니다.

```markdown
<!-- CLAUDE.md 에 추가 -->
## Response rules
- 코드 변경 시 변경된 부분만 출력, 전체 파일 재출력 금지
- 설명은 3문장 이내. 요청하지 않은 대안 제시 금지
- 파일 읽기 전 Glob/Grep으로 범위를 먼저 좁힐 것
```

## 🧠 세션 간 메모리 유지

Claude Code의 가장 큰 불편은 세션이 끝나면 맥락이 초기화된다는 점이죠.

[thedotmack/claude-mem](https://github.com/thedotmack/claude-mem)은 세션 중 발생한 작업을 캡처해서 AI로 압축한 뒤, 다음 세션에 관련 컨텍스트만 주입합니다. Codex, Gemini, Copilot에서도 동작해요.

조금 다른 방향으로 [BayramAnnakov/claude-reflect](https://github.com/BayramAnnakov/claude-reflect)가 있습니다. 내가 "그거 말고 이렇게 해줘"라고 교정한 내용을 수집해서 CLAUDE.md와 AGENTS.md에 반영하는 방식이에요. 같은 지적을 반복하지 않게 됩니다.

```bash
npm install -g claude-mem
claude-mem install   # hook 자동 등록
```

## 🎨 Skill: 이제 사실상 표준

SKILL.md 포맷이 Claude Code를 넘어 Cursor, Codex, Gemini CLI까지 퍼졌습니다. 리스트 중 절반 이상이 스킬 모음이에요.

실무에서 바로 쓸 만한 것들:

- [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) — 프로덕션 엔지니어링 스킬. 구글 Addy Osmani가 관리
- [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) — Karpathy가 지적한 LLM 코딩 함정을 CLAUDE.md 한 장으로 방어
- [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) — UI/UX 결과물 품질 개선
- [ciembor/agent-rules-books](https://github.com/ciembor/agent-rules-books) — Clean Code, DDD, Clean Architecture 기반 규칙셋

재밌는 건 [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail)입니다. "가장 게으른 시니어 개발자처럼 생각하게" 만드는 스킬인데, AI가 불필요한 코드를 양산하는 걸 막는 게 목적이에요. 안 쓴 코드가 최고의 코드라는 관점이죠.

설치는 대부분 동일합니다.

```bash
# 프로젝트 단위 설치
mkdir -p .claude/skills
git clone https://github.com/addyosmani/agent-skills .claude/skills/eng

# 또는 공식 플러그인 디렉토리에서
/plugin marketplace add anthropics/claude-plugins-official
```

## 🗺️ 코드베이스 이해시키기

대형 레포에서 AI가 헤매는 문제를 그래프로 푸는 시도가 늘었습니다.

[Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify)는 코드·SQL 스키마·설정·PDF를 AST 파싱해서 질의 가능한 knowledge graph(지식 그래프)로 만듭니다. 벡터 스토어 없이 결정론적으로 동작하는 게 특징이에요. 임베딩 기반 검색의 "그럴듯하지만 틀린" 결과를 피할 수 있습니다.

[idosal/git-mcp](https://github.com/idosal/git-mcp)는 더 간단합니다. 외부 라이브러리 API를 환각 없이 참조하고 싶을 때 쓰는 remote MCP 서버예요. 설정 한 줄이면 끝납니다.

## ✅ 바로 써먹기

**1단계 — CLAUDE.md 정리 (5분)**
위 Response rules 블록을 프로젝트 CLAUDE.md에 추가하세요. 체감 효과가 가장 빠릅니다.

**2단계 — 메모리 붙이기 (10분)**
`npm install -g claude-mem && claude-mem install`. 하루 써보고 컨텍스트 주입이 거슬리면 바로 제거하면 됩니다.

**3단계 — 스킬 1개만 (5분)**
전부 설치하지 마세요. 본인 약점 하나만 고르세요. 프론트 품질이 문제면 ui-ux-pro-max, 과잉 코드가 문제면 ponytail, 설계가 문제면 agent-rules-books.

## 📌 마치며

도구를 늘리는 것보다 CLAUDE.md 한 장을 다듬는 게 효율이 높을 때가 많습니다. 하나씩 넣고 효과를 확인하세요.

다음 편에서는 **claude-mem과 claude-reflect를 2주간 실제 프로젝트에 적용한 기록**을 토큰 사용량 비교와 함께 정리해보겠습니다.