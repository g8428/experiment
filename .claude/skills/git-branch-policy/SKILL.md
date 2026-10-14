---
name: git-branch-policy
description: 이 레포(g8428/experiment)의 브랜치 이름, 수명, 커밋 메시지, 태그, 정리 규칙. 브랜치를 만들거나 머지·삭제하기 전, 커밋 메시지를 쓸 때, "브랜치 정리", "PC에 남은 테스트 브랜치 분류", "딥코인봇 태그" 요청이 있을 때 사용.
---

# 브랜치·버전관리 규칙 (GitHub Flow 간소화판)

핵심 한 줄: **master는 완성본 하나. 작업은 이름표 붙은 복사본에서 짧게 하고, 합치면 바로 지운다.**
요약본은 `AGENTS.md` "브랜치 전략"에 있고, 이 문서는 그 상세판이다. 둘이 어긋나면 AGENTS.md를 기준으로 하고 이 문서를 고친다.

비유: master = 공유드라이브의 최종본 폴더, 브랜치 = 내 작업대, 푸시 = 회사 금고(GitHub)에 넣기, 머지 = 최종본에 반영, 태그 = "이 날 실거래 버전" 스티커. PC에만 있고 푸시 안 한 브랜치는 서랍 속 메모라서 PC가 고장 나면 사라진다.

## 1. 브랜치 이름

| 접두사 | 용도 | 예시 | 푸시 | 수명 |
|---|---|---|---|---|
| `master` | 완성본. 실거래·배포 기계는 이것만 받음 | — | 항상 | 영구 |
| `project/<이름표>-<할일>` | 로컬 PC 개발 | `project/deepcoin-eth-slot` | 하루 끝에 반드시 | 머지 후 삭제, 최대 2주 |
| `claude/<자동이름>` | 클라우드 세션이 자동 생성. **이름 바꾸지 않음** | `claude/charming-tesla-cypq91` | 자동 | 최대 7일 |
| `worktree-<이름>` | 로컬 `claude --worktree`가 자동 생성 | `worktree-deepcoin-backtest` | 필요할 때만 | 종료 시 정리 |
| `test/<MMDD>-<내용>` | 손으로 하는 실험 | `test/1014-langfuse-try` | 기본 안 올림 | 2주 |
| `archive/<YYYY-MM>-<내용>` | 버리기 아까운 것 보관 | `archive/2026-10-smc-b` | 올림 | 분기마다 재검토 |
| `bot/<봇이름>` | 봇이 코드를 고쳐야 할 때만 | `bot/mvno-monitor` | 봇이 푸시 | 머지 후 삭제 |

이름표: `deepcoin`(딥코인봇), `iching`(주역 앱), `mvno-monitor`, `cc-monitor`(claude-code-monitor), `biz`(사업발굴투트랙), `infra`(레포 공통·문서).

Claude의 임의 이름(`claude/…`)은 바꾸지 않는다. `claude/` 자체를 "클라우드에서 온 1회용 작업대"로 분류하고, 어느 프로젝트 작업인지는 커밋 메시지 맨 앞 이름표로 구분한다.

## 2. 수명

1. 최신 master에서 시작: `git switch master && git pull && git switch -c project/<이름표>-<할일>`
2. 하루 작업이 끝나면 커밋 + 푸시.
3. 동작이 확인되면 master로 머지. 2주를 넘기면 쪼개서 일부만 먼저 머지하거나 `archive/`로 보낸다.
4. 머지가 끝나면 로컬·원격 브랜치를 즉시 삭제(기본값). 기록은 master에 남는다.
5. 딥코인봇은 백테스트·모의 확인 결과를 커밋 메시지나 문서에 적은 뒤 머지하고, 머지 직후 태그를 찍는다.
6. 봇 예외: github-actions[bot]과 파이 스케줄 태스크는 자기 결과물 폴더(`research/`, `automation/mvno-monitor/` 로그 등)에 한해 master 직접 커밋 허용. 푸시 전 `git pull --rebase`.

## 3. 커밋 메시지와 태그

```
<이름표>: <무엇을> (<왜>, 선택)
```

