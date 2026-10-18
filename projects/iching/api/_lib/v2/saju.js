// 주역사주 v2 — 사주 명식 계산. 절기·간지·대운은 lunar-javascript(6tail, MIT)가 계산하고,
// 여기서는 한국 출생 시각 보정, 한글 변환, 십신·오행 집계, 대운·세운·월운 정리를 한다.
//
// 출생 시각 보정(2026-10-18): 시계 시각 → (IANA tz 'Asia/Seoul'로) 세계시 → 서울 경도 126.978°의 평균태양시.
//   · 표준시 경도(135°)와 서울 경도 차이 약 32분을 빼는 '30분 보정'이 여기서 자동으로 들어간다.
//   · 한국 서머타임(1948~51, 1955~60, 1987~88)과 1954~61년 UTC+8:30 표준시도 tz 데이터가 알고 있다.
//   손으로 기간 표를 두지 않는 이유: 연도별 정확한 시작·종료일을 공개 자료로 확인하기 어려웠고, tz 데이터가 근거를 갖고 있다.
// 자시 처리: lunar-javascript sect 1 — 평균태양시 23시(시계로 약 23시 30분)부터 다음 날 일주. 국내 만세력 기본값과 같다.
import lunar from 'lunar-javascript';

const { Solar, Lunar } = lunar;
const SEOUL_LON = 126.978;

const GAN = '甲乙丙丁戊己庚辛壬癸';
const ZHI = '子丑寅卯辰巳午未申酉戌亥';
const GAN_KO = '갑을병정무기경신임계';
const ZHI_KO = '자축인묘진사오미신유술해';
const EL = ['목', '화', '토', '금', '수'];
const ZHI_EL = [4, 2, 0, 0, 2, 1, 1, 2, 3, 3, 2, 4];
const ZHI_MAIN = [9, 5, 0, 1, 4, 2, 3, 5, 6, 7, 4, 8]; // 지지 본기(정기) 천간
const ZHI_YANG = [true, false, true, false, true, false, true, false, true, false, true, false];
const ZODIAC = ['쥐', '소', '호랑이', '토끼', '용', '뱀', '말', '양', '원숭이', '닭', '개', '돼지'];

// 일간의 모습 — 명리에서 흔히 쓰는 자연 비유
const DAY_MASTER = {
  갑: { image: '큰 나무', trait: '곧게 위로 뻗어 가려는 사람. 앞장서고 원칙을 세우며, 꺾이는 것을 싫어해요.' },
  을: { image: '풀과 덩굴', trait: '부드럽게 감고 오르는 사람. 사람 사이에서 길을 찾고, 끈질기게 살아남아요.' },
  병: { image: '한낮의 해', trait: '드러내고 밝히는 사람. 열정이 크고, 숨기기보다 보여 주며 움직여요.' },
  정: { image: '등불', trait: '가까운 곳을 섬세하게 비추는 사람. 한 가지에 오래 마음을 쏟아요.' },
  무: { image: '큰 산', trait: '묵직하게 버티고 품는 사람. 쉽게 흔들리지 않아 믿음을 얻어요.' },
  기: { image: '논밭의 흙', trait: '길러 내고 다듬는 사람. 실속을 챙기고 사람을 키워요.' },
  경: { image: '바위와 쇠', trait: '결단하고 끊어 내는 사람. 의리가 있고, 아닌 건 아니라고 말해요.' },
  신: { image: '보석과 칼날', trait: '예리한 기준을 가진 사람. 완성도에 민감하고 섬세해요.' },
  임: { image: '큰 강과 바다', trait: '넓게 흐르며 담는 사람. 판을 크게 보고 꾀가 많아요.' },
  계: { image: '비와 이슬', trait: '조용히 스며드는 사람. 직관이 밝고 남의 마음을 먼저 읽어요.' },
};

const ganIdx = (c) => GAN.indexOf(c);
const zhiIdx = (c) => ZHI.indexOf(c);
const ganEl = (i) => Math.floor(i / 2);
const ganYang = (i) => i % 2 === 0;
const gzKo = (gz) => (gz && gz.length === 2 ? GAN_KO[ganIdx(gz[0])] + ZHI_KO[zhiIdx(gz[1])] : '');

