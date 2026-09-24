# 딥코인봇 (DeepCoin Bot) — CLAUDE.md

## 프로젝트 개요

BTC/ETH/XRP 무기한 선물 자동매매 봇. Deepcoin 거래소 API 기반.
**ICT(Inner Circle Trader) + MTF(5m/15m/1H/D1) + 실거래 승률 기반 자가진화** 통합.

**현재 상태**: 활성 개발 중 / 자가진화 모드 / **실거래 운용 중** (BTC/ETH/XRP)

---

## 세션 시작 시 반드시 할 것

1. **`HANDOVER.md` 읽기** — 프로젝트 배경, 용어 사전, 결정 이력 파악 (처음이면 필수)
2. **`STRATEGY.md` 읽기** — 현재 매매 원칙 및 금지 패턴 파악
3. **`python evolution/review_trades.py`** 실행 — 최신 패턴 통계 갱신
4. pending_updates 있으면 `STRATEGY.md` 자동 반영됨 (버전 +0.1)

---

## 디렉토리 구조

```
deepcoin_bot/
├── CLAUDE.md              ← 이 파일 (하네스 가이드)
├── STRATEGY.md            ← 매매 원칙 (자가진화 대상 — 반드시 읽을 것)
├── server.py              ← 라이브 봇 서버 (포트 5000)
├── ict_engine.py          ← ICT 분석 엔진 (Premium/Discount/OTE/Breaker/NDOG)
├── smc_engine.py          ← SMC 엔진 (BOS/ChoCh/OB/FVG/Sweep) — ict_engine이 상속
├── index.html             ← 봇 대시보드
├── tuning.json            ← 파라미터 (60초마다 자동 reload)
├── HANDOVER.md            ← 인수인계서 (용어/결정 이력/삭제된 것)
├── backtest/
│   ├── run.py             ← 백테스트 CLI (--all --days 180 --risk 10 --leverage 20)
│   ├── strategy.py        ← ICT 백테스트 전략 4종 (killzone/ote/breaker/mtf)
│   ├── engine.py          ← 백테스트 엔진 (동적 사이징, 가중치 반영)
│   ├── weights.py         ← 패턴 가중치 (실거래+백테스트 누적 학습)
│   └── pattern_weights.json ← 자동 생성 (거래 청산 시 sync)
├── evolution/
│   ├── review_trades.py   ← 패턴 통계 분석 + STRATEGY.md 자동 업데이트
│   ├── dashboard_gen.py   ← 대시보드 데이터 생성
│   └── pattern_stats.json ← 자동 생성
├── dashboard/
│   ├── index.html         ← 전략 대시보드 (localhost:8899)
│   └── serve.py           ← 대시보드 서버
└── trade_logs/daily/      ← 일별 거래 일지 + 패턴 학습 통계
```

---

## 에이전트 모델 정책

| 에이전트 | 모델 | 역할 |
|---------|------|------|
| `trade-supervisor` | **Opus** | 거래 품질 감독 — 타점/TP/SL 사후 검증 |
| `project-lead` | Sonnet | 작업 조율 및 위임 |
| `engineer` | Sonnet | 코드 구현/버그 수정 |
| `researcher` | Sonnet | 기술/시장 조사 |

> 감독 에이전트 호출: `/agent trade-supervisor` — 최근 거래 로그 분석 후 STRATEGY.md 개선 제안

---

## 자가진화 루프 (닫힌 상태)

```
실거래 발생
  → server.py _rec() 패턴 통계 누적
  → weights.sync_live_stats() 즉시 호출 → pattern_weights.json 갱신
  → 다음 진입 시 get_weight(pattern_key) → 포지션 사이징에 반영

매일 KST 21:00 (거래일 전환)
  → server.py 날짜 감지 → review_trades.py 자동 실행
  → trade_logs/ 파싱 → pattern_stats.json 갱신
  → pending_updates 있으면 STRATEGY.md 자동 업데이트 (버전+0.1)
  → 다음 세션 시작 시 새 원칙 적용
```

