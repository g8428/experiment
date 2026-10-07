"""강의 핵심 주장 실증 검정 (BTC, 롱 관점 컨텍스트 = 원본 가격).
1) 9강 데일리 바이어스  2) 8강 ITL 보호  3) 4·6·11강 구역 반응(+유동성 앞)  4) 수수료 0일 때 전략 손익
python claims_test.py → 콘솔 + claims_test.md
"""
import os
import pickle
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from core import intermediate  # noqa: E402

CACHE = os.path.join(os.path.dirname(__file__), "..", "backtest", "cache")
out = []


def p(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    out.append(s)


c = pickle.load(open(os.path.join(CACHE, "ctx_v2_long.pkl"), "rb"))
F = c["F"]

# ── 1) 9강 데일리 바이어스 (4년 일봉) ──
D = F["1D"]
h, l, cl = D["h"].values, D["l"].values, D["c"].values
base = (h[2:] > h[1:-1]).mean()
m_sw = (l[1:-1] < l[:-2]) & (cl[1:-1] > l[:-2]) & (h[1:-1] <= h[:-2])   # 전일 저점 스윕 후 위 마감
m_ct = cl[1:-1] > h[:-2]                                                # 전일 고점 위 종가(지속)
nxt_hi = h[2:] > h[1:-1]
p("## 1) 9강 데일리 바이어스 (일봉", len(D), "개)")
p(f"- 무조건 '다음 날 고가 > 오늘 고가' 확률: {base:.1%}")
p(f"- 전일 저점 스윕 후 위 마감 → 다음 날 오늘 고점 돌파: {nxt_hi[m_sw].mean():.1%} (n={m_sw.sum()})")
p(f"- 전일 고점 위 종가 마감 → 다음 날 오늘 고점 돌파: {nxt_hi[m_ct].mean():.1%} (n={m_ct.sum()})")
m_sh = (h[1:-1] > h[:-2]) & (cl[1:-1] < h[:-2]) & (l[1:-1] >= l[:-2])
nxt_lo = l[2:] < l[1:-1]
p(f"- (대칭) 전일 고점 스윕 후 아래 마감 → 다음 날 오늘 저점 이탈: {nxt_lo[m_sh].mean():.1%} (n={m_sh.sum()}), 무조건 {nxt_lo.mean():.1%}")

# ── 2) 8강 ITL 보호: 상승 바이어스에서 확정된 1H ITL이 ITH 돌파 전에 몸통으로 깨지는가 ──
H1 = F["1H"]
hh, ll, cc = H1["h"].values, H1["l"].values, H1["c"].values
sh, sl = c["SW"]["1H"]
ith, itl = intermediate(sh, "H"), intermediate(sl, "L")
ith_c = sorted(ith, key=lambda x: x[2])
end1h = (H1.index + np.timedelta64(1, "h")).values
pos1m = np.searchsorted(c["idx"].values, end1h, "left")


def first_idx(cond_arr, start):
    k = np.flatnonzero(cond_arr[start:])
    return start + k[0] if k.size else None


res = {1: [], -1: [], 0: []}
for (p_l, b, cf) in itl:
    prev = [x for x in ith_c if x[2] <= cf and x[0] > p_l]
    if not prev:
        continue
    tgt = prev[-1][0]
    i1 = min(pos1m[cf], c["n"] - 1)
    tr = c["ddir_structure"][i1]
    tr = int(tr) if not np.isnan(tr) else 0
    s = cf + 1
    if s >= len(cc) - 1:
        continue
    kb = first_idx(cc < p_l, s)
    kt = first_idx(hh >= tgt, s)
    if kb is None and kt is None:
        continue
    res[tr].append(1 if (kb is not None and (kt is None or kb < kt)) else 0)
p("\n## 2) 8강 ITL 보호 (1H ITL이 ITH 돌파 전에 1H 종가로 깨진 비율)")
for k, name in ((1, "일봉 상승 바이어스"), (-1, "일봉 하락 바이어스"), (0, "중립")):
    if res[k]:
        p(f"- {name}: {np.mean(res[k]):.1%} 깨짐 (n={len(res[k])})  ← 강의 주장: 상승 바이어스면 0%에 가까워야 함")

# ── 3) 구역 반응: 첫 탭에서 +2h 도달이 −1h 이탈보다 먼저인가 (h = 진입가-무효선, 무작위 기대 ≈ 33%) ──
hi1, lo1 = c["h"], c["l"]


def reaction(z, maxbars=3 * 1440):
    i = z["touch"]
    e = z["entry"]
    hgt = max(e - z["inv"], e * 0.0005)
    up, dn = e + 2 * hgt, e - hgt
    j = min(c["n"], i + maxbars)
    a = np.flatnonzero(hi1[i:j] >= up)
    b = np.flatnonzero(lo1[i:j] <= dn)
    if not a.size and not b.size:
        return None
    if a.size and (not b.size or a[0] < b[0]):
        return 1
    return 0


p("\n## 3) 구역 첫 탭 반응 (+2h 먼저 = 성공, 무작위 기대 약 33%)")
for tf in ("15m", "1H", "4H", "1D"):
    zs = [z for z in c["Z"][tf] if z["side"] == 1 and 0 <= z["touch"] < min(z["inval"], c["n"]) and z["avail"] < z["touch"]]
    rows = {}
    for z in zs:
        r = reaction(z)
        if r is None:
            continue
        rows.setdefault(("전체",), []).append(r)
        rows.setdefault(("유동성 앞 " + ("있음" if z["liq"] else "없음"),), []).append(r)
        rows.setdefault((z["kind"],), []).append(r)
        g = c["gate_structure"][z["touch"]]
        rows.setdefault(("바이어스 게이트 " + ("통과" if g else "불통과"),), []).append(r)
    p(f"### {tf} (매수 구역 {len(zs)}개)")
    for k, v in sorted(rows.items(), key=lambda kv: -len(kv[1])):
        if len(v) >= 30:
            p(f"- {k[0]}: {np.mean(v):.1%} (n={len(v)})")

# ── 4) 수수료 0일 때 (롱만, structure, 3일, 킬존 on) ──
import strats2 as S  # noqa: E402
p("\n## 4) 비용 분해 (롱 관점만, structure·3일·킬존 on)")
runs = {k: S.RUNNERS[k][0] for k in ("S2", "S3d", "S8a", "S9")}
res4 = {}
for name, fn in runs.items():
    tr = fn(c, "structure", 3 * 1440)
    res4[name] = tr
S.FEE, S.SLIP, S.FEE_MAKER = 0.0, 0.0, 0.0
for name, fn in runs.items():
    tr0 = fn(c, "structure", 3 * 1440)
    r = np.array([t["R"] for t in res4[name]])
    r0 = np.array([t["R"] for t in tr0])
    risk = np.median([t["risk"] for t in tr0]) * 100 if tr0 else float("nan")
    p(f"- {name}: n={len(r0)}  수수료 포함 {r.sum():+.1f}R (거래당 {r.mean() if len(r) else 0:+.2f})  →  수수료 0 {r0.sum():+.1f}R "
      f"(거래당 {r0.mean() if len(r0) else 0:+.2f}), 승률 {np.mean(r0 > 0) if len(r0) else 0:.0%}, 손절폭 중앙 {risk:.2f}%")

open(os.path.join(os.path.dirname(__file__), "claims_test.md"), "w", encoding="utf-8").write("\n".join(out))
