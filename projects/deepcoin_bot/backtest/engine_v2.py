"""
engine_v2.py — 정직한(honest) 백테스트 엔진 (2026-10-01 Opus 점검에서 신규 작성)

기존 engine.py는 라이브보다 낙관적인 숫자를 냈다. 이 엔진이 고친 것:
  1) D1 레짐이 백테스트에서 꺼져 있었음 — engine.py는 D1을 window=50으로 잘랐는데
     get_market_regime()은 55개 미만이면 무조건 "ranging"을 반환한다. 즉 지금까지의 모든
     백테스트에서 "D1 역방향 진입 금지"(P3)가 한 번도 작동하지 않았다. 라이브는 n=120이라 작동.
  2) 미래 데이터 누수(look-ahead) — engine.py는 HTF 캔들을 "시작시각 ≤ 현재"로 슬라이스해서
     아직 안 끝난 1H/1D 캔들의 '최종' 종가를 썼다. 여기서는 "종료시각 ≤ 결정시각"인 캔들만 쓴다.
  3) 수수료·슬리피지 0 → 딥코인 USDT 무기한 taker 0.06% (진입+청산 왕복 0.12%,
     20x면 증거금 기준 2.4%) + 슬리피지를 반영한다. SL 0.3~0.5%짜리 거래에서는 리스크의 25~40%다.
  4) 신호 캔들 종가에 즉시 체결 → 다음 캔들 시가 + 슬리피지로 체결.
  5) 같은 캔들에서 SL/TP 둘 다 닿으면 SL 우선(보수적), 갭으로 SL을 뚫으면 시가 체결.

전략 인터페이스:
    class S:
        name, base_tf ("15m" | "1H" | "5m")
        def prepare(self, data): ...           # 지표 미리 계산 (data: {tf: DataFrame})
        def signal(self, i, ctx) -> dict|None  # i = base 캔들 인덱스(종가 시점 결정)
            {"dir": 1|-1, "sl": float, "tp": float|None,
             "trail_atr": float|None,  # 샹들리에 트레일링 ATR 배수 (None=없음)
             "trail_after_r": float,   # 몇 R 이익 후 트레일링 시작 (기본 1.0)
             "be_after_r": float|None, # 몇 R 이익 후 본절 이동
             "time_stop": int|None,    # base 캔들 수
             "risk_mult": float,       # 리스크 배수 (기본 1.0)
             "tag": str}
"""

import bisect
import json
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

TF_MS = {"5m": 300_000, "15m": 900_000, "1H": 3_600_000, "4H": 14_400_000, "1D": 86_400_000}
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")


# ─────────────────────────────── 데이터 ───────────────────────────────

def load_df(sym, tf, days):
    path = os.path.join(CACHE_DIR, f"{sym}_{tf}_{days}d.json")
    with open(path) as f:
        kl = json.load(f)
    df = pd.DataFrame(kl).drop_duplicates("t").sort_values("t").reset_index(drop=True)
    df["ct"] = df["t"] + TF_MS[tf]          # 종료 시각
    return df


