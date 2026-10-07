"""MTF 사슬 위의 S1·S2·S3 (1분봉 체결/트리거). 롱 로직, 숏은 미러.

공통 게이트(모두 충족해야 셋업 생성):
  일봉 ITH/ITL 추세 상승 · 데일리 바이어스≠하락 · 주간 바이어스≠하락 · 4H 보호저점 유지
  · 일봉 딜링레인지 디스카운트 · 위쪽 상위TF 목표 존재 · (체결 시) 시가 규칙 · (옵션) 킬존
"""
import numpy as np

from strategies import Book, nearest_above

BUF = 0.1


class MBook(Book):
    def allowed(self, i):
        c = self.c
        return (c["trend"][i] == 1 and c["dbias"][i] != -1 and c["wbias"][i] != -1 and c["h4_ok"][i] == 1)


def discount(c, i, price):
    lo, hi = c["dr_lo"][i], c["dr_hi"][i]
    if np.isnan(lo) or np.isnan(hi) or hi <= lo:
        return True  # 레인지 미형성 시 필터 미적용
    return price <= (lo + hi) / 2


def htf_target(c, i, price):
    """위쪽 첫 상위TF 유동성: 일봉 스윙 고점 / 딜링레인지 고점 / 전주 고점 중 가장 가까운 것."""
    cands = [x for x in (c["dr_hi"][i], c["pwh"][i]) if not np.isnan(x) and x > price]
    s = nearest_above(c["shD"], price, i, lookback=60)
    if s is not None:
        cands.append(s)
    return min(cands) if cands else None


def run_s1(c, window, kz_on, open_mode):
    """8강 프랙탈 매핑: 1H 스윙 저점(=15m ITL)을 보호 레벨로, 1H ITH까지. 진입 = 디스카운트 15m FVG."""
    bk = MBook(c, kz_on, open_mode)
    sl1h, ith, f15 = c["sl1h"], c["ith1"], c["fvg15"]
    js, jh, jf, last_ith, st, zones = 0, 0, 0, None, None, []
    for i in range(1, c["n"]):
        while jh < len(ith) and ith[jh][2] <= i:
            last_ith = ith[jh]
            jh += 1
        while jf < len(f15) and f15[jf][3] <= i:
            zones.append(f15[jf])
            jf += 1
        zones = zones[-150:]
        new = None
        while js < len(sl1h) and sl1h[js][2] <= i:
            new = sl1h[js]
            js += 1
        bk.step(i)
        if bk.pos is not None:
            st = None
            continue
        if new is not None and last_ith is not None and last_ith[0] > new[0] and bk.allowed(i) \
                and htf_target(c, i, c["c"][i]) is not None:
            st = dict(L=new[0], tL=new[1], ith=last_ith[0], start=i, mid=(last_ith[0] + new[0]) / 2, dead=set())
        if st is None:
            continue
        if i - st["start"] > window or (c["m15_end_bar"][i] and c["c"][i] < st["L"]) or not bk.allowed(i):
            st = None
            continue
        best = None
        for z in zones:
            lo, hi, t1, av = z
            if t1 < st["tL"] or av > i or hi > st["mid"] or lo <= st["L"] or id(z) in st["dead"]:
                continue
            if c["l"][i] <= hi and (best is None or hi > best[1]):
                best = z
        if best is None:
            continue
        if not discount(c, i, best[1]):
            st["dead"].add(id(best))
            continue
        sl = st["L"] - BUF * c["atr1h"][i]
        if bk.try_fill(i, best[1], sl, st["ith"], exit_level=st["L"], tag="S1"):
            st = None
        else:
            st["dead"].add(id(best))
    return bk.trades


def _entry_from_leg(c, sb, i):
    sel = (c["fvg1_c1"] >= sb) & (c["fvg1_c3"] <= i)
    return sel


