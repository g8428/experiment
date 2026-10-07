"""[SMC-A] 사슬 v2 위의 전략 전체 (스윕·구조전환을 1분봉 스윙으로 감지하는 버전 — SMC-B는 strats_b.py)
 (롱 로직, 숏은 미러 컨텍스트). 설계서 S1~S9 대응 — 체크리스트_v2.md 참고.

window = 셋업 유효 기간(1m 봉 수, 강의에 수치 없음). 각 전략 docstring에 적용 단계 명시.
"""
import numpy as np

from chain2 import frame_pos_at, htf_target, nearest_level

FEE, SLIP, BUF = 0.0006, 0.0002, 0.1
FEE_MAKER = 0.0002   # [가정] 지정가 체결(진입 지정가·익절) maker 수수료 — R_mk(현실 비용) 계산용
DISP_FVG, DISP_MULT = 2, 2.0        # [미정의] displacement = 다리 안 FVG ≥ 2 & 최대 봉 범위 ≥ 2×ATR20
CBDR_MAX = 0.3                      # [미정의] CBDR 폭 ≤ 일평균 범위(20일) × 0.3
OTE_CLEAN = 0.5                     # [미정의] '깨끗한 레그' = 내부 풀백이 레그 50% 미만
JUDAS_MIN = 0.5                     # [미정의] 세션 시작 후 30분은 OTE 금지(유다 스윙)
ALL_KINDS = ("FVG", "VI", "BPR", "OB", "AOB", "MIT", "BRK", "REJ")


# ── 포지션 관리 ─────────────────────────────────────────────────────
class Book2:
    """한 방향 한 포지션. 10강 관리: 1차 유동성 도달 시 50% 익절 + 손절 본절, 2차 레벨에서 손절을 중간으로, 최종 목표 청산.
    xl: (레벨, TF) — 그 TF 종가가 레벨 아래 마감 시 다음 봉 시가 청산(8강 ITL 몸통 이탈).
    trail: 스윙 저점 목록 — 진입 후 확정된 스윙 저점으로 손절 상향(8강 STL)."""

    def __init__(self, c, gate, kz_on=True, open_mode="strict"):
        self.c, self.gate, self.kz_on, self.open_mode = c, gate, kz_on, open_mode
        self.pos, self.trades = None, []

    def ok(self, i, px):
        c = self.c
        if not self.gate[i]:
            return False
        if self.kz_on and not c["kz"][i]:
            return False
        if px >= c["dopen"][i]:            # 9강 시가 규칙 (상승이면 시가 아래에서만 매수)
            return False
        if self.open_mode == "strict" and (px >= c["wopen"][i] or px >= c["mopen"][i]):
            return False
        return True

    def limit(self, i, entry, sl, final, **kw):
        c = self.c
        if c["l"][i] > entry:
            return False
        px = min(c["o"][i], entry)
        return self._open(i, px, sl, final, market=False, **kw)

    def market(self, i, sl, final, **kw):
        return self._open(i, self.c["o"][i], sl, final, market=True, **kw)

    def _open(self, i, px, sl, final, market, L1=None, L2=None, xl=None, trail=None, tag=""):
        if final is None or px <= sl or final <= px or not self.ok(i, px):
            return False
        L1 = L1 if (L1 is not None and px < L1 < final) else None
        L2 = L2 if (L2 is not None and L1 is not None and L1 < L2 < final) else None
        self.pos = dict(e=px, sl=sl, sl0=sl, L1=L1, L2=L2, fin=final, left=1.0, parts=[], i0=i, xl=xl,
                        trail=trail, jt=None, tag=tag, t=self.c["idx"][i], mk=market, why="")
        if self.c["l"][i] <= sl:
            self._close(sl, 1.0, True, "SL")
        return True

    def step(self, i):
        p, c = self.pos, self.c
        if p is None or i == p["i0"]:
            return
        o, h, l = c["o"][i], c["h"][i], c["l"][i]
        if p["xl"] is not None:
            lvl, tf = p["xl"]
            cl = c[f"close_{tf}"][i]
            if not np.isnan(cl) and cl < lvl:
                self._close(o, p["left"], True, "XL")
                return
        if l <= p["sl"]:
            self._close(min(o, p["sl"]), p["left"], p["sl"] < p["e"], "SL" if p["sl"] < p["e"] else "BE")
            return
        if p["L1"] is not None and p["left"] == 1.0 and h >= p["L1"]:
            p["parts"].append((p["L1"], 0.5, False))
            p["left"], p["sl"] = 0.5, max(p["sl"], p["e"])
        if p["L2"] is not None and h >= p["L2"]:
            p["sl"] = max(p["sl"], (p["e"] + p["L2"]) / 2)
            p["L2"] = None
        if h >= p["fin"]:
            self._close(max(o, p["fin"]), p["left"], False, "TP")
            return
        if p["trail"] is not None:
            tl = p["trail"]
            if p["jt"] is None:
                p["jt"] = int(np.searchsorted([x[1] for x in tl], p["i0"], "right"))
            while p["jt"] < len(tl) and tl[p["jt"]][1] <= i:
                sp = tl[p["jt"]][0] - BUF * c["atr1H"][i]
                if p["sl"] < sp < c["c"][i - 1]:
                    p["sl"] = sp
                p["jt"] += 1

    def exit_now(self, i, why):
        if self.pos is not None and i != self.pos["i0"]:
            self._close(self.c["o"][i], self.pos["left"], True, why)

    def _close(self, px, frac, slip, why):
        p = self.pos
        p["parts"].append((px, frac, slip))
        ae = abs(p["e"])
        risk = (p["e"] - p["sl0"]) / ae
        gross = sum((x - p["e"]) / ae * f for x, f, s in p["parts"])
        # 보수적: 진입·청산 모두 taker + 손절·시장가 슬리피지
        ret = gross - sum((2 * FEE + (SLIP if s else 0)) * f for x, f, s in p["parts"]) - (SLIP if p["mk"] else 0)
        # 현실: 지정가 진입·지정가 익절은 maker, 손절·시장가는 taker+슬리피지
        fin = FEE + SLIP if p["mk"] else FEE_MAKER
        ret_mk = gross - fin - sum(((FEE + SLIP) if s else FEE_MAKER) * f for x, f, s in p["parts"])
        self.trades.append(dict(t=p["t"], tag=p["tag"], R=ret / risk, R_mk=ret_mk / risk, ret=ret,
                                risk=risk, why=why))
        self.pos = None


