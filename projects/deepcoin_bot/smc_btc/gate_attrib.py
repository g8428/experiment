"""체결 시도 차단 원인 집계 (강의 충실 설정: 킬존 on, 시가 strict, window 3일).
체결 시도마다 처음 걸린 조건을 세고, 게이트에 막힌 경우 어떤 하위 조건이 거짓이었는지 모두 센다.
python gate_attrib.py → gate_attrib.csv
"""
import collections
import os
import pickle
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import strats2 as S  # noqa: E402

CACHE = os.path.join(os.path.dirname(__file__), "..", "backtest", "cache")
LOG = collections.Counter()
CUR = {"name": None, "mode": None}


def comps(c, i, mode):
    return {
        "월 방향≠상승": c["mdir"][i] != 1, "일봉 방향≠상승": c[f"dir_{mode}"][i] != 1,
        "주간바이어스=하락": c["wbias"][i] == -1, "데일리바이어스=하락": c["dbias"][i] == -1,
        "일봉OB 휴식": bool(c["rest_block"][i]), "ATH 규칙": bool(c["atl_block"][i]),
        "4H 반대확정": c["h4_bear"][i] == 1, "4H 3캔들 미확정": c["h4_bull"][i] != 1,
        "1H 구조≠상승": c["h1_state"][i] != 1, "장애물": bool(c["obstacle_block"][i]),
    }


orig = S.Book2._open


def _open(self, i, px, sl, final, market, **kw):
    c, k = self.c, CUR["name"]
    if final is None:
        r = "목표 없음"
    elif px <= sl:
        r = "가격≤손절"
    elif final <= px:
        r = "목표≤진입가"
    elif not self.gate[i]:
        r = "게이트"
        for name, bad in comps(c, i, CUR["mode"]).items():
            if bad:
                LOG[(k, CUR["mode"], "게이트 세부", name)] += 1
    elif self.kz_on and not c["kz"][i]:
        r = "킬존 밖"
    elif px >= c["dopen"][i]:
        r = "일봉 시가 위"
    elif px >= c["wopen"][i] or px >= c["mopen"][i]:
        r = "주·월 시가 위"
    else:
        r = "체결"
    LOG[(k, CUR["mode"], "결과", r)] += 1
    return orig(self, i, px, sl, final, market, **kw)


S.Book2._open = _open

if __name__ == "__main__":
    C = {s: pickle.load(open(os.path.join(CACHE, f"ctx_v2_{s}.pkl"), "rb")) for s in ("long", "short")}
    for name, (fn, uses_w) in S.RUNNERS.items():
        for mode in ("structure", "narrative"):
            CUR.update(name=name, mode=mode)
            for c in C.values():
                fn(c, mode, 3 * 1440, True, "strict")
            print(name, mode, {k[3]: v for k, v in LOG.items() if k[0] == name and k[1] == mode and k[2] == "결과"},
                  flush=True)
    rows = [dict(strat=k[0], mode=k[1], kind=k[2], reason=k[3], count=v) for k, v in LOG.items()]
    pd.DataFrame(rows).to_csv(os.path.join(os.path.dirname(__file__), "gate_attrib.csv"), index=False,
                              encoding="utf-8-sig")
