# 딥코인봇 인수인계서 (handover.md)

> 처음 이 프로젝트를 접하는 AI/인간 모두를 위한 문서.
> CLAUDE.md는 "지금 뭘 해야 하는가"를 알려주고, HANDOVER.md(이 파일)는 "왜 이렇게 됐는가"를 알려준다.

---

## 1. 도메인 용어 사전

| 용어 | 의미 |
|------|------|
| **ICT** | Inner Circle Trader. 시장 구조 기반 매매 기법 총칭 |
| **SMC** | Smart Money Concept. ICT와 거의 동의어로 사용 |
| **OB** (Order Block) | 기관이 대량 주문을 넣은 캔들 구역. 가격이 재방문하면 반응 |
| **FVG** (Fair Value Gap) | 세 캔들 사이 미충전 공백. 가격이 돌아와 채우는 경향 |
| **BOS** (Break of Structure) | 직전 스윙 고점/저점 돌파. 추세 전환 또는 지속 확인 |
| **ChoCh** (Change of Character) | 추세 전환 시그널. BOS보다 강한 신호 |
| **Kill Zone** | ICT가 정의한 고확률 매매 시간대. 런던(UTC 07~10), 뉴욕(UTC 12~15) |
| **OTE** (Optimal Trade Entry) | 피보나치 0.618~0.786 구간. 눌림목 진입 최적점 |
| **POI** (Point of Interest) | OB 또는 FVG. 가격이 재방문할 때 반응을 기대하는 레벨 |
| **MTF** | Multi TimeFrame. D1→1H→15m→5m 계층적 분석 |
| **D1 Regime** | 일봉 기준 시장 국면. bull/bear/ranging으로 분류. 역방향 진입 차단 |
| **Breaker Block** | 무효화된 OB가 반대 방향 POI로 전환된 레벨 |
| **Sweep** | 유동성 사냥. 직전 고점/저점을 잠깐 넘어서 청산 유발 후 반전 |
| **RR** | Risk/Reward. TP거리 ÷ SL거리. 현재 최소 기준 2.5 |
| **증거금 기준 수익** | 실제 투입 마진 대비 수익률. 가격 기준 × 레버리지로 환산 |

---

## 2. 파일 역할 맵

```
server.py          ← 라이브 봇 서버 (포트 5000). 심볼별 스레드 _run_claude_bot() 이 매매 로직의 전부
ict_engine.py      ← ICT 분석 엔진 (smc_engine 상속). get_ote_signal/get_mtf_signal/get_killzone_signal/
                     get_breaker_signal — 라이브 멀티전략 4종 (backtest/strategy.py 이식)
smc_engine.py      ← SMC 기본 엔진. 스윙/킬존/아시안레인지
tuning.json        ← 봇 파라미터. 서버 워처가 60초마다 reload → 재시작 없이 적용 (active_symbols 포함)
STRATEGY.md        ← 매매 원칙. "코드에 구현된 것만" 적는다. 자가진화 루프가 자동 업데이트
HANDOVER.md        ← 이 파일. 배경지식 및 결정 이력
index.html         ← 봇 대시보드 (server.py가 서빙)
backtest/run.py    ← 백테스트 CLI (--sym, --days, --tp_min, --rr_min 등)
backtest/engine.py ← 백테스트 엔진 (고정 SL/TP 단발거래용)
backtest/strategy.py ← 얇은 래퍼 — 전략 로직 없음, ict_engine의 4개 함수를 TradeSignal로 감싸기만 함
research/          ← 워뇨띠 매매기록 원본데이터·분석리포트 (2026-09-23 확보)
research/wonyotti_engine/ ← 무손절+물타기 스타일 전용 백테스트 엔진 (미검증 보류, 라이브가 import하지 않음)
backtest/weights.py, pattern_weights.json ← 패턴 가중치 (거래 청산 시 자동 갱신)
evolution/review_trades.py  ← 패턴 통계 분석 + STRATEGY.md 자동 업데이트 (KST 21:00 날짜 전환 시 server.py가 실행)
trade_logs/persist.json     ← 거래 로그/일별 통계/심볼별 봇 상태 (재시작 복원용)
trade_logs/daily/*.md       ← 일별 거래 일지
.claude/agents/trade-supervisor.md  ← 거래 품질 감독 에이전트 (Opus 모델)
```

**2026-09-23에 삭제된 것 (git 이력에만 있음)**: `strategies.py`(EMA크로스/BB/아시안 보조전략), `signal_scorer.py`/`claude_signal.py`/`market_reports/`(composite_score 리포트 봇), `daily_review.py`+`run_review.bat`+`register_task.ps1`+`setup_scheduler.bat`(옛 자정 튜너 — Windows 예약작업도 현재 등록 안 됨), `patch_*.py`/`apply_patch.py`/`tmp_*`/`show_*`/`read_*`/`server.py.bak` 등 스크래치. **다시 만들지 말 것.**

