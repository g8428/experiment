"""탐지 감사: 코드가 잡은 실제 진입 사례를 5분봉 차트로 그려 강의 정의와 눈으로 대조.
python audit_charts.py → audit/*.png
"""
import os
import pickle
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
import strats2 as S  # noqa: E402
import strats_b as SB  # noqa: E402

CACHE = os.path.join(os.path.dirname(__file__), "..", "backtest", "cache")
OUT = os.path.join(os.path.dirname(__file__), "audit")
os.makedirs(OUT, exist_ok=True)
c = pickle.load(open(os.path.join(CACHE, "ctx_v2_long.pkl"), "rb"))
F5 = c["F"]["5m"]

CAP = []
orig = S.Book2._open


def _open(self, i, px, sl, final, market, **kw):
    ok = orig(self, i, px, sl, final, market, **kw)
    if ok:
        CAP.append(dict(i=i, e=px, sl=sl, fin=final, L1=kw.get("L1"), tag=kw.get("tag")))
    return ok


S.Book2._open = _open


def draw(rec, name, extra):
    t = c["idx"][rec["i"]]
    w0, w1 = t - np.timedelta64(10, "h"), t + np.timedelta64(8, "h")
    seg = F5[(F5.index >= w0) & (F5.index <= w1)]
    fig, ax = plt.subplots(figsize=(13, 6))
    x = np.arange(len(seg))
    o, h, l, cl = (seg[k].values for k in "ohlc")
    col = np.where(cl >= o, "#26a69a", "#ef5350")
    ax.vlines(x, l, h, color=col, lw=0.8)
    ax.vlines(x, np.minimum(o, cl), np.maximum(o, cl), color=col, lw=3)
    xi = np.searchsorted(seg.index.values, t.to_datetime64().astype(seg.index.values.dtype))
    ax.axvline(xi, color="k", ls=":", lw=1)
    for y, lab, cc in [(rec["e"], "진입", "blue"), (rec["sl"], "손절", "red"), (rec["fin"], "최종TP", "green"),
                       (rec["L1"], "1차TP", "olive")] + extra:
        if y is not None and not np.isnan(y):
            ax.axhline(y, color=cc, lw=1, ls="--")
            ax.text(len(seg) - 1, y, f" {lab} {y:,.0f}", color=cc, va="center", fontsize=8)
    # 1분봉 스윙(코드가 스윕·MSS 판단에 쓴 것) 중 창 안의 것 표시 → 5분봉 위치로
    ax.set_title(f"{name} {rec['tag']} {t:%Y-%m-%d %H:%M} UTC  (5분봉, 점선=진입 시점)", fontsize=10)
    ax.set_xticks(x[::24])
    ax.set_xticklabels([d.strftime("%m-%d %H:%M") for d in seg.index[::24]], fontsize=7)
    plt.rcParams["font.family"] = "Malgun Gothic"
    fig.tight_layout()
    path = os.path.join(OUT, f"{name}.png")
    fig.savefig(path, dpi=90)
    plt.close(fig)
    return path


plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False
rng = np.random.default_rng(7)
VER = sys.argv[1] if len(sys.argv) > 1 else "A"
if VER == "B":
    for name, tagp in (("S3d-B", "S3D-B"), ("S8a-B", "S8a-B")):
        CAP.clear()
        SB.RUNNERS_B[name](c, "structure", 3 * 1440, False, "daily")
        recs = [r for r in CAP if r["tag"] == tagp] or CAP
        for k, r in enumerate(rng.choice(len(recs), size=min(5, len(recs)), replace=False)):
            rec = recs[r]
            ex = [(c["pdl"][rec["i"]], "전일저점", "purple"), (c["pdh"][rec["i"]], "전일고점", "purple")] if "S3" in name else []
            draw(rec, f"B_{name}_{k}", ex)
        print(name, len(recs))
else:
    CAP.clear()
    S.RUNNERS["S3d"][0](c, "structure", 3 * 1440, False, "daily")
    s3 = [r for r in CAP if r["tag"] == "S3D"] or CAP
    for k, r in enumerate(rng.choice(len(s3), size=min(6, len(s3)), replace=False)):
        rec = s3[r]
        draw(rec, f"S3d_{k}", [(c["pdl"][rec["i"]], "전일저점", "purple"), (c["pdh"][rec["i"]], "전일고점", "purple")])
    CAP.clear()
    S.RUNNERS["S2"][0](c, "structure", 3 * 1440, False, "daily")
    s2 = [r for r in CAP if r["tag"] == "S2"] or CAP
    for k, r in enumerate(rng.choice(len(s2), size=min(4, len(s2)), replace=False)):
        draw(s2[r], f"S2_{k}", [])
    print("S3d", len(s3), "S2", len(s2), "→", sorted(os.listdir(OUT)))
