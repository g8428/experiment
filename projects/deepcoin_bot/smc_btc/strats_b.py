"""SMC-B: 감지기 개선판 (SMC-A = strats2.py의 1분봉 감지 버전과 비교용).

바뀐 점 (강의 3·5·6·8·10·11강 정의에 맞춤):
  1) 스윙은 15분봉 3캔들 스윙만, 크기(직전·직후 3봉 반대 극값까지 거리) ≥ k × ATR(15m)인 것만 유동성·구조로 인정 [미정의 k]
  2) 스윕 = 15분봉 캔들 마감 시 꼬리는 레벨 너머, 종가는 레벨 안쪽 (3강: 꼬리만 넘으면 스윕, 5·6강 스윕 캔들). 1분봉 요동은 무시
  3) 구조전환 = 15분봉 종가가 스윕 왼쪽 보호 스윙(마지막 유의미 스윙 고점)을 넘음 (3·11강)
  4) displacement 필수 = 스윕~구조전환 다리 안에 15분봉 상승 FVG (6·11강)
  5) 진입 = 그 다리의 가장 깊은 15분봉 FVG 상단, 손절 = 스윕 캔들 꼬리 아래
  6) 1차 익절 = 진입가+1R 이상인 첫 유의미 스윙 고점(15m→1H), 2차 = 그 위 4H 스윙 고점 (10강 '유동성1·2', 1R 미만 잔파동 제외)
게이트·포지션 관리·비용은 SMC-A(strats2)와 동일.
"""
import numpy as np

from chain2 import htf_target
from strats2 import BUF, Book2, alive, deepest, gates, zones_by_avail, zones_by_touch
from core import atr

K_DEFAULT = 1.0
LAST_AUDIT = {}   # 검증용: 마지막으로 확정된 셋업의 스윕·구조전환 정보


def prep_b(c, k=K_DEFAULT):
    """유의미 스윙 목록과 15분봉 배열을 컨텍스트에 붙인다(k별 캐시)."""
    key = f"_b{k}"
    if key in c:
        return c[key]
    out = {}
    for tf in ("15m", "1H", "4H"):
        fr = c["F"][tf]
        h, l = fr["h"].values, fr["l"].values
        a = atr(h, l, fr["c"].values)
        sh, sl = c["SW"][tf]
        av = c["av"][tf]

        def sig_h(b):
            lo = l[max(0, b - 3):b + 4].min()
            return h[b] - lo >= k * a[b]

        def sig_l(b):
            hi = h[max(0, b - 3):b + 4].max()
            return hi - l[b] >= k * a[b]
        out[f"sh_{tf}"] = sorted([(p, av[cf], b) for (p, b, cf) in sh if sig_h(b)], key=lambda x: x[1])
        out[f"sl_{tf}"] = sorted([(p, av[cf], b) for (p, b, cf) in sl if sig_l(b)], key=lambda x: x[1])
        out[f"sh_{tf}_av"] = np.array([x[1] for x in out[f"sh_{tf}"]])
        out[f"sl_{tf}_av"] = np.array([x[1] for x in out[f"sl_{tf}"]])
    F15 = c["F"]["15m"]
    out["h15"], out["l15"], out["c15"] = F15["h"].values, F15["l"].values, F15["c"].values
    f15 = [z for z in c["Z"]["15m"] if z["kind"] == "FVG" and z["side"] == 1]
    out["f15_t0"] = np.array([z["t0"] for z in f15])
    out["f15_k"] = np.array([z["k"] for z in f15])
    out["f15_top"] = np.array([z["hi"] for z in f15])
    out["k15_at"] = np.searchsorted(c["ends"]["15m"], c["idx"].values, side="right") - 1  # 1m→마지막 완결 15m 봉
    c[key] = out
    return out


def recent(B, key, i, n=300):
    """avail<=i 인 유의미 스윙 중 최근 n개 (목록은 avail 순 정렬)."""
    lst = B[key]
    j = np.searchsorted(B[key + "_av"], i, "right")
    return lst[max(0, j - n):j]


def last_below(levels, i, price, before_bar=None):
    """확정(avail<=i)된 유의미 스윙 중 price 아래 가장 가까운 것 (before_bar 이전 봉만)."""
    best = None
    for p, a_, b in reversed(levels):
        if a_ > i:
            continue
        if before_bar is not None and b >= before_bar:
            continue
        if p < price and (best is None or p > best[0]):
            best = (p, b)
            break
    return best