---

## 3. 현재 운용 상태 (2026-09-23 기준)

| 항목 | 값 |
|------|-----|
| 모드 | **실거래 (real)** |
| 활성 심볼 | BTC-USDT-SWAP, ETH-USDT-SWAP (tuning.json `active_symbols`). XRP 비활성 |
| 레버리지 | 20x |
| 리스크 | 잔고의 10% / 트레이드 (동적 사이징) |
| TP 범위 | 구조적 레벨 기준. 심볼별 최소 증거금 5%(BTC)/3%(ETH·XRP), 최대 가격 15% |
| 최소 RR | 2.5 (`rr_min`) |
| SL 최대 | 2% (가격 기준) |
| 일 한도 (계좌 전체, 3심볼 합산) | 손실 -25% / 손절 3회 / 거래 7회 / 수익 +10% |
| 킬존 | 전략별 조건 — MTF 런던/뉴욕, 킬존NY 뉴욕만, OTE·Breaker 없음. 전역 게이트 없음 |
| 계약 단위 | BTC 0.001 / ETH 0.1 / XRP 0.1 (거래소 실측, `_CONTRACT_SZ`), XRP 최소 100계약 |
| 서버 포트 | localhost:5000 |

**API 엔드포인트:**
```bash
GET  /api/bots/status                  # 전체 심볼 상태
GET  /api/claude/status?sym=BTC-USDT-SWAP  # 개별 심볼 상태
POST /api/claude/start  {"mode":"real","syms":["BTC-USDT-SWAP",...]}  # 시작
POST /api/claude/stop                  # 중단
```

---

## 4. 주요 결정 이력 (왜 이렇게 됐는가)

### TP/SL 파라미터가 tuning.json에서 관리되는 이유
초기에는 server.py에 `_TP_MIN = 0.012` 등 하드코딩. tuning.json 값이 무시됐음.
2026-09-23에 발견 + 수정. 현재는 모든 TP/SL/RR 파라미터를 tuning.json에서 읽어옴.
tuning.json 워처가 30초마다 reload하므로 서버 재시작 없이 파라미터 변경 가능.

### tp_min_margin_pct를 0으로 둔 이유
레버리지 20x에서 수수료 감안 최소 수익을 TP_MIN으로 표현하려 했음.
그러나 6개월 백테스트 결과, ICT 구조적 TP가 대부분 0.2~1.5% 범위라서
tp_min이 오히려 좋은 셋업을 걸러버림 (BTC: 32건 +44% → 20건 +21%).
수익 품질 필터는 rr_min(RR 2.5)으로만 하는 게 더 효과적임을 확인.

### XRP가 비활성인 이유
ICTMTFStrategy는 D1+1H+15m 삼중 필터를 요구함.
XRP는 변동성이 커서 세 타임프레임 방향이 동시에 맞는 경우가 드물어
6개월 백테스트에서 신호가 2건밖에 안 나옴. ict_mtf 전략 자체가 XRP에 부적합.
XRP 트레이딩이 필요하면 더 낮은 타임프레임 기반 전략(ict_breaker 등)으로 검토 필요.

### 레버리지 20x, 6x가 아닌 이유
초기에 tuning.json에 `"leverage": 6`이 남아있어 실제 20x 설정이 덮어쓰여졌음.
매매 로직은 20x로 계획됐으나 실제 레버리지 설정이 6x로 갔던 버그.
2026-09-23에 수정. tuning.json의 `"leverage": 20`이 최종 기준.

### 딥코인 UI에서 TP/SL이 90%/25%처럼 크게 보이는 이유
딥코인은 TP/SL 수익률을 **증거금(마진) 기준**으로 표시함.
예: 현물 기준 TP 5% × 레버리지 20x = UI에서 100%로 표시.
버그가 아님. 실제 현물 이동폭은 UI 표시 ÷ 20.

### 자가진화 루프
거래 청산 → `sync_live_stats()` → `pattern_weights.json` 즉시 갱신 → 다음 진입 크기에 반영.
매일 KST 21:00 → `review_trades.py` 자동 실행 → `pattern_stats.json` + `STRATEGY.md` 갱신.

### 워뇨띠(BitMEX aoa) 매매기록 기반 전략 — 백테스트 후 기각 (2026-09-23)
재영님이 워뇨띠가 공개한 BitMEX 체결기록(140만건, 2018-03~2021-12, 공식 자료와 대조검증됨)으로 "더 보수적인 버전"을 만들자고 제안. `research/`에 원본 데이터(실거래 1,183건 재구성분, `wonyotti_eps.json`)와 이미 존재하던 정교한 통계 분석 17편(`research/docs/`)을 저장해뒀다.

