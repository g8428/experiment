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
backtest/engine_wonyotti.py, run_wonyotti.py ← 무손절+물타기+분할익절 스타일 전용 엔진 (미검증 보류중, 위 결정이력 참고)
research/          ← 워뇨띠 매매기록 원본데이터·분석리포트 (2026-09-23 확보)
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
| 킬존 | 런던(16~19 KST)·뉴욕(22~01 KST) 외 진입 금지 (실제 차단) |
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
