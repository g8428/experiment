// lib/prompt-reading-v2.js
// 다산역 + 육효점 하이브리드 7섹션 프롬프트 빌더
// index.html의 generateReading에 주입할 buildReadingPrompt(ben, ji, S)

// ── 팔괘 자연물 / 성격 ──
const NAT_MAP = {
  '양양양': { name: '건(乾)', nat: '하늘', char: '강건함·창조·아버지·굳셈' },
  '양음음': { name: '진(震)', nat: '우레', char: '움직임·시작·진동·장남' },
  '음양양': { name: '손(巽)', nat: '바람', char: '들어감·유연함·전파·장녀' },
  '음양음': { name: '감(坎)', nat: '물',   char: '위험·흐름·빠져듦·중남' },
  '양음양': { name: '이(離)', nat: '불',   char: '밝음·문명·아름다움·중녀' },
  '음음양': { name: '간(艮)', nat: '산',   char: '멈춤·굳건함·고요함·막내아들' },
  '양양음': { name: '태(兌)', nat: '연못', char: '기쁨·말·소통·막내딸' },
  '음음음': { name: '곤(坤)', nat: '땅',   char: '수용·포용·순응·어머니' },
};

// ── 64괘 GUA 룩업 (호체 계산용 — 상괘[하괘] 순서) ──
// 키: hi_key → lo_key → {n, no}
const GUA_MAP = {
  '양양양':{'양양양':{n:'중천건',no:1},'양양음':{n:'천택리',no:10},'양음양':{n:'천화동인',no:13},'양음음':{n:'천뢰무망',no:25},'음양양':{n:'천풍구',no:44},'음양음':{n:'천수송',no:6},'음음양':{n:'천산둔',no:33},'음음음':{n:'천지비',no:12}},
  '양양음':{'양양양':{n:'택천쾌',no:43},'양양음':{n:'중택태',no:58},'양음양':{n:'택화혁',no:49},'양음음':{n:'택뢰수',no:17},'음양양':{n:'택풍대과',no:28},'음양음':{n:'택수곤',no:47},'음음양':{n:'택산함',no:31},'음음음':{n:'택지췌',no:45}},
  '양음양':{'양양양':{n:'화천대유',no:14},'양양음':{n:'화택규',no:38},'양음양':{n:'중화이',no:30},'양음음':{n:'화뢰서합',no:21},'음양양':{n:'화풍정',no:50},'음양음':{n:'화수미제',no:64},'음음양':{n:'화산려',no:56},'음음음':{n:'화지진',no:35}},
  '양음음':{'양양양':{n:'뢰천대장',no:34},'양양음':{n:'뢰택귀매',no:54},'양음양':{n:'뢰화풍',no:55},'양음음':{n:'중뢰진',no:51},'음양양':{n:'뢰풍항',no:32},'음양음':{n:'뢰수해',no:40},'음음양':{n:'뢰산소과',no:62},'음음음':{n:'뢰지예',no:16}},
  '음양양':{'양양양':{n:'풍천소축',no:9},'양양음':{n:'풍택중부',no:61},'양음양':{n:'풍화가인',no:37},'양음음':{n:'풍뢰익',no:42},'음양양':{n:'중풍손',no:57},'음양음':{n:'풍수환',no:59},'음음양':{n:'풍산점',no:53},'음음음':{n:'풍지관',no:20}},
  '음양음':{'양양양':{n:'수천수',no:5},'양양음':{n:'수택절',no:60},'양음양':{n:'수화기제',no:63},'양음음':{n:'수뢰둔',no:3},'음양양':{n:'수풍정',no:48},'음양음':{n:'중수감',no:29},'음음양':{n:'수산건',no:39},'음음음':{n:'수지비',no:8}},
  '음음양':{'양양양':{n:'산천대축',no:26},'양양음':{n:'산택손',no:41},'양음양':{n:'산화비',no:22},'양음음':{n:'산뢰이',no:27},'음양양':{n:'산풍고',no:18},'음양음':{n:'산수몽',no:4},'음음양':{n:'중산간',no:52},'음음음':{n:'산지박',no:23}},
  '음음음':{'양양양':{n:'지천태',no:11},'양양음':{n:'지택임',no:19},'양음양':{n:'지화명이',no:36},'양음음':{n:'지뢰복',no:24},'음양양':{n:'지풍승',no:46},'음양음':{n:'지수사',no:7},'음음양':{n:'지산겸',no:15},'음음음':{n:'중지곤',no:2}},
};