---

## 매매 엔진 — 타임프레임 구조

| 타임프레임 | 역할 |
|-----------|------|
| **1D** | 시장 국면 (bull/bear/ranging) — 역방향 진입 차단 |
| **1H** | 추세 방향 (EMA20 + 스윙 구조) |
| **15m** | 메인 시그널 (ICT: OB/FVG/BOS/Breaker/OTE) |
| **5m** | 진입 타이밍 확인 (EMA9/21 + 캔들 방향 일치 필수) |

진입 조건 체크 순서 (`_run_claude_bot` 진입 체인 그대로):
1. 일 한도 (`_can_trade`)
2. 킬존 (런던/뉴욕 외 진입 금지)
3. **멀티전략 체인** (`ict_engine._SIGNAL_CHAIN`) — OTE → MTF → 킬존NY전용 → Breaker 순으로 시도, 먼저 나오는 시그널 채택 (STRATEGY.md 4-1 참고, 백테스트 성과순)
4. 직전 손절 구조 재진입 차단
5. RSI (롱 >68 / 숏 <32 스킵)
6. 15m EMA9/21 배열
7. D1 레짐 (bull이면 숏, bear이면 롱 차단)
8. 쿨다운
9. 5m 진입 타이밍
10. TP 최소 / RR 2.5 → 패턴 가중치 → 동적 사이징 → 주문

---

## 매매 환경 설정

- **거래소**: Deepcoin. 심볼별 독립 스레드. 매매 대상은 `tuning.json: active_symbols` (현재 BTC, ETH)
- **레버리지**: 20x (`leverage`)
- **리스크**: 잔고의 10% / 트레이드 (`risk_pct`)
  - 공식: `증거금% = min(80%, 10% / (SL거리 × 20)) × 패턴가중치`
- **TP**: 구조적 레벨 기준. 심볼별 최소 증거금 `tp_min_margin_by_sym` (BTC 5% / ETH·XRP 3% → 가격 기준 ÷20), 최대 `tp_max_pct` 15%
  - 딥코인 UI에서는 마진 기준으로 표시됨 (가격% × 20배)
- **SL 최대**: 가격 기준 2% (`sl_cap_pct`)
- **최소 RR**: 2.5 (`rr_min`)
- **일 한도 (계좌 전체, 3심볼 합산)**: 손실 -25% (`daily_loss_stop`) / 손절 3회 (`max_daily_losses`) / 거래 7회 / 수익 +10%
- **쿨다운**: 900초 (`cooldown`)
- **주문가 정밀도**: `_PX_DEC` BTC 1 / ETH 2 / XRP 4 자리

> **tuning.json 우선 적용**: 위 파라미터는 모두 `tuning.json`에서 읽어옴. 서버 워처가 60초마다 reload → 재시작 없이 변경 가능.
> `active_symbols`에서 심볼을 빼면 포지션 없는 시점에 해당 스레드가 자동 정지됨.

---

## Key Commands

```bash
# 봇 서버 시작
python server.py  # http://localhost:5000

# 봇 시뮬/실제 시작 (API)
curl -X POST localhost:5000/api/claude/start -d '{"mode":"sim"}'
curl -X POST localhost:5000/api/claude/start -d '{"mode":"real"}'

# 백테스트
python backtest/run.py --all --sym BTC-USDT-SWAP --days 180 --risk 10 --leverage 20

# 패턴 통계 리뷰 + STRATEGY.md 자동 업데이트
python evolution/review_trades.py

# 대시보드 (전략 가중치 / 시장 국면)
python dashboard/serve.py  # http://localhost:8899
```

---

## 주의사항

- `.env` — API 키 포함, 절대 커밋 금지
- `trade_logs/` — 실제 거래 기록, 원칙 진화의 원천 데이터
- `STRATEGY.md` — 자동 업데이트됨. 수동 수정 시 버전/날짜 반드시 기재
- `pattern_weights.json` — 자동 생성, gitignore 대상 아님 (진화 상태 보존)
