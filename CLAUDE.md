# CLAUDE.md

## Project Overview

Python 기반 범용 실험 워크스페이스. 데이터 분석, 시각화, 자동화, AI 에이전트 개발 등 다양한 실험을 수행하는 모노레포.

## 에이전트 조직 구조

이 레포에서 여러 AI 에이전트가 어떻게 계층을 이루고(헤드봇/프로젝트 에이전트/하위 에이전트), 어떤 브랜치 전략을 쓰고, 언제 Cowork 스케줄 태스크를 쓰고 언제 로컬 Claude Code를 쓰는지는 **`AGENTS.md`**에 정리되어 있다. 새 프로젝트를 시작하거나 에이전트를 spawn하기 전에 먼저 읽을 것.

하위 에이전트 정의는 `.claude/agents/*.md`에 커밋되어 있다 (project-lead, engineer, researcher).

## Directory Structure

- `projects/` — **새 프로젝트는 여기부터 시작** (`projects/_template/` 복사해서 사용, 프로젝트당 브랜치 1개)
- `analysis/` — 데이터 분석 프로젝트
- `visualization/` — 시각화 프로젝트
- `automation/` — 자동화 스크립트 및 도구 (레거시 — 신규 프로젝트는 `projects/`로)
- `agents/` — AI 에이전트 개발 및 유지관리 (레거시, 비어있음 — 신규는 `projects/`로)
- `랍스터주식회사/` — 초기 프로토타입. 문화/톤 문서(`회사규칙.md`)는 유효하지만 실행 구조(`slack_commander.py`)는 `AGENTS.md`의 구조로 대체됨
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

## Notes

- 한국어 프로젝트 — README 및 커밋 메시지는 한국어 사용
- `sandbox/`는 임시 실험용이므로 코드 품질 기준이 낮아도 됨
- `shared/utils/`에 재사용 가능한 유틸리티를 모아 중복 방지

---

## 프로젝트: 랍스터 주식회사 (레거시 프로토타입)

AI Agent Teams로 운영되는 가상 기업 프로젝트의 첫 시도. 캐릭터/톤/Slack 채널 구조는 `랍스터주식회사/회사규칙.md`에 남아있고 여전히 유효하다.

다만 `slack_commander.py`(로컬 폴링 데몬 + 텍스트 보고만 하는 페르소나 구조)는 실제 산출물 없이 상태 메시지만 반복하는 문제가 있어 실행 구조로는 더 이상 쓰지 않는다. 대체 구조는 `AGENTS.md` 참고 — 반복 작업은 Cowork 스케줄 태스크(헤드봇), 실제 개발은 로컬 Claude Code(`projects/` + `.claude/agents/`)가 맡는다.

### Slack 채널 (구조는 유효, 계속 사용)
- #랍스터본부 — 전체 공지, 중요 결정사항
- #인사팀장실 — 사장님 ↔ 인사팀장 소통
- #실무팀 — 사원들 협업 및 진행상황 공유
- #성과보고 — 주간/월간 성과 보고 전용