**분석 자체의 결론(우리가 낸 게 아니라 원 분석가가 이미 검증):**
- 승률 75.6%는 방향 예측이 아니라 **무손절 + 물타기(59~67%가 불리한 쪽 추가) + 1배대 레버리지**가 만든 숫자. 고정 청산지평(1h/4h/24h)으로 재측정하면 방향 엣지는 **51~52%**(랜덤과 구분 불가)
- 원 분석가가 **손절 17종을 전부 백테스트** — 전부 무손절보다 결과가 나쁨. 손절은 꼬리도 못 막고 승자만 먼저 자름
- 유일하게 재현 가능한 규칙: 직전 60분 1%+ 움직임+거래량2배 후 **직전 5분 반대 방향** 진입(역추세 페이드)

이 트리거만 뽑아 `backtest/strategy.py`의 `WonyottiFadeStrategy`(`wonyotti_fade`)로 이식해 우리 표준 SL/TP(ATR기반)·RR≥2.5로 BTC 6개월 백테스트 → **승률 17.6%, 수익률 -95.23%, MDD 96.95%**. 원 분석의 "방향 엣지 없음" 결론이 그대로 재현됨 (오히려 마이너스).

**결론: 라이브 `_SIGNAL_CHAIN`에 추가 안 함.** `wonyotti_fade` 백테스트 코드는 비교/재현용으로 `backtest/strategy.py`에 남겨둠 — **진입 트리거만 뽑아 손절 거는 방식은 재시도하지 말 것** (이미 증명됨, -95%).

**후속: 풀 패키지(무손절+물타기+분할익절)는 별도 엔진으로 재현 → "폐기"까진 아니고 "미검증"으로 보류.**
기존 `backtest/engine.py`는 고정 SL/TP 단발거래 전제라 재사용 불가 → `backtest/engine_wonyotti.py`(포지션이 자랐다 줄어드는 구조, 유지증거금 강제청산 시뮬레이션 포함) + `backtest/run_wonyotti.py` 신규 작성. 원본 규칙(60분1%+거래량2배 역추세 진입 / 동일수량 물타기·간격무규칙 / 손절없음 / 3%씩 분할익절)을 기계화해서 BTC 180일 돌린 결과:

| 레버리지 | 수익률 | MDD | 강제청산 |
|---|---|---|---|
| 1x | +1.12% | 0.74% | 0 |
| 5x | +8.47% | 4.31% | 1 |
| 10x | +16.19% | 10.39% | 1 |
| 20x | +34.66% | 13.56% | 4 |

강제청산이 끼어도 전체 수익률은 플러스 — 진입 트리거만으론 없던 엣지가 "무손절+물타기+분할익절" 패키지 전체론 살아난다는 원본 리포트(손익분기 대비 +12pp, 4년 유의)의 방향과 일치.

**단, "검증됐다"고 보기엔 부족함 — 라이브 후보 아님:**
- 6개월(180일) 단일 구간 백테스트뿐. 그의 최악 구간(2021 Q4, 회복까지 수개월)급 장기 역추세가 이 창에 없었을 수 있음
- 분할익절 기준(`take_step_pct=0.3%`)은 원본에 규칙이 없어(재량) 임의로 정한 근사치 — 민감도 미검증
- 수수료/슬리피지 미반영 (원본 엣지의 70%가 비트멕스 메이커 리베이트인데 이건 캔들종가 체결 가정)
- 여러 기간·자산으로 재검증 + 파라미터 스윕 전까지는 흥미로운 신호일 뿐
- 백테스트가 아무리 좋아도 **포지션 무한 성장(물타기) 구조는 우리 봇(20x 단일 포지션 슬롯, RR고정 SL/TP)과 여전히 양립 불가** — 실거래 전환은 별도 봇 루프 + 별도 자본배분 + 딥코인 수수료 구조 확인이 선행돼야 함 (재영님 판단 대기)