def resample(df, tf_from, tf_to):
    """1H → 4H 같은 UTC 정렬 리샘플. 구성 캔들이 다 모인 버킷만 남긴다."""
    step = TF_MS[tf_to]
    need = step // TF_MS[tf_from]
    g = df.assign(b=(df["t"] // step) * step).groupby("b")
    out = pd.DataFrame({
        "t": g["t"].first().index,
        "o": g["o"].first().values, "h": g["h"].max().values,
        "l": g["l"].min().values, "c": g["c"].last().values, "v": g["v"].sum().values,
        "n": g["t"].count().values,
    })
    out = out[out["n"] == need].drop(columns="n").reset_index(drop=True)
    out["ct"] = out["t"] + step
    return out


# ─────────────────────────────── 지표 ───────────────────────────────

def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def atr(df, n=14):
    pc = df["c"].shift(1)
    tr = pd.concat([df["h"] - df["l"], (df["h"] - pc).abs(), (df["l"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def rsi(s, n=14):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def adx(df, n=14):
    up = df["h"].diff(); dn = -df["l"].diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    a = atr(df, n)
    pdi = 100 * pd.Series(pdm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / a
    mdi = 100 * pd.Series(mdm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / a
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean(), pdi, mdi


def regime_label_d1(d1):
    """리포트용 시장국면 라벨 (전략 판단과 무관, 사후 분류용).
    상승: 종가>EMA50 & EMA20>EMA50 & 30일 수익률>+5%
    하락: 종가<EMA50 & EMA20<EMA50 & 30일 수익률<-5%
    횡보: 그 외"""
    e20, e50 = ema(d1["c"], 20), ema(d1["c"], 50)
    r30 = d1["c"] / d1["c"].shift(30) - 1
    lab = np.where((d1["c"] > e50) & (e20 > e50) & (r30 > 0.05), "상승",
                   np.where((d1["c"] < e50) & (e20 < e50) & (r30 < -0.05), "하락", "횡보"))
    return pd.Series(lab, index=d1.index)


class Ctx:
    """base 캔들 i의 결정 시각(종가 시각)에 '이미 끝난' HTF 캔들 개수를 알려준다."""

    def __init__(self, data, base_tf, lookahead=False):
        self.data = data
        self.base = data[base_tf]
        self._ct = {tf: df["ct"].values for tf, df in data.items()}
        self._t = {tf: df["t"].values for tf, df in data.items()}
        self.base_ct = self.base["ct"].values
        self.base_t = self.base["t"].values
        self.lookahead = lookahead
        self.base_tf_name = base_tf

    def n_closed(self, tf, i):
        """base 캔들 i 종가 시점에 완결된 tf 캔들 개수 (마지막 완결 = n-1).
        lookahead=True는 옛 engine.py의 버그 재현용 — '시작시각 ≤ base 시작시각'인 HTF 캔들을
        (그 캔들의 최종 OHLC째로) 포함한다 = 미래 데이터 누수."""
        if self.lookahead and tf != self.base_tf_name:
            return int(np.searchsorted(self._t[tf], self.base_t[i], side="right"))
        return int(np.searchsorted(self._ct[tf], self.base_ct[i], side="right"))


# ─────────────────────────────── 엔진 ───────────────────────────────

def run(strategy, data, *, initial=1000.0, risk_pct=2.0, max_lev=20.0,
        fee=0.0006, slip=0.0002, daily_limits=None, cooldown_bars=0,
        start_ts=None, end_ts=None, label_series=None, lookahead=False, fill="next_open"):
    """
    risk_pct: 1회 손절 시 잃는 자본 % (수수료 제외 가격 손실 기준) — 라이브 risk_pct와 같은 의미
    max_lev:  명목가 상한 = 자본 × max_lev (라이브 20x)
    fee:      한쪽 체결당 수수료율 (딥코인 taker 0.06%)
    slip:     시장가 체결 슬리피지 (진입, SL, 트레일/타임스탑 청산에 불리하게 적용)
    daily_limits: {"max_losses":3, "max_trades":7, "loss_stop":25, "profit_stop":10} — 라이브 _can_trade
                  거래일 경계는 KST 21:00(=UTC 12:00), 라이브 server.py와 동일
    """
    base = data[strategy.base_tf]
    strategy.prepare(data)
    ctx = Ctx(data, strategy.base_tf, lookahead=lookahead)
    ctx.base_tf_name = strategy.base_tf
    o = base["o"].values; h = base["h"].values; l = base["l"].values; c = base["c"].values
    t = base["t"].values
    N = len(base)
    base_atr = atr(base, 14).values

    equity = initial
    trades = []
    eq_curve = np.full(N, np.nan)
    pos = None
    pending = None
    last_exit_i = -10**9
    day_stat = {}

    lo_i = 0 if start_ts is None else int(np.searchsorted(t, start_ts))
    hi_i = N if end_ts is None else int(np.searchsorted(t, end_ts))

    def trade_day(ts):
        return (ts - 12 * 3_600_000) // 86_400_000   # KST 21:00 경계

    def close_pos(i, px, reason):
        nonlocal equity, pos, last_exit_i
        d = pos["dir"]
        gross = pos["notional"] * (px / pos["entry"] - 1) * d
        fees = pos["notional"] * fee + pos["notional"] * (px / pos["entry"]) * fee
        pnl = gross - fees
        equity += pnl
        pnl += pos["partial_pnl"]          # 분할 청산으로 이미 실현한 손익(equity에는 반영 완료)
        fees += pos["partial_fees"]
        r_mult = pnl / pos["risk_amt0"] if pos["risk_amt0"] else 0
        dk = trade_day(t[i])
        ds = day_stat.setdefault(dk, {"pnl": 0.0, "n": 0, "loss": 0, "start": equity - pnl})
        ds["pnl"] += pnl
        if pnl < 0:
            ds["loss"] += 1
        trades.append({
            "open_t": int(t[pos["i0"]]), "close_t": int(t[i]), "dir": d,
            "entry": pos["entry"], "exit": px, "sl0": pos["sl0"], "tp": pos["tp"],
            "reason": reason, "pnl": pnl, "fees": fees, "r": r_mult,
            "partial": pos["partial_done"],
            "ret_pct": pnl / (equity - pnl) * 100, "tag": pos["tag"],
            "bars": i - pos["i0"] + 1,
            "regime": (label_series[pos["i0"]] if label_series is not None else ""),
        })
        pos = None
        last_exit_i = i

    def partial_check(i):
        """진입가 + partial_r×R 지정가에 닿으면 partial_frac만큼 익절(수수료 반영, 슬리피지 없음).
        SL 우선 규칙 때문에 같은 캔들에서 SL과 동시에 닿으면 부분익절은 일어나지 않는다."""
        nonlocal equity
        if pos["partial_r"] is None or pos["partial_done"]:
            return
        d = pos["dir"]
        lvl = pos["entry"] + d * pos["partial_r"] * pos["R"]
        if (d == 1 and h[i] >= lvl) or (d == -1 and l[i] <= lvl):
            px = max(o[i], lvl) if d == 1 else min(o[i], lvl)
            part = pos["notional"] * pos["partial_frac"]
            gross = part * (px / pos["entry"] - 1) * d
            fees = part * fee + part * (px / pos["entry"]) * fee
            equity += gross - fees
            pos["partial_pnl"] += gross - fees
            pos["partial_fees"] += fees
            pos["notional"] -= part
            pos["partial_done"] = True
            if pos["partial_be"]:
                be = pos["entry"] * (1 + 2 * fee * d)
                pos["sl"] = max(pos["sl"], be) if d == 1 else min(pos["sl"], be)

    for i in range(max(lo_i, 1), hi_i):
        # ── 1) 대기 주문 체결: 직전 캔들 종가에서 낸 신호 → 이번 캔들 시가 ──
        if pending is not None and pos is None:
            s = pending; pending = None
            d = s["dir"]
            entry = (o[i] if fill == "next_open" else c[i - 1]) * (1 + slip * d)
            # 손절은 '신호 시점 종가 대비 거리'를 유지한다 (라이브 server.py도 현재가×(1±거리)로 SL을 건다).
            # 절대가격을 그대로 쓰면 데이터 공백·갭 뒤 체결 시 손절폭이 0.1%로 쪼그라들어
            # 포지션이 20배로 커지는 엣지케이스가 생긴다 (BTC 2024-03-05 12시간 공백에서 실제 발생).
            ref = c[i - 1]
            intended = max((ref - s["sl"]) / ref * d, 0.0)
            sl = entry * (1 - intended * d)
            stop_dist = intended
            if t[i] - t[i - 1] > 4 * TF_MS[strategy.base_tf]:   # 데이터 공백 직후 체결 금지
                stop_dist = 0
            if s.get("tp") is not None:
                s["tp"] = entry + (s["tp"] - ref)
            if stop_dist > 0.0005:
                risk_amt = equity * risk_pct / 100 * s.get("risk_mult", 1.0)
                notional = min(risk_amt / stop_dist, equity * max_lev)
                pos = {"dir": d, "entry": entry, "sl": sl, "sl0": sl, "tp": s.get("tp"),
                       "notional": notional, "risk_amt": notional * stop_dist,
                       "i0": i, "best": entry, "tag": s.get("tag", strategy.name),
                       "trail_atr": s.get("trail_atr"), "trail_dist": s.get("trail_dist"),
                       "trail_after_r": s.get("trail_after_r", 1.0),
                       "be_after_r": s.get("be_after_r"), "time_stop": s.get("time_stop"),
                       "R": entry * stop_dist,
                       "partial_r": s.get("partial_r"), "partial_frac": s.get("partial_frac", 0.5),
                       "partial_be": s.get("partial_be", False),
                       "partial_done": False, "partial_pnl": 0.0, "partial_fees": 0.0,
                       "risk_amt0": notional * stop_dist}
                dk = trade_day(t[i])
                day_stat.setdefault(dk, {"pnl": 0.0, "n": 0, "loss": 0, "start": equity})["n"] += 1

        # ── 2) 보유 포지션 청산 체크 (SL 우선, 갭은 시가) ──
        if pos is not None:
            d = pos["dir"]
            sl, tp = pos["sl"], pos["tp"]
            if d == 1:
                if l[i] <= sl:
                    close_pos(i, min(o[i], sl) * (1 - slip), "SL" if sl == pos["sl0"] else "TRAIL")
                elif tp is not None and h[i] >= tp:
                    close_pos(i, max(o[i], tp), "TP")
                else:
                    partial_check(i)
            else:
                if h[i] >= sl:
                    close_pos(i, max(o[i], sl) * (1 + slip), "SL" if sl == pos["sl0"] else "TRAIL")
                elif tp is not None and l[i] <= tp:
                    close_pos(i, min(o[i], tp), "TP")
                else:
                    partial_check(i)

        # ── 3) 종가 기준 트레일링/본절/타임스탑 갱신 ──
        if pos is not None:
            d = pos["dir"]
            pos["best"] = max(pos["best"], h[i]) if d == 1 else min(pos["best"], l[i])
            gain_r = (pos["best"] - pos["entry"]) * d / pos["R"]
            if pos["be_after_r"] is not None and gain_r >= pos["be_after_r"]:
                be = pos["entry"] * (1 + 2 * fee * d)
                pos["sl"] = max(pos["sl"], be) if d == 1 else min(pos["sl"], be)
            if (pos["trail_atr"] or pos["trail_dist"]) and gain_r >= pos["trail_after_r"]:
                dist = pos["trail_dist"] or pos["trail_atr"] * base_atr[i]
                ch = pos["best"] - d * dist
                pos["sl"] = max(pos["sl"], ch) if d == 1 else min(pos["sl"], ch)
            if pos["time_stop"] and i - pos["i0"] + 1 >= pos["time_stop"]:
                close_pos(i, c[i] * (1 - slip * d), "TIME")

        # ── 4) 신규 신호 (종가 결정 → 다음 캔들 시가 체결) ──
        if pos is None and pending is None and i < hi_i - 1 and i - last_exit_i > cooldown_bars:
            allowed = True
            if daily_limits:
                ds = day_stat.get(trade_day(t[i]))
                if ds:
                    if (ds["loss"] >= daily_limits.get("max_losses", 99)
                            or ds["n"] >= daily_limits.get("max_trades", 99)
                            or ds["pnl"] <= -ds["start"] * daily_limits.get("loss_stop", 1e9) / 100
                            or ds["pnl"] >= ds["start"] * daily_limits.get("profit_stop", 1e9) / 100):
                        allowed = False
            if allowed:
                s = strategy.signal(i, ctx)
                if s:
                    pending = s

        # ── 5) 시가평가 자본 ──
        if pos is not None:
            unreal = pos["notional"] * (c[i] / pos["entry"] - 1) * pos["dir"]
            eq_curve[i] = equity + unreal
        else:
            eq_curve[i] = equity
        if equity <= initial * 0.02:   # 사실상 파산
            break

    if pos is not None:
        close_pos(min(i, N - 1), c[min(i, N - 1)], "END")
        eq_curve[min(i, N - 1)] = equity

    return {"trades": trades, "equity": eq_curve[lo_i:hi_i], "final": equity, "initial": initial,
            "t": t[lo_i:hi_i]}


# ─────────────────────────────── 지표 요약 ───────────────────────────────

def summarize(res, label=""):
    tr = res["trades"]
    eq = res["equity"]
    eq = eq[~np.isnan(eq)]
    n = len(tr)
    out = {"label": label, "trades": n}
    if len(eq):
        peak = np.maximum.accumulate(eq)
        out["mdd_pct"] = round(float(((peak - eq) / peak).max() * 100), 2)
    else:
        out["mdd_pct"] = 0.0
    out["return_pct"] = round((res["final"] / res["initial"] - 1) * 100, 2)
    if n == 0:
        out.update({"win_rate": 0, "pf": 0, "exp_r": 0, "fees_pct": 0, "avg_bars": 0})
        return out
    pnl = np.array([x["pnl"] for x in tr])
    wins = pnl[pnl > 0]; losses = pnl[pnl <= 0]
    out["win_rate"] = round(len(wins) / n * 100, 1)
    out["pf"] = round(float(wins.sum() / -losses.sum()), 3) if losses.sum() < 0 else float("inf")
    out["exp_r"] = round(float(np.mean([x["r"] for x in tr])), 3)
    out["fees_pct"] = round(sum(x["fees"] for x in tr) / res["initial"] * 100, 2)
    out["avg_bars"] = round(float(np.mean([x["bars"] for x in tr])), 1)
    out["longs"] = sum(1 for x in tr if x["dir"] == 1)
    out["shorts"] = n - out["longs"]
    # 국면별
    by = {}
    for x in tr:
        g = by.setdefault(x["regime"] or "-", {"n": 0, "w": 0, "r": 0.0, "pnl": 0.0})
        g["n"] += 1; g["w"] += x["pnl"] > 0; g["r"] += x["r"]; g["pnl"] += x["pnl"]
    out["by_regime"] = {k: {"n": v["n"], "win_rate": round(v["w"] / v["n"] * 100, 1),
                            "sum_r": round(v["r"], 2), "avg_r": round(v["r"] / v["n"], 3)}
                        for k, v in by.items()}
    return out


def label_for_base(data, base_tf):
    """base 캔들마다 '직전 완결 D1' 기준 국면 라벨."""
    d1 = data["1D"]
    lab = regime_label_d1(d1).values
    ctx = Ctx(data, base_tf)
    out = []
    ct = d1["ct"].values
    for i in range(len(data[base_tf])):
        n = int(np.searchsorted(ct, ctx.base_ct[i], side="right"))
        out.append(lab[n - 1] if n > 0 else "-")
    return np.array(out)


def ts(s):
    return int(datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
