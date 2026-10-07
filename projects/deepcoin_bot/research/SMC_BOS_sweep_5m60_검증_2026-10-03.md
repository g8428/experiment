# SMC 구조·스윕 5분봉 60개 제한 검증 — 2026-10-03

## 조건

최근 완결 5분봉 60개(300분) 안에서만 BOS/ChoCh 구조와 스윙·sweep/reclaim 이벤트를 탐색했다. 15분봉 OB/FVG/OTE, HTF 필터, 진입·청산은 유지했다. BTC 2년 결과는 거래당 가격 손절 리스크 2%, 편도 수수료 0.06%, 편도 슬리피지 0.02%, 일일 제한과 동일한 체결 엔진 기준이다.

## BTC 2년 비교

| 전략 | 기존 15m | 30개 (150분) | 40개 (200분) | 60개 (300분) |
|---|---:|---:|---:|---:|
| 원시 SMC | 522건 / -98.03% | 510건 / -98.00%, PF 0.593 | 516건 / -98.01%, PF 0.637 | 519건 / -98.04%, PF 0.643 |
| OTE | 52건 / -54.16% | 0건 | 0건 | 0건 |
| MTF | 21건 / -12.27% | 14건 / -7.07%, PF 0.715 | 18건 / -5.76%, PF 0.829 | 23건 / -1.17%, PF 0.971 |
| 뉴욕 킬존 | 30건 / -29.04% | 13건 / -6.54%, PF 0.663 | 16건 / -3.14%, PF 0.858 | 22건 / -12.45%, PF 0.622 |

60개 MTF가 전체 BTC 2년 중 세 제한값에서 가장 나은 누적 손익을 보였다. 다만 수익률은 여전히 -1.17%, PF는 0.971, 평균 R은 +0.011로 비용 포함 손익분기점 바로 아래다. 킬존은 60개에서 거래가 늘었지만 전체 손실이 30·40개보다 커졌다. 원시 SMC는 창을 바꿔도 사실상 계좌를 소진했고, OTE는 거래가 없었다.

## 후반 1년 교차 심볼

구간을 `--since 2025-10-01`로 별도 실행했다.

| 전략 | BTC | ETH | XRP |
|---|---:|---:|---:|
| MTF + 5m×60 | +5.56% (11건), PF 1.366 | +3.96% (7건), PF 1.462 | -5.04% (2건) |
| 뉴욕 킬존 + 5m×60 | +11.69% (11건), PF 2.145 | -5.91% (11건), PF 0.652 | -9.26% (4건) |

60개 MTF는 후반 BTC·ETH에서 양수였지만 XRP에서는 손실이다. 킬존의 후반 BTC 이익도 ETH·XRP에서 재현되지 않았다. 세 심볼 각각 거래가 적어 샘플 편향 가능성이 높다.

## 판정

**시험한 창 길이 중 MTF에는 60개가 가장 나았지만, 채택할 만한 검증은 아니다.** BTC 2년 성과가 아직 음수이고 XRP 교차 심볼 결과도 마이너스다. 따라서 60개는 연구 후보로만 두고 라이브 기본값은 바꾸지 않는다. 다음 단계는 창 길이를 더 만지는 것보다 시간 순서 워크포워드와 여러 시장 국면·심볼에서 신호 표본을 늘려 재검증하는 것이다.

## 재현 명령

```powershell
python projects/deepcoin_bot/backtest/run_v2.py --sym BTC-USDT-SWAP --strat smc_raw_m5_60,smc_ote_m5_60,smc_mtf_m5_60,smc_kz_m5_60 --quiet
python projects/deepcoin_bot/backtest/run_v2.py --sym BTC-USDT-SWAP --strat smc_mtf_m5_60,smc_kz_m5_60 --since 2025-10-01 --quiet
python projects/deepcoin_bot/backtest/run_v2.py --sym ETH-USDT-SWAP --strat smc_mtf_m5_60,smc_kz_m5_60 --since 2025-10-01 --quiet
python projects/deepcoin_bot/backtest/run_v2.py --sym XRP-USDT-SWAP --strat smc_mtf_m5_60,smc_kz_m5_60 --since 2025-10-01 --quiet
```

60개 변형은 백테스트 전용 `m5_structure_lookback=60` 옵션으로 구현했고 라이브 체인에 추가하지 않았다. 결과는 `research/backtest_v2/*_m5_60*.json`에 저장된다.