### 백테스트 전략(OTE/MTF/킬존NY/Breaker)이 왜 라이브에 없었다가 생겼나
`backtest/strategy.py`는 `ict_engine.py`의 원재료 함수(find_liquidity_sweep, get_ote, find_breaker_blocks 등)로 4개 전략을 조립한 **연구용 코드**였다. 라이브 `server.py`는 그중 어느 것도 쓰지 않고 `get_ict_signal()`(OB/FVG 기반) 하나만 썼다 — 누구도 이긴 전략을 라이브에 연결하지 않았던 것.
2026-09-23 BTC 6개월 백테스트에서 OTE가 +164.75%로 압도적으로 1위(MTF +20.6%, 킬존NY +25.16%, Breaker -26.53%)인 걸 확인 후, 4개를 전부 `ict_engine.py`에 `get_ict_signal`과 동일한 dict 형태로 반환하는 함수로 이식하고, `server.py`에 우선순위 체인(`_multi_strategy_signal`, OTE→MTF→킬존NY→Breaker)으로 연결했다. 심볼당 포지션 슬롯이 1개뿐이라 동시 보유가 아니라 순차 우선순위로 결정 — 사용자가 직접 이 방식을 선택함 (별도 슬롯 동시보유는 증거금 리스크가 전략 수만큼 곱해져서 기각).
패턴키에 전략명이 접두사로 붙어(`OTE+...`, `MTF+...`) pattern_weights.json/STRATEGY.md 자가진화가 전략별로 따로 집계된다. Breaker는 백테스트 최하위라 우선순위 최후 — 실거래에서도 승률이 낮으면 `enabled_strategies`류 스위치로 빼는 것을 다음 리뷰에서 검토.

### 2026-10-03 일목균형표 A 실거래 연결 (별도 슬롯)
- 코덱스가 만든 `ichimoku_cloud_state.py`는 규칙 계산부뿐이었고 서버에는 연결돼 있지 않았다 → `server.py`에 별도 슬롯으로 연결했다.
- **사용자 결정**: 롱·숏 전환, 3x·증거금 10%(손절 없는 일봉 보유라 저레버리지), BTC·ETH·XRP, 기존 전략과 동시 보유.
- 자세한 동작은 `ICHIMOKU_A_STRATEGY.md`의 '실거래 연결' 절을 볼 것.
- 연결 시점에 세 심볼 모두 일봉 종가가 구름 위였다. 그래서 서버를 실거래로 켜면 즉시 롱 3개가 진입한다.

### 2026-10-01 전략 재검증 (Opus) — 기존 백테스트 숫자는 신뢰하지 말 것
전체 보고서: `research/전략재검증_2026-10-01.md`. 9/22~9/30 실거래 12건 2승10패(계좌 일손익 합 약 -47%)를 계기로 백테스트 엔진부터 다시 점검했다.
- **`backtest/engine.py`의 결함 3개**: ① D1을 50개로 잘라서 `get_market_regime()`(55개 미만이면 ranging)이 항상 꺼짐 → D1 레짐 필터가 백테스트에서 한 번도 작동하지 않음 ② HTF 캔들을 "시작시각 ≤ 현재"로 잘라 미완성 1H/1D의 최종 종가를 사용(미래 누수) ③ 수수료·슬리피지 0. 그래서 "+164%/+206%"는 엔진이 만든 숫자다.
- **정직한 엔진 `backtest/engine_v2.py`** 신규 작성: 완결 봉만 사용, taker 0.06%×2 + 슬리피지, 다음 봉 시가 체결, SL 우선, 갭 시가 체결, 데이터 공백 직후 체결 금지, 신호 시점 손절 거리 유지. CLI `run_v2.py`, 결함별 영향 측정 `ablation_v2.py`, 견고성 그리드 `robust_v2.py`, 국면별 엣지케이스 `edgecase_v2.py`. 2년(15m/5m)·4년(1H/D1) 캔들 캐시를 `backtest/cache/*_{730,800,1460,1600}d.json`에 받아둠(커밋하지 않음).
- **결론**: 현재 15m ICT 체인은 비용 전 +0.06R, 비용 후 -0.34R/거래. BTC 2년 정직 백테스트는 현재 체인 -73%, 4전략 체인은 파산. 원인 1순위는 20x + 좁은 SL(0.3~0.5%)이라 왕복 비용이 리스크의 30~50%라는 점이다. **SL을 좁게 잡는 15m 전략은 비용 구조상 재시도하지 말 것.**
- **살아남은 것**: 큰 타임프레임 추세추종 + 횡보장 휴식 + 리스크 2%. `strategies_v2.RegimeTrend(allow_short=False)` BTC 4년 +61%, MDD 13.7%, 전반·후반 모두 양수, 비용 2배에도 +53%. ETH는 약하고 XRP는 음수.
- **라이브 반영 (2026-10-01 저녁, 재영님 지시)**: `trend_live.py` 신규 + `server.py` 연결 + 대시보드 개편. BTC/ETH/XRP 3종목, 계좌리스크 2%/거래, 롱 전용. `tuning.json`의 `trend`(enabled/symbols/risk_pct/allow_short/liq_mult)로 제어. 서버는 열린 포지션 없음을 확인한 뒤 재시작했고 `/api/claude/start`로 real 3종목 재가동.
  - 신호는 `strategies_v2.RegimeTrend`를 그대로 import (두 벌 금지). 백테스트 대조: 신호 213/213, 무신호 450/450, 청산 188/188 일치.
  - 판단은 1H 봉 마감 직후 1회만(신호 유효 20분). 거래소에는 최초 손절만 걸고, 추적 손절·타임스탑은 봇이 시장가 청산 → **서버가 죽으면 추적 이익 보호가 없어지고 최초 손절만 남는다.** 거래소 SL 수정 API를 찾으면 개선할 것.
  - 레버리지는 거래별: 청산가가 손절폭의 2배 밖(`liq_mult`)이 되도록 `floor(1/(2×손절폭))`, 최대 20x. 20x 고정이면 손절 5%가 청산(≈5%)보다 멀다.
  - 재시작 복원: `persist.json`의 `trend_ctx`(진입가 1% 이내 일치 시)로 추적 손절·레버리지 복원.
  - **기존 OTE→MTF 체인은 `legacy_chain_enabled=true`로 그대로 켜져 있다(리스크 10%).** 정직한 백테스트상 음수라 끄기를 권장 — 재영님 결정 대기. 한 심볼에 포지션 슬롯은 1개라 서로 막는다.
  - XRP는 4년 백테스트 -13%, ETH는 +7%(전반 음수)로 근거가 약한데 재영님 판단으로 포함. 3종목 동시 신호 시 최대 리스크 6%(상관 높음).

