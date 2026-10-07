"""
engine_wonyotti.py — 워뇨띠(BitMEX aoa) 실제 매매 규칙 재현 백테스트 엔진.

기존 backtest/engine.py는 "고정 SL/TP 단발 거래"를 전제로 한다. 워뇨띠 스타일은
포지션이 계속 자라났다가(물타기) 조금씩 줄어드는(분할 익절) 구조라 재사용이 안 돼서
별도 엔진으로 만들었다.

research/docs/01_반복_규칙_매매기법.md, 07_종합_리포트.md 에서 통계적으로 검증된
규칙만 기계화했다:
  - 진입 트리거: 직전 60분 1%+ 움직임 + 거래량 2배, 직전 5분 반대방향 (역추세)
  - 물타기: 같은 트리거가 포지션과 같은 방향으로 재발생하면 최초 진입과 "동일 수량"
    추가 (수량비 중앙 1.00). 간격은 규칙 없음(그리드 아님) — 트리거 재발생이 곧 타이밍.
  - 손절: 없음 (MAE 분포에 고정 손절선이 없다고 확정됨)
  - 익절: 포지션의 3%씩 분할 청산이 규칙. "목표치"는 재량이라 정확한 재현이
    불가능 — 여기선 평단 대비 유리한 방향으로 take_step_pct%씩 새 고점을 갱신할 때마다
    3%를 떼어내는 걸로 근사한다 (원본과 다를 수 있는 유일한 큰 근사).
  - 레버리지: 그의 실제 실행처럼 낮게(기본 1x) — 원본엔 없던 안전장치인 강제청산(유지증거금)
    시뮬레이션을 추가했다. 레버리지가 있는 한 반영 안 하면 결과가 비현실적으로 좋게 나온다.

한계: "익절 목표치 재량"의 스텝 근사, 물타기 최대 횟수 상한(원본은 무제한 자금을 전제하지만
실제 자본은 무한하지 않다), BitMEX 메이커 리베이트 구조 미반영(딥코인 수수료로 근사) 등
여러 근사가 들어간다. 정확한 재현이 아니라 "이 스타일이 우리 데이터/레버리지에서
방향성 있게 동작하는가"를 보는 게 목적이다.
"""


def _fade_trigger(kl, m5_kl):
    """60분 1%+ 움직임 + 거래량 2배 + 직전 5분 반대방향. 없으면 None."""
    if len(kl) < 30:
        return None
    window60 = kl[-5:-1]
    if len(window60) < 4:
        return None
    move60 = (window60[-1]["c"] - window60[0]["o"]) / window60[0]["o"]

    vol60 = sum(k["v"] for k in window60) / len(window60)
    base_win = kl[-25:-5]
    if len(base_win) < 10:
        return None
    vol_avg = sum(k["v"] for k in base_win) / len(base_win)
    if vol_avg <= 0 or abs(move60) < 0.01 or vol60 / vol_avg < 2.0:
        return None

    if not m5_kl:
        return None
    last5 = m5_kl[-1]
    if not last5.get("o"):
        return None
    move5 = (last5["c"] - last5["o"]) / last5["o"]
    if move5 == 0:
        return None
    return "short" if move5 > 0 else "long"


