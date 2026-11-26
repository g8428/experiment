# 2팀 주역 — TEAM.md

> 팀장 세션이 가장 먼저 읽는 문서. 다음으로 `HANDOVER.md`를 읽는다. 이 프로젝트는 `CLAUDE.md` 대신 `HANDOVER.md`가 실행·구조 문서를 겸한다.

## 팀 구성

| 자리 | 누가 | 모델 |
|---|---|---|
| 팀장 | `team-lead` 세션 | Sonnet 5.5 |
| 설계 | `architect` | Fable 5.2 |
| 리뷰 | `reviewer` | Opus 5.5 |
| 구현 | `engineer` | Sonnet 5.5 |
| 화면 디자인 | `impeccable` 스킬 + `impeccable-*` 서브에이전트 (팀 전용) | 세션 모델 |
| 랜딩·검증 | `lander` | Sonnet 5.5 |
| 작은 일 | `quick-worker` | Haiku 5.5 |

## 담당 범위

- 폴더: `projects/iching/`
- 팀 브랜치: `iching-v2-main` (원격 미푸시)

## 검증 (lander가 병합마다 실행)

```bash
node projects/iching/local-server.js     # .claude/launch.json의 "iching" (포트 3000)
```

- 브라우저로 확인할 화면:
  - `/`: v2 주역사주. 동전 던지기 → 무료 점사 → 풀이
  - `/v1`: 예전 주역점
- 풀이 API는 Langfuse 트레이스로 노드별 실패가 없는지 본다.
- 화면 기획안이 있는 작업이면 **모든 화면**을 기획안과 대조한다.

## 출시

- 방법: `projects/iching`에서 `vercel --prod --yes`. 프로젝트는 `work-f28c/iching`이고 GitHub 자동 배포는 없다.
- 승인: 메인 코디네이터를 거쳐 재영이 #인사팀장실에서 승인한다.
- 출시 후 확인:
  - `iching-nu.vercel.app` HTML이 로컬 `v2/index.html`과 같은지
  - `/HANDOVER.md` 같은 문서 주소가 공개되지 않는지 (`.vercelignore`)

## 팀 고유 금지 사항

- `.vercelignore`에서 `*.md`, `*.sql`, `.env*` 제외 규칙을 빼는 것
- `.vercelignore`에 `package.json`을 넣는 것 (Langfuse import가 깨진다)

## 현재 상태

- 2026-11-23: v2 운영 배포 완료 (커밋 0dcd8f0). 운영 주소 iching-nu.vercel.app.