// ── 12벽괘 추이 ──
const BYEOKGWE = {
  24: '지뢰복(동지/11월) — 양기가 막 땅 밑에서 되살아나는 시작',
  19: '지택임(대설/12월) — 양이 두 개, 성장 에너지가 쌓이는 시기',
  11: '지천태(입춘/1월) — 음양이 균형 잡혀 태평한 봄',
  34: '뢰천대장(춘분/2월) — 양 에너지가 강하게 전진하는 힘',
  43: '택천쾌(청명/3월) — 결단의 시기, 단호히 내보내야 할 것',
  1:  '중천건(하지전/4월) — 순양, 창조력의 절정, 극양은 이미 꺾임의 예고',
  44: '천풍구(하지/5월) — 음이 하나 돌아옴, 작은 것이 자라기 시작',
  33: '천산둔(소서/6월) — 물러남이 지혜인 시기',
  12: '천지비(입추/7월) — 음양이 막혀 소통이 끊긴 상태',
  20: '풍지관(처서/8월) — 관찰·성찰, 보이지 않던 것이 보임',
  23: '산지박(한로/9월) — 박탈·소멸, 허물을 벗어야 하는 시기',
  2:  '중지곤(입동/10월) — 순음, 겨울 시작, 받아들이고 기다림',
};

// ── 효 위치 의미 ──
const LINE_POS = [
  '초효 — 아직 드러나지 않은 씨앗. 섣부른 행동은 금물.',
  '이효 — 내부 현장. 실무자의 자리, 지금 일이 실제로 일어나는 곳.',
  '삼효 — 내괘의 끝, 외괘로 넘어가는 불안정한 전환점. 결단이 필요한 자리.',
  '사효 — 외괘의 시작. 윗사람 가까이, 신중함이 요구되는 자리.',
  '오효 — 군주의 자리. 이 점괘에서 가장 영향력 있는 변화의 중심.',
  '상효 — 극단. 한계에 다다른 자리. 집착을 내려놓아야 할 때.',
];

// ── 60갑자 계산 ──
const CHEONGAN = ['갑','을','병','정','무','기','경','신','임','계'];
const JIJI = ['자','축','인','묘','진','사','오','미','신','유','술','해'];
const JIJI_OHAENG = { '자':'水','축':'土','인':'木','묘':'木','진':'土','사':'火','오':'Fire','미':'土','신':'金','유':'金','술':'土','해':'水' };
const OHAENG_LABEL = { '木':'목','火':'화','土':'토','金':'금','水':'수','Fire':'화' };

function getYearGanji(year) {
  const idx = ((year - 4) % 60 + 60) % 60;
  return CHEONGAN[idx % 10] + JIJI[idx % 12];
}

function getMonthGanji(year, month) {
  // 연간 기준 월간 오프셋 (갑기년=병인월시작, 을경=무인, 병신=경인, 정임=임인, 무계=갑인)
  const stemIdx = ((year - 4) % 60 + 60) % 60 % 10;
  const monthStemBase = [2, 4, 6, 8, 0, 2, 4, 6, 8, 0][stemIdx]; // 甲己年 → 丙(2)
  const mStem = (monthStemBase + (month - 1)) % 10;
  // 인월(1월) = 지지 인(2번), 월 +1 하면 다음 지지
  const mBranch = (1 + (month - 1)) % 12; // 인=2 → index: 인월=2
  return CHEONGAN[mStem] + JIJI[(2 + month - 1) % 12];
}