### 2026-09-26 실거래/백테스트 가중치 파일 분리 + 오염 제거
"학습·조정 상태 점검해줘"에 답하다가 발견: `backtest/weights.py`의 `update_weights()`(백테스트용)와 `sync_live_stats()`(실거래용)가 **같은 파일**(`backtest/pattern_weights.json`)에 썼다. 이 파일은 `server.py`가 실제 포지션 사이징에 곱하는 가중치(`_wt = get_weight(...)`) 원본이라, 오늘 세션 내내 검증용으로 돌린 백테스트(`--all`을 BTC/ETH/XRP로 여러 번)가 실거래 사이징에 실제로 영향을 주고 있었다(예: `ict_breaker_long_BTC` total=1150 — 실거래 이력에 있을 수 없는 숫자, 명백히 백테스트 누적).

추가로 발견: 라이브 패턴키(`_pat_key`)에 심볼 티커가 없어서 BTC/ETH/XRP가 구조적으로 같은 패턴이면 통계가 섞였다(`sync_live_stats` 호출도 `sym=""`로 고정).

**조치**:
1. `weights.py`: `WEIGHTS_PATH`(실거래, `pattern_weights.json`)와 `BACKTEST_WEIGHTS_PATH`(백테스트 전용, `backtest_pattern_weights.json`) 분리. `update_weights()`는 백테스트 파일에만, `sync_live_stats()`/`get_weight()`는 실거래 파일에만 접근. 격리 확인(백테스트 실행 전후 실거래 파일 해시 동일, 백테스트 파일만 새로 생성됨).
2. `server.py`의 `_pat_key`에 심볼 티커 추가(`...+BTC`/`+ETH`/`+XRP`) — 앞으론 심볼별로 따로 학습됨.
3. `pattern_weights.json`을 `persist.json`의 실제 청산 로그(36건 중 패턴키 있는 청산 16건)만으로 재구성 — 전부 표본<5라 가중치는 전부 1.0(중립)으로 리셋됨. 오염된 원본은 `backtest/pattern_weights.json.contaminated-2026-09-26.bak`에 보관.
4. 겸사겸사 `weights.py`의 파일 입출력에 `encoding="utf-8"` 명시 — 이전엔 없어서 Windows에서 cp949로 잘못 쓰여 다음에 읽을 때 `UnicodeDecodeError` 나던 버그도 같이 고쳐짐.

**앞으로**: 실제 학습량이 아직 적다(패턴당 최대 3건). `MIN_TRADES=5` 채워지기 전까진 전부 가중치 1.0 그대로다 — 이게 정상이고, 억지로 빨리 채우려고 백테스트 결과를 실거래 파일에 넣거나 하지 말 것.