def protected_high(B, i, before_bar):
    """구조전환 기준: 스윕 봉 이전의 마지막 유의미 15분봉 스윙 고점."""
    for p, a_, b in reversed(recent(B, "sh_15m", i, 400)):
        if b < before_bar:
            return p
    return None


def tp_b(B, i, e, sl):
    """1차 = e+1R 이상 첫 유의미 스윙 고점(15m, 없으면 1H), 2차 = 그 위 4H 스윙 고점."""
    R = e - sl
    lvl = []
    for tf in ("15m", "1H"):
        lvl += [p for p, a_, b in recent(B, f"sh_{tf}", i, 400) if p >= e + R]
    L1 = min(lvl) if lvl else None
    L2 = None
    if L1 is not None:
        up = [p for p, a_, b in recent(B, "sh_4H", i, 200) if p > L1]
        L2 = min(up) if up else None
    return L1, L2


def leg_entry_15(B, k_s, k_now):
    """다리(스윕 15m 봉 ~ 현재 15m 봉) 안 15분봉 상승 FVG 중 가장 깊은 상단."""
    m = (B["f15_t0"] >= k_s) & (B["f15_k"] <= k_now)
    return B["f15_top"][m].min() if m.any() else None


def sweep_15(c, B, i, level):
    """i가 15분봉 마감 시점이고 그 봉이 level을 꼬리로 쓸고 위에서 마감했으면 (스윕 저점, 15m 봉 인덱스)."""
    if np.isnan(c["close_15m"][i]):
        return None
    k = B["k15_at"][i]
    if B["l15"][k] < level < B["c15"][k]:
        return B["l15"][k], k
    return None


class Setup:
    """스윕 → 15m 구조전환(+15m FVG) → 가장 깊은 15m FVG 재진입 단계 기계."""

    def __init__(self, low, k_s, i, ph, window):
        self.low, self.k_s, self.i0, self.ph, self.window = low, k_s, i, ph, window
        self.e, self.mb = None, None

    def step(self, c, B, i):
        """반환: None(계속) / 'dead' / 'order'(진입가 확정)."""
        if self.e is None:
            if i - self.i0 > self.window:
                return "dead"
            if c["l"][i] < self.low:
                # 11강: displacement 전 더 깊은 저점 → 더 깊은 유동성을 가져가는 중. 다음 15분봉이 꼬리 스윕 마감하면 스윕 갱신,
                # 몸통으로 깨고 마감하면(스윕 아님) 셋업 소멸
                self.pending_low = True
            cl = c["close_15m"][i]
            if getattr(self, "pending_low", False) and not np.isnan(cl):
                k = B["k15_at"][i]
                if B["c15"][k] > self.low:          # 꼬리만 내려갔다 복귀 → 스윕 저점 갱신
                    self.low, self.k_s = B["l15"][k], k
                    self.ph = protected_high(B, i, k) or self.ph
                    self.pending_low = False
                else:
                    return "dead"
            cl = c["close_15m"][i]
            if self.ph is None and getattr(self, "wait_after", None) is not None:
                for p, a_, b in reversed(recent(B, "sh_15m", i, 50)):
                    if b > self.wait_after:
                        self.ph = p
                        break
                    if b <= self.wait_after:
                        break
            if np.isnan(cl) or self.ph is None:
                return None
            if cl > self.ph:
                e = leg_entry_15(B, self.k_s, B["k15_at"][i])
                if e is None:
                    # 6강: FVG 없는 돌파 = 가짜 레그 → 이후 새로 확정되는 유의미 15m 스윙 고점이 새 기준(그 전까지 대기)
                    self.ph, self.wait_after = None, B["k15_at"][i]
                    return None
                self.e, self.mb = e, i
                self.audit = dict(sweep_k=self.k_s, low=self.low, ph=self.ph, mss_close=cl, mss_k=B["k15_at"][i], e=e,
                                  level=getattr(self, "level", None), mss_i=i)
                LAST_AUDIT.clear()
                LAST_AUDIT.update(self.audit)
                return "order"
            return None
        if i - self.mb > self.window or c["l"][i] < self.low:
            return "dead"
        return None