def run_wonyotti_backtest(kl_all, m5_all=None, initial_balance=1000.0,
                          leverage=1.0, unit_risk_pct=1.0,
                          take_step_pct=0.3, take_chunk_pct=3.0,
                          max_adds=30, maint_buffer=0.2):
    """
    unit_risk_pct : 최초 진입 크기 — 잔고의 이 %를 증거금으로 잡아 첫 수량(BTC) 결정.
                    물타기도 이 '수량'(BTC)을 그대로 반복 (동일 랏, 마틴게일 아님).
    take_step_pct : 평단 대비 이 %만큼 새로 유리해질 때마다 분할 익절 1회 발동.
    take_chunk_pct: 분할 익절 1회당 '현재 수량'의 몇 %를 청산할지.
    max_adds      : 최대 물타기 횟수 — 원본엔 없는 안전장치(무한 자본 불가하므로).
    maint_buffer  : 유지증거금 버퍼 — 미실현손실이 투입증거금의 (1-maint_buffer)를
                    넘으면 강제청산(원본엔 없는 근사 — 레버리지 리스크를 정직하게 반영하기 위함).

    반환: {"trades":[...], "equity_curve":[...], "summary":{...}}
    trades는 '분할 익절' 또는 '강제청산' 등 개별 청산 이벤트 단위.
    """
    balance = initial_balance
    equity_curve = [balance]
    trades = []
    liquidations = 0
    pos = None  # {"dir","qty","avg","unit_qty","n_adds","take_level","open_idx"}

    import bisect
    m5_ts_list = [k["t"] for k in m5_all] if m5_all else []

    def slice_m5(current_t):
        if not m5_ts_list:
            return None
        idx = bisect.bisect_right(m5_ts_list, current_t) - 1
        if idx < 0:
            return None
        return m5_all[max(0, idx - 3): idx + 1]

    warmup = 30
    for i in range(warmup, len(kl_all)):
        kl_window = kl_all[max(0, i - 40): i + 1]
        current = kl_all[i]
        price = current["c"]
        m5_win = slice_m5(current["t"])
        trig = _fade_trigger(kl_window, m5_win)

        # ── 무포지션: 신규 진입 ──────────────────────────────
        if pos is None:
            if trig:
                unit_qty = balance * (unit_risk_pct / 100.0) * leverage / price
                pos = {"dir": trig, "qty": unit_qty, "avg": price,
                       "unit_qty": unit_qty, "n_adds": 0,
                       "take_level": 0.0, "open_idx": i}
            equity_curve.append(round(balance, 4))
            continue

        d = pos["dir"]
        fav_pct = ((price - pos["avg"]) / pos["avg"] if d == "long"
                   else (pos["avg"] - price) / pos["avg"])

        # ── 강제청산 체크 (유지증거금 근사) ──────────────────
        margin_used = pos["qty"] * pos["avg"] / leverage
        unrealized = pos["qty"] * (price - pos["avg"]) * (1 if d == "long" else -1)
        if unrealized < 0 and -unrealized >= margin_used * (1 - maint_buffer):
            balance -= margin_used   # 투입 증거금 전액 소실 (근사)
            liquidations += 1
            trades.append({
                "action": "LIQUIDATION", "dir": d, "open_idx": pos["open_idx"],
                "close_idx": i, "avg": pos["avg"], "exit": price,
                "qty": pos["qty"], "n_adds": pos["n_adds"], "pnl": round(-margin_used, 4),
            })
            pos = None
            equity_curve.append(round(balance, 4))
            continue

        # ── 분할 익절: 평단 대비 유리한 새 구간(step) 진입마다 발동 ──
        while fav_pct >= pos["take_level"] + take_step_pct / 100.0:
            pos["take_level"] += take_step_pct / 100.0
            take_qty = pos["qty"] * (take_chunk_pct / 100.0)
            if take_qty <= 0:
                break
            realized = take_qty * (price - pos["avg"]) * (1 if d == "long" else -1)
            balance += realized
            pos["qty"] -= take_qty
            trades.append({
                "action": "PARTIAL_TP", "dir": d, "open_idx": pos["open_idx"],
                "close_idx": i, "avg": pos["avg"], "exit": price,
                "qty": take_qty, "pnl": round(realized, 4),
            })
            if pos["qty"] <= pos["unit_qty"] * 0.02:   # 잔량 먼지 수준이면 완전 종료
                balance += pos["qty"] * (price - pos["avg"]) * (1 if d == "long" else -1)
                pos = None
                break

        if pos is None:
            equity_curve.append(round(balance, 4))
            continue

        # ── 물타기: 같은 방향 트리거 재발생 시 동일 수량 추가 ──
        if trig == d and pos["n_adds"] < max_adds:
            add_qty = pos["unit_qty"]
            new_qty = pos["qty"] + add_qty
            pos["avg"] = (pos["avg"] * pos["qty"] + price * add_qty) / new_qty
            pos["qty"] = new_qty
            pos["n_adds"] += 1
            pos["take_level"] = 0.0   # 평단이 바뀌었으니 분할익절 기준 리셋

        unrealized_now = (pos["qty"] * (price - pos["avg"]) * (1 if pos["dir"] == "long" else -1)
                          if pos else 0.0)
        equity_curve.append(round(balance + unrealized_now, 4))

    # 마지막까지 남은 포지션은 마지막 가격으로 청산
    if pos and kl_all:
        last = kl_all[-1]
        realized = pos["qty"] * (last["c"] - pos["avg"]) * (1 if pos["dir"] == "long" else -1)
        balance += realized
        trades.append({
            "action": "FORCE_CLOSE", "dir": pos["dir"], "open_idx": pos["open_idx"],
            "close_idx": len(kl_all) - 1, "avg": pos["avg"], "exit": last["c"],
            "qty": pos["qty"], "pnl": round(realized, 4),
        })
        equity_curve.append(round(balance, 4))

    total_pnl = balance - initial_balance
    peak = initial_balance
    max_dd = 0.0
    for eq in equity_curve:
        peak = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak * 100 if peak > 0 else 100.0)

    wins = sum(1 for t in trades if t["pnl"] > 0)
    losses = sum(1 for t in trades if t["pnl"] <= 0)

    summary = {
        "initial_balance": initial_balance,
        "final_balance": round(balance, 4),
        "total_pnl": round(total_pnl, 4),
        "total_return_pct": round(total_pnl / initial_balance * 100, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "event_count": len(trades),
        "wins": wins, "losses": losses,
        "liquidations": liquidations,
        "leverage": leverage,
    }
    return {"trades": trades, "equity_curve": equity_curve, "summary": summary}