# ── 공통 도우미 ─────────────────────────────────────────────────────
def gates(c, mode):
    g = c[f"gate_{mode}"]
    return dict(
        dir=g,
        cont=g & (c["h4_bull"] == 1) & (c["h1_state"] == 1) & ~c["obstacle_block"] & (c["h4_bear"] != 1),
        rev=g & (c["h4_bear"] != 1),
        s3=g & ~c["obstacle_block"] & (c["h4_bear"] != 1),
        counter=(c[f"dir_{mode}"] == -1) & ~c["atl_block"] & ~c["rest_block"],
        # 셋업 시작(POI 탭) 시점용: 방향 조건만(휴식 제외). 휴식·킬존·시가는 체결 시점에 Book2가 확인
        tap=((c["mdir"] == 1) & (c[f"dir_{mode}"] == 1) & (c["wbias"] != -1) & (c["dbias"] != -1)
             & ~c["atl_block"] & (c["h4_bear"] != 1)),
    )


def alive(z, i):
    return z["avail"] <= i and z["touch"] >= i and z["inval"] > i


def leg_fvg_entry(c, sb, i):
    """1m 다리 [sb, i] 안 상승 FVG 중 가장 깊은 것(=다리 시작 OB 쪽)의 진입가와 개수."""
    m = (c["fvg1_t0"] >= sb) & (c["fvg1_k"] <= i)
    if not m.any():
        return None, 0
    return c["fvg1_top"][m].min(), int(m.sum())


def displacement(c, sb, i):
    e, nf = leg_fvg_entry(c, sb, i)
    rng = (c["h"][sb:i + 1] - c["l"][sb:i + 1]).max()
    return e if (nf >= DISP_FVG and rng >= DISP_MULT * c["atr1"][sb]) else None


def tp_levels(c, i, entry, t1, t2):
    L1 = nearest_level(c[f"sh_{t1}"], entry, i)
    L2 = nearest_level(c[f"sh_{t2}"], L1, i) if L1 is not None else None
    return L1, L2


def leg_discount(c, z, i):
    """0-2 필터: 구역 TF 다리(구역 형성 전 마지막 스윙 저점 → 이후 최고가)의 50% 아래인가."""
    F = c["F"][z["tf"]]
    sl = c["SW"][z["tf"]][1]
    bars = [b for (p, b, cf) in sl if b <= z["t0"]]
    if not bars:
        return True
    b = bars[-1]
    lo = F["l"].values[b]
    pos = frame_pos_at(c, z["tf"], i)
    hh = F["h"].values[b:pos + 1].max() if pos >= b else F["h"].values[b]
    return z["entry"] <= (lo + hh) / 2


def zones_by_touch(c, tfs, side=1, kinds=ALL_KINDS):
    d = {}
    for tf in tfs:
        for z in c["Z"][tf]:
            if z["side"] == side and z["kind"] in kinds and 0 <= z["touch"] < min(z["inval"], c["n"]):
                d.setdefault(z["touch"], []).append(z)
    return d


def zones_by_avail(c, tfs, side=1, kinds=ALL_KINDS):
    zs = [z for tf in tfs for z in c["Z"][tf] if z["side"] == side and z["kind"] in kinds and z["touch"] >= 0]
    return sorted(zs, key=lambda z: z["avail"])


def deepest(cands, i):
    """9·11강: 풀백에서는 '마지막(가장 깊은)' PD 배열만. 리젝션 블록은 다른 구역이 없을 때만(7강)."""
    live = [z for z in cands if alive(z, i)]
    main = [z for z in live if z["kind"] != "REJ"]
    pool = main if main else live
    return min(pool, key=lambda z: z["entry"]) if pool else None