function getDayGanji(date) {
  // 기준: 1900-01-31 = 甲子(갑자)일
  const base = new Date(1900, 0, 31);
  const diff = Math.floor((date - base) / 86400000);
  const idx = ((diff % 60) + 60) % 60;
  return CHEONGAN[idx % 10] + JIJI[idx % 12];
}

// 공망: 10간 60갑자에서 순 내 마지막 간지 이후 남는 지지 2개
function getGongmang(dayGanji) {
  const stemIdx = CHEONGAN.indexOf(dayGanji[0]);
  const branchIdx = JIJI.indexOf(dayGanji[1]);
  if (stemIdx < 0 || branchIdx < 0) return ['', ''];
  // 순의 시작 지지
  const순Start = (branchIdx - stemIdx + 12) % 12;
  const gm1 = JIJI[(순Start + 10) % 12];
  const gm2 = JIJI[(순Start + 11) % 12];
  return [gm1, gm2];
}

// ── 효 자연 key에서 음양 추출 ──
function throwsToNats(throws) {
  // throws: [{sum},...] sum 6/9=변효, 7=소양(양), 8=소음(음), 9=노양(양→음변), 6=노음(음→양변)
  if (!throws || throws.length !== 6) return null;
  return throws.map(t => (t.sum === 7 || t.sum === 9) ? '양' : '음');
}

// ── 호체 계산 ──
function calcHoche(nats) {
  if (!nats || nats.length < 6) return null;
  // 내호체: 2·3·4효 (index 1,2,3) — 하괘=1,2,3 상괘= 사실상 호체는 6효괘 전체
  // 정통: 내호체(하호, 2~4효), 외호체(상호, 3~5효)
  const 내Lo = nats[1] + nats[2] + nats[3];
  const 외Hi = nats[2] + nats[3] + nats[4];
  const hoche = GUA_MAP[외Hi]?.[내Lo];
  const 내체 = NAT_MAP[내Lo];
  const 외체 = NAT_MAP[외Hi];
  if (!hoche) return null;
  return {
    gua: hoche,
    naeHo: 내체 ? 내체.nat : 내Lo,
    oaeHo: 외체 ? 외체.nat : 외Hi,
  };
}

// ── 서법 변효 개수별 포커스 규칙 ──
function seobeopFocus(chg, benNo) {
  const n = chg.length;
  const labels = ['초효','이효','삼효','사효','오효','상효'];
  if (n === 0) return {
    rule: '변효 0개 → 본괘 괘사만',
    guide: '지금 상황은 고정되어 있다. 움직이지 말고 본괘의 메시지를 그대로 받아들일 것.',
  };
  if (n === 1) return {
    rule: `변효 1개(${labels[chg[0]]}) → 변효 효사가 메인. 본괘 괘사는 배경, 지괘는 귀결`,
    guide: `${labels[chg[0]]}의 효사가 이 점의 핵심 메시지다. ${LINE_POS[chg[0]]}`,
    mainLine: chg[0],
  };
  if (n === 2) return {
    rule: `변효 2개(${chg.map(i=>labels[i]).join(', ')}) → 위쪽 효(${labels[Math.max(...chg)]}) 위주, 아래 효 보조`,
    guide: `${labels[Math.max(...chg)]}가 주효. ${LINE_POS[Math.max(...chg)]}`,
    mainLine: Math.max(...chg),
  };
  if (n === 3) return {
    rule: '변효 3개 → 본괘·지괘 괘사 비교 중심. 효사보다 괘의 큰 흐름이 중요한 시점',
    guide: '지금은 개별 효 하나보다 두 괘 사이의 전환 자체가 메시지다.',
  };
  if (n === 4) return {
    rule: '변효 4개 → 지괘(변괘) 하괘 중 불변효를 주목',
    guide: '변하지 않는 것이 오히려 이 상황의 본질이다.',
  };
  if (n === 5) return {
    rule: '변효 5개 → 남은 불변효 하나의 지괘 쪽 효사',
    guide: '단 하나 변하지 않은 효에 이 점의 핵심이 응축되어 있다.',
  };
  if (n === 6) {
    if (benNo === 1) return { rule: '건괘 6효 전변 → 용구(用九) 효사', guide: '건의 순수한 양이 완전히 뒤집힌다. 용구를 보라.' };
    if (benNo === 2) return { rule: '곤괘 6효 전변 → 용육(用六) 효사', guide: '곤의 순수한 음이 완전히 뒤집힌다. 용육을 보라.' };
    return { rule: '변효 6개 → 지괘 괘사만', guide: '완전 전환. 모든 것이 바뀌었다. 지괘의 세계가 이미 시작되었다.' };
  }
  return { rule: '', guide: '' };
}

