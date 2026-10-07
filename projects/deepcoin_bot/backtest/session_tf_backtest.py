"""현재 라이브 단타 체인(OTE→MTF)을 진입 시간봉 1m/5m/15m/1H/4H로 바꿔 돌리고,
신호 시각의 킬존(아시안/런던/뉴욕/킬존외, 서머타임 자동 반영)별로 성과를 나눈다. (2026-10-08)

- 데이터: BTC 1분봉 2년(backtest/cache/BTC-USDT-SWAP_1m/*.csv)에서 5m/15m/1H/4H/1D를 만든다.
- 진입 게이트: server.py 진입 블록(v15)과 동일 — tp2 업그레이드, TP 상한(tp_max_pct·ATR×3),
  SL 하한 max(ATR×1.2, 0.35%)·상한, 상한<하한 스킵, TP 앞 역방향 FVG 절단, 비용 바닥(tp_min_margin), RR 1.2.
  (기존 strategies_v2.LegacyChain은 v15 게이트가 빠져 있어 따로 둔다.)
- 시간봉 역할: 15m 기준이 라이브와 같다(kl=15m, h1=1H, d1=1D, m5=5m).
  다른 기준은 상위·하위를 한 칸씩 옮긴다: 1m(h1=1H, m5 없음) 5m(1H, 1m) 1H(4H, 15m) 4H(1D, 1H).
- 엔진: engine_v2(완결봉, 다음 봉 시가 체결, 손절 우선). 실제 계정 수수료 taker 0.04% + 슬리피지 0.02%.
  리스크 2%/거래, 일 한도 없음(시간대 비교를 왜곡하지 않도록), 쿨다운 15분.
python backtest/session_tf_backtest.py 15m   → research/session_tf/trades_15m.csv
"""
import math
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import engine_v2 as E  # noqa: E402
import strategies_v2 as S  # noqa: E402
from run_v2 import tuning  # noqa: E402
from smc_engine import find_fvg, get_kill_zone  # noqa: E402

E.TF_MS["1m"] = 60_000
OUT = os.path.join(ROOT, "research", "session_tf")
SYM = "BTC-USDT-SWAP"
ROLES = {"1m": ("1H", None), "5m": ("1H", "1m"), "15m": ("1H", "5m"), "1H": ("4H", "15m"), "4H": ("1D", "1H")}
FEE, SLIP = 0.0004, 0.0002


def load_all():
    import glob
    files = sorted(glob.glob(os.path.join(E.CACHE_DIR, f"{SYM}_1m", "*.csv")))
    df = pd.concat([pd.read_csv(f) for f in files]).sort_values("t").drop_duplicates("t").reset_index(drop=True)
    df = df[["t", "o", "h", "l", "c"]].astype({"t": "int64", "o": float, "h": float, "l": float, "c": float})
    df["v"] = 0.0
    df["ct"] = df["t"] + 60_000
    data = {"1m": df}
    for tf in ("5m", "15m", "1H", "4H", "1D"):
        data[tf] = E.resample(df, "1m", tf)
    return data