- 한국어. 예: `deepcoin: ETH·XRP에도 동시 슬롯 최대 3 적용 (사용자 결정)`
- 봇 커밋만 `chore: …`. Conventional Commits(`feat:`/`fix:`)는 강제하지 않는다.
- 태그는 실거래에 영향을 주는 프로젝트(지금은 딥코인봇)만. 실거래 기계가 새 코드를 받기 직전에 머지한 커밋에 찍는다.
  ```bash
  git tag -a deepcoin-live-YYYYMMDD -m "무엇을 반영했는지"
  git push origin deepcoin-live-YYYYMMDD
  ```
  같은 날 두 번이면 `-2`. 되돌릴 때는 실거래 기계에서 직전 태그로 `git checkout`.

## 4. 로컬 PC와 클라우드가 겹치지 않게

1. 한 브랜치는 한 장소에서만 만진다. `claude/*`는 클라우드, `project/*`·`worktree-*`·`test/*`는 PC.
2. 작업 시작 전 받아온다(`git pull`, PC는 `git fetch --prune`). 오래된 master에서 시작하지 않는다.
3. 장소를 떠날 때 커밋 + 푸시. 푸시 안 한 작업이 있으면 다른 장소에서 같은 일을 시작하지 않는다.
4. 클라우드 작업을 PC에서 이어갈 때: 클라우드 세션 종료 확인 → `git fetch` → `git switch -c project/<이름표>-<할일> origin/claude/<그 브랜치>` → 이후 PC 브랜치만 사용하고 원래 `claude/…`는 삭제.
5. PC에서 Claude 세션을 동시에 여러 개 돌리면 `claude --worktree <이름>`으로 분리.
6. 실거래 기계에서 직접 코드를 수정하지 않는다. master(또는 태그)만 받는다.

## 5. 월 1회 정리 루틴

```bash
git fetch --prune                 # GitHub에서 이미 지워진 브랜치 흔적 정리
git branch -vv                    # PC 브랜치 목록. ': gone' = GitHub에선 삭제됨
git stash list                    # 잊고 있던 임시 보관 작업
git branch --merged master        # master에 다 들어간 브랜치 = 지워도 안전
```

목록의 브랜치(master 제외)는 하나씩 안전 삭제한다. `-d`는 합쳐진 것만 지우므로 안전하다.

```bash
git branch -d <브랜치이름>
git push origin --delete <브랜치이름>
```

`git worktree list`로 남은 작업 폴더도 확인한다. `-D`(강제 삭제)는 아래 분류를 끝낸 뒤에만 쓴다.

## 6. PC에 남은 테스트 브랜치 분류 3단계

먼저 브랜치마다 `git log master..<브랜치> --oneline`과 `git status`를 본다. 분류만 하고, 사용자 확인 없이 삭제하지 않는다.

| 단계 | 질문 | 처리 |
|---|---|---|
| 1 | `git log master..브랜치`가 비어 있나? | 예 → 삭제 (`git branch -d`) |
| 2 | 고유 커밋이 있고 2주 안에 이어갈 일이거나 실거래·앱에 들어갈 내용인가? | 예 → 이름을 `project/<이름표>-<할일>`로 바꿔 푸시하고 2주 안에 머지 |
| 3 | 고유 커밋이 있지만 당장 계획이 없나? | `archive/<YYYY-MM>-<내용>`으로 이름을 바꿔 푸시한 뒤, GitHub에 올라간 것을 확인하고 로컬 삭제 |

애매하면 3단계(보관)가 기본값이다.

## 7. 에이전트가 지킬 것

- 작업 시작 시 `git branch --show-current`로 현재 브랜치를 확인한다. 현재 브랜치가 `claude/…`이면 새 브랜치를 만들지 말고 그대로 쓴다.
- master에서 시작해야 한다면 `git pull` 후 `project/<이름표>-<할일>`을 만든다.
- 사용자가 요청하지 않은 PR 생성, 브랜치 삭제, 강제 푸시, 태그 푸시는 하지 않는다.
- 이 문서에서 확인하지 못한 것: `claude/` 접두사가 강제인지 여부, 사용자 PC의 로컬 브랜치·stash, 파이 스케줄 태스크가 커밋하는 브랜치. 이 부분은 추측하지 말고 사용자에게 확인한다.