// 십신: 일간을 기준으로 다른 천간(지지는 본기)과의 오행 관계 + 음양
function tenGod(dayGan, otherGan) {
  const rel = (ganEl(otherGan) - ganEl(dayGan) + 5) % 5;
  const same = ganYang(otherGan) === ganYang(dayGan);
  return [['비견', '겁재'], ['식신', '상관'], ['편재', '정재'], ['편관', '정관'], ['편인', '정인']][rel][same ? 0 : 1];
}
const TEN_MEANING = {
  비견: '나와 같은 힘 — 자존심, 동료, 독립',
  겁재: '나와 겨루는 힘 — 경쟁, 승부욕, 나눠 갖기',
  식신: '내가 내놓는 것 — 재능, 꾸준한 생산, 여유',
  상관: '틀을 깨는 표현 — 말솜씨, 반항, 새로운 시도',
  편재: '크게 움직이는 돈 — 사업, 기회, 활동 반경',
  정재: '차곡차곡 쌓는 돈 — 성실, 관리, 안정',
  편관: '나를 누르는 힘 — 압박, 도전, 돌파',
  정관: '나를 바로 세우는 틀 — 직장, 책임, 명예',
  편인: '남다른 배움 — 직관, 전문성, 고독',
  정인: '나를 받쳐 주는 힘 — 공부, 문서, 돌봄',
};

function zhiInfo(dg, z) {
  const zi = zhiIdx(z);
  return { ko: ZHI_KO[zi], el: EL[ZHI_EL[zi]], yang: ZHI_YANG[zi], ten: tenGod(dg, ZHI_MAIN[zi]), animal: ZODIAC[zi] };
}
// isDay: 일주의 천간만 '일간'. 다른 기둥에 같은 천간이 있으면 비견이다(년주 경이 '일간'으로 나온 일이 있었다)
function ganInfo(dg, g, isDay = false) {
  const gi = ganIdx(g);
  return { ko: GAN_KO[gi], el: EL[ganEl(gi)], yang: ganYang(gi), ten: isDay ? '일간' : tenGod(dg, gi) };
}
// 간지 두 글자 → 일간 기준 한글 풀이
function gzRead(dg, gz) {
  if (!gz || gz.length !== 2) return null;
  const g = ganInfo(dg, gz[0]), z = zhiInfo(dg, gz[1]);
  return { gz: g.ko + z.ko, gan: g.ko, zhi: z.ko, ganEl: g.el, zhiEl: z.el, ganTen: tenGod(dg, ganIdx(gz[0])), zhiTen: z.ten };
}

/* ── 시각 보정: 서울 시계 시각 → 서울 평균태양시 ── */
const SEOUL_FMT = new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Seoul', hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
function seoulOffsetMin(utcMs) {
  const p = SEOUL_FMT.formatToParts(new Date(utcMs));
  const g = (t) => +p.find((x) => x.type === t).value;
  return (Date.UTC(g('year'), g('month') - 1, g('day'), g('hour'), g('minute'), g('second')) - utcMs) / 60000;
}
function seoulClockToUtc(y, mo, d, h, mi) {
  const wall = Date.UTC(y, mo - 1, d, h, mi);
  let utc = wall - 9 * 3600000;
  for (let i = 0; i < 3; i++) utc = wall - seoulOffsetMin(utc) * 60000;
  return utc;
}
function toLocalMeanTime(utcMs) {
  const t = new Date(utcMs + SEOUL_LON * 4 * 60000); // 경도 1° = 4분
  return { y: t.getUTCFullYear(), m: t.getUTCMonth() + 1, d: t.getUTCDate(), h: t.getUTCHours(), mi: t.getUTCMinutes() };
}

/**
 * @param {object} b  { calendar: 'solar'|'lunar', year, month, day, leap?, hour?, minute?, timeKnown, gender: 'M'|'F' }
 * @param {Date} now  기준 시각(대운·세운·월운 계산용)
 */
