# 1팀 트레이딩 — TEAM.md

> 팀장 세션이 가장 먼저 읽는 문서. 다음 순서로 `HANDOVER.md` → `CLAUDE.md` → `STRATEGY.md`를 읽는다.

## 팀 구성

| 자리 | 누가 | 모델 |
|---|---|---|
| 팀장 | `team-lead` 세션 | **Opus 5.5** (실거래 자금이 걸려 있어 상위 모델) |
| 거래 감독 | `trade-supervisor` (팀 전용) | Opus 5.5 |
| 설계 | `architect` | Fable 5.2 |
| 리뷰 | `reviewer` | Opus 5.5 |
| 구현 | `engineer` | Sonnet 5.5 |
| 랜딩·검증 | `lander` | Sonnet 5.5 |
| 조사 (전략·강의 분석) | `researcher` | Sonnet 5.5 |
| 작은 일 (로그 요약·통계 보고) | `quick-worker` | Haiku 5.5 |

## 담당 범위

- 폴더: `projects/deepcoin_bot/`
- 브랜치: 전략 연구는 `project/<전략명>` (예: `project/ichimoku-cloud-state-strategy`, `project/smc-c`)

## 검증 (lander가 병합마다 실행)

```bash
cd projects/deepcoin_bot
python -m py_compile server.py ict_engine.py smc_engine.py ichimoku_cloud_state.py
python backtest/run.py --all --days 180 --risk 10 --leverage 20   # 전략·SL 로직을 바꿨을 때
python evolution/review_trades.py                                  # 통계 갱신 확인
```

- 백테스트는 바꾸기 전과 후를 같은 기간으로 비교한다. 결과는 `backtest/` 아래 파일로 남긴다.

## 출시 (= 실거래 반영)

- **실거래 서버에 반영하려면 반드시 재영 승인이 필요하다.** 팀장 → 메인 코디네이터 → #인사팀장실 `[1팀][승인요청]`.
- 승인 요청에 들어갈 것:
  - 백테스트 전후 비교
  - 바뀌는 심볼, 레버리지, 비중
  - 되돌리는 방법
- 서버는 세션과 독립된 프로세스로 돈다. 재시작 시점과 로그(`trade_logs/server_stdout.log`) 확인은 팀장이 직접 지휘한다.

## 팀 고유 금지 사항

- 승인 없이 실거래 파라미터(`tuning.json`의 레버리지·비중·SL)를 바꾸거나, 실거래 서버를 재시작하는 것
- 런타임 데이터를 다른 작업에 섞어 커밋하는 것. 해당 파일: `trade_logs/`, `backtest/cache/`, `evolution/*.json`, `backtest/pattern_weights.json`
- 연구용 전략(`smc_btc/`, `sensei_btc/`)을 백테스트 통과 없이 실거래 체인에 연결하는 것

## 현재 상태

- 2026-11-26: 팀 체계 도입. 실거래 구성은 `CLAUDE.md` 상단(2026-10-03 기준)을 따른다.
