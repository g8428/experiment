# 딥코인봇 (DeepCoin Bot) — CLAUDE.md

## 프로젝트 개요

BTC/ETH/XRP 무기한 선물 자동매매 봇. Deepcoin 거래소 API 기반.
**ICT(Inner Circle Trader) + MTF(5m/15m/1H/D1) + 실거래 승률 기반 자가진화** 통합.

**현재 상태**: 활성 개발 중 / 자가진화 모드 / 시뮬 운용 중

---

## 세션 시작 시 반드시 할 것

1. **`STRATEGY.md` 읽기** — 현재 매매 원칙 및 금지 패턴 파악
2. **`python evolution/review_trades.py`** 실행 — 최신 패턴 통계 갱신
3. pending_updates 있으면 `STRATEGY.md` 자동 반영됨 (버전 +0.1)

---

## 디렉토리 구조

```
deepcoin_bot/
├── CLAUDE.md              ← 이 파일 (하네스 가이드)
├── STRATEGY.md            ← 매매 원칙 (자가진화 대상 — 반드시 읽을 것)
├── server.py              ← 라이브 봇 서버 (포트 5000)
├── ict_engine.py          ← ICT 분석 엔진 (Premium/Discount/OTE/Breaker/NDOG)
├── smc_engine.py          ← SMC 엔진 (BOS/ChoCh/OB/FVG/Sweep) — ict_engine이 상속
├── strategies.py          ← 보조 전략 (EMA크로스/BB/아시안브레이크아웃)
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

진입 조건 체크 순서:
1. D1 레짐 필터 (bull이면 숏 차단, bear이면 롱 차단)
2. 킬존 필터 (런던/뉴욕만 허용)
3. 15m ICT 시그널 (OB재터치 또는 FVG진입)
4. 15m EMA9/21 배열 확인
5. RSI 필터 (과매수/과매도 제외)
6. 5m 진입 타이밍 확인
7. 패턴 가중치 → 포지션 사이징

---

## 매매 환경 설정

- **거래소**: Deepcoin (BTC-USDT-SWAP, ETH, XRP)
- **레버리지**: 20x
- **리스크**: 잔고의 10% / 트레이드 (동적 사이징)
  - 공식: `증거금% = min(80%, 10% / (SL거리 × 20배))`
- **일 손실 한도**: -3% (도달 시 당일 거래 중단)
- **일 수익 한도**: +10%
- **최대 일 거래 횟수**: 7회

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
