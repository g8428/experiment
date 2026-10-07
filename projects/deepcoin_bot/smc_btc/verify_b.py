"""SMC-B 불변식 검사: 모든 체결 거래가 감지 규칙을 지켰는지 자동 확인."""
import os, pickle, sys, collections
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import strats2 as S
import strats_b as SB
CACHE = os.path.join(os.path.dirname(__file__), "..", "backtest", "cache")
REC = []
orig = S.Book2._open
def _open(self, i, px, sl, final, market, **kw):
    ok = orig(self, i, px, sl, final, market, **kw)
    if ok:
        REC.append(dict(i=i, px=px, sl=sl, fin=final, L1=kw.get("L1"), tag=kw.get("tag"), a=dict(SB.LAST_AUDIT), side=CUR[0]))
    return ok
S.Book2._open = _open
CUR = [None]
fail = collections.Counter(); n = collections.Counter()
for side in ("long", "short"):
    c = pickle.load(open(os.path.join(CACHE, f"ctx_v2_{side}.pkl"), "rb"))
    CUR[0] = side
    B = SB.prep_b(c)
    for name in ("S2-B", "S3d-B", "S3w-B", "S8a-B"):
        REC.clear()
        SB.RUNNERS_B[name](c, "structure", 3 * 1440, False, "daily")
        for r in REC:
            a = r["a"]; n[name] += 1
            chk = {}
            if "rc" not in r["tag"]:
                k = a["sweep_k"]
                lv = a["level"]
                chk["스윕캔들 꼬리<레벨<종가"] = lv is not None and B["l15"][k] < lv < B["c15"][k] or (B["l15"][k] == a["low"] and B["c15"][k] > a["low"])
                chk["보호스윙 = 유의미 15m 스윙 고점"] = a["ph"] is not None and any(p == a["ph"] for p, av, b in B["sh_15m"])
                chk["구조전환 종가>보호스윙"] = a["mss_close"] > a["ph"]
                m = (B["f15_t0"] >= k) & (B["f15_k"] <= a["mss_k"])
                chk["다리 안 15m FVG·진입=최심 FVG"] = m.any() and abs(B["f15_top"][m].min() - a["e"]) < 1e-9
                chk["체결이 구조전환 확정 이후"] = r["i"] >= a["mss_i"]
                chk["체결가≤진입가"] = r["px"] <= a["e"] + 1e-9
                chk["손절<스윕저점"] = r["sl"] < a["low"]
            chk["1차익절≥1R(있으면)"] = r["L1"] is None or r["L1"] - r["px"] >= (r["px"] - r["sl"]) * 0.999 or r["L1"] <= r["px"]
            for kname, ok in chk.items():
                if not ok:
                    fail[(name, kname)] += 1
print("검사 거래 수:", dict(n))
print("위반:", dict(fail) if fail else "없음")