export function computeSaju(b, now = new Date()) {
  const year = +b.year, month = +b.month, day = +b.day;
  if (!(year >= 1900 && year <= 2100 && month >= 1 && month <= 12 && day >= 1 && day <= 31)) throw new Error('생년월일을 확인해 주세요');
  let sy = year, sm = month, sd = day;
  if (b.calendar === 'lunar') {
    const s = Lunar.fromYmd(year, b.leap ? -month : month, day).getSolar();
    sy = s.getYear(); sm = s.getMonth(); sd = s.getDay();
  }
  const timeKnown = Boolean(b.timeKnown) && b.hour !== '' && b.hour != null;
  const hh = timeKnown ? +b.hour : 12, mm = timeKnown ? +(b.minute || 0) : 0;
  const lmt = toLocalMeanTime(seoulClockToUtc(sy, sm, sd, hh, mm));
  const solar = Solar.fromYmdHms(lmt.y, lmt.m, lmt.d, lmt.h, lmt.mi, 0);
  const ec = solar.getLunar().getEightChar();
  ec.setSect(1);
  const dg = ganIdx(ec.getDayGan());

  const raw = [['년주', ec.getYear()], ['월주', ec.getMonth()], ['일주', ec.getDay()], ['시주', timeKnown ? ec.getTime() : '']];
  const pillars = raw.map(([name, gz]) => (gz ? {
    name,
    gz: gzKo(gz),
    gan: ganInfo(dg, gz[0], name === '일주'),
    zhi: zhiInfo(dg, gz[1]),
  } : { name, gz: '', unknown: true }));
  const hidden = { 년주: ec.getYearHideGan(), 월주: ec.getMonthHideGan(), 일주: ec.getDayHideGan(), 시주: timeKnown ? ec.getTimeHideGan() : [] };
  pillars.forEach((p) => { if (!p.unknown) p.hidden = (hidden[p.name] || []).map((g) => ({ ko: GAN_KO[ganIdx(g)], ten: tenGod(dg, ganIdx(g)) })); });

  // 오행 개수(드러난 글자만) — 지장간까지 넣으면 사람마다 셈법이 달라 보이는 수만 센다
  const elements = Object.fromEntries(EL.map((e) => [e, 0]));
  pillars.filter((p) => !p.unknown).forEach((p) => { elements[p.gan.el]++; elements[p.zhi.el]++; });
  // 십신 개수(일간 제외)
  const tens = {};
  pillars.filter((p) => !p.unknown).forEach((p) => {
    if (p.gan.ten !== '일간') tens[p.gan.ten] = (tens[p.gan.ten] || 0) + 1;
    tens[p.zhi.ten] = (tens[p.zhi.ten] || 0) + 1;
  });

  // 대운·세운
  const yun = ec.getYun(b.gender === 'F' ? 0 : 1, 1);
  const thisYear = now.getFullYear();
  const daewoon = yun.getDaYun().filter((d) => d.getGanZhi()).slice(0, 10).map((d) => ({
    startAge: d.getStartAge(), endAge: d.getEndAge(), startYear: d.getStartYear(), endYear: d.getEndYear(),
    ...gzRead(dg, d.getGanZhi()),
  }));
  const current = daewoon.find((d) => d.startYear <= thisYear && thisYear <= d.endYear) || null;
  const yearGz = (y) => gzRead(dg, Solar.fromYmd(y, 7, 1).getLunar().getYearInGanZhiExact());
  const seun = [thisYear, thisYear + 1].map((y) => ({ year: y, ...yearGz(y) }));

  // 앞으로 12개월 월운 — 달마다 그 달 20일의 월주(절기 기준). 시기 창은 monthAt()으로 따로 짚는다.
  const monthly = [];
  for (let k = 0; k < 12; k++) {
    const t = new Date(now.getFullYear(), now.getMonth() + k, 20);
    monthly.push({ ym: `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}`, ...monthAt(dg, t) });
  }

  return {
    input: { calendar: b.calendar === 'lunar' ? '음력' : '양력', year, month, day, leap: Boolean(b.leap), timeKnown, hour: timeKnown ? hh : null, minute: timeKnown ? mm : null, gender: b.gender === 'F' ? '여' : '남' },
    solarDate: `${sy}-${String(sm).padStart(2, '0')}-${String(sd).padStart(2, '0')}`,
    zodiac: ZODIAC[zhiIdx(ec.getYear()[1])],
    pillars,
    dayMaster: { gan: GAN_KO[dg], el: EL[ganEl(dg)], yang: ganYang(dg), ...DAY_MASTER[GAN_KO[dg]] },
    elements,
    tens,
    yunStart: { years: yun.getStartYear(), months: yun.getStartMonth(), forward: yun.isForward() },
    daewoon,
    current,
    seun,
    monthly,
  };
}

// 특정 날의 월운(절기 기준 월주)과 그해 세운
export function monthAt(dayGanIdxOrKo, date) {
  const dg = typeof dayGanIdxOrKo === 'number' ? dayGanIdxOrKo : GAN_KO.indexOf(dayGanIdxOrKo);
  const l = Solar.fromYmd(date.getFullYear(), date.getMonth() + 1, date.getDate()).getLunar();
  return { month: gzRead(dg, l.getMonthInGanZhiExact()), year: gzRead(dg, l.getYearInGanZhiExact()) };
}

export { TEN_MEANING };