# ── S1: 1H ITH/ITL 레인지 (8강) ─────────────────────────────────────
def run_s1(c, mode, window, kz_on=True, open_mode="strict"):
    """1H 스윙 저점(=15m ITL, 8강 프랙탈 매핑) → 디스카운트의 가장 깊은 15m PD 배열(유동성 앞 확인)에서 매수.
    POI 없으면 ITL 꼬리 스윕 후 15m 종가 복귀에 진입. SL = ITL 아래, 15m 종가 ITL 이탈 청산, 1H 스윙 저점 트레일.
    TP: 1H 스윙 고점(50%+본절) → 4H 스윙 고점(손절 중간) → ITH. window: 셋업→체결."""
    G = gates(c, mode)
    bk = Book2(c, G["cont"], kz_on, open_mode)
    sl1h, ith = c["sl_1H"], c["ith_1H"]
    z15 = zones_by_avail(c, ["15m"])
    js = jh = jz = 0
    last_ith, st, recent = None, None, []

    def qualifies(z):
        return z["t0time"] >= st["tL"] and z["lo"] > st["L"] and z["entry"] <= st["mid"]
    for i in range(1, c["n"]):
        while jh < len(ith) and ith[jh][1] <= i:
            last_ith = ith[jh]
            jh += 1
        while jz < len(z15) and z15[jz]["avail"] <= i:
            recent.append(z15[jz])
            if st is not None and qualifies(z15[jz]):
                st["cands"].append(z15[jz])
            jz += 1
        recent = recent[-300:]
        new = None
        while js < len(sl1h) and sl1h[js][1] <= i:
            new = sl1h[js]
            js += 1
        bk.step(i)
        if bk.pos is not None:
            st = None
            continue
        if new is not None and last_ith is not None and last_ith[0] > new[0] and G["cont"][i]:
            st = dict(L=new[0], tL=new[2], ith=last_ith[0], start=i, mid=(last_ith[0] + new[0]) / 2,
                      dead=set(), sweep=None, cands=[])
            st["cands"] = [z for z in recent if qualifies(z)]
        if st is None:
            continue
        cl15 = c["close_15m"][i]
        if i - st["start"] > window or (not np.isnan(cl15) and cl15 < st["L"]):
            st = None
            continue
        st["cands"] = [z for z in st["cands"] if z["inval"] > i and z["touch"] >= i and id(z) not in st["dead"]]
        cands = st["cands"]
        z = deepest(cands, i)
        if z is not None and z["touch"] == i:
            if not z["liq"]:                       # 11강: 앞에 유동성 없는 구역은 깨진다
                st["dead"].add(id(z))
                continue
            sl = st["L"] - BUF * c["atr1H"][i]
            L1, L2 = tp_levels(c, i, z["entry"], "1H", "4H")
            if bk.limit(i, z["entry"], sl, st["ith"], L1=L1, L2=L2, xl=(st["L"], "15m"), trail=sl1h, tag="S1"):
                st = None
            else:
                st["dead"].add(id(z))
            continue
        if z is None and c["l"][i] < st["L"]:      # 8강 대체 진입: 디스카운트 POI 없음 → ITL 꼬리 스윕
            st["sweep"] = c["l"][i] if st["sweep"] is None else min(st["sweep"], c["l"][i])
        if st["sweep"] is not None and not np.isnan(cl15) and cl15 >= st["L"]:
            sl = st["sweep"] - BUF * c["atr1H"][i]
            L1, L2 = tp_levels(c, i, c["o"][i], "1H", "4H")
            if bk.market(i, sl, st["ith"], L1=L1, L2=L2, xl=(st["L"], "15m"), trail=sl1h, tag="S1sw"):
                st = None
            else:
                st["sweep"] = None
    return bk.trades


# ── S2: 상위TF POI 진입 모듈 + 리클레임 블록 (6·7·11강) ─────────────────
def run_s2(c, mode, window, kz_on=True, open_mode="strict"):
    """4H·일봉 매수 구역 첫 탭(유동성 앞·다리 디스카운트) → 1m 스윕 → displacement+MSS → 가장 깊은 1m FVG 리테스트.
    상위TF 종가가 구역 무효선 아래 마감 시 취소. 이후 접근 다리 5m 스윙 저점 블록(리클레임)을 차례로 재진입.
    TP: 5m 스윙 고점(50%+본절) → 15m 스윙 고점 → 상위TF 목표. window: 탭→스윕, 스윕→MSS, MSS→체결 각각."""
    G = gates(c, mode)
    bk = Book2(c, G["rev"], kz_on, open_mode)
    taps = zones_by_touch(c, ["4H", "1D"])
    F5 = c["F"]["5m"]
    sw5 = c["sl_5m"]
    sw5_t = np.array([x[2].value for x in sw5])
    st = None
    for i in range(1, c["n"]):
        bk.step(i)
        if st is None:
            if bk.pos is None and G["tap"][i]:  # 휴식은 체결 시점에 확인 — 탭 자체가 일봉 OB 휴식을 발동시키므로(6강)
                for z in taps.get(i, []):
                    if z["liq"] and leg_discount(c, z, i):
                        st = dict(z=z, tap=i, low=None, order=None, mb=None, rc=[], used=set())
                        break
            continue
        z = st["z"]
        if z["inval"] <= i or (st["low"] is not None and c["l"][i] < st["low"] and st["mb"] is not None):
            st = None
            continue
        if st["low"] is None:
            if i - st["tap"] > window:
                st = None
            elif c["l"][i] < c["sl1m_p"][i]:
                st.update(low=c["l"][i], sb=i, mss=c["sh1m_p"][i])
            continue
        if st["mb"] is None:
            if i - st["sb"] > window:
                st = None
                continue
            if c["l"][i] < st["low"]:
                st.update(low=c["l"][i], sb=i, mss=c["sh1m_p"][i])
                continue
            if c["c"][i] > st["mss"]:
                e = displacement(c, st["sb"], i)
                if e is None:
                    st["mss"] = max(c["h"][i], c["sh1m_p"][i])   # 6강: FVG 없는 장대 = 가짜 레그
                    continue
                st["mb"], st["order"] = i, e
                # 리클레임 후보: 접근 다리(탭 1일 전 ~ 스윕) 5m 스윙 저점 캔들, 스윕 저점 위
                t_lo = (c["idx"][st["tap"]] - np.timedelta64(1, "D")).value
                t_hi = c["idx"][st["sb"]].value
                for k in np.flatnonzero((sw5_t >= t_lo) & (sw5_t <= t_hi)):
                    p, a_, tb = sw5[k]
                    if p > st["low"]:
                        b5 = F5.index.get_loc(tb)
                        st["rc"].append(dict(lo=F5["l"].values[b5], hi=F5["h"].values[b5], on=False))
            continue
        if i - st["mb"] > window:
            st = None
            continue
        if bk.pos is not None:
            continue
        for r in st["rc"]:
            if not r["on"] and c["c"][i] > r["hi"]:
                r["on"] = True
        if st["order"] is not None and c["l"][i] <= st["order"]:
            e = st["order"]
            st["order"] = None
            L1, L2 = tp_levels(c, i, e, "5m", "15m")
            bk.limit(i, e, st["low"] - BUF * c["atr15m"][i], htf_target(c, i, e), L1=L1, L2=L2, tag="S2")
            continue
        for r in sorted(st["rc"], key=lambda r: -r["hi"]):
            if r["on"] and id(r) not in st["used"] and c["l"][i] <= r["hi"]:
                st["used"].add(id(r))
                L1, L2 = tp_levels(c, i, r["hi"], "5m", "15m")
                bk.limit(i, r["hi"], r["lo"] - BUF * c["atr15m"][i], htf_target(c, i, r["hi"]), L1=L1, L2=L2,
                         tag="S2rc")
                break
    return bk.trades


