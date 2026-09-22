# 딥코인봇 (DeepCoin Bot) — CLAUDE.md

## 프로젝트 개요

BTC/USDT 무기한 선물 자동매매 봇. Deepcoin 거래소 API 기반.
**SMC(Smart Money Concepts) + O'Neil/Minervini 방법론 + Claude AI 분석** 통합.

**현재 상태**: 활성 개발 중 / 자가진화 모드

---

## 디렉토리 구조

```
deepcoin_bot/
├── CLAUDE.md              ← 이 파일 (하네스 가이드)
├── STRATEGY.md            ← 매매 원칙 (자가진화 대상 — 반드시 읽을 것)
├── smc_engine.py          ← SMC 분석 엔진 (BOS/ChoCh/OB/FVG/Sweep)
├── signal_scorer.py       ← 복합 스코어링 (추세/모멘텀/변동성/거래량/SMC/캔들)
├── claude_signal.py       ← Claude CLI 기술적 분석 (30분마다 호출)
├── trade_logs/daily/      ← 일별 거래 일지 + 패턴 학습 통계
├── market_reports/        ← latest_signal.json (최신 스코어 캐시)
└── evolution/
    ├── review_trades.py   ← 패턴 통계 분석 + 원칙 업데이트 제안
    └── pattern_stats.json ← 최신 집계 패턴 통계 (자동 생성)
```

---

## 세션 시작 시 반드시 할 것

1. **`STRATEGY.md` 읽기** — 현재 매매 원칙 파악
2. **`python evolution/review_trades.py`** 실행 — 최신 패턴 통계 갱신
3. 원칙 업데이트 제안이 있으면 (`evolution/pattern_stats.json` 의 `pending_updates`) — `STRATEGY.md` 업데이트

---

## 자가진화 프로토콜

### 진화 트리거 조건
패턴 키당 **≥5 거래** AND **승률 ≥70% 또는 ≤30%** (통계적 유의성 기준)

### 진화 사이클
```
거래 발생 → trade_logs/ 기록 → review_trades.py 자동 실행
→ pattern_stats.json 갱신 → 조건 충족 시 STRATEGY.md 업데이트
→ 다음 진입 시 개선된 원칙 적용
```

### Claude가 STRATEGY.md를 업데이트하는 경우
- 특정 패턴의 거래 수가 5개를 넘고 승률이 통계적으로 명확할 때
- 연속 손실 3회 이상 동일 패턴에서 발생했을 때
- 사용자가 명시적으로 원칙 업데이트 요청 시

### 업데이트 시 형식
`STRATEGY.md`의 버전을 올리고, 변경 이력(## 진화 이력)에 날짜/이유/변경내용 추가.

---

## 핵심 모듈 설명

### smc_engine.py
- `get_smc_signal(kl, h1_kl)` → SMC 종합 시그널 (long/short/None)
- `find_bos_choch()`, `find_order_blocks()`, `find_fvg()`, `find_liquidity_sweep()`
- **1H EMA 추세 필터** 내장 — 역추세 진입 차단

### signal_scorer.py
- `compute_and_save(signal_path)` → composite 0~100점 계산 → `latest_signal.json` 저장
- 점수 구성: 추세(30) + 모멘텀(25) + 변동성(15) + 거래량(20) + SMC(15) + 캔들보너스(-10~+10)
- **allowed_bots**: `composite≥55 → "both"`, `≥40 → "scalp"`, else `"none"`

### claude_signal.py
- `analyze()` → Claude CLI 호출 → JSON 분석 결과 반환
- O'Neil Stage 분석 + VCP 탐지 + SMC + 캔들 + 거래량 통합

---

## 매매 환경 설정

- **거래소**: Deepcoin (BTC-USDT-SWAP)
- **레버리지**: 10x
- **일 손실 한도**: -3% (도달 시 당일 거래 중단)
- **일 수익 한도**: +10% (도달 시 당일 거래 중단)
- **최대 일 거래 횟수**: 7회

---

## 스킬 활용 가이드

이 프로젝트에서 활용 가능한 스킬:

| 스킬 | 용도 |
|------|------|
| `technical-analyst` | Claude 시그널 프롬프트에 주입 (현재 적용 중) |
| `vcp-screener` | VCP 패턴 탐지 프롬프트에 주입 (현재 적용 중) |
| `backtest-expert` | 전략 검증 및 백테스트 |
| `market-environment-analysis` | 거시 환경 분석 |
| `options-strategy-advisor` | 리스크 헤징 전략 |
| `uptrend-analyzer` | 추세 강도 확인 |

---

## Key Commands

```bash
# 스코어 계산 (수동)
python signal_scorer.py

# Claude 분석 실행 (수동)
python claude_signal.py

# 패턴 통계 리뷰 + 원칙 업데이트 제안
python evolution/review_trades.py

# 백테스트 (TODO)
# python evolution/backtest.py
```

---

## 주의사항

- `.env` — API 키 포함, 절대 커밋 금지
- `trade_logs/` — 실제 거래 기록, 원칙 진화의 원천 데이터
- `STRATEGY.md` — 항상 최신 버전 유지, 버전 번호와 날짜 필수
