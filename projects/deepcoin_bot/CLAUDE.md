# 딥코인봇 (DeepCoin Bot) — CLAUDE.md

## 프로젝트 개요

BTC/ETH/XRP 무기한 선물 자동매매 봇. Deepcoin 거래소 API 기반.
**ICT(Inner Circle Trader) + MTF(5m/15m/1H/D1) + 실거래 승률 기반 자가진화** 통합.

**현재 상태**: 활성 개발 중 / 자가진화 모드 / **실거래 운용 중** (BTC/ETH/XRP)

> **2026-10-03 기준 실거래 구성**: ① 일목균형표 A(일봉 구름 상태, 별도 슬롯 — BTC·XRP 3x/10%, ETH 10x/25%, 롱·숏, 손절 없음) ② 일봉+4H 추세돌파 ③ 기존 단타 체인(tuning.json 설정대로). 서버는 세션과 독립된 프로세스로 실행하고 출력은 `trade_logs/server_stdout.log`. SMC 강의 전략(`smc_btc/`)은 연구용이며 실거래에 연결하지 않았다(백테스트 마이너스).

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
├── index.html             ← 봇 대시보드 하나로 통합 (localhost:5000) — 멀티심볼 탭·전략체인·시장국면 포함
├── tuning.json            ← 파라미터 (60초마다 자동 reload)
├── HANDOVER.md            ← 인수인계서 (용어/결정 이력/삭제된 것)
├── backtest/
│   ├── run.py             ← 백테스트 CLI (--all --days 180 --risk 10 --leverage 20)
│   ├── strategy.py        ← ICT 백테스트 전략 5종 (killzone/ote/breaker/mtf/wonyotti_fade)
│   ├── engine.py          ← 백테스트 엔진 (동적 사이징, 가중치 반영)
│   ├── engine_wonyotti.py, run_wonyotti.py ← 무손절+물타기 스타일 전용 엔진 (미검증 보류)
│   ├── weights.py         ← 패턴 가중치 (실거래+백테스트 누적 학습)
│   └── pattern_weights.json ← 자동 생성 (거래 청산 시 sync)
├── evolution/
│   ├── review_trades.py   ← 패턴 통계 분석 + STRATEGY.md 자동 업데이트
│   └── pattern_stats.json ← 자동 생성
├── ichimoku_cloud_state.py ← 일목 A 규칙 (server.py가 별도 슬롯으로 호출, ICHIMOKU_A_STRATEGY.md)
├── trend_live.py           ← 일봉+4H 추세돌파 실거래 모듈
├── smc_btc/                ← SMC 강의(1~11강) 규칙 구현·MTF 사슬·1분봉 백테스트 (연구용, 실거래 미연결)
│   └── 체크리스트_v2.md · 결과_사슬v2.md · 원인분석 문서
├── research/               ← 워뇨띠 매매기록·분석리포트, smc_youtube/(강의 노트·설계서)
└── trade_logs/daily/      ← 일별 거래 일지 + 패턴 학습 통계
```

캔들 캐시(`backtest/cache/`)는 로컬 전용: 1분봉은 `BTC-USDT-SWAP_1m/YYYY-MM.csv`(2024-10~, `smc_btc/fetch_1m.py`로 이어받기, `core.load_1m()`로 로드, gitignore), 컨텍스트 피클 `ctx_v2_*.pkl`(약 500MB, 커밋 금지).

**2026-09-24**: 별도 대시보드(`dashboard/serve.py`, localhost:8899, `evolution/dashboard_gen.py`)는 정적 파일 서버일 뿐 매매서버와 합칠 이유가 없어서 삭제하고 메인 `index.html`(localhost:5000)에 전부 통합했다. **대시보드를 두 개로 쪼개지 말 것.**

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

진입 순서 (`_run_claude_bot`) — **전략 밖 시그널 필터는 없다** (킬존·D1·1H·RR은 각 전략 함수 안):
1. 일 한도 (`_can_trade`)
2. **멀티전략 체인** (`server._SIGNAL_CHAIN` → `ict_engine.get_*_signal`) — OTE → MTF → 킬존NY → Breaker, 4개 전부 평가 후 우선순위 순 첫 시그널 채택. 같은 함수를 `backtest/strategy.py`가 감싸므로 백테스트 = 라이브 로직
3. 직전 손절 구조 재진입 차단
4. 쿨다운
5. TP 최소(증거금) / RR 2.5 / SL·TP 상한 → 패턴 가중치 → 동적 사이징 → 주문

계약 단위는 `_CONTRACT_SZ`(BTC 0.001 / ETH 0.1 / XRP 0.1, 거래소 instruments 실측)·`_MIN_SZ`(XRP 100)를 따른다 — 틀리면 사이징이 10배 어긋난다.

SL은 구조 레벨을 그대로 안 쓴다. `_SL_MIN = max(ATR×배율, 0.3%)`가 구조 레벨보다 넓으면 그걸로 대체한다 — 배율은 `sl_min_atr_mult`(전역 0.8) / `sl_min_atr_mult_by_sym`(심볼별 오버라이드, XRP 0.4)로 tuning.json에서 조정. SL 상한도 `sl_cap_pct_by_sym`으로 심볼별 오버라이드 가능(XRP 0.8%). 2026-09-26부터 `backtest/engine.py`도 같은 ATR SL 규칙을 쓴다(`run.py`가 tuning.json의 심볼별 값을 자동으로 읽어 넘김) — 이제 SL도 백테스트=라이브다.

패턴 가중치 파일은 두 개로 분리돼 있다: `backtest/pattern_weights.json`(실거래 전용, `get_weight()`/`sync_live_stats()`만 접근 — 라이브 사이징에 직결)과 `backtest/backtest_pattern_weights.json`(백테스트 전용, `update_weights()`). **백테스트를 아무리 돌려도 실거래 파일은 안 바뀐다** — 섞으면 안 됨(2026-09-26에 한 번 섞였던 걸 발견하고 분리함).

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
```

대시보드(전략체인/시장국면/패턴성과)는 별도 서버 없이 `python server.py` 하나로 http://localhost:5000 에서 전부 볼 수 있다.

---

## 주의사항

- `.env` — API 키 포함, 절대 커밋 금지
- `trade_logs/` — 실제 거래 기록, 원칙 진화의 원천 데이터
- `STRATEGY.md` — 자동 업데이트됨. 수동 수정 시 버전/날짜 반드시 기재
- `pattern_weights.json` — 자동 생성, gitignore 대상 아님 (진화 상태 보존)
