# CLAUDE.md

## Project Overview

Python 기반 범용 실험 워크스페이스. 데이터 분석, 시각화, 자동화, AI 에이전트 개발 등 다양한 실험을 수행하는 모노레포.

## 새 세션 시작 시 읽기 순서

1. **이 파일 (CLAUDE.md)** — 레포 전체 구조
2. **`AGENTS.md`** — 조직도(메인 코디네이터·팀·본사 공용 에이전트), 모델 정책, 7단계 흐름, Slack 규칙
3. **작업 대상 프로젝트의 `TEAM.md`** — 팀장 모델, 팀원, 검증·출시 방법, 현재 상태
4. **해당 프로젝트의 `HANDOVER.md`** — 결정 이력과 도메인 용어
5. **해당 프로젝트의 `CLAUDE.md`** — 실행 명령어와 세부 규칙

> 딥코인봇(1팀): `TEAM.md` → `HANDOVER.md` → `CLAUDE.md` → `STRATEGY.md`

---

## 에이전트 조직 (요약 — 자세한 건 `AGENTS.md`)

```
재영 (오너)
  └ 메인 코디네이터 (Opus 5.5, 레포 루트 세션) ─ 팀 배정·팀 간 조율·출시 승인 요청
      ├ 본사 공용: architect(Fable 5.2) · reviewer(Opus 5.5) · lander · engineer · researcher(Sonnet 5.5) · quick-worker(Haiku 5.5)
      ├ 1팀 트레이딩  팀장 Opus 5.5    projects/deepcoin_bot
      ├ 2팀 주역      팀장 Sonnet 5.5  projects/iching
      ├ 3팀 콘텐츠    팀장 Sonnet 5.5  projects/claude-code-monitor
      ├ 4팀 사업발굴  팀장 Sonnet 5.5  projects/사업발굴투트랙프로젝트
      └ 운영팀 (메인 직할) automation/mvno-monitor, GitHub Actions
```

- **모델 원칙**: 판단(코디네이터·설계·리뷰·감독)은 상위 모델 Opus 5.5·Fable 5.2, 실행(구현·랜딩·조사·잡무)은 하위 모델 Sonnet 5.5·Haiku 5.5.
- **코디네이터는 코드를 쓰지 않는다.** 메인이든 팀장이든 계획·배정·검수만 한다.
- **이 세션이 레포 루트에서 특정 팀 지시 없이 열렸다면 메인 코디네이터다.** 요청을 받으면 담당 팀을 정해 팀장 세션에 넘기고, 직접 고치지 않는다. 한두 줄 문서 수정 같은 아주 작은 일은 예외로 `quick-worker`에게 맡긴다.
- 팀장 세션은 `.claude/agents/team-lead.md` 지침과 자기 팀 `TEAM.md`로 일한다.
- Slack: #인사팀장실(재영↔메인, 승인), #실무팀(`[N팀]` 보고), #성과보고(정기 결과), #랍스터본부(출시 공지). 산출물 링크 없는 메시지는 금지.

## Directory Structure

- `projects/` — **새 프로젝트는 여기부터 시작** (`projects/_template/` 복사해서 사용, 프로젝트당 브랜치 1개)
- `analysis/` — 데이터 분석 프로젝트
- `visualization/` — 시각화 프로젝트
- `automation/` — 자동화 스크립트 및 도구 (레거시 — 신규 프로젝트는 `projects/`로)
- `agents/` — AI 에이전트 개발 및 유지관리 (레거시, 비어있음 — 신규는 `projects/`로)
- `content/`, `research/` — 3팀(콘텐츠)의 블로그·인스타 원고와 조사 결과
- `.claude/agents/` — 서브에이전트 정의 (본사 공용 + 팀 전용)
- `sandbox/` — 임시 실험 및 테스트
- `shared/utils/` — 공통 유틸리티 함수
- `data/raw/`, `data/processed/` — 데이터 저장소
- `notebooks/` — Jupyter 노트북
- `configs/` — 설정 파일

## Conventions

- Language: Python
- Dependencies: `requirements.txt` (pip)
- Config/secrets: `.env` files (gitignored), `configs/` for non-secret config
- Large data files in `data/` are gitignored — only `.gitkeep` is tracked
- `.mcp.json` is gitignored (contains secrets)

## Key Commands

```bash
pip install -r requirements.txt   # Install dependencies
```

## 활성 프로젝트

| 팀 | 프로젝트 | 경로 | 상태 |
|---|---|---|---|
| 1팀 | **딥코인봇** | `projects/deepcoin_bot/` | **실거래 운용 중** (BTC/ETH/XRP). 일목 A·추세돌파·단타 체인 |
| 2팀 | 주역사주 | `projects/iching/` | v2 운영 배포 (Vercel `iching-nu.vercel.app`, CLI 배포) |
| 3팀 | Claude Code 트렌드 모니터 | `projects/claude-code-monitor/` | GitHub Actions 주간 실행 → 블로그·인스타 원고 → Slack |
| 4팀 | 사업발굴 투트랙 | `projects/사업발굴투트랙프로젝트/` | 발굴 → 실현계획 문서 작업 |
| 운영팀 | mvno-monitor | `automation/mvno-monitor/` | 예약 루틴으로 매일 알뜰폰 특가 → Slack DM |

## Notes

- 한국어 프로젝트 — README 및 커밋 메시지는 한국어 사용
- `sandbox/`는 임시 실험용이므로 코드 품질 기준이 낮아도 됨
- `shared/utils/`에 재사용 가능한 유틸리티를 모아 중복 방지
- **HANDOVER.md 패턴**: 복잡한 프로젝트는 반드시 `HANDOVER.md`를 두어 "왜 이렇게 됐는가"를 기록한다. 새 세션이 열릴 때 대화 히스토리는 압축/소실되지만 HANDOVER.md는 결정 이력을 보존한다. 딥코인봇이 이 패턴의 첫 구현 사례.

---

## 랍스터 주식회사 (레거시)

첫 에이전트 조직 실험. 문서와 `slack_commander.py`는 커밋 `e18becc`에서 삭제됐다. 로컬 폴링 데몬이 산출물 없이 상태 메시지만 반복했기 때문이다. Slack 채널 구조, 봇 5개, "결론부터·사족 없이" 톤은 `AGENTS.md` 5장으로 옮겨 계속 쓴다.

---

## Claude Code 확장 툴 (권장 설치)

| 툴 | GitHub | 역할 |
|---|---|---|
| Ponytail | DietrichGebert/ponytail | 불필요한 파일 생성 방지 |
| Graphify | Graphify-Labs/graphify | 코드 지식 그래프 → 토큰 절약 |
| OmniRoute | diegosouzapw/OmniRoute | 멀티모델 자동 폴백 라우팅 |