# ── S3: 전일/전주 고저 스윕 (5·9강) ──────────────────────────────────
def run_s3(c, mode, window, kz_on=True, open_mode="strict", level="D"):
    """추세 방향: 전일(전주) 저점 스윕 → 1m 왼쪽 첫 스윙 돌파(CHoCH로 간주) → 다리의 가장 깊은 FVG 리테스트 → TP 전일(전주) 고점.
    역추세(카운터, 5강): 하락추세에서 저점 스윕 → 위 첫 미탭 매도 구역(15m·1H·4H)까지만, 부분익절 없음.
    FVG가 없으면 새 구조 대기(5강). window: 스윕→MSS, MSS→체결."""
    G = gates(c, mode)
    gate = G["s3"] | G["counter"]
    bk = Book2(c, gate, kz_on, open_mode)
    lvl_lo = c["pdl"] if level == "D" else c["pwl"]
    lvl_hi = c["pdh"] if level == "D" else c["pwh"]
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
            if kk != last and c["l"][i] < lvl_lo[i] and not np.isnan(c["sh1m_p"][i]):
                if G["s3"][i]:
                    st = dict(low=c["l"][i], sb=i, mss=c["sh1m_p"][i], tp=lvl_hi[i], ctr=False, e=None)
                elif G["counter"][i]:
                    st = dict(low=c["l"][i], sb=i, mss=c["sh1m_p"][i], tp=None, ctr=True, e=None)
                last = kk
            continue
        if st["e"] is None:
            if i - st["sb"] > window:
                st = None
                continue
            if c["l"][i] < st["low"]:
                st.update(low=c["l"][i], sb=i, mss=c["sh1m_p"][i])
                continue
            if c["c"][i] > st["mss"]:
                e, nf = leg_fvg_entry(c, st["sb"], i)
                if e is None:
                    st["mss"] = max(c["h"][i], c["sh1m_p"][i])
                    continue
                st.update(e=e, mb=i)
            continue
        if i - st["mb"] > window or c["l"][i] < st["low"]:
            st = None
            continue
        if c["l"][i] <= st["e"]:
            e, sl = st["e"], st["low"] - BUF * c["atr15m"][i]
            if st["ctr"]:
                m = np.flatnonzero(b_av <= i)
                ups = [bear[k]["entry"] for k in m if alive(bear[k], i) and bear[k]["entry"] > e]
                tp = min(ups) if ups else lvl_hi[i]
                bk.limit(i, e, sl, tp, tag=f"S3{level}c")
            else:
                L1, L2 = tp_levels(c, i, e, "5m", "15m")
                bk.limit(i, e, sl, st["tp"], L1=L1, L2=L2, tag=f"S3{level}")
            st = None
    return bk.trades


# ── S4: 딜링 레인지 (9강) ───────────────────────────────────────────
def run_s4(c, mode, window, kz_on=True, open_mode="strict"):
    """상승 딜링레인지(SSL→BSL)의 디스카운트에서 가장 깊은 1H·4H PD 배열(유동성 앞) 탭 → 15m 거부(꼬리 진입·위 마감) 확인 후 진입.
    SL 레인지 저점, TP 1H→4H 스윙 고점 관리, 최종 레인지 고점. 이후 첫 진입 뒤 생긴 15m PD 배열 재탭마다 추가 진입.
    window: 구역 탭→15m 거부, 첫 체결→추가 진입 기간."""
    G = gates(c, mode)
    bk = Book2(c, G["rev"], kz_on, open_mode)
    zs = zones_by_avail(c, ["1H", "4H"])
    t15 = zones_by_touch(c, ["15m"])
    st, dr_key = None, None
    jz = 0
    seen = []
    for i in range(1, c["n"]):
        lo, hi, dd = c["dr_lo"][i], c["dr_hi"][i], c["dr_dir"][i]
        valid = dd == 1 and not np.isnan(lo) and not np.isnan(hi) and hi > lo
        mid = (lo + hi) / 2 if valid else None
        while jz < len(zs) and zs[jz]["avail"] <= i:
            z = zs[jz]
            seen.append(z)
            if st is not None and valid and lo < z["entry"] <= mid:
                st["cands"].append(z)
            jz += 1
        bk.step(i)
        k = (lo, hi)
        if k != dr_key:
            dr_key, st = k, None
            seen = [z for z in seen if z["touch"] >= i and z["inval"] > i]
            if valid:
                st = dict(tz=None, t_touch=None, t_fill=None, dead=set(), used=set(),
                          cands=[z for z in seen if lo < z["entry"] <= mid])
        if st is None or not valid or bk.pos is not None:
            continue
        sl = lo - BUF * c["atr1H"][i]
        if st["t_fill"] is None:
            if st["tz"] is None:
                st["cands"] = [z for z in st["cands"] if z["touch"] >= i and z["inval"] > i and id(z) not in st["dead"]]
                z = deepest(st["cands"], i)
                if z is not None and z["touch"] == i:
                    if z["liq"]:
                        st.update(tz=z, t_touch=i)
                    else:
                        st["dead"].add(id(z))
                continue
            z = st["tz"]
            cl, lw = c["close_15m"][i], c["low_15m"][i]
            if i - st["t_touch"] > window:
                st["dead"].add(id(z))
                st["tz"] = None
                continue
            if not np.isnan(cl):
                if cl < z["inv"]:
                    st["dead"].add(id(z))
                    st["tz"] = None
                elif lw <= z["entry"] and cl > z["entry"]:   # 15m 거부
                    L1, L2 = tp_levels(c, i, c["o"][i], "1H", "4H")
                    if bk.market(i, sl, hi, L1=L1, L2=L2, tag="S4"):
                        st["t_fill"] = i
                    else:
                        st["dead"].add(id(z))
                        st["tz"] = None
            continue
        if i - st["t_fill"] > window:
            continue
        for z in t15.get(i, []):
            if z["t0time"] >= c["idx"][st["t_fill"]] and id(z) not in st["used"] and z["entry"] < hi:
                st["used"].add(id(z))
                L1, L2 = tp_levels(c, i, z["entry"], "1H", "4H")
                if bk.limit(i, z["entry"], sl, hi, L1=L1, L2=L2, tag="S4re"):
                    break
    return bk.trades