class ChainTF(S.LegacyChain):
    def __init__(self, base, tu):
        super().__init__(SYM, tu, chain=("OTE", "MTF"), m15_confirm_n=2, name=f"chain_{base}")
        self.base_tf = base
        self.htf, self.ltf = ROLES[base]
        self.tu = tu
        lev = tu.get("leverage", 20)
        self.tp_atr_mult = tu.get("tp_max_atr_mult_by_sym", {}).get(SYM, tu.get("tp_max_atr_mult", 3.0))
        self.sl_mult = tu.get("sl_min_atr_mult_by_sym", {}).get(SYM, tu.get("sl_min_atr_mult", 1.2))
        self.rr_min = tu.get("rr_min", 1.2)
        self.fvg_block = tu.get("tp_fvg_block", True)
        tpm = tu.get("tp_min_margin_by_sym", {}).get(SYM, tu.get("tp_min_margin_pct", 0))
        self.tp_min = tpm / (100.0 * lev) if tpm > 0 else 0.0

    def prepare(self, data):
        need = {self.base_tf, self.htf, "1D"} | ({self.ltf} if self.ltf else set())
        self.k = {tf: S._records(data[tf]) for tf in need}

    def _windows(self, i, ctx):
        kl = self.k[self.base_tf][max(0, i - self.n15 + 1): i + 1]
        nh = ctx.n_closed(self.htf, i); h1 = self.k[self.htf][max(0, nh - self.n1h): nh]
        nd = ctx.n_closed("1D", i); d1 = self.k["1D"][max(0, nd - self.n1d): nd]
        m5 = None
        if self.ltf:
            n5 = ctx.n_closed(self.ltf, i); m5 = self.k[self.ltf][max(0, n5 - self.n5): n5]
        return kl, h1, d1, m5

    def evaluate(self, kl, h1, d1, m5):
        """server.py _run_claude_bot 진입 실행 블록(v15)과 같은 순서·같은 값."""
        if len(kl) < 30:
            return None
        smc, src = None, None
        for name in self.chain:
            try:
                r = self.fns[name](kl, h1, d1, m5, None)
            except Exception:
                continue
            if r.get("signal"):
                smc, src = r, name
                break
        if not smc:
            return None
        sig = smc["signal"]; s_sl = smc.get("sl"); s_tp = smc.get("tp1"); s_tp2 = smc.get("tp2")
        price = kl[-1]["c"]
        atr = S._atr14_list(kl) or price * 0.01
        sl_min = max(atr / price * self.sl_mult, 0.0035)
        tp_atr_cap = (atr / price * self.tp_atr_mult) if self.tp_atr_mult > 0 else 1e9
        if s_tp and s_tp2:
            if sig == "long" and s_tp2 > s_tp and 0 < (s_tp2 - price) / price <= 0.02:
                s_tp = s_tp2
            elif sig == "short" and s_tp2 < s_tp and 0 < (price - s_tp2) / price <= 0.02:
                s_tp = s_tp2
        if s_sl and s_tp:
            if sig == "long":
                tp_d = min((s_tp - price) / price, self.tp_cap, tp_atr_cap) if s_tp > price else atr / price * 2
                raw = (price - s_sl) / price if s_sl < price else atr / price * self.sl_mult
            else:
                tp_d = min((price - s_tp) / price, self.tp_cap, tp_atr_cap) if s_tp < price else atr / price * 2
                raw = (s_sl - price) / price if s_sl > price else atr / price * self.sl_mult
            sl_d = min(max(raw, sl_min), self.sl_cap)
        else:
            tp_d = min(atr / price * 2, self.tp_cap, tp_atr_cap)
            sl_d = min(max(atr / price * self.sl_mult, sl_min), self.sl_cap)
        if self.sl_cap < sl_min:
            return None
        if self.fvg_block:
            try:
                b_fvg, d_fvg = find_fvg(kl)
            except Exception:
                b_fvg, d_fvg = [], []
            raw_tp = price * (1 + tp_d) if sig == "long" else price * (1 - tp_d)
            if sig == "long":
                walls = [f["bot"] for f in d_fvg if price < f["bot"] < raw_tp]
                if walls:
                    tp_d = max((min(walls) * 0.999 - price) / price, 0.0)
            else:
                walls = [f["top"] for f in b_fvg if raw_tp < f["top"] < price]
                if walls:
                    tp_d = max((price - max(walls) * 1.001) / price, 0.0)
        if self.tp_min > 0 and tp_d < self.tp_min:
            return None
        if tp_d < sl_d * self.rr_min:
            return None
        d = 1 if sig == "long" else -1
        return {"dir": d, "sl": price * (1 - sl_d * d), "tp": price * (1 + tp_d * d), "tag": src}

    def signal(self, i, ctx):
        s = self.evaluate(*self._windows(i, ctx))
        if s:
            kz = get_kill_zone(datetime.fromtimestamp(ctx.base_ct[i] / 1000, tz=timezone.utc)) or "off"
            s["tag"] = f"{s['tag']}|{kz}"
        return s


def main(base):
    os.makedirs(OUT, exist_ok=True)
    data = load_all()
    strat = ChainTF(base, tuning())
    cd = math.ceil(900_000 / E.TF_MS[base]) - 1   # 라이브 쿨다운 900초
    res = E.run(strat, data, risk_pct=2.0, max_lev=20.0, fee=FEE, slip=SLIP, cooldown_bars=max(cd, 0))
    tr = pd.DataFrame(res["trades"])
    if len(tr):
        tr[["strat", "session"]] = tr["tag"].str.split("|", expand=True)
        tr["tf"] = base
    tr.to_csv(os.path.join(OUT, f"trades_{base}.csv"), index=False, encoding="utf-8-sig")
    print(base, "거래", len(tr), "최종", round(res["final"], 1))


if __name__ == "__main__":
    main(sys.argv[1])
