# SMC-C 규칙 원장 — 강의 내용에서 새로 구성

SMC-C는 별도 연구 구현이다. 기존 SMC 엔진·전략·백테스트 구현을 import하거나 복사하지 않는다. 규칙 근거는 `research/smc_youtube/notes_02.md`~`notes_11.md`에 기록된 강의 자막 내용이며, 여기서는 강의가 말한 사실과 실행을 위해 추가한 해석을 반드시 구분한다.

## 시장·시간 구조

- 시작 시장: BTC 무기한 선물. 첫 평가 구간은 로컬 BTC 1분봉 자료의 실제 보유 구간을 사용한다.
- 크립토 매핑: 주·일봉은 목표와 큰 방향, 4H·1H는 구조/매매 구역, 15m는 기준 실행, 5m·1m는 세부 진입 확인. 8강의 24시간 시장 권고와 11강의 상위TF 우선 원칙을 따른다.
- 구조는 확정된 봉만 사용한다. HTF 종가·스윙은 봉이 닫힌 뒤 하위TF에 노출한다.
- 세션은 `America/New_York` 현지시간으로 계산해 서머타임을 적용한다. Asian 20:00–24:00, London 02:00–05:00, New York 07:00–10:00, London Close 10:00–12:00. London Close 이후 신규 진입 금지.
- 24시간 일봉 경계는 UTC 00:00로 둔다. 이는 크립토 데이터 정렬을 위한 운용 정의이며, 강의에서 지정한 거래소 규칙은 아니다.

## 공통 원칙

1. 상위TF 바이어스·미탭 목적지를 먼저 정하고 하위TF에서 진입한다. 바이어스 방향이 없으면 진입하지 않는다.
2. 상승은 해당 월·주·일 시가 아래에서만 매수, 하락은 각 시가 위에서만 매도한다. 상위 바이어스 중 반대 방향 셋업은 별도 counter 전략으로만 기록하고 목적지는 가장 가까운 POI로 제한한다.
3. 종가가 구조 레벨을 넘을 때만 BOS/CHoCH 인정. 꼬리만 넘고 종가가 되돌아오면 스윕으로 기록한다.
4. PD 배열은 상위 맥락과 유동성 근거가 있어야 한다. 기본 OB는 연관 FVG가 필요하며, Advanced OB·블록은 각 전용 정의를 따른다.
5. 매수는 구조 레그/레인지 디스카운트, 매도는 프리미엄에서만 허용한다(강의가 균형 0.5를 경계로 설명한 경우).
6. 일반적인 반전형 실행 순서는 `HTF POI → 반대편 유동성 sweep → displacement → MSS/구조 확인 → 새 OB/FVG 리테스트`다. 스윕 자체만으로 즉시 진입하지 않는다.
7. 각 전략은 서로 독립된 시뮬레이션으로 실행한다. 같은 시장 구간에 전략 간 우선순위·공유 포지션을 두지 않는다.

## 진입 모듈 원장

각 행은 별도 전략/실험 ID다. C(Refined OB)와 I(공통 진입 모듈)는 독립 방향 신호라기보다 실행/컨펌 모듈이므로, 기반 setup과 조합한 결과와 단독 비교 결과를 구분한다.

| ID | 강의 타점 | 규칙 요약 | 근거 |
|---|---|---|---|
| A1 | IDM sweep | IDM 꼬리 sweep 후 회복; IDM 아래 남은 미탭 OB/FVG 존재 여부를 별도 strata로 기록 | 3·4·6강 |
| A2 | IDM 바로 아래 첫 OB | IDM 몸통 이탈로 A1 무효 후, 첫 유효 OB/FVG 탭+거부 | 3·4·6강 |
| A3 | Extreme OB | 첫 OB 무효 후 중간 블록을 건너뛰고 CHoCH/HL 바로 앞 마지막 OB 재탭 | 3·6강 |
| B | Order Flow | 추세 레그의 마지막 미탭 반대 풀백 구역 재탭; 구역 내부 OB/FVG 유무도 나눠 기록 | 4강 |
| C | Refined OB | HTF OB 내부의 하위TF FVG 결합 OB로 진입 정밀화; 기반 셋업 ID를 유지해 단독 성과와 혼동하지 않음 | 4·7강 |
| D | Mitigation block | 실패한 HH/LL 돌파 후 깨진 스윙 캔들의 마지막 반대색 블록 재탭; FVG/OB 중첩 필수 | 7강 |
| E | ITH/ITL range | BTC용 상위 구조. 1H ITH/ITL·STH/STL 매핑; 상승 ITL 디스카운트 POI 또는 ITL wick sweep 매수, 하락은 대칭 | 8·11강 |
| F | HTF 3-candle continuation | 4H/일봉 POI에서 확정된 3캔들 형성 후, 확정 전에 하위TF 중첩 PD 배열에서 진입 | 8강 |
| G | Fractal pullback | 일봉 POI → 1H 이상 MSS+displacement → 4H pullback 목적지 지정 → 마지막 하위TF OB 재탭 | 11강 |
| H | PDH/PDL, PWH/PWL sweep | 방향/카운터별로 다음 목표를 분리. sweep 뒤 MSS 후 FVG 결합 OB 재탭 | 5·9강 |
| I | Liquidity → displacement → retest | 동일고저/스윙 유동성 sweep 이후 displacement가 만든 OB/FVG 재탭 | 6·11강 |
| J1 | BOS sweep reversal | BOS 레벨 꼬리 돌파 후 종가 복귀, 반대방향 진입; 종가가 BOS 너머면 포지션 무효 | 5·6강 |
| J2 | CHoCH sweep continuation | CHoCH 레벨 꼬리 sweep 후 복귀; 추세 지속 방향 진입 | 5·6강 |
| K | CHoCH 후 첫 되돌림 | CHoCH에서 바로 추세 반전 추격 금지; 반대방향 첫 가까운 OB를 이용한 counter와 이후 본추세 leg를 구분 | 5강 |
| L | Breaker block | 선행 유동성 sweep → 반대편 유동성 구조 이탈 → sweep된 swing block 재탭 | 7강 |
| M | Reclaimed OB | HTF POI·displacement·MSS 이후, 진입 레그 왼쪽 swing OB들을 순서대로 재탭 | 7강 |
| N | Rejection block | 요구 꼬리 수가 형성된 extreme wick의 MT; 주변 OB/FVG 소진 또는 부재 및 외부 유동성 맥락 필요 | 7강 |
| O | Asian session | 뉴욕 15:30–20:00 구간의 POI/swing liquidity 표시; Asian session sweep/rejection 후 진입 | 10강 |
| P | CBDR | 뉴욕 14:00–20:00 박스; HTF 목적지 남음 + 세션이 Asian 반대 extreme sweep + displacement 후 retest | 10강 |
| Q | OTE | 몸통 기준 깨끗한 leg 또는 세션 range의 0.62–0.79, 하위TF 거부 확인; bias·HTF POI 필요 | 10강 |
| R | Time-cycle spike | 각 TF POI의 1~2회 탭 후 같은 봉 거부, 바로 위 TF 미탭 POI를 향한 진입 | 11강 |
| S1 | STL/STH failure pullback | 상승 bias에서 STL 이탈은 임시 pullback; STL~ITL 목적지에서만 counter, 이미 목적지 탭 후 재신호는 금지 | 11강 |
| S2 | IRL/ERL liquidity sequence | 상위 목적지까지 가는 동안 내부 유동성을 먼저 수집하는 문맥. 단독 entry strategy가 아니라 다른 setup에 붙는 context tag | 5·11강 |