# ── S5: 프랙탈 풀백 (11강) ──────────────────────────────────────────
def run_s5(c, mode, window, kz_on=True, open_mode="strict"):
    """일봉 매수 구역 탭(유동성 앞) → 1H MSS(구조 상태 하락→상승) + 15m displacement → MSS 직후 진입 금지,
    다리 디스카운트의 가장 깊은 4H 매수 구역까지 풀백 대기 → 그 안 15m 구역으로 리파인해 지정가.
    4H 구역이 없으면 매매 안 함(풀백 끝점 불명). SL 4H 구역 아래, TP 1H→4H 스윙 고점 관리, 최종 상위TF 목표.
    window: 탭→MSS, MSS→체결."""
    G = gates(c, mode)
    bk = Book2(c, G["rev"], kz_on, open_mode)
    taps = zones_by_touch(c, ["1D"])
    z4 = zones_by_avail(c, ["4H"])
    z15 = zones_by_avail(c, ["15m"])
    z4av = np.array([z["avail"] for z in z4])
    z15av = np.array([z["avail"] for z in z15])
    tvals = c["idx"].values
    h1s = c["h1_state"]
    st = None
    for i in range(1, c["n"]):
        bk.step(i)
        if st is None:
            if bk.pos is None and G["tap"][i]:  # 휴식은 체결 시점에 확인 (일봉 POI 도달 → 휴식 → 1H MSS → 풀백, 6·11강)
                for z in taps.get(i, []):
                    if z["liq"]:
                        st = dict(z=z, tap=i, low=c["l"][i], tlow=c["idx"][i], hh=c["h"][i], mss=None, ent=None)
                        break
            continue
        if st["mss"] is None:
            if i - st["tap"] > window or st["z"]["inval"] <= i:
                st = None
                continue
            if c["l"][i] < st["low"]:
                st.update(low=c["l"][i], tlow=c["idx"][i], hh=c["h"][i])
            st["hh"] = max(st["hh"], c["h"][i])
            if h1s[i] == 1 and h1s[i - 1] != 1:
                tl = st["tlow"].value
                m15 = (c["m15_t"] >= tl) & (c["m15_t"] < c["idx"][i].value)
                nf = int(((c["fvg15_t0"] >= tl) & (c["fvg15_av"] <= i)).sum())
                big = m15.any() and c["m15_range"][m15].max() >= DISP_MULT * c["m15_atr"][np.flatnonzero(m15)[0]]
                if nf >= DISP_FVG and big:
                    st.update(mss=i, z4=None, ent=None)
            continue
        if i - st["mss"] > window or c["l"][i] < st["low"]:
            st = None
            continue
        st["hh"] = max(st["hh"], c["h"][i])
        recheck = st["z4"] is None and (not np.isnan(c["close_4H"][i]) or i == st["mss"] + 1)
        if (st["z4"] is not None and not alive(st["z4"], i)) or recheck:
            # 11강: 1H displacement가 만든 4H 구역(다리 안에서 형성, 디스카운트, 유동성 앞)이 생기면 그중 가장 깊은 것까지 풀백 대기
            # (4H 봉 마감 시점마다 재검색)
            mid = (st["low"] + st["hh"]) / 2
            t4 = st["tlow"] - np.timedelta64(4, "h")
            a0 = np.searchsorted(tvals, t4.to_datetime64().astype(tvals.dtype) if hasattr(t4, "to_datetime64") else t4, "left")
            lo_k, hi_k = np.searchsorted(z4av, a0, "left"), np.searchsorted(z4av, i, "right")
            cands = [z for z in z4[lo_k:hi_k] if alive(z, i) and z["t0time"] >= t4 and z["entry"] <= mid and z["liq"]]
            zz = deepest(cands, i)
            if zz is None:
                st["z4"] = None
                continue
            b0 = np.searchsorted(z15av, np.searchsorted(tvals, st["tlow"].to_datetime64().astype(tvals.dtype), "left"), "left")
            inner = [y for y in z15[b0:np.searchsorted(z15av, i, "right")] if alive(y, i)
                     and y["t0time"] >= st["tlow"] and zz["lo"] <= y["entry"] <= zz["hi"]]
            yy = deepest(inner, i)
            st.update(z4=zz, ent=(yy["entry"] if yy else zz["entry"]))
        if st["z4"] is None:
            continue
        if bk.pos is None and c["l"][i] <= st["ent"]:
            e = st["ent"]
            L1, L2 = tp_levels(c, i, e, "1H", "4H")
            bk.limit(i, e, st["z4"]["lo"] - BUF * c["atr1H"][i], htf_target(c, i, e), L1=L1, L2=L2, tag="S5")
            st = None
    return bk.trades