def run_s2(c, window, kz_on, open_mode, min_fvg=2, disp_mult=2.0):
    """6·11강 진입 모듈: 4H/일봉 FVG(디스카운트) 탭 → 1m 스윕 → displacement+MSS → 1m FVG 리테스트.
    TP1 = 15m 스윙 고점(바로 위 TF 유동성, 부분익절+본절), TP2 = 상위TF 목표."""
    bk = MBook(c, kz_on, open_mode)
    poi, jp, pois, st = c["poi"], 0, [], None
    for i in range(1, c["n"]):
        while jp < len(poi) and poi[jp][2] <= i:
            pois.append(poi[jp])
            jp += 1
        h4c = c["h4_close"][i]
        if not np.isnan(h4c):
            pois = [p for p in pois if h4c >= p[0]][-40:]
        bk.step(i)
        if bk.pos is not None:
            st = None
            continue
        if st is None:
            if not bk.allowed(i):
                continue
            for p in reversed(pois):
                if c["l"][i] <= p[1] and c["h"][i] >= p[0] and discount(c, i, p[1]):
                    st = dict(poi=p, tap=i, low=None)
                    pois.remove(p)
                    break
            continue
        p = st["poi"]
        if (not np.isnan(h4c) and h4c < p[0]) or not bk.allowed(i):
            st = None
            continue
        if st["low"] is None:
            if i - st["tap"] > window:
                st = None
            elif c["l"][i] < c["sl1m_p"][i]:
                st.update(low=c["l"][i], sb=i, mss=c["sh1m_p"][i], order=None)
            continue
        if st["order"] is None:
            if i - st["sb"] > window:
                st = None
                continue
            if c["l"][i] < st["low"]:
                st.update(low=c["l"][i], sb=i, mss=c["sh1m_p"][i])
                continue
            if c["c"][i] > st["mss"]:
                sel = _entry_from_leg(c, st["sb"], i)
                rng = (c["h"][st["sb"]:i + 1] - c["l"][st["sb"]:i + 1]).max()
                if sel.sum() >= min_fvg and rng >= disp_mult * c["atr1"][st["sb"]]:
                    e = c["fvg1"][np.flatnonzero(sel)[0]][1]
                    tp1 = nearest_above(c["sh15"], e, i)
                    tp2 = htf_target(c, i, e)
                    if tp1 is None or tp2 is None:
                        st = None
                        continue
                    if tp2 <= tp1:
                        tp1, tp2 = tp2, None
                    st["order"] = dict(e=e, sl=st["low"] - BUF * c["atr15"][i], tp1=tp1, tp2=tp2, mb=i)
                else:
                    st["mss"] = max(c["h"][i], c["sh1m_p"][i])  # displacement 없는 돌파 = 가짜, 다음 구조 대기
            continue
        od = st["order"]
        if i - od["mb"] > window or c["l"][i] < st["low"]:
            st = None
            continue
        if bk.try_fill(i, od["e"], od["sl"], od["tp1"], od["tp2"], tag="S2"):
            st = None
    return bk.trades


def run_s3(c, window, kz_on, open_mode):
    """5·9강: 전일 저점 스윕(게이트 충족) → 1m CHoCH(왼쪽 첫 스윙 돌파) → 다리 첫 FVG 리테스트 → TP 전일 고점."""
    bk = MBook(c, kz_on, open_mode)
    st, last_day = None, None
    for i in range(1, c["n"]):
        bk.step(i)
        if bk.pos is not None:
            st = None
            continue
        day = c["idx"][i].date()
        if st is None:
            if day != last_day and c["l"][i] < c["pdl"][i] and bk.allowed(i) and discount(c, i, c["pdl"][i]) \
                    and not np.isnan(c["sh1m_p"][i]):
                st = dict(low=c["l"][i], sb=i, mss=c["sh1m_p"][i], tp=c["pdh"][i], order=None)
                last_day = day
            continue
        if st["order"] is None:
            if i - st["sb"] > window:
                st = None
                continue
            if c["l"][i] < st["low"]:
                st.update(low=c["l"][i], sb=i, mss=c["sh1m_p"][i])
                continue
            if c["c"][i] > st["mss"]:
                sel = _entry_from_leg(c, st["sb"], i)
                if not sel.any():
                    st["mss"] = max(c["h"][i], c["sh1m_p"][i])  # 5강: FVG 불명확 → 새 구조 대기
                    continue
                e = c["fvg1"][np.flatnonzero(sel)[0]][1]
                st["order"] = dict(e=e, sl=st["low"] - BUF * c["atr15"][i], mb=i)
            continue
        od = st["order"]
        if i - od["mb"] > window or c["l"][i] < st["low"]:
            st = None
            continue
        if bk.try_fill(i, od["e"], od["sl"], st["tp"], tag="S3"):
            st = None
    return bk.trades


RUNNERS = {"S1": run_s1, "S2": run_s2, "S3": run_s3}
