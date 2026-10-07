# SMC-C

강의 자막 정리(`research/smc_youtube/notes_02.md`~`notes_11.md`)를 규칙 원장과 독립 모듈로 옮긴 BTC 연구용 구현이다. 기존 SMC-A/B 엔진은 import하거나 실행하지 않는다.

## 구성

- `SMC_C_RULEBOOK.md`: 편별 타점 목록, 강의 원칙, 숫자가 빠진 규칙에 둔 기본 해석값
- `data.py`, `structure.py`, `zones.py`, `events.py`: UTC 캔들, 완결 상위봉, 확정 스윙, ITH/ITL, FVG/OB, sweep/displacement
- `bias.py`, `sessions.py`, `blocks.py`, `lifecycle.py`: 방향·세션·블록·셋업 상태 도구
- `setups.py`: 강의 타점별 상태 원장 및 첫 sweep→displacement→FVG 재시험 신호기
- `simulator.py`: 다음 봉부터 limit 체결, 같은 봉 손절/익절 동시 터치 시 손절 우선, 명시적 수수료·슬리피지
- `run_btc.py`: 로컬 BTC 1분봉 캐시 실험 runner
- `selftest.py`: lookahead, 스윙 확정, FVG 가용시점, sweep, 체결 관례의 소형 결정론 검사

## 구현 범위 읽기

`setups.py`의 `SPECS`가 강의 타점의 전체 원장이다. 현재 신호 생성기는 H(PDH/PDL·PWH/PWL), I(동일 고저), J1(확정 스윙 sweep)에서만 주문 후보를 만든다. 이 셋도 강의가 요구하는 HTF 문맥을 완전히 재현한 것이 아니라, sweep→연속 FVG displacement→FVG 재시험을 공통 기계 규칙으로 둔 1차 실험이다. 나머지는 `interpreted`, `context-only`, `deferred` 상태와 이유를 기록했다. 이 상태가 남아 있는 유형은 결과에 신호 전략으로 포함되었다고 보면 안 된다.

각 셋업을 완전 기계화하지 않은 이유는 강의에서 “마지막 미탭 블록”, “강한 충동”, “목표 POI”, “진짜 반전인지 임시 되돌림인지” 등 시각적 구조 판단을 요구하면서 일부는 임계값/선택 순서를 주지 않았기 때문이다. 규칙 원장의 입력/출력과 강의 편 번호를 먼저 확인하고, 모호한 숫자는 연구 설정값으로 분리해야 한다.

## 실행

레포 루트에서:

```powershell
python -m projects.deepcoin_bot.smc_c.selftest
python -m projects.deepcoin_bot.smc_c.run_btc
```

runner는 `backtest/cache/BTC-USDT-SWAP_1m/*.csv`를 읽는다. 거래소 VIP 등급과 실제 주문형태가 확정되기 전까지 `run_btc.py`의 왕복 비용은 편도 수수료 5bp + 편도 슬리피지 2bp라는 stress 가정이다. 결과는 `btc_first_pass_summary.csv`, `btc_first_pass_trades.csv`에 생성된다. 이 기본값을 실제 계정 예상 비용으로 인용하면 안 된다.

## 검증 한계

- 로컬 캐시는 강의 전략 검증에 필요한 5년 이상이 아니라 약 2년 범위다. 이 파일에는 완전한 SMC-C 전체 유형 성과를 주장하지 않는다.
- 1분봉 OHLC만으로 한 봉 안에서 limit 체결 후 손절/목표 순서를 복원할 수 없다. 손절 우선은 보수적 실행 관례다.
- SMC-C는 리서치 코드다. 실계정 자동매매 연결이나 포지션 사이징을 포함하지 않는다.