## 강의가 숫자를 주지 않은 부분: 코드화 해석값

다음 값은 강의의 직접 수치가 아니다. 작은 기본값으로 실행 가능하게 만들고, config와 결과표에 항상 노출한다. 성과가 좋은 값으로 사후 선택하지 않는다.

| 항목 | SMC-C 기본 구현값 | 성격 |
|---|---|---|
| Consecutive FVG displacement | 같은 방향의 연속 FVG 2개 이상. leg 안에 최근 완결 5m bar의 평균 range보다 큰 1m range candle 1개 이상이면 별도 확인 태그 | 강의의 “FVG 연속”, “1m 한 캔들이 평소 5m보다 큼”을 최소 규칙화; FVG 개수/평균 lookback은 해석값 |
| Equal highs/lows | 데이터의 최소 호가 단위(tick) 안에서 같은 레벨 | “동일”을 가격단위로 표현한 운용 해석; tick은 instrument metadata에서 읽음 |
| Swing | 유효 3-candle/fractal swing을 확정 이후 사용. ITH/ITL은 양쪽의 유효 swing이 확정되어야 사용 | 강의가 허용한 객관 구조 정의; 인사이드바 묶음 처리 규칙은 이벤트 보존 테스트로 확인 |
| Setup lifetime | 지정 숫자 만료 없음. zone invalidation, 더 깊은 liquidity 갱신, 목적지 도달, 새 상위TF 방향/목표 생성 중 해당 setup의 강의상 무효 조건 발생 시 종료 | 임의 `window`를 만들지 않음 |
| Structural stop buffer | 해당 시장의 최소 tick 1개를 구조 level 밖에 둠 | “조금 너머”의 최소 실행 단위 해석 |
| Partial exit | 첫 유동성에서 50% 청산, SL 본절; 다음 유동성에서 나머지 관리 | 강의는 “부분”만 명시한 경우가 있어 50%는 테스트 기본 가정이며 25/50/75% 민감도 표에 병기 |
| Same-candle stop and target | stop 우선 | 강의 규칙 아님; OHLC만으로 순서를 모를 때 손실을 과소평가하지 않기 위한 simulator convention |
| Day/session boundary | UTC 일봉, `America/New_York` 세션과 DST | 24/7 BTC에 적용하기 위한 데이터/시간대 정의 |
| Costs | 실행 config에서 fee/slippage를 명시. gross 및 net을 함께 저장; fee 입력을 숨기지 않음 | 강의 외 백테스트 가정; 결과 해석에 반드시 표시 |

## 포지션 관리

- 구조 무효: 보호 스윙/OB/POI의 강의상 무효 종가를 사용한다. sweep의 꼬리만으로 구조 무효라고 판정하지 않는다.
- 계획 TP는 전략별 강의 목적지다: 직전/다음 swing, HTF BOS, ERL, 반대편 POI, 또는 세션/CBDR 목표.
- 1차 유동성에서 partial 후 breakeven은 공통 simulator 기능이지만, 강의가 언급하지 않은 전략에 자동으로 강제하지 않는다.
- 레버리지·계좌 수익률은 진입 규칙 연구와 분리한다. 결과 기본 단위는 가격 변화와 R이며 실제 계좌 복리는 계산하지 않는다.

## 기준 자료

- `research/smc_youtube/notes_02.md`~`notes_11.md` — 편별 자막 정독 노트.
- 특히 8강의 BTC/24시간 시장 ITH/ITL 권고와 11강의 주·일 방향 / 4H·1H 구역 / 15m 이하 실행 위계를 SMC-C 구조의 기준으로 삼는다.
- 강사의 승률·성공률 주장은 신호 규칙으로만 다루며, 재현 전에는 기대 승률로 사용하지 않는다.