# ── S6: BOS 스윕 반전 (6·8강) ───────────────────────────────────────
def run_s6(c, mode, window=None, kz_on=True, open_mode="strict"):
    """상승 바이어스 중 1H 구조가 하락(BOS 진행)일 때, 1H 봉이 직전 1H 스윙 저점(BOS 레벨)을 꼬리로 쓸고 그 위로 마감
    → 다음 봉 매수. SL 그 봉 저점 아래, 1H 종가가 레벨 아래 마감 시 청산. TP 15m 스윙 고점(50%) → 최종 1H 스윙 고점.
    (ITL/CHoCH 스윕 지속형은 S1 대체 진입에 포함.)"""
    G = gates(c, mode)
    gate = G["rev"] & (c["h1_state"] == -1)
    gate_fill = G["rev"]
    bk = Book2(c, gate_fill, kz_on, open_mode)
    sl1 = c["sl_1H"]
    av1 = np.array([x[1] for x in sl1])
    for i in range(61, c["n"]):
        bk.step(i)
        cl = c["close_1H"][i]
        if bk.pos is not None or np.isnan(cl) or not gate[i - 1]:
            continue
        k = np.searchsorted(av1, i - 60, "left") - 1    # 이 1H 봉 시작 전 확정된 스윙 저점
        if k < 0:
            continue
        lvl = sl1[k][0]
        if c["low_1H"][i] < lvl <= cl:
            final = nearest_level(c["sh_1H"], c["o"][i], i)
            L1 = nearest_level(c["sh_15m"], c["o"][i], i)
            bk.market(i, c["low_1H"][i] - BUF * c["atr1H"][i], final, L1=L1, xl=(lvl, "1H"), tag="S6")
    return bk.trades


# ── S8: 세션 전략 (10강) ────────────────────────────────────────────
def run_s8a(c, mode, window, kz_on=True, open_mode="strict"):
    """아시안 진입: 뉴욕 15:30~20:00 구간의 15m 매수 구역·스윙 저점 표시 → 아시안 킬존(20~24)에서 탭/스윕 → 1m MSS
    → 다리 가장 깊은 FVG 리테스트. SL 스윕 저점 아래. TP 15m 스윙 고점(50%+본절) → 1H 스윙 고점(손절 중간) → 4H 스윙 고점.
    바이어스 반대(카운터)는 가까운 유동성(15m 스윙 고점)만. 런던 시작 시 같은 방향 새 15m 구역(지지)이 없으면 청산.
    window: 탭→MSS, MSS→체결."""
    G = gates(c, mode)
    gate = G["dir"] | G["counter"]
    bk = Book2(c, gate, kz_on, open_mode)
    nyh, nyd = c["ny_hour"], c["ny_date"]
    z15 = zones_by_avail(c, ["15m"])
    zav = np.array([z["avail"] for z in z15])
    win, st, cur = None, None, None
    z15t = zones_by_touch(c, ["15m"])
    for i in range(1, c["n"]):
        bk.step(i)
        d, hr = nyd[i], nyh[i]
        # 10강: 진입 후 런던(뉴욕 02시)이 같은 방향 새 POI로 지지하지 않으면 아시안에서 손 뗌
        p = bk.pos
        if p is not None and p["tag"].startswith("S8a") and 2 <= hr < 2 + 1 / 60:
            t_in = p["t"]
            k0 = np.searchsorted(zav, i, "right")
            sup = [z15[k] for k in range(max(0, k0 - 200), k0)
                   if z15[k]["t0time"] >= t_in and alive(z15[k], i)]
            if not sup:
                bk.exit_now(i, "LDN")
        if 15.5 <= hr < 20:
            if win is None or win["d"] != d:
                win = dict(d=d, lo=c["l"][i], s=i, zs=[])
            win["lo"] = min(win["lo"], c["l"][i])
        if win is not None and hr >= 20 and win["d"] == d and not win["zs"] and win.get("e") is None:
            m = np.flatnonzero((zav >= win["s"]) & (zav <= i))
            win["zs"] = [z15[k] for k in m]
            win["e"] = i
        if bk.pos is not None:
            st = None
            continue
        if st is None:
            if win is not None and win["d"] == d and hr >= 20:
                tap = any(alive(z, i) and c["l"][i] <= z["entry"] for z in win["zs"])
                if (tap or c["l"][i] < win["lo"]) and (G["dir"][i] or G["counter"][i]):
                    st = dict(low=c["l"][i], sb=i, mss=c["sh1m_p"][i], e=None, ctr=not G["dir"][i])
            continue
        if st["e"] is None:
            if i - st["sb"] > window:
                st = None
                continue
            if c["l"][i] < st["low"]:
                st.update(low=c["l"][i], sb=i, mss=c["sh1m_p"][i])
                continue
            if c["c"][i] > st["mss"]:
                e, nf = leg_fvg_entry(c, st["sb"], i)
                if e is None:
                    st["mss"] = max(c["h"][i], c["sh1m_p"][i])
                    continue
                st.update(e=e, mb=i)
            continue
        if i - st["mb"] > window or c["l"][i] < st["low"]:
            st = None
            continue
        if c["l"][i] <= st["e"]:
            e, sl = st["e"], st["low"] - BUF * c["atr15m"][i]
            L1 = nearest_level(c["sh_15m"], e, i)
            if st["ctr"]:
                bk.limit(i, e, sl, L1, tag="S8a_c")
            else:
                L2 = nearest_level(c["sh_1H"], L1, i) if L1 else None
                fin = nearest_level(c["sh_4H"], L2 or L1 or e, i)
                bk.limit(i, e, sl, fin, L1=L1, L2=L2, tag="S8a")
            st = None
    return bk.trades


