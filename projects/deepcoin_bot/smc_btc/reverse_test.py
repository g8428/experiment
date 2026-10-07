"""반대매매 검증: SMC 신호가 체결될 때 같은 가격에 반대 방향으로 진입.
익절 = 진입가에서 OB(원래 손절이 걸린 스윕 저점 구역) 쪽으로 거리의 3/4 (= 원래 손절폭의 0.75배)
손절 3안: ① 원래 손절폭과 같은 거리 ② 원래 신호의 1차 익절 지점 ③ 원래 손절폭 1.5배
비용: 진입 taker(시장성), 익절 maker 지정가 / 손절 taker+슬리피지 (R)와 전부 taker(R_t) 두 가지.
컨텍스트 공간(미러 포함)에서 '원래=롱'이므로 반대매매는 항상 숏으로 시뮬레이션하면 된다.
python reverse_test.py → reverse_test.md
"""
import collections
import os
import pickle
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import strats2 as S  # noqa: E402
import strats_b as SB  # noqa: E402

CACHE = os.path.join(os.path.dirname(__file__), "..", "backtest", "cache")
TAKER, MAKER, SLIP = 0.0006, 0.0002, 0.0002
MAXH = 30 * 1440
SIG = []
orig = S.Book2._open


def _open(self, i, px, sl, final, market, **kw):
    ok = orig(self, i, px, sl, final, market, **kw)
    if ok:
        SIG.append(dict(i=i, e=px, sl=sl, L1=kw.get("L1"), fin=final, tag=kw.get("tag"),
                        orig_R=None, book=self))
    return ok


S.Book2._open = _open


def sim_short(c, i, e, tp, slp):
    """숏 진입 e, 익절 tp(<e), 손절 slp(>e). 체결 봉부터 보수적(같은 봉 손절 우선)."""
    h, l, o = c["h"], c["l"], c["o"]
    if h[i] >= slp:
        return slp, "SL"
    end = min(c["n"], i + MAXH)
    hh = h[i + 1:end] >= slp
    ll = l[i + 1:end] <= tp
    a = np.flatnonzero(hh)
    b = np.flatnonzero(ll)
    if not a.size and not b.size:
        return c["c"][end - 1], "TIME"
    if a.size and (not b.size or a[0] <= b[0]):
        j = i + 1 + a[0]
        return max(o[j], slp), "SL"
    j = i + 1 + b[0]
    return min(o[j], tp), "TP"


def evaluate(c, sig, variant):
    e, sl0 = sig["e"], sig["sl"]
    d = e - sl0                       # 원래 손절폭 (OB 구역까지)
    tp = e - 0.75 * d                 # OB 도달 전 3/4 지점
    if variant == "①같은거리":
        slp = e + d
    elif variant == "②원래1차익절":
        if sig["L1"] is None or sig["L1"] <= e:
            return None
        slp = sig["L1"]
    else:
        slp = e + 1.5 * d
    x, why = sim_short(c, sig["i"], e, tp, slp)
    ae = abs(e)
    risk = (slp - e) / ae
    gross = (e - x) / ae
    fee_mk = TAKER + (MAKER if why == "TP" else TAKER + SLIP)
    fee_tk = TAKER + TAKER + (SLIP if why != "TP" else 0)
    return dict(R=(gross - fee_mk) / risk, R_t=(gross - fee_tk) / risk, why=why, risk=risk * 100,
                rr=(e - tp) / (slp - e))


def main():
    C = {s: pickle.load(open(os.path.join(CACHE, f"ctx_v2_{s}.pkl"), "rb")) for s in ("long", "short")}
    runners = {**{f"A:{k}": v[0] for k, v in S.RUNNERS.items()}, **{f"B:{k}": v for k, v in SB.RUNNERS_B.items()}}
    rows, lines = [], []
    for kz in (True, False):
        for name, fn in runners.items():
            sigs = []
            for side, c in C.items():
                SIG.clear()
                fn(c, "structure", 3 * 1440, kz, "strict")
                o_R = [t["R"] for t in (SIG[0]["book"].trades if SIG else [])]
                for s_ in SIG:
                    s_["side"], s_["c"] = side, c
                sigs += list(SIG)
                rows.append(dict(kind="orig", strat=name, kz=kz, side=side, n=len(o_R), R=sum(o_R)))
            for v in ("①같은거리", "②원래1차익절", "③1.5배"):
                res = [evaluate(s_["c"], s_, v) for s_ in sigs]
                res = [r for r in res if r]
                if not res:
                    continue
                R = np.array([r["R"] for r in res])
                Rt = np.array([r["R_t"] for r in res])
                rows.append(dict(kind="rev", strat=name, kz=kz, variant=v, n=len(R), win=np.mean([r["why"] == "TP" for r in res]),
                                 avgR=R.mean(), totR=R.sum(), totR_taker=Rt.sum(), rr=np.median([r["rr"] for r in res]),
                                 risk=np.median([r["risk"] for r in res])))
                print(name, "kz" if kz else "--", v, len(R), f"승률 {rows[-1]['win']:.0%} 거래당 {R.mean():+.3f}R 합 {R.sum():+.1f}R (전부taker {Rt.sum():+.1f})", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(os.path.dirname(__file__), "reverse_test.csv"), index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