// ── 메인 함수 ──
export function buildReadingPrompt(ben, ji, S) {
  const now = new Date();
  const yearGj = getYearGanji(now.getFullYear());
  const monthGj = getMonthGanji(now.getFullYear(), now.getMonth() + 1);
  const dayGj = getDayGanji(now);
  const [gm1, gm2] = getGongmang(dayGj);
  const dateStr = `${now.getFullYear()}년 ${now.getMonth()+1}월 ${now.getDate()}일 (${yearGj}년 ${monthGj}월 ${dayGj}일)`;

  const labels = ['초효','이효','삼효','사효','오효','상효'];
  const chg = S.chg || [];
  const chgCount = chg.length;

  // ── 본괘 효 nats 계산 ──
  const nats = throwsToNats(S.throws);
  const loKey = nats ? nats.slice(0,3).join('') : null;
  const hiKey = nats ? nats.slice(3,6).join('') : null;
  const loInfo = loKey ? NAT_MAP[loKey] : null;
  const hiInfo = hiKey ? NAT_MAP[hiKey] : null;

  // ── 물상 ──
  const mulSang = (loInfo && hiInfo)
    ? `하괘=${loInfo.nat}(${loInfo.char}) / 상괘=${hiInfo.nat}(${hiInfo.char})\n   형상: "${hiInfo.nat} 아래 ${loInfo.nat}이 있는 그림"`
    : '(본괘 하괘·상괘의 자연물 상징을 물상으로 펼쳐서 현재 상황을 그림처럼 묘사할 것)';

  // ── 호체 ──
  let hocheStr = '(계산 불가 — 호체로 드러나는 숨은 구조를 추론해서 서술할 것)';
  if (nats) {
    const hoche = calcHoche(nats);
    if (hoche) {
      hocheStr = `${hoche.gua.n}(${hoche.gua.no}번)\n   내호체=${hoche.naeHo} / 외호체=${hoche.oaeHo}\n   → 표면 아래 실제로 움직이는 내부 구조, 아직 드러나지 않은 맥락`;
    } else {
      hocheStr = '호체 도출 불가 (순수 중괘 등). 표면에 보이는 것이 전부인 상황.';
    }
  }

  // ── 추이 ──
  const benNo = S.benGua?.no;
  const byeokEntry = BYEOKGWE[benNo];
  const chuiStr = byeokEntry
    ? `이 괘는 12벽괘 중 하나: ${byeokEntry}`
    : `비벽괘(非辟卦) — 12벽괘 흐름 안에서 변형된 괘. 고정된 계절 에너지가 아니라 두 벽괘 사이 어딘가의 전환적 상태.`;

  // ── 변효 효사 ──
  const chgHyosaLines = chgCount > 0
    ? chg.map(i => {
        const hs = ben?.hy?.[i] || '(효사 없음)';
        return `  ${labels[i]}(${i+1}번째, 아래에서 ${i+1}번): "${hs}"\n  위치 의미: ${LINE_POS[i]}`;
      }).join('\n')
    : '  없음';

  // ── 서법 규칙 ──
  const focus = seobeopFocus(chg, benNo);

  // ── 육효점 날짜 간지 정보 ──
  const gongmangStr = (gm1 && gm2) ? `공망지(空亡支): ${gm1}·${gm2} — 이 지지(地支)에 해당하는 효는 "아직 실체가 없거나 비어있는 상태"` : '(공망 계산 불가)';

  // ── Q&A ──
  const qap = (S.q5 && S.a5 && S.q5.length > 0)
    ? S.q5.map((q, i) => `  Q${i+1}. ${q}\n  A. ${S.a5[i] || '(답변 없음)'}`).join('\n\n')
    : '  (없음)';

  // ── 괘 기본 정보 ──
  const benName = S.benGua ? `${S.benGua.n}(${S.benGua.no}번)` : '?';
  const jiName  = S.jiGua  ? `${S.jiGua.n}(${S.jiGua.no}번)`   : '없음 (변효 없음)';
  const benSummary = ben
    ? `${benName}\n   괘사: ${ben.k}\n   핵심 기운: ${ben.v}\n   대상전(大象傳): ${ben.dst}`
    : benName;
  const jiSummary = ji
    ? `${jiName}\n   괘사: ${ji.k}\n   핵심 기운: ${ji.v}`
    : jiName;

  return `당신은 사주명리와 주역점사 전문가입니다. 아래 데이터로 ${S.name||'상담자'}님의 점사 리포트를 작성하세요.

━━━━━━━━ 기본 정보 ━━━━━━━━
이름: ${S.name || '상담자'}
고민: ${S.q || '(없음)'}
점친 날: ${dateStr}

━━━━━━━━ 괘 데이터 ━━━━━━━━
본괘: ${benSummary}
지괘: ${jiSummary}
변효: ${chgCount}개 ${chgCount > 0 ? `(${chg.map(i=>labels[i]).join(' · ')})` : ''}

변효 효사 원문:
${chgHyosaLines}

서법(筮法) 해석 규칙:
${focus.rule}
→ ${focus.guide}

━━━━━━━━ 다산역(茶山易) 분석 데이터 ━━━━━━━━
[물상(物象)] ${mulSang}

[호체(互體)] ${hocheStr}

[추이(推移)] ${chuiStr}

[효변(爻變)] ${chgCount > 0
  ? chg.map(i => `${labels[i]}: ${LINE_POS[i]}`).join(' / ')
  : '변효 없음 — 현재 상황이 고정된 구조임을 물상·호체로 읽을 것'}

━━━━━━━━ 육효점(六爻占) 날짜 간지 ━━━━━━━━
점친 날 일진: ${dayGj}일 (${yearGj}년 ${monthGj}월)
${gongmangStr}

→ 이 간지 정보를 활용해 섹션 3(점괘의 심장)과 섹션 5(시기)에서 효들과의 에너지 흐름을 서술형으로 자연스럽게 엮을 것.
   "세효는 壬午이고..." 같은 기계적 나열 절대 금지. 대신:
   "이 날의 기운이 오효를 짓누른다", "지금 달의 에너지가 변효 쪽을 돕고 있다" 처럼 풀어쓸 것.

━━━━━━━━ 추가 질문·답변 ━━━━━━━━
${qap}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 작성 규칙 (반드시 지킬 것)

절대 하지 말 것:
1. "이것은 이러이러한 뜻입니다" 식 사전적·원론적 설명
2. 괘마다 결론이 "중심을 지켜라", "바름을 잃지 말라"로 수렴
3. 사용자 질문 원문을 그대로 복붙 인용
4. "AI로서", "점사를 생성하면" 등 AI 티 나는 표현
5. 전문 용어(세효·응효·납갑 등)를 수치·표 형태로 나열
6. 변효 효사 없이 자의적 해석만 늘어놓기
7. 여러 경계사항 나열 — 조심할 것은 딱 1가지만

반드시 할 것:
1. 변효 효사 원문을 큰따옴표로 정확히 인용하고, 인용 바로 뒤에 쉬운 현대어 풀이를 붙임
2. 구체적 시기 구간 제시 — "이번 달은 ~, 다음 달 말부터는 ~" 형태의 캘린더 대응 시간 구간
3. 짧고 힘 있는 문단, 담담하고 깊은 톤 (타로 마스터처럼 — 호들갑 없이)
4. 서법 규칙에 따른 포커스를 실제로 지킬 것
5. 이름(${S.name||'상담자'})을 자연스럽게 1~2회 언급
6. 마지막에 한 줄 핵심 메시지로 응축
7. 최종 선택은 본인 몫이라는 여지를 남기며 마무리

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 출력 형식 — 순수 JSON만, 마크다운 코드블록 없이

{
  "headline": "한 문장 핵심 총평. 소제목처럼 짧고 인상적으로. 괘 이름이나 자연물 이미지를 쓸 것.",
  "sections": [
    {
      "tag": "지금 서 있는 자리",
      "title": "재치 있는 3~6자 제목",
      "content": "다산역 물상으로 현재 상황을 그림처럼 묘사. 상괘·하괘가 만드는 구체적 장면 → 호체로 드러나는 숨은 맥락 → 변효 위치가 말하는 지금 이 변화의 성격. 이름 직접 언급. 짧은 문단 3~4개."
    },
    {
      "tag": "이 점괘의 심장",
      "title": "재치 있는 3~6자 제목",
      "content": "${chgCount === 0
        ? '변효 없음 — 본괘 괘사 원문 큰따옴표 인용 + 바로 쉬운 풀이. 일진과의 에너지 흐름 서술. 지금 상황이 고정된 구조임을 짧게 전달. 3~4문단.'
        : '변효 효사 원문 큰따옴표 인용 + 즉각 쉬운 풀이. 서법 규칙상 포커스 효사를 메인으로. 일진 기운과 변효의 상호작용을 서술형으로. 3~4문단.'}"
    },
    {
      "tag": "방향",
      "title": "재치 있는 3~6자 제목",
      "content": "${ji ? '지괘가 말하는 귀결의 성격. 지괘 괘사·핵심 인용 후 "이쪽으로 흘러간다"는 방향 서술. 2~3문단.' : '변효 없음 — 지금 상황이 그대로 유지된다. 고정된 에너지 안에서 어디를 향해야 하는지. 2~3문단.'}"
    },
    {
      "tag": "시기",
      "title": "재치 있는 3~6자 제목",
      "content": "구체적 시간 구간별 가이드. 추이 계절 에너지 + 일진 간지 흐름을 근거로. 예: '이번 달(${now.getMonth()+1}월)은 ~, 다음 달부터는 ~, 3개월 후에는 ~'. 언제 움직임이 오는지 명확히 답할 것. 3~4문단."
    },
    {
      "tag": "조심할 것",
      "title": "재치 있는 3~6자 제목",
      "content": "경계 포인트 딱 1가지. 여러 개 나열 절대 금지. 짧고 명확하게. 1~2문단."
    },
    {
      "tag": "마무리",
      "title": "",
      "content": "한두 문장. 담담하고 깊게. 선택은 본인 몫이라는 여지를 남기며 끝."
    }
  ],
  "closing_line": "이 점괘의 핵심 한 줄 메시지. 짧고 진하게. 의문문이나 명령형도 가능."
}`;
}

// 브라우저 전역 노출 (index.html에서 window.buildReadingPrompt로 접근)
if (typeof window !== 'undefined') {
  window.buildReadingPrompt = buildReadingPrompt;
}