def run_s8b(c, mode, window, kz_on=True, open_mode="strict"):
    """CBDR: 뉴욕 14~20시 박스(폭 ≤ 일평균범위×0.3), 아시안 20~24시 범위. 다음 날 런던(02~05)·뉴욕(07~10) 킬존에서
    아시안 저점 스윕(아시안 고점을 먼저 스윕하면 그날 제외) → displacement+MSS → 15m(없으면 1m) 다리 구역 리테스트.
    상위TF 목표 존재 필수. SL 스윕 저점 아래, TP 박스 고점+1폭(50%+본절) → 박스 고점+2폭. window: 스윕→MSS, MSS→체결."""
    G = gates(c, mode)
    bk = Book2(c, G["dir"], kz_on, open_mode)
    nyh, nyd = c["ny_hour"], c["ny_date"]
    D = c["F"]["1D"]
    adr = (D["h"] - D["l"]).rolling(20).mean()
    adr_v = np.full(c["n"], np.nan)
    pos = np.searchsorted(D.index.values, c["idx"].values, "right") - 2
    ok = pos >= 0
    adr_v[ok] = adr.values[pos[ok]]
    z15 = zones_by_avail(c, ["15m"])
    zav = np.array([z["avail"] for z in z15])
    box = asia = None
    day = st = None
    for i in range(1, c["n"]):
        bk.step(i)
        d, hr = nyd[i], nyh[i]
        if 14 <= hr < 20:
            if box is None or box["d"] != d:
                box = dict(d=d, hi=c["h"][i], lo=c["l"][i])
            box["hi"], box["lo"] = max(box["hi"], c["h"][i]), min(box["lo"], c["l"][i])
        if hr >= 20:
            if asia is None or asia["d"] != d:
                asia = dict(d=d, hi=c["h"][i], lo=c["l"][i])
            asia["hi"], asia["lo"] = max(asia["hi"], c["h"][i]), min(asia["lo"], c["l"][i])
        if hr < 12 and box is not None and asia is not None and box["d"] == asia["d"] and d > box["d"]:
            if day is None or day["d"] != d:
                w = box["hi"] - box["lo"]
                day = dict(d=d, w=w, ok=w > 0 and not np.isnan(adr_v[i]) and w <= CBDR_MAX * adr_v[i],
                           hi_first=False, done=False)
        else:
            if st is None:
                continue
        if bk.pos is not None:
            st = None
            continue
        kz_sess = (2 <= hr < 5) or (7 <= hr < 10)
        if st is None:
            if day is None or not day["ok"] or day["done"] or not kz_sess:
                continue
            if c["h"][i] > asia["hi"]:
                day["done"] = True       # 바이어스 쪽을 먼저 스윕 → 그날 CBDR 사용 안 함
                continue
            if c["l"][i] < asia["lo"] and G["dir"][i] and htf_target(c, i, c["c"][i]) is not None:
                st = dict(low=c["l"][i], sb=i, mss=c["sh1m_p"][i], e=None, bh=box["hi"], w=day["w"])
                day["done"] = True
            continue
        if st["e"] is None:
            if i - st["sb"] > window:
                st = None
                continue
            if c["l"][i] < st["low"]:
                st.update(low=c["l"][i], sb=i, mss=c["sh1m_p"][i])
                continue
            if c["c"][i] > st["mss"]:
                e1 = displacement(c, st["sb"], i)
                if e1 is None:
                    st["mss"] = max(c["h"][i], c["sh1m_p"][i])
                    continue
                m = np.flatnonzero((zav >= st["sb"]) & (zav <= i))
                zz = deepest([z15[k] for k in m if z15[k]["t0time"] >= c["idx"][st["sb"]]], i)
                st.update(e=zz["entry"] if zz else e1, mb=i)
            continue
        if i - st["mb"] > window or c["l"][i] < st["low"]:
            st = None
            continue
        if c["l"][i] <= st["e"]:
            bk.limit(i, st["e"], st["low"] - BUF * c["atr15m"][i], st["bh"] + 2 * st["w"],
                     L1=st["bh"] + st["w"], tag="S8b")
            st = None
    return bk.trades