def run_s3b(c, mode, window, kz_on=True, open_mode="strict", level="D", k=K_DEFAULT):
    """S3-B: 전일(전주) 저점을 15분봉 꼬리로 스윕하고 위에서 마감 → 15m 구조전환+FVG → 재진입. 추세 방향은 TP 전일 고점,
    카운터(하락추세)는 위 첫 미탭 매도 구역까지만(5강)."""
    B = prep_b(c, k)
    G = gates(c, mode)
    bk = Book2(c, G["s3"] | G["counter"], kz_on, open_mode)
    lo_lv = c["pdl"] if level == "D" else c["pwl"]
    hi_lv = c["pdh"] if level == "D" else c["pwh"]
    key = c["idx"].normalize() if level == "D" else (c["idx"] - np.array(c["idx"].dayofweek, dtype="timedelta64[D]")).normalize()
    bear = sorted([z for tf in ("15m", "1H", "4H") for z in c["Z"][tf] if z["side"] == -1 and z["touch"] >= 0],
                  key=lambda z: z["avail"])
    b_av = np.array([z["avail"] for z in bear])
    st, last = None, None
    for i in range(1, c["n"]):
        bk.step(i)
        if bk.pos is not None:
            st = None
            continue
        if st is None:
            kk = key[i]
            if kk == last:
                continue
            sw = sweep_15(c, B, i, lo_lv[i])
            if sw and (G["s3"][i] or G["counter"][i]):
                st = Setup(sw[0], sw[1], i, protected_high(B, i, sw[1]), window)
                st.ctr, st.tp, st.level = not G["s3"][i], hi_lv[i], lo_lv[i]
                last = kk
            continue
        r = st.step(c, B, i)
        if r == "dead":
            st = None
        elif st.e is not None and c["l"][i] <= st.e:
            sl = st.low - BUF * c["atr15m"][i]
            if st.ctr:
                m = np.flatnonzero(b_av <= i)
                ups = [bear[j]["entry"] for j in m[-2000:] if alive(bear[j], i) and bear[j]["entry"] > st.e]
                bk.limit(i, st.e, sl, min(ups) if ups else st.tp, tag=f"S3{level}c-B")
            else:
                L1, L2 = tp_b(B, i, st.e, sl)
                bk.limit(i, st.e, sl, st.tp, L1=L1, L2=L2, tag=f"S3{level}-B")
            st = None
    return bk.trades


def run_s2b(c, mode, window, kz_on=True, open_mode="strict", k=K_DEFAULT):
    """S2-B: 4H·일봉 매수 구역 첫 탭(유동성 앞) → 15분봉이 아래 유의미 15m 스윙 저점을 꼬리 스윕하고 위 마감
    → 15m 구조전환+FVG → 가장 깊은 15m FVG 재진입. 이후 접근 다리 15m 스윙 저점 블록 리클레임 재진입."""
    from strats2 import leg_discount
    B = prep_b(c, k)
    G = gates(c, mode)
    bk = Book2(c, G["rev"], kz_on, open_mode)
    taps = zones_by_touch(c, ["4H", "1D"])
    F15 = c["F"]["15m"]
    st = None
    for i in range(1, c["n"]):
        bk.step(i)
        if st is None:
            if bk.pos is None and G["tap"][i]:
                for z in taps.get(i, []):
                    if z["liq"] and leg_discount(c, z, i):
                        st = dict(z=z, tap=i, setup=None, rc=[], used=set())
                        break
            continue
        z = st["z"]
        if z["inval"] <= i:
            st = None
            continue
        if st["setup"] is None:
            if i - st["tap"] > window:
                st = None
                continue
            if not np.isnan(c["close_15m"][i]):
                k15 = B["k15_at"][i]
                cands = [p for p, a_, b in recent(B, "sl_15m", i, 300) if b < k15 and B["l15"][k15] < p < B["c15"][k15]]
                if cands:   # 유의미 15m 스윙 저점을 꼬리로 쓸고 위에서 마감한 15분봉
                    st["setup"] = Setup(B["l15"][k15], k15, i, protected_high(B, i, k15), window)
                    st["setup"].level = max(cands)
            continue
        s = st["setup"]
        r = s.step(c, B, i)
        if r == "dead":
            st = None
            continue
        if r == "order":
            t_lo = F15.index[max(0, s.k_s - 96)]
            for p, a_, b in recent(B, "sl_15m", i, 400):
                if F15.index[b] >= t_lo and b < s.k_s and p > s.low:
                    st["rc"].append(dict(lo=B["l15"][b], hi=B["h15"][b], on=False))
        if s.e is None or bk.pos is not None:
            continue
        for rr in st["rc"]:
            if not rr["on"] and c["c"][i] > rr["hi"]:
                rr["on"] = True
        if c["l"][i] <= s.e and "main" not in st["used"]:
            st["used"].add("main")
            sl = s.low - BUF * c["atr15m"][i]
            L1, L2 = tp_b(B, i, s.e, sl)
            bk.limit(i, s.e, sl, htf_target(c, i, s.e), L1=L1, L2=L2, tag="S2-B")
            continue
        for rr in sorted(st["rc"], key=lambda r_: -r_["hi"]):
            if rr["on"] and id(rr) not in st["used"] and c["l"][i] <= rr["hi"]:
                st["used"].add(id(rr))
                sl = rr["lo"] - BUF * c["atr15m"][i]
                L1, L2 = tp_b(B, i, rr["hi"], sl)
                bk.limit(i, rr["hi"], sl, htf_target(c, i, rr["hi"]), L1=L1, L2=L2, tag="S2rc-B")
                break
    return bk.trades


def run_s8ab(c, mode, window, kz_on=True, open_mode="strict", k=K_DEFAULT):
    """S8a-B: 뉴욕 15:30~20:00 구간의 15m 매수 구역·구간 저점 → 아시안 킬존(20~24)에서 15분봉이 구간 저점(또는 구역 무효선)을
    꼬리 스윕하고 위 마감 → 15m 구조전환+FVG → 재진입. 카운터는 1차 유동성까지만. 런던 시작 시 지지 없으면 청산."""
    B = prep_b(c, k)
    G = gates(c, mode)
    bk = Book2(c, G["dir"] | G["counter"], kz_on, open_mode)
    nyh, nyd = c["ny_hour"], c["ny_date"]
    z15 = zones_by_avail(c, ["15m"])
    zav = np.array([z["avail"] for z in z15])
    win, st = None, None
    for i in range(1, c["n"]):
        bk.step(i)
        d, hr = nyd[i], nyh[i]
        p_ = bk.pos
        if p_ is not None and p_["tag"].startswith("S8a") and 2 <= hr < 2 + 1 / 60:
            k0 = np.searchsorted(zav, i, "right")
            if not [z15[j] for j in range(max(0, k0 - 200), k0) if z15[j]["t0time"] >= p_["t"] and alive(z15[j], i)]:
                bk.exit_now(i, "LDN")
        if 15.5 <= hr < 20:
            if win is None or win["d"] != d:
                win = dict(d=d, lo=c["l"][i], s=i, zs=None)
            win["lo"] = min(win["lo"], c["l"][i])
        if win is not None and hr >= 20 and win["d"] == d and win["zs"] is None:
            m = np.flatnonzero((zav >= win["s"]) & (zav <= i))
            win["zs"] = [z15[j] for j in m]
        if bk.pos is not None:
            st = None
            continue
        if st is None:
            if win is not None and win["d"] == d and hr >= 20 and win["zs"] is not None and (G["dir"][i] or G["counter"][i]):
                levels = [win["lo"]] + [z["inv"] for z in win["zs"] if alive(z, i)]
                for lv in sorted(levels, reverse=True):
                    sw = sweep_15(c, B, i, lv)
                    if sw:
                        st = Setup(sw[0], sw[1], i, protected_high(B, i, sw[1]), window)
                        st.ctr, st.d, st.level = not G["dir"][i], d, lv
                        break
            continue
        # 10강: 아시안 진입은 그 세션(+런던 지지)까지만 — 주문은 런던 킬존 종료(뉴욕 05시)에 만료
        if st.d != d and hr >= 5:
            st = None
            continue
        r = st.step(c, B, i)
        if r == "dead":
            st = None
        elif st.e is not None and c["l"][i] <= st.e:
            sl = st.low - BUF * c["atr15m"][i]
            L1, L2 = tp_b(B, i, st.e, sl)
            if st.ctr:
                bk.limit(i, st.e, sl, L1, tag="S8a_c-B")
            else:
                fin = None
                if L2 is not None:
                    up = [p for p, a_, b in recent(B, "sh_4H", i, 200) if p > L2]
                    fin = min(up) if up else L2
                bk.limit(i, st.e, sl, fin or L1, L1=L1 if fin else None, L2=L2 if fin and L2 != fin else None, tag="S8a-B")
            st = None
    return bk.trades


RUNNERS_B = {
    "S2-B": run_s2b,
    "S3d-B": lambda *a, **kw: run_s3b(*a, level="D", **kw),
    "S3w-B": lambda *a, **kw: run_s3b(*a, level="W", **kw),
    "S8a-B": run_s8ab,
}
