# N팀 <팀 이름> — TEAM.md

> 팀장 세션이 가장 먼저 읽는 문서. 조직 규칙은 루트 `AGENTS.md`, 결정 이력은 `HANDOVER.md`, 실행 명령은 `CLAUDE.md`에 있다.

## 팀 구성

| 자리 | 누가 | 모델 |
|---|---|---|
| 팀장 | `team-lead` 세션 | Opus 5.5 (실거래·운영 서비스 팀) / Sonnet 5.5 (그 밖) |
| 설계 | `architect` (본사) | Fable 5.2 |
| 리뷰 | `reviewer` (본사) | Opus 5.5 |
| 구현 | `engineer` (본사) | Sonnet 5.5 |
| 랜딩·검증 | `lander` (본사) | Sonnet 5.5 |
| 조사 | `researcher` (본사) | Sonnet 5.5 |
| 작은 일 | `quick-worker` (본사) | Haiku 5.5 |
| 팀 전용 | (있으면) | |

## 담당 범위

- 폴더: `projects/<p>/`
- 팀 브랜치: `project/<p>`
- 손대지 않는 곳: 다른 팀 폴더, `shared/`, 루트 문서, `.claude/`. 바꿔야 하면 메인 코디네이터에게 요청한다.

## 검증 (lander가 병합마다 실행)

```bash
# 예: python -m pytest projects/<p>/tests -q
```

- 확인할 화면·결과:

## 출시

- 방법: (예: `vercel --prod`, GitHub Actions, 예약 루틴)
- 승인: 메인 코디네이터를 거쳐 재영이 #인사팀장실에서 승인
- 출시 후: #랍스터본부에 `[N팀][출시] 한 줄 — URL/커밋`

## 팀 고유 금지 사항

-

## 현재 상태

> 팀장이 세션을 끝낼 때마다 갱신한다. 날짜, 한 줄, 커밋 해시.

- YYYY-MM-DD:
