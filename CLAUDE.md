# CLAUDE.md

## Project Overview

Python 기반 범용 실험 워크스페이스. 데이터 분석, 시각화, 자동화, AI 에이전트 개발 등 다양한 실험을 수행하는 모노레포.

## Directory Structure

- `analysis/` — 데이터 분석 프로젝트
- `visualization/` — 시각화 프로젝트
- `automation/` — 자동화 스크립트 및 도구
- `agents/` — AI 에이전트 개발 및 유지관리
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

## 프로젝트: 랍스터 주식회사

AI Agent Teams로 운영되는 가상 기업 프로젝트.
상세 내용은 `랍스터주식회사/회사규칙.md` 참고.

### 빠른 시작
```bash
# 인사팀장 spawn
"랍스터주식회사/조직도/인사팀장.md 읽고
인사팀장 spawn해줘"

# CEO 지시
"이번 주 AI 자동화 사업 아이템 조사해"
```

### Slack 채널
- #랍스터본부 — 전체 공지, 중요 결정사항
- #인사팀장실 — 사장님 ↔ 인사팀장 소통
- #실무팀 — 사원들 협업 및 진행상황 공유
- #성과보고 — 주간/월간 성과 보고 전용