### 2026-09-25 XRP SL 타이트하게 (ATR 최소폭이 구조 레벨을 무시하던 문제)
XRP OTE 롱이 진입 22:47→손절 23:03, 증거금 기준 -18.2%로 청산. 재영님이 "TP/SL 비율이 맞냐" 물어서 역산해보니:
- 구조적 저점(OTE가 스윕한 레벨)은 진입가 대비 **약 0.17%** 거리 — 타이트하고 신뢰도 높은 지점이었음
- 그런데 실제 사용된 SL은 **0.91%** — 5배 넓음. 원인은 `_SL_MIN = max(ATR×0.8, 0.3%)`가 구조 레벨보다 넓으면 무조건 그걸로 교체하는 로직. XRP는 그 시점 ATR이 상대적으로 커서(가격의 ~1.14%) 0.8배해도 0.91%가 나와 구조 레벨을 완전히 덮어씀
- **`backtest/engine.py`는 이 ATR 확장을 아예 안 쓴다** (`sig.sl` 원본 구조 레벨 그대로 청산 시뮬레이션) — 그래서 XRP 백테스트(OTE +20.69%, Breaker +23.85%)는 라이브보다 훨씬 타이트한 SL을 가정한 결과였고, 라이브 SL이 실제로는 그보다 넓게 잡히고 있었음. **이게 백테스트=라이브라고 했던 것의 숨은 예외였음.**

**조치**: SL 상한/ATR배율에 심볼별 오버라이드 추가 (`sl_cap_pct_by_sym`, `sl_min_atr_mult_by_sym`). XRP만 ATR배율 0.8→0.4, 상한 2%→0.8%로 타이트하게. BTC/ETH는 기존값(0.8배, 2%) 그대로. `_claude_cfg`에 두 키 추가하고 `_load_tuning`이 동기화하도록 반영, `_SL_MIN`/ATR폴백 세 곳 전부 심볼별 배율 쓰도록 통일.

**남은 과제**: 이 ATR 확장 로직 자체를 백테스트 엔진에도 반영해서 완전히 일치시킬지는 아직 안 함 — 지금은 "라이브만 심볼별로 타이트하게" 조정한 상태. 다음에 백테스트-라이브 완전 일치가 필요하면 `engine.py`에도 `_SL_MIN` 로직을 넣거나, 반대로 라이브에서 이 확장 로직 자체를 없애는 걸 검토할 것.

### 2026-09-24 밤~25일 자동 재시작(워치독) 추가
재영님이 아침에 "매매로직 돌고있는거 맞아?"로 발견 — 전날 21:59 KST에 real로 시작해놨는데 서버 프로세스는 15시간 내내 살아있었지만(`server.err.log` 완전히 비어 크래시 아님) 매매 루프만 멈춰서 그 사이 딥코인에 체결이 하나도 없었음. 누가/왜 껐는지 로그로는 특정 안 됨(같은 컴퓨터의 다른 세션이 `/api/claude/stop`을 호출했을 가능성).

**대응**: `_bots_want[sym] = {"running": bool, "mode": str, "restarts": [...]}` 로 "의도 상태"를 별도 추적하는 워치독 스레드(`_bot_watchdog`, 20초 주기) 추가.
- `/api/claude/start` 호출 시 `_bots_want[sym]["running"]=True` — 이후 죽으면 같은 모드로 자동 재시작
- `/api/claude/stop` 호출 시 `_bots_want[sym]["running"]=False` — **사용자가 의도적으로 끈 건 건드리지 않음** (재시작 안 함, 테스트로 확인)
- `active_symbols`에서 빠져서 스레드가 정상 종료된 경우도 재시작 안 함 (`sym not in _active_syms_cfg` 체크)
- 30분 안에 5번 넘게 재시작되면 루프 자체 버그로 보고 포기 (무한 재시작 스팸 방지)
- 대시보드 심볼 카드에 "⚠ 죽음 — 자동재시작 대기" / "30분내 자동재시작 N회" 배지로 표시

**한계**: 서버 프로세스 자체가 죽으면(정전, 강제종료 등) 이 워치독도 같이 죽는다 — 매매 루프 스레드 죽음만 잡는다. 서버 프로세스 재시작은 여전히 사람이 해야 하고, 그때 `_bots_want`는 초기화되므로 `/api/claude/start`를 다시 호출해야 한다(기존 안전 원칙 유지 — 서버 재시작 시 포지션 확인 후 수동 재개).