def run_s8c(c, mode, window, kz_on=True, open_mode="strict"):
    """OTE: 15m 깨끗한 레그(몸통 기준 스윙 저점→스윙 고점, 내부 풀백 < 50%) 확정 → 0.62~0.79 진입 구간 도달 후
    1m MSS(거부)로 시장가 진입. 0.5 아래~0.62 사이 15m 매수 구역이 있으면 그 구역 지정가로 먼저 진입 가능.
    세션 시작 30분(유다 스윙) 금지, 상위TF 목표 존재 필수. SL 레그 시작(스윙 저점) 아래.
    TP 레그 고점(0, 50%+본절) → -0.27(손절 중간) → -0.62. window: 레그 확정→체결."""
    G = gates(c, mode)
    bk = Book2(c, G["dir"], kz_on, open_mode)
    F15 = c["F"]["15m"]
    o15, c15, l15 = F15["o"].values, F15["c"].values, F15["l"].values
    sh15, sl15 = c["SW"]["15m"]
    sl_b = np.array([b for (p, b, cf) in sl15])
    sh_conf = sorted([(p, b, cf, c["av"]["15m"][cf]) for (p, b, cf) in sh15], key=lambda x: x[3])
    z15 = zones_by_avail(c, ["15m"])
    zav = np.array([z["avail"] for z in z15])
    nyh = c["ny_hour"]
    js, st = 0, None
    for i in range(1, c["n"]):
        bk.step(i)
        while js < len(sh_conf) and sh_conf[js][3] <= i:
            p, b, cf, a_ = sh_conf[js]
            js += 1
            k = np.searchsorted(sl_b, b, "left") - 1
            if k < 0:
                continue
            bl = sl15[k][1]
            L, H = min(o15[bl], c15[bl]), max(o15[b], c15[b])
            if H <= L:
                continue
            kk = np.searchsorted(sl_b, b, "left")
            inner = [q for (q, bb, _) in sl15[k + 1:kk]]
            if inner and min(inner) < L + OTE_CLEAN * (H - L):
                continue
            if bk.pos is None:
                st = dict(L=L, H=H, wick=l15[bl], start=i, armed=None)
        if st is None or bk.pos is not None:
            continue
        R = st["H"] - st["L"]
        f62, f79, f50 = st["H"] - 0.62 * R, st["H"] - 0.79 * R, st["H"] - 0.5 * R
        if i - st["start"] > window or c["l"][i] < st["wick"] or c["h"][i] > st["H"]:
            st = None
            continue
        judas = (2 <= nyh[i] < 2 + JUDAS_MIN) or (7 <= nyh[i] < 7 + JUDAS_MIN) or (20 <= nyh[i] < 20 + JUDAS_MIN)
        if judas or not G["dir"][i] or htf_target(c, i, c["c"][i]) is None:
            continue
        sl = st["wick"] - BUF * c["atr15m"][i]
        kw = dict(L1=st["H"], L2=st["H"] + 0.27 * R, tag="S8c")
        m = np.flatnonzero(zav <= i)
        early = [z15[k] for k in m[-300:] if alive(z15[k], i) and f62 < z15[k]["entry"] <= f50]
        ez = deepest(early, i)
        if ez is not None and ez["touch"] == i:
            if bk.limit(i, ez["entry"], sl, st["H"] + 0.62 * R, **kw):
                st = None
            continue
        if st["armed"] is None and c["l"][i] <= f62:
            st["armed"] = dict(low=c["l"][i], mss=c["sh1m_p"][i])
        elif st["armed"] is not None:
            if c["l"][i] < st["armed"]["low"]:
                st["armed"].update(low=c["l"][i], mss=c["sh1m_p"][i])
            elif c["c"][i - 1] > st["armed"]["mss"] and f79 <= c["o"][i] <= f50:
                if bk.market(i, sl, st["H"] + 0.62 * R, **kw):
                    st = None
    return bk.trades


# ── S9: 시간순환 스파이크 (11강) ────────────────────────────────────
def run_s9(c, mode, window=None, kz_on=True, open_mode="strict"):
    """TF X(5m→15m, 15m→1H, 1H→4H)의 매수 구역(FVG·OB)을 X봉이 처음 탭하고 같은 봉에서 위로 마감(거부),
    바로 위 TF Y에 최근 Y 스윙 저점 이후 생긴 미충전 매수 FVG가 아직 없음(=Y POI 만들러 달릴 차례) → 다음 봉 시장가 매수.
    SL 구역 아래, TP = Y의 위쪽 첫 매도 구역(없으면 Y 스윙 고점)."""
    G = gates(c, mode)
    gate = G["rev"]
    bk = Book2(c, gate, kz_on, open_mode)
    ladder = (("5m", "15m"), ("15m", "1H"), ("1H", "4H"))
    taps = {x: zones_by_touch(c, [x], kinds=("FVG", "OB")) for x, _ in ladder}
    yf = {y: sorted([z for z in c["Z"][y] if z["side"] == 1 and z["kind"] == "FVG"], key=lambda z: z["avail"]) for _, y in ladder}
    yb = {y: sorted([z for z in c["Z"][y] if z["side"] == -1 and z["touch"] >= 0], key=lambda z: z["avail"]) for _, y in ladder}
    pend = []
    for i in range(1, c["n"]):
        bk.step(i)
        for x, y in ladder:
            for z in taps[x].get(i, []):
                pend.append((x, y, z, i))
        if bk.pos is not None:
            pend = []
            continue
        keep = []
        for (x, y, z, ti) in pend:
            cl = c[f"close_{x}"][i]
            if np.isnan(cl):
                keep.append((x, y, z, ti))
                continue
            if cl > z["entry"] and gate[i]:
                sly = c[f"sl_{y}"]
                k = np.searchsorted([s[1] for s in sly], i, "right") - 1
                t_sw = sly[k][2] if k >= 0 else c["idx"][0]
                fresh = [f for f in yf[y] if f["avail"] <= i and f["t0time"] >= t_sw and alive(f, i)]
                if not fresh:
                    ups = [b["entry"] for b in yb[y] if b["avail"] <= i and alive(b, i) and b["entry"] > c["o"][i]]
                    tp = min(ups) if ups else nearest_level(c[f"sh_{y}"], c["o"][i], i)
                    if bk.market(i, z["lo"] - BUF * c["atr15m"][i], tp, tag=f"S9_{x}"):
                        break
        pend = keep if bk.pos is None else []
    return bk.trades


RUNNERS = {
    "S1": (run_s1, True), "S2": (run_s2, True), "S3d": (lambda *a, **k: run_s3(*a, level="D", **k), True),
    "S3w": (lambda *a, **k: run_s3(*a, level="W", **k), True), "S4": (run_s4, True), "S5": (run_s5, True),
    "S6": (run_s6, False), "S8a": (run_s8a, True), "S8b": (run_s8b, True), "S8c": (run_s8c, True),
    "S9": (run_s9, False),
}
