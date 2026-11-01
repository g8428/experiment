# 릴스 분석: "AI 에이전트 그만 만드세요 — 잘하는 사람들의 위임법"

- 원본: https://www.instagram.com/reel/DerPUzhzDH5/ (1분 22초, 계정 표기 없음)
- 분석: vidIQ 장면 분석 + 웹 크로스체크, 2026-11-01
- 한 줄 결론: **방법론은 쓸 만하다. 제목은 과장이고, 영상 프롬프트대로 만들면 SKILL.md 필수 항목이 빠진다.**

## 영상이 말하는 방법 (AI 위임 루프)

1. **인터뷰** — Claude/ChatGPT가 나를 인터뷰해서(한 번에 질문 하나, 최소 8개) 업무를 매뉴얼로 만든다. 다뤄야 할 것: 계기·빈도, 입력물과 위치, 실제 순서, 결정과 그 규칙, 완료 확인 항목, 예전 실패 사례, 톤·기준. 결과는 `[job-name]/SKILL.md`.
2. **툴박스** — 통과한 산출물(스크립트·템플릿·예시·참조 데이터·톤 규칙)을 `[job-name]/files/`에 저장하고 `files/INDEX.md`에 한 줄(파일명·용도·날짜). SKILL.md 단계가 파일을 이름으로 가리키게 한다. "한 번 만든 건 다시 만들지 않는다."
3. **완료 검증(Definition of Done)** — 증거로 확인 가능한 체크리스트를 매뉴얼에 넣는다: 원본까지 추적되는 숫자, 실제로 열리는 링크, 렌더링 스크린샷, 실제로 도는 테스트, 인용과 대조된 주장, 참조 파일과 대조된 값. "명확한·전문적인·고품질" 같은 애매한 말 금지.
4. **루프** — 에이전트가 틀리면 채팅에서 고치지 말고 그 작업의 매뉴얼(SKILL.md)을 고친다(v1 → v2).

## 크로스체크

| 영상 주장 | 판정 | 근거 |
|---|---|---|
| 앤트로픽 엔지니어들이 몇 달 전부터 에이전트 만들기를 멈췄다 | 과장 | 출처는 2025-12 AI Engineer 발표 "Don't Build Agents, Build Skills Instead"(Barry Zhang·Mahesh Murag). 요지는 "분야별 에이전트 대신 범용 에이전트 하나 + 스킬"이지 에이전트 금지가 아니다. 앤트로픽은 지금도 에이전트 제품(Claude Duet 등)을 낸다. |
| 에이전트 하나 + 작업별 매뉴얼 | 맞음 | 발표 핵심. 공식 이름은 Agent Skills |
| `[job-name]/SKILL.md` 폴더로 매뉴얼 | 절반 | SKILL.md 맨 위 YAML에 `name`(소문자·숫자·하이픈, 64자 이하)과 `description`(무엇을 하는지 + 언제 쓰는지)이 **필수**. Claude는 시작할 때 이 둘만 읽고 description으로 언제 꺼낼지 정한다. 영상 프롬프트엔 없다 |
| Claude나 ChatGPT로 | 대체로 | SKILL.md 폴더는 Claude·Codex 공식 지원. ChatGPT는 일부 요금제 베타라는 보도 |
| 검증은 아무도 몰랐던 것 | 틀림 | Claude Code 공식 모범 사례의 핵심 항목 "Give Claude a way to verify its work" |
| 틀리면 매뉴얼을 고친다 | 맞음 | 스킬 운영의 기본 |

## 이 레포에서 쓸 때 (개발 체크리스트)

- 반복 업무는 에이전트를 새로 만들기 전에 **스킬로 만들 수 있는지 먼저** 본다. 에이전트(`.claude/agents/`)는 역할·모델·도구 권한을 나눠야 할 때만(예: Opus 감독 vs Sonnet 실행).
- 스킬 위치: `.claude/skills/<name>/SKILL.md` (예: `git-branch-policy`). 맨 위에 반드시:
  ```yaml
  ---
  name: weekly-client-update
  description: 매주 고객 업데이트 메일 초안을 만든다. "주간 업데이트", "고객 보고" 요청이나 금요일 정기 보고 때 사용.
  ---
  ```
- 본문 구성: 목적 / 언제 쓰는지(언제 안 쓰는지) / 입력과 위치 / 순서 / 결정 규칙 / **완료 기준(증거로 확인 가능하게)** / 예외·과거 실패.
- 보조 파일은 스킬 폴더 안에 두고 SKILL.md에서 이름으로 가리킨다. 긴 참고 자료는 본문에 넣지 말고 파일로(필요할 때만 읽힌다).
- 실패하면 대화로 땜질하지 말고 SKILL.md를 고쳐 커밋한다. 왜 고쳤는지는 커밋 메시지나 HANDOVER.md에.
- 영상 인터뷰 프롬프트를 쓸 때는 마지막 지시에 "맨 위에 name·description YAML 머리말을 넣어라"를 추가한다.

## 콘텐츠 형식 메모 (내 채널 참고)

- 훅: 권위 인용("앤트로픽 엔지니어도") + 통념 뒤집기("에이전트 만들지 마세요"). 효과는 크지만 과장이면 신뢰를 깎는다 — 같은 구조를 사실 범위 안에서 쓸 것.
- 구성: 공감(반쯤 만든 프로젝트 15개) → 원인 → 해법 3단계(각 단계마다 복붙 프롬프트 화면) → 루프 정리.
- CTA: 저장 + 공유 대상 지정("AI로 대체 못 한다는 사람한테") + 댓글 키워드("매뉴얼") → 자료 발송.

## 출처

- [Don't Build Agents, Build Skills Instead – AI Engineer](https://www.ai.engineer/talks/CEvIs9y1uog-agent-skills)
- [에이전트를 만들지 마라, 스킬을 만들어라 (wikidocs 정리)](https://wikidocs.net/blog/@jaehong/8112/)
- [Agent Skills overview – Claude Platform Docs](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview?version=published)
- [Equipping agents for the real world with Agent Skills](https://www.anthropic.com/research/equipping-agents-for-the-real-world-with-agent-skills)
- [Claude Code Best Practices](https://code.claude.com/docs/en/best-practices.md)
- [Codex CLI Agent Skills guide](https://itecsonline.com/post/codex-cli-agent-skills-guide-install-usage-cross-platform-resources-2026)