### 2026-09-24 2차 점검 — 백테스트와 라이브를 같은 코드로, 거래소 원장 기준으로
재영님 지적 세 가지에서 출발: ① 전역 킬존 게이트가 OTE/Breaker까지 막는다(백테스트엔 없던 조건), ② 대시보드가 옛 필터(SMC시그널/RSI/BB·EMA)를 그대로 보여준다, ③ 9/23 BTC 매매기록이 딥코인 앱엔 없다.
- **전략 단일 원본**: `ict_engine.py`의 4개 `get_*_signal`이 킬존·D1·1H·RR 조건을 전부 자체 포함하도록 보강(이전엔 MTF/킬존NY 포팅이 일부 조건을 빠뜨리고 라이브 전역 필터가 그걸 메우고 있었음). `backtest/strategy.py`는 그 함수를 감싸는 래퍼로 교체. **전략 로직을 두 벌 두지 말 것.**
- **라이브 전략 밖 필터 전부 제거**: 전역 킬존, RSI, 15m EMA, BB, 5m 확인, 별도 D1 체크. 남은 건 리스크 게이트(일한도/직전SL/쿨다운/RR·TP·SL 한도)뿐. `_ind()`는 ATR만 계산.
- **가짜 청산 기록 버그**: 시뮬 포지션이 persist.json → real 시작 시 이어져 "거래소에 없음 → SL_HIT +0.22%"로 기록됨. real은 이제 항상 거래소 조회로만 포지션 복원, 모드가 다르면 로컬 포지션 폐기. 해당 가짜 항목은 persist에서 제거하고 일별 통계 재계산.
- **계약 단위 실측**: `/deepcoin/market/instruments` 기준 ETH ctVal 0.1(코드 0.01 → 10배 과대 주문), XRP 0.1(코드 1.0 → 10배 과소). XRP minSz 100. 수정 전 XRP 실거래 -3.63 USDT가 이 오류의 증거.
- **실거래 기록의 기준은 거래소 원장**: `/api/fills`(딥코인 orders-history)로 대시보드에 표시. 봇 내부 `_logs`는 "판단 기록"으로 격하.
- **대시보드 전면 재작성**(`index.html`): 심볼 카드·전략 체인 상태(각 전략이 지금 왜 안 되는지)·리스크 게이트·거래소 원장·봇 판단 기록·전략별 성과. 옛 필터 UI/지표 API(`/api/indicators`, `/api/fvg`, `/api/debrief`) 삭제.
- `wonyotti_fade`(기각) 백테스트 코드 삭제, 워뇨띠 전용 엔진은 `research/wonyotti_engine/`로 격리.

### 2026-09-23 코드 전수 점검 — 왜 뼈대를 손봤나
매매 루프는 옛 BTC 단일심볼 봇이고, 그 위에 멀티심볼/20x/tuning.json을 덧붙인 상태였다. 그날 XRP 실거래 사고(-28.6%)를 계기로 전수 점검해 아래를 고쳤다. **같은 실수를 반복하지 않으려면 이 목록을 기억할 것.**
- **XRP TP/SL이 소수 1자리로 반올림**돼 거래소로 나감 (SL 1.5999→1.6, TP→1.7). 심볼별 `_PX_DEC` 도입. 지표(EMA/ATR/BB)도 2자리 반올림이라 XRP는 EMA9==EMA21이 되어 EMA 필터가 무력화됐음 → 6자리.
- **XRP 진입 근거에 BTC/ETH 가격이 섞임**: `_klines()` 기본 심볼이 BTC였고, `_smc_event_log`가 전역 공유였음 → 둘 다 심볼별로 분리.
- **킬존 필터가 진입을 안 막고 메시지만 표시**했음 (실제로 02:42 킬존외 진입 기록). 진입 체인에 넣어 실제 차단.
- **일손실 3%가 트레이드당 리스크 10%와 모순** → 매 손실마다 서킷브레이커. 25% / 손절 3회로 상향. 일별 통계는 계좌 전체(3심볼 합산)이며 실제 투입 증거금 비율로 계산.
- **tuning `active_symbols`가 무시**되어 XRP가 매매됨 → 반영. 포지션 없을 때 목록에서 빼면 스레드 자동 정지.
- `_load_tuning`이 2번 정의되고 `rr_min`/`tp_*`/`sl_cap` 키를 안 읽었음 → 통합.
- `persist.json`이 BTC 상태만 저장 → 심볼별 `bot_states`.
- STRATEGY.md에 코드에 없는 원칙(composite_score, 1H EMA, O'Neil/VCP)이 적혀 있었음 → 삭제. **STRATEGY.md는 코드에 구현된 것만 적는다.**

---

## 4-1. 새 전략 추가/제거하는 법 (수동 — 재영 담당)

자가진화 루프(패턴 가중치, `trade-supervisor`)는 **체인 안의 전략 가중치만** 조정하고 체인 구조 자체는 건드리지 않는다. 새 전략을 조사해서 넣거나 구린 전략을 빼는 건 사람이 코드를 고쳐야 한다.

**추가할 때:**
1. `ict_engine.py`에 `get_{이름}_signal(kl, h1_kl=None, d1_kl=None, m5_kl=None)` 함수 작성 — `get_smc_signal()`과 같은 dict 형태(`signal/sl/tp1/tp2/bos_type/bos_dir/*_count/sweep/reason` 등)로 반환해야 기존 파이프라인(패턴키/이벤트로그/사이징)을 그대로 탄다. `ict_engine.py`의 `_EMPTY_SIGNAL`을 베이스로 `dict(_EMPTY_SIGNAL, ...)` 쓰면 편함.
2. 먼저 `backtest/strategy.py`에 같은 로직으로 `BaseStrategy` 서브클래스를 만들어 `python backtest/run.py --strategy {이름} --sym BTC-USDT-SWAP --days 180 --risk 10 --leverage 20 --rr_min 2.5`로 성과 확인 (백테스트 없이 바로 라이브에 넣지 말 것)
3. 성과가 괜찮으면 `server.py`의 `_SIGNAL_CHAIN`에 `(이름, 함수)` 튜플을 성과 순위에 맞는 위치에 추가
4. `STRATEGY.md` 섹션 4-1 표 + 진화 이력, `HANDOVER.md`(이 파일) 갱신

**뺄 때:**
1. `server.py`의 `_SIGNAL_CHAIN`에서 해당 튜플 삭제 (함수 자체는 `ict_engine.py`에 남겨둬도 무방 — 재평가할 수 있게)
2. `STRATEGY.md` 섹션 4-1 표에서 제거하고 진화 이력에 이유 기록
3. `pattern_weights.json`의 해당 전략 접두사 패턴은 자동으로 더 안 쌓일 뿐 삭제할 필요 없음 (과거 기록 보존)

---

## 5. 에이전트 모델 정책

| 에이전트 | 모델 | 역할 |
|---------|------|------|
| `trade-supervisor` | **Opus** | 거래 품질 감독. 타점/TP/SL 사후 검증 |
| `project-lead` | Sonnet | 작업 조율 및 위임 |
| `engineer` | Sonnet | 코드 구현/버그 수정 |
| `researcher` | Sonnet | 기술/시장 조사 |

---

## 6. 진입 안전 조건

| 조건 | 기준 | 비고 |
|------|------|------|
| RR | 2.5 이상 | TP거리 ÷ SL거리. 미달 시 진입 스킵 |
| D1 레짐 | bull이면 숏 차단, bear이면 롱 차단 | 역방향 진입 전면 금지 |
| 킬존 | 런던(UTC 07~10) / 뉴욕(UTC 12~15) | 그 외 시간대 진입 없음 |

---

## 7. 절대 건드리면 안 되는 것

| 항목 | 이유 |
|------|------|
| `.env` 파일 | API 키 포함. 절대 커밋/노출 금지 |
| `trade_logs/` | 실제 거래 기록. 자가진화 원천 데이터 |
| `pattern_weights.json` | 자동 갱신됨. 수동으로 값 바꾸지 말 것 |
| `tuning.json` `"leverage"` | 20x 고정. 낮추면 포지션 사이징 전체가 어긋남 |
| 실거래 모드에서 서버 재시작 | 열린 포지션은 거래소에서 복원되지만(`[DC복원]`) 진입 컨텍스트(패턴키·증거금비율)는 유실. 재시작 전 포지션 확인 |
| `_PX_DEC` / `_px_round` | 심볼별 주문가 정밀도. `round(x, 1)`로 되돌리면 XRP 사고 재발 |
| `_CONTRACT_SZ` / `_MIN_SZ` | 거래소 instruments 실측값. 추측으로 적으면 사이징 10배 어긋남 (2026-09-24 실제 발생) |
| 전략 밖 시그널 필터 추가 | 백테스트와 라이브가 달라짐. 필터는 `ict_engine.py` 전략 함수 안에 넣고 백테스트 재실행 |
| `_bot_watchdog` 삭제/비활성화 | 매매 루프가 조용히 멈춰도 아무도 모름 (2026-09-24 밤~25일 15시간 무매매 사고 원인) |
| STRATEGY.md에 코드에 없는 원칙 추가 | 다음 세션이 "구현돼 있다"고 오해함. 코드 먼저, 문서는 그 다음 |

---

## 7. 백테스트 요약 (2026-09-23, 6개월, 20x, risk 10%)

| 심볼 | 전략 | 거래수 | 승률 | 손익비 | 6개월 수익률 | 비고 |
|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| BTC | ict_mtf | 32건 | 34.4% | 4.04 | **+44.3%** | 최우수 |
| ETH | ict_mtf | 36건 | 25.0% | 3.87 | **+28.3%** | rr_min 2.5 적용 시 |
| XRP | ict_mtf | 2건 | 0.0% | - | -5.0% | 전략 부적합 |
| BTC | ict_breaker | 215건 | 31.2% | 2.33 | +11.8% | 거래 많지만 낙폭 큼 |
| ETH | ict_breaker | 215건 | 34.0% | 1.96 | +2.7% | 수익 미미 |
