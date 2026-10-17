// 주역 점사 그래프. 화자는 역술가 '연서'. 독자가 궁금한 순서(답 → 왜 → 무엇을 → 언제)로 리포트를 만든다.
//
//   analyze_hexagram ─▶ plan_reading ─┬▶ write_open  질문에 대한 답 · 지금의 형세(본괘)
//   (괘 데이터만)        (편집장 구성안)  ├▶ write_core  이 점의 심장(변효/불변효) · 흘러가는 곳(지괘) · 할 것/피할 것
//                                      └▶ write_tail  때(타임라인) · 남겨 주신 답에(질문별) · 마무리
//                                               ▼
//                                     assemble (코드) → 리포트 객체
//
// 왜 구성안 노드가 있나(2026-10-17): 작가들이 같은 원문을 받아 서로 모른 채 병렬로 쓰면 같은 효사 인용이 5개 섹션에
// 반복되고, 계절·사정이 섹션마다 어긋났다. 구성안이 판정·키워드·국면(season)·상담자 사실(facts)·섹션별 메시지(points)·
// 인용 배정(quotes)을 한 번 정하고, 작가들은 그 기준과 자기 섹션 원문만 받아 확장한다.
// 2026-10-06에 배운 것도 유지: 작가는 분석 메모만이 아니라 원문 조각(input.src)을 직접 받는다(메모만 주면 괘 이름이 사라진다).

const MODEL = 'claude-haiku-4-5-20251001';
const MAX_ATTEMPTS = 3;
// api/reading.js는 vercel.json에서 maxDuration 120초(Hobby + Fluid compute 한도는 300초). 그 안에서 응답을 돌려주도록
// 전체 마감을 GRAPH_BUDGET_MS로 둔다. 가끔 한 호출만 30초 넘게 멈추는 일이 있어서(2026-10-05 트레이스)
// 노드별 시도 시간을 끊고 다시 부르는 쪽이 빠르다. 평소 한 편은 30~40초.
const GRAPH_BUDGET_MS = 100000;

class NodeError extends Error {
  constructor(message, { status = 502, retryable = true } = {}) {
    super(message);
    this.status = status;
    this.retryable = retryable;
  }
}

const str = (description) => ({ type: 'string', description });
const obj = (properties) => ({ type: 'object', properties, required: Object.keys(properties) });
const arr = (items, description, minItems, maxItems) => ({ type: 'array', items, description, ...(minItems != null && { minItems }), ...(maxItems != null && { maxItems }) });
// optional: 모델이 가끔 빼먹는데 없어도 리포트가 되는 필드 — 빠졌다고 노드 전체를 다시 부르지 않는다
const tool = (name, description, properties, optional = []) => ({
  name, description,
  input_schema: { type: 'object', properties, required: Object.keys(properties).filter((k) => !optional.includes(k)) },
});
// 모델이 가끔 중첩 객체·배열을 JSON 문자열로 돌려준다 — 스키마가 객체·배열인 자리의 문자열은 풀어서 쓴다
function coerce(schema, v) {
  if ((schema?.type === 'object' || schema?.type === 'array') && typeof v === 'string') {
    try { v = JSON.parse(v); } catch { return v; }
  }
  if (schema?.type === 'object' && v && typeof v === 'object' && !Array.isArray(v)) {
    return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, coerce(schema.properties?.[k], x)]));
  }
  if (schema?.type === 'array' && Array.isArray(v)) return v.map((x) => coerce(schema.items, x));
  return v;
}
// 중첩 객체·배열까지 required 필드가 빠졌는지 본다(맨 위만 보면 verdict 속 kind가 빠진 채로 화면까지 갔다)
function missingFields(schema, v, path = '') {
  if (schema?.type === 'object') {
    if (!v || typeof v !== 'object') return [path || '(전체)'];
    return (schema.required || []).flatMap((k) => (v[k] == null ? [path + k] : missingFields(schema.properties?.[k], v[k], `${path}${k}.`)));
  }
  if (schema?.type === 'array' && Array.isArray(v)) return v.flatMap((x, i) => missingFields(schema.items, x, `${path}${i}.`));
  return [];
}
const json = (o) => JSON.stringify(o);
const block = (title, text) => (text && String(text).trim() ? `[${title}]\n${String(text).trim()}` : '');
const lines = (...parts) => parts.filter(Boolean).join('\n\n');
const qaText = (qa) => qa.map((x, i) => `Q${i + 1}. ${x.q}\nA. ${x.a}`).join('\n') || '(추가 문답 없음)';

const HANJA_RULE = `- 한자는 한 글자도 쓰지 않습니다. 괄호 속 한자("감(坎)"), 한자 인용, 지지·간지(子丑寅卯辰巳午未申酉戌亥, 壬午 등)도 금지입니다. 괘 이름·자연 상징·절기는 한글로만 씁니다.
- 시기는 하루짜리 날짜("10월 14일", "○일 무렵")로 말하지 않습니다. "빠르면 다음 주, 늦어도 두 달 안", "올해 안"처럼 폭이 있는 범위로만 씁니다. 지지의 한글 읽기("술월", "자일", "진월", "유월")도 쓰지 않습니다.
- 육효 용어(공망, 출공, 세효, 응효, 용신, 월건, 일진, 동효)는 쓰지 않고 뜻으로 풀어 씁니다(예: "막혀 있던 일이 풀리는 때", "상대 쪽 사정").
- "추계", "하계" 같은 딱딱한 한자어 대신 "가을", "여름"처럼 쉬운 말을 씁니다.`;

/* ── 화자 '연서'와 공통 문체: 쓰기 노드(write_*)에만 붙는다 ── */
const VOICE = `[화자 — 연서]
- 화자는 '연서'입니다. 30대 초반의 역술가로, 주역을 오래 공부했고 또래에게 상담하듯 차분하고 섬세하게 말합니다.
- 해요체 존댓말이 기본입니다("괘가 나왔어요", "이 자리는 이렇게 읽혀요"). 무게를 실어야 하는 판단 한두 곳에서만 하십시오체("돌려 말하지 않겠습니다")를 씁니다. 반말 종결("~어.", "~다.", "~지.", "~야.")은 한 문장도 쓰지 않습니다.
- 1인칭은 "저"입니다("제가 보기엔", "이 괘에서 제 눈에 먼저 들어온 건"). 판단의 근거는 언제나 괘·효로 댑니다.
- 상담자는 "이름+님"으로 부르되 한 섹션에 많아야 한 번입니다. 주어가 분명하면 이름을 빼고 씁니다. "당신"이라고 쓰지 않습니다.

[구성안을 따릅니다 — 가장 중요]
- [구성안]의 point는 이 섹션의 제목으로 화면에 크게 나옵니다. 본문 첫 문장에서 제목을 되풀이하지 말고 바로 장면이나 근거로 들어갑니다. 다른 섹션의 메시지를 끌어오지 않습니다.
- 인용은 [구성안]이 이 섹션에 배정한 문구만 따옴표로 그대로, 한 번만 씁니다. 배정되지 않은 괘사·효사·대상전은 인용하지 않습니다.
- 계절·국면(season)은 화면의 「때」 카드에 따로 나옵니다. 다른 섹션에서는 그 문장을 옮겨 적거나 계절을 다시 말하지 않습니다. 꼭 필요하면 season과 같은 뜻으로 몇 단어만 쓰고, 다른 계절·절기를 새로 꺼내지 않습니다.
- 상담자의 사정은 [구성안]의 facts에 있는 것만 씁니다. "이미 결정하셨으니"처럼 말하지 않은 사정을 가정하지 않습니다.
- 시기 표현("11월 초", "12월 중순", "다음 주", "두 달 안")은 「때」에서만 씁니다. 다른 섹션에서는 시기를 꺼내지 않습니다 — 같은 시기가 다섯 군데 되풀이된 일이 있었습니다.
- 괘사·효사·대상전 원문은 화면에 따로 상자로 보입니다. 본문에서 원문을 따옴표로 다시 옮겨 적지 않고, "괘사가 말하는 곤궁은 …"처럼 그 말이 지금 무엇을 가리키는지만 풉니다.
- 판정 한 줄(verdict.line)과 판정 이유(reasons)는 화면 맨 위에 따로 나옵니다. 그 문장을 되풀이하지 않고, 이 섹션에서만 할 수 있는 이야기를 씁니다.

[쉬운 말 — 해설서 문장이 아니라 사람에게 하는 말]
- 친한 언니·누나가 카페에서 말해 주듯 생활 말로 씁니다. 해설서·번역서 문장을 옮기지 않습니다.
- 이렇게 바꿉니다: "외부 진입이 지연되고 있다" → "회사 밖으로 나가는 일이 생각보다 늦어지고 있어요" / "물질적·외적 제약" → "돈이나 주변 여건" / "불굴의 의지가 형태를 갖춘 것" → "포기하지 않고 실제로 만들어 낸 것" / "결과 도출이 예상된다" → "결과가 보이기 시작할 수 있어요".
- 피할 말: 진입, 지연, 물질적, 외적, 내적, 제약, 불굴, 도출, 시사, 측면, 요소, 형태를 갖추다, ~에 해당하다.
- 추상어보다 상담자의 실제 장면을 씁니다("퇴사 날짜를 먼저 정하기보다, 첫 고객 한 명을 먼저 찾는 쪽").

[읽는 법]
- 괘 원문이 풀이의 주인입니다. 괘 이름과 효 위치를 직접 짚습니다("수화기제는 …", "오효는 …").
- 상괘·하괘의 자연 상징(물·불·산·못·바람·우레·하늘·땅)으로 장면을 그리듯 풀고, 그 그림이 상담자의 지금과 어떻게 겹치는지 보여 줍니다.
- 용어(본괘·지괘·변효·불변효·대상전·호체)는 처음 나올 때 한 구절로 풀어 줍니다("지괘, 곧 이 일이 흘러가 닿는 괘").

[문체]
- 결론부터, 돌려 말하지 않습니다. "~일 수도 있어요"를 남발하지 않습니다. 조심할 점도 분명히 말하되 겁주지 않습니다.
- 권할 때는 사람이 실제로 하는 말처럼 "~해 보세요", "~해 두세요", "~하는 게 좋아요", "~는 미뤄 두세요"를 섞어 씁니다. "~하십시오", "~해야 합니다", "~하라"는 쓰지 않습니다.
- 같은 문장 끝을 되풀이하지 않습니다. "~쪽이 좋아요", "~라는 뜻이에요", "~거예요", "~중요해요", "~핵심이에요"는 한 섹션에 한 번까지. 기계가 찍어 낸 것처럼 문장마다 같은 끝맺음이 이어지면 바로 티가 납니다.
- 글의 짜임을 설명하지 않습니다("이 섹션에서는", "다른 각도로 보면", "정리하면", "~로 보면"). 바로 내용을 말합니다.
- 문단은 2~4문장. 정해진 길이를 넘기지 않습니다.
${HANJA_RULE}
- 금지: 원론 설명("~라는 것은 ~라는 뜻입니다"), "중심을 지켜라"식 결론, 날짜·서명, "에너지", "기운이 감싼다" 같은 막연한 말.`;

const writerSystem = (parts, toolName, rules) =>
  `점사 리포트 가운데 ${parts}을 ${toolName} 도구로 씁니다.

[이 부분의 규칙]
${rules}

${VOICE}`;

/* ── 노드 1: 괘 분석 — 상담자의 고민을 모르는 채로 괘 데이터만 읽는다 ── */
const ANALYZE = {
  name: 'analyze_hexagram',
  temperature: 0.2,
  timeoutMs: 25000,
  maxTokens: 1800,
  system: `당신은 주역·다산역·육효점 해석가입니다. 상담자의 고민을 모르는 채로 괘 데이터만 읽고, 뒤 단계가 쓸 해석 재료를 record_hexagram 도구로 메모합니다.
- 메모입니다. 꾸미지 않되 판단의 근거(어느 괘·어느 효·어느 상징)를 이름으로 남깁니다. 각 필드 1~2문장.
- 데이터에 없으면 빈 문자열이나 빈 배열로 둡니다.
- 변효 개수별 [해석 원칙]을 따르고, 어떤 효를 읽을지는 [심장 규칙]이 정합니다.
- 효사는 데이터의 국문 문구 그대로 옮기고, 한자를 만들어 붙이지 않습니다. 메모에는 한자를 쓰지 않습니다. 지지·간지(酉, 戌 같은 한자도, "술월"·"자일" 같은 한글 읽기도)는 어느 필드에도 쓰지 말고 "10월 14일"처럼 숫자 날짜·달로만 적습니다.
- 시기는 [추이 — 계절 국면]과 [시기 판단 근거 — 육효 응기]에서만 고릅니다. 세효·용신·동효의 응기 후보만, 가까운 일은 날짜, 먼 일은 달로. 블록에 없는 달·어림 숫자 금지.`,
  tool: tool('record_hexagram', '괘 데이터만으로 해석 재료를 메모한다', {
    fortune: { type: 'string', enum: ['길', '소길', '평', '조심', '흉'], description: '전체 길흉 기조' },
    why: str('길흉 근거 1~2문장 (어느 괘사·효사 때문인지)'),
    image: str('물상 — 본괘 상괘·하괘의 자연 상징이 그리는 장면 1~2문장'),
    phase: str('추이 — 자라는 국면인지 거두는 국면인지와 근거 1~2문장'),
    hidden: str('호체 — "겉은 ~, 안은 ~" 1문장. 데이터 없으면 빈 문자열'),
    flow: str('본괘 → 중심 효 → 지괘로 이어지는 이야기 한 줄'),
    heart: str('이 점괘의 핵심 메시지 1~2문장 (읽는 효의 위치와 그 자리의 의미 포함)'),
    direction: str('지괘(없으면 본괘)가 가리키는 방향 1~2문장'),
    liuyao: str('세효·응효·공망 등의 의미 1~2문장. 계산값 나열 금지'),
    season: str('시기 국면 + 가까운 일인지 먼 일인지 1문장'),
    windows: arr(obj({
      when: str('숫자 날짜·달만. 예: "10월 17일 무렵", "2027년 4월". 지지·간지는 쓰지 않음'),
      why: str('근거. 예: "세효 값", "용신 합"'),
      what: str('그때 움직이는 일'),
    }), '응기에서 고른 시기 창. 근거 없으면 빈 배열', 0, 3),
  }, ['image', 'phase', 'hidden', 'flow', 'heart', 'direction', 'liuyao', 'season', 'windows']),
  user: ({ input }) => lines(`오늘: ${input.today}`, input.hexagram, block('심장 규칙', input.heartRule)),
};

/* ── 노드 2: 구성안(편집장) — 리포트 전체의 단일 기준을 정한다. 이후 작가들은 이 기준만 따른다 ── */
// 출력은 평평한 필드로 받는다 — 중첩 객체(verdict·points·quotes·bubbles)로 받았을 때 Haiku가 객체째 빼먹는 일이 잦았다.
// 작가 노드가 쓰기 편하게 nestPlan()이 다시 묶는다.
const PLAN = {
  name: 'plan_reading',
  styleSkip: ['facts', 'keywords', 'point_shape', 'point_heart', 'point_flow', 'point_dos', 'point_donts', 'quote_shape', 'quote_flow', 'quote_dos'],
  noQuote: ['verdict_label', 'verdict_line', 'reasons', 'empathy', 'bubble_heart', 'bubble_flow', 'bubble_timing', 'season'],
  noTiming: true,
  timingOk: ['season'], // season은 「때」 카드 맨 위에 나오니 달 이름이 있어도 된다 — 이것 때문에 구성안을 다시 쓰면 순차 구간이 8~10초 늘었다
  temperature: 0.3,
  timeoutMs: 20000,
  maxTokens: 1800,
  checkStyle: true,
  system: `당신은 주역 점사 리포트의 편집장입니다. 괘 분석 메모·괘 원문·상담자의 고민과 문답을 보고, 화자 '연서'가 쓸 리포트의 기준을 plan_reading 도구로 한 번에 정합니다. 이 기준이 섹션 사이의 반복과 모순을 막습니다.
- verdict_kind: 고민에 대한 분명한 판정. go(해도 좋다) / wait(아직 때가 아니다) / conditional(조건이 맞으면 좋다) / no(하지 않는 편이 길하다) / general(고민 없이 본 점). 괘 분석의 길흉 기조와 어긋나지 않게 정합니다.
- verdict_label: 연서가 건네는 판정 한 마디(해요체, 20자 안팎. 예: "떠나도 괜찮아요, 조건이 하나 있어요").
- verdict_line: 리포트 전체를 한 줄로(30자 안팎). 명사형이나 해요체로 끝내고 "~열린다."처럼 반말로 끝내지 않습니다.
- reasons: 2~3개. 각각 근거가 된 괘나 효 이름을 넣은 해요체 한 문장. 원문 문구를 따옴표로 옮기지 말고 뜻으로 풀어 쓰고(인용은 각 섹션 몫), 날짜는 넣지 않습니다.
- keywords: 이 점을 요약하는 명사형 단어 3개(2~6자, 해시태그 없이).
- season: 지금의 국면을 해요체 한 문장(50자 안팎, 쉬운 말)으로 확정합니다. 날짜·괘 이름·벽괘 이름은 넣지 않습니다. 분석 메모와 [추이] 블록을 따르고 다른 계절·절기를 새로 만들지 않습니다. 이후 모든 섹션은 이 문장만 씁니다.
- facts: 상담자가 고민·문답에서 실제로 말한 사실만 3~6개. 짐작이나 해석은 넣지 않습니다.
- empathy: 연서가 여는 공감 한 문장(해요체). 상담자가 쓴 말을 빌려 지금의 갈등을 짚습니다.
- point_shape / point_heart / point_flow / point_dos / point_donts: 섹션 제목입니다. 화면에 크게 나오니 잡지 기사 소제목처럼 장면이 보이게, 18자 안팎으로 씁니다. "지금의 형세", "이 점의 핵심"처럼 섹션 이름을 설명하는 말은 제목이 아닙니다. 서로 겹치지 않게: shape=본괘 그림이 말하는 지금(예: "물이 다 빠진 연못 앞이에요"), heart=중심 효가 고민에 답하는 것(예: "금 수레는 늦게 와도 와요"), flow=지괘가 보여 주는 귀결(예: "험한 물길을 두 번 건너는 일"), dos=지금 해 둘 일의 큰 줄기(예: "바닥이 드러났을 때 할 일"), donts=멀리할 일의 큰 줄기(예: "서둘러 문을 열지 않기").
- quote_shape / quote_flow / quote_dos: 입력 원문에서 글자 그대로 복사해 섹션에 하나씩 배정합니다. shape=본괘 괘사 풀이, flow=지괘 괘사 풀이(지괘가 없으면 빈 문자열), dos=본괘 대상전 풀이. 효사는 효 읽기 섹션이 효마다 한 번씩 인용하므로 여기서 배정하지 않습니다.
- 어느 필드에도 하루짜리 날짜("○월 ○일")를 쓰지 않습니다.
- bubble_heart / bubble_flow / bubble_timing: 그 섹션 앞에서 연서가 상담자에게 건네는 짧은 혼잣말 같은 한마디(해요체, 30자 안팎). 다음 섹션을 소개하지 말고("~를 볼게요", "제일 중요한 자리예요" 금지), 상담자의 사정(facts)을 짚은 한마디를 합니다. 예: "6개월이면 짧지 않아요. 그래도 이 효는 서두르지 말래요.", "배우자분 걱정이 괜한 게 아니었네요." verdict_line·reasons·season을 되풀이하지 않고 시기(달·주)를 넣지 않습니다.
- verdict_line·reasons·point_*는 서로 다른 말이어야 합니다. 같은 원문 구절(예: "믿음을 잃지 않으면")을 두 필드 이상에 쓰지 않습니다.
- 모든 필드는 해설서 말투가 아닌 쉬운 생활 말로 씁니다(진입·지연·제약·물질적·외적·도출 같은 말 대신 "나가는 일", "늦어지는", "돈이나 여건").
- mood: 판정을 말할 때 연서의 표정. smile(길·소길), serious(조심·흉), warm(평·general).
- 화면에 그대로 나가는 필드(verdict_*, reasons, empathy, season, bubble_*)는 해요체 존댓말로 쓰고, "당신"이라 부르지 않으며, "에너지"·"기운" 같은 막연한 말과 육효 용어(공망·세효·응효·용신 등)를 쓰지 않습니다.
${HANJA_RULE}`,
  tool: tool('plan_reading', '리포트 전체의 판정·기준·섹션별 메시지와 인용 배정을 정한다', {
    verdict_kind: { type: 'string', enum: ['go', 'wait', 'conditional', 'no', 'general'] },
    verdict_label: str('판정 한 마디, 해요체 20자 안팎. 예: "떠나도 괜찮아요, 조건이 하나 있어요"'),
    verdict_line: str('리포트 전체 한 줄, 30자 안팎. 명사형이나 해요체. 예: "정성으로 시작하고 끝까지 살피는 길"'),
    reasons: arr(str('근거 괘·효 이름을 넣은 해요체 한 문장. 예: "수화기제 오효가 소박한 정성을 길하다고 말해요."'), '판정 이유', 2, 3),
    keywords: arr(str('명사형 2~6자'), '요약 단어 3개', 3, 3),
    season: str('지금의 국면, 해요체 한 문장. 예: "가을이 깊어지며 하나씩 정리하는 때예요."'),
    facts: arr(str('상담자가 실제로 말한 사실'), '상담자 사실 3~6개', 0, 6),
    empathy: str('연서의 공감 한 문장, 해요체. 예: "준비는 해 두셨는데 막상 떠나려니 마음이 무거우시죠."'),
    point_shape: str('본괘 섹션 제목, 18자 안팎, 장면이 보이게'),
    point_heart: str('중심 효 섹션 제목, 18자 안팎'),
    point_flow: str('지괘 섹션 제목, 18자 안팎'),
    point_dos: str('해 둘 일 섹션 제목, 18자 안팎'),
    point_donts: str('멀리할 일 섹션 제목, 18자 안팎'),
    quote_shape: str('본괘 괘사 풀이 그대로'),
    quote_flow: str('지괘 괘사 풀이 그대로, 없으면 빈 문자열'),
    quote_dos: str('본괘 대상전 풀이 그대로'),
    bubble_heart: str('중심 효 앞 한마디, 해요체, 상담자 사정을 짚는 말'),
    bubble_flow: str('지괘 앞 한마디, 해요체, 상담자 사정을 짚는 말'),
    bubble_timing: str('시기 앞 한마디, 해요체, 상담자 사정을 짚는 말'),
    mood: { type: 'string', enum: ['smile', 'serious', 'warm'] },
  }, ['quote_flow', 'facts']),
  user: ({ input, analysis: a }) => lines(
    block('괘 분석 메모', json(without(a, ['windows']))), // 시기 창은 「때」 작가 몫 — 구성안에 주면 달 이름을 여기저기 옮겨 적었다
    input.src.ben,
    input.src.ji,
    block('중심 자리', input.src.lines),
    input.src.tui,
    `[상담자] ${input.name}\n고민: ${input.question}\n${qaText(input.qa)}`,
  ),
};

function nestPlan(f) {
  return {
    verdict: { kind: f.verdict_kind, label: f.verdict_label, line: f.verdict_line, reasons: f.reasons },
    keywords: f.keywords,
    season: f.season,
    facts: f.facts || [],
    empathy: f.empathy,
    points: { shape: f.point_shape, heart: f.point_heart, flow: f.point_flow, dos: f.point_dos, donts: f.point_donts },
    quotes: { shape: f.quote_shape, flow: f.quote_flow || '', dos: f.quote_dos },
    bubbles: { heart: f.bubble_heart, flow: f.bubble_flow, timing: f.bubble_timing },
    mood: f.mood,
  };
}

/* ── 노드 3: 쓰기 노드들 — 구성안 뒤에 병렬로 돈다. 구성안 + 자기 섹션 원문만 받는다 ──
   2026-10-17 피드백으로 효 읽기(write_yao)와 질문별 답(write_qa)을 따로 뗐다: 한 노드에 몰았더니 효사는 한두 줄,
   질문 답은 한 마디로 줄어들었다. 변효가 없으면 여섯 효를 초반·중반·후반 흐름으로 하나씩 읽는다. */
const STAGE_RULE = `효의 자리는 흐름의 단계이기도 합니다: 초효·이효 = 초반 흐름(일의 시작, 가까운 때), 삼효·사효 = 중반 흐름(전환, 안과 밖이 만나는 때), 오효·상효 = 후반 흐름(정점과 마무리, 먼 때).`;

const WRITE_OPEN = {
  name: 'write_open',
  noQuote: ['answer', 'shape'],
  noTiming: true,
  temperature: 0.4,
  timeoutMs: 25000,
  maxTokens: 1600,
  checkStyle: true,
  system: writerSystem('질문에 대한 답과 본괘 풀이', 'write_open', `- answer 4~5문장(380자 이내): empathy는 화면에서 연서의 말풍선으로, verdict.label은 바로 위 판정 줄로 따로 보이니 다시 쓰지 않습니다. 판정의 이유를 괘·효 이름을 짚어 두 가지쯤 풀고, 그것이 상담자의 사정(facts)에서 무엇을 뜻하는지 — 지금 무엇은 되고 무엇은 아직인지, 어떤 조건이 갖춰지면 달라지는지 — 실제 장면으로 말합니다. 원문 인용과 시기 표현은 쓰지 않습니다.
- shape 4~5문장(400자 이내): 제목(point_shape)이 화면에 크게 나오니 첫 문장에서 되풀이하지 말고, 본괘의 상괘·하괘 자연 상징이 겹친 장면부터 그립니다("못 아래로 물이 다 빠져나간 모습이에요…"). 그 그림이 상담자의 지금과 어떻게 겹치는지 잇습니다. 괘사(quote_shape)는 화면 상자에 나오니 옮겨 적지 말고 그 말이 지금 무엇을 가리키는지 풉니다. 호체 블록이 있으면 "겉은 ~이지만 안에는 ~가 숨어 있어요" 한 문장을 넣습니다(호체를 지괘와 섞지 않습니다).`),
  tool: tool('write_open', '질문에 대한 답과 본괘 풀이를 쓴다', {
    answer: str('질문에 대한 답 4~5문장, 해요체'),
    shape: str('본괘 풀이 4~5문장, 해요체'),
  }),
  user: ({ input, analysis: a, plan: p }) => lines(
    `이름: ${input.name}\n고민: ${input.question}`,
    block('구성안', json({ verdict: p.verdict, empathy: p.empathy, facts: p.facts, point_shape: p.points.shape, quote_shape: p.quotes.shape })),
    input.src.ben,
    input.src.hoche,
    block('괘 분석 메모', json({ image: a.image, hidden: a.hidden, why: a.why })),
  ),
};

const WRITE_YAO = {
  name: 'write_yao',
  noQuote: ['heart', 'yao', 'stages'],
  noTiming: true,
  temperature: 0.4,
  timeoutMs: 30000,
  maxTokens: 3200,
  checkStyle: true,
  system: writerSystem('중심 효 풀이와 효 하나하나', 'write_yao', `- 쓰는 순서: yao(효 전부) → stages → heart. yao를 빈 배열로 두면 안 됩니다([중심 자리]가 "여섯 효 모두 변함"일 때만 빈 배열).
- heart 3~4문장(300자 이내): 제목(point_heart)은 화면에 크게 나오니 되풀이하지 않습니다. 길흉 기조를 한 번 분명히 하고, 아래 효들이 모여 고민에 무엇을 말하는지 한데 묶어 줍니다.
- yao: [중심 자리]에 적힌 효를 하나도 빼지 않고, 적힌 순서대로 하나씩 읽습니다. 각 항목은 {pos: "초효"처럼 효 이름, stage: "초반"·"중반"·"후반" 중 하나, reading: 3~4문장}. 효사 원문은 화면에서 그 효 바로 위 상자에 보이니 옮겨 적지 않습니다. reading은 효사의 그림이 무슨 뜻인지 쉬운 말로 풀고 → 그 자리의 의미(자리 풀이 참고)를 짚고 → 상담자의 고민에서 그것이 어떤 장면인지 구체적으로 잇습니다. 효마다 다른 이야기를 해서 같은 말을 되풀이하지 않습니다.
- stages: [중심 자리]가 "변효 없음"이면 초반·중반·후반 흐름 세 개를 {stage, reading: 2~3문장}으로 씁니다 — 각 단계에서 상담자의 일이 어떻게 펼쳐지는지 이야기처럼 잇습니다(시기 표현 없이). 변효가 있으면 빈 배열.
- [중심 자리]가 "여섯 효 모두 변함"이면 yao는 빈 배열이고, heart를 6~8문장으로 늘려 [해석 원칙]대로 읽습니다.
- ${STAGE_RULE}
- [해석 원칙]과 [심장 규칙]이 이 부분의 다른 지침보다 우선합니다.`),
  // 효 읽기(yao)를 맨 앞에 둔다 — heart를 먼저 쓰게 했더니 요약만 쓰고 yao를 빈 배열로 내는 일이 잦았다(2026-10-18)
  tool: tool('write_yao', '효 하나하나를 읽고, 중심 효 풀이로 묶는다', {
    yao: arr(obj({ pos: str('효 이름, 예: "초효"'), stage: { type: 'string', enum: ['초반', '중반', '후반'] }, reading: str('그 효의 풀이 3~4문장, 해요체, 효사 원문은 옮겨 적지 않음') }), '필수 — [중심 자리]에 적힌 효 전부를 순서대로(변효 없음이면 여섯 개)', 0, 6),
    stages: arr(obj({ stage: { type: 'string', enum: ['초반 흐름', '중반 흐름', '후반 흐름'] }, reading: str('그 단계의 흐름 2~3문장, 해요체') }), '변효가 없을 때만 세 단계, 아니면 빈 배열', 0, 3),
    heart: str('중심 효 풀이 3~4문장, 해요체'),
  }, ['stages']),
  // [중심 자리]에 적힌 효 수만큼 읽었는지 — 모자라면 다시 쓰게 한다
  validate: ({ input }, out) => {
    const want = (String(input.src.lines).match(/^(초효|이효|삼효|사효|오효|상효)\(/gm) || []).length;
    const got = (out.yao || []).length;
    return got < want ? `yao가 ${got}개뿐 — [중심 자리]의 효 ${want}개를 하나도 빼지 않고 모두 읽어야 함` : '';
  },
  user: ({ input, analysis: a, plan: p }) => lines(
    `이름: ${input.name}\n고민: ${input.question}`,
    block('구성안', json({ verdict: p.verdict.kind, facts: p.facts, point_heart: p.points.heart })),
    block('중심 자리', input.src.lines),
    block('해석 원칙', input.src.focus),
    block('심장 규칙', input.heartRule),
    block('괘 분석 메모', json({ fortune: a.fortune, heart: a.heart, liuyao: a.liuyao })),
  ),
};

const WRITE_CORE = {
  name: 'write_core',
  noQuote: ['flow'],
  noTiming: true,
  temperature: 0.4,
  timeoutMs: 25000,
  maxTokens: 1000,
  checkStyle: true,
  system: writerSystem('지괘 풀이', 'write_core', `- flow 3~5문장(350자 이내): 제목(point_flow)은 화면에 크게 나오니 되풀이하지 않습니다. 지괘의 이름과 상괘·하괘 상징으로 이 일이 닿는 장면을 그리고(예: "택수곤은 못에 물이 빠진 형상이에요…"), 지괘 괘사(quote_flow)는 화면 상자에 나오니 옮겨 적지 말고 그곳에 닿았을 때 갖출 태도로 맺습니다. 지괘가 없으면 본괘의 자리가 그대로 이어진다는 뜻으로 씁니다.`),
  tool: tool('write_core', '지괘 풀이를 쓴다', {
    flow: str('지괘 풀이 3~5문장, 해요체'),
  }),
  user: ({ input, analysis: a, plan: p }) => lines(
    `이름: ${input.name}\n고민: ${input.question}`,
    block('구성안', json({ verdict: p.verdict.kind, facts: p.facts, point_flow: p.points.flow, quote_flow: p.quotes.flow })),
    input.src.ji,
    block('괘 분석 메모', json({ direction: a.direction })),
  ),
};

/* 해 둘 일 · 멀리할 일 — 2026-10-18 피드백: 한 칸에 둘을 몰아 한 줄짜리 뻔한 조언("배우자와 대화하는 쪽이 좋아요")만
   늘어놓아 나이브하고 읽는 재미가 없다 → 두 섹션으로 나누고, 항목마다 한 줄 제목 + 왜(괘·효의 그림) + 어떻게(구체적인 방법)로 쓴다. */
const WRITE_MOVES = {
  name: 'write_moves',
  noQuote: ['dos', 'donts'],
  noTiming: true,
  temperature: 0.45,
  timeoutMs: 30000,
  maxTokens: 2400,
  checkStyle: true,
  system: writerSystem('해 둘 일과 멀리할 일', 'write_moves', `- dos 3개, donts 3개. 각 항목은 {head, body, basis}.
  · head: 한 줄 제목, 16자 안팎. 행동이 보이게("첫 고객 한 명부터 만나 보기", "퇴사 날짜는 아직 비워 두기").
  · body 2~3문장: ① 왜 — 근거가 된 괘·효의 그림이 무엇을 말하는지 한 문장(원문을 따옴표로 옮기지 않고 그림으로: "곤괘는 물이 빠진 연못이라…") ② 어떻게 — 상담자의 사정(facts) 안에서 무엇을, 얼마나, 어떤 순서로 할지 구체적으로.
  · basis: 근거 이름 짧게. "대상전"은 본괘 대상전(quote_dos)에만 씁니다. 지괘 블록의 대상전이면 "지괘 대상전". 그 밖에는 효 이름("사효"), "괘사", "단전", "지괘". "괘 분석"·"방향" 같은 말은 쓰지 않습니다.
- 뻔한 조언 금지: "가족과 충분히 대화하기", "준비를 철저히", "신중하게 결정하기", "건강 챙기기"처럼 괘를 보지 않아도 누구나 할 수 있는 말은 쓰지 않습니다. 이 괘가 아니었다면 떠올리지 못했을, 조금은 의외인 한 수를 찾습니다. 예: 수뢰둔(막 싹이 트는 혼돈)이면 "혼자 다 하지 말고 '제후를 세우듯' 역할을 나눌 사람 한 명을 먼저 정해 두기".
- dos 첫 항목은 본괘 대상전(quote_dos)의 태도를 상담자 사정으로 옮긴 것(basis "대상전"). donts에는 중심 효나 지괘가 경고하는 장면을 하나 이상 넣습니다.
- 여섯 항목이 서로 겹치지 않게 하고, 같은 문장 끝을 되풀이하지 않습니다.`),
  tool: tool('write_moves', '해 둘 일과 멀리할 일을 쓴다', {
    dos: arr(obj({ head: str('한 줄 제목 16자 안팎'), body: str('왜 + 어떻게, 2~3문장, 해요체'), basis: str('근거 이름') }), '해 둘 일', 3, 3),
    donts: arr(obj({ head: str('한 줄 제목 16자 안팎'), body: str('왜 + 어떻게, 2~3문장, 해요체'), basis: str('근거 이름') }), '멀리할 일', 3, 3),
  }),
  user: ({ input, plan: p }) => {
    const nameOf = (blk) => (String(blk || '').match(/^\[(?:본괘|지괘)\] (\S+?)\(/m) || [])[1] || '';
    const ben = nameOf(input.src.ben), ji = nameOf(input.src.ji);
    return lines(
      `이름: ${input.name}\n고민: ${input.question}\n${qaText(input.qa)}`,
      `[근거 이름 정하기] 본괘는 ${ben}${ji ? `, 지괘는 ${ji}` : ', 지괘 없음'}입니다. basis "괘사"·"대상전"·"단전"은 ${ben}의 것에만 씁니다.${ji ? ` ${ji}의 괘사·대상전에서 가져왔다면 "지괘", "지괘 대상전"이라고 쓰고, 본문에서도 ${ji}라고 부릅니다.` : ''}`,
      block('구성안', json({ verdict: p.verdict, facts: p.facts, point_dos: p.points.dos, point_donts: p.points.donts, quote_dos: p.quotes.dos })),
      input.src.ben,
      block('중심 자리', input.src.lines),
      input.src.ji,
    );
  },
};

/* 때 — 2026-10-18 피드백: "빠르면 다음 주, 늦어도 한 달 안"이 괘와 상관없이 모든 풀이에 박혀 있었다(작가 규칙의 예시를
   그대로 옮김). 이제 범위는 index.html의 timingWindows()가 육효 응기 달에서 계산해 input.timing으로 넘기고, 이 노드는
   창마다 그 사이 무엇이 움직일지만 쓴다. range는 assemble이 코드 값으로 채운다. */
const WRITE_TAIL = {
  name: 'write_tail',
  noQuote: ['timeline', 'closing', 'timing_title'],
  temperature: 0.4,
  timeoutMs: 25000,
  maxTokens: 1600,
  checkStyle: true,
  system: writerSystem('시기와 마무리', 'write_tail', `- timeline: [시기 창]의 창마다 하나씩, 같은 순서·같은 개수로 {what, watch}를 씁니다. 범위(range)는 화면이 그대로 보여 주니 쓰지 않고, 달 이름도 다시 쓰지 않습니다.
  · what 2문장: 그 창의 근거(basis)에 적힌 자리가 무엇을 나타내는지에 맞춰, 그 사이 상담자에게 실제로 움직일 수 있는 일을 장면으로 씁니다. 나를 나타내는 자리(세효)면 상담자 쪽의 마음·준비·결단, 상대·결과를 나타내는 자리(응효)면 상대나 바깥의 반응, 물으신 일을 맡은 자리(용신)면 물으신 그 일 자체(일자리·돈·관계)의 움직임, 움직이는 자리면 지금 바뀌고 있는 일. "비어 있던 자리가 차는 달"은 그동안 실체가 없던 것이 생기는 때, "깨진 자리가 다시 서는 달"은 틀어졌던 것이 바로 서는 때, "짝을 만나 묶이는 달"은 사람·조건이 맞물리는 때, "부딪혀 깨어나는 달"은 멈춰 있던 일이 부딪힘으로 움직이는 때로 읽습니다. "진전이 나타난다" 같은 추상어로 끝내지 않습니다.
  · watch 1문장: 그때 무엇을 보면 흐름을 알 수 있는지("~가 오는지 보세요").
  · what·watch·closing에는 계절·달·"내년"·"다음 주" 같은 시기 말을 쓰지 않습니다. 범위는 화면이 창마다 따로 보여 줍니다.
  · what은 할 일 목록이 아니라 그 사이 일어날 수 있는 일(사건·반응·변화)입니다. 할 일은 다른 섹션 몫입니다.
  · focus가 있는 창은 그 말을 what에 자연스럽게 녹입니다.
- timing_title: 시기 섹션 제목 18자 안팎, 장면이 보이게(예: "봄이 오기 전에 한 번 움직여요"). 달 이름은 넣지 않습니다.
- closing 2문장: 연서의 다정한 마무리. 판정과 같은 결로, 시기와 판정 한 줄(verdict.line)을 되풀이하지 않고 상담자의 사정(facts)에 닿는 한마디로 맺습니다.
- 괘사·효사·대상전을 인용하지 않습니다.`),
  tool: tool('write_tail', '시기 창마다 움직일 일과 마무리를 쓴다', {
    timeline: arr(obj({
      what: str('그 사이 움직일 수 있는 일 2문장, 해요체'),
      watch: str('그때 볼 것 1문장, 해요체'),
    }), '[시기 창]과 같은 순서·같은 개수', 1, 3),
    timing_title: str('시기 섹션 제목 18자 안팎'),
    closing: str('마무리 2문장, 해요체'),
  }),
  validate: ({ input }, out) => {
    if ((out.timeline || []).length < input.timing.length) return `timeline이 ${(out.timeline || []).length}개뿐 — [시기 창] ${input.timing.length}개마다 하나씩`;
    // 창 안의 글이 다른 때를 말하면 범위와 어긋난다("내년 9~10월" 창에 "내년 봄쯤")
    const other = [...(out.timeline || []).flatMap((t) => [t.what, t.watch]), out.closing].join(' ').match(/봄|여름|가을|겨울|연말|연초|내년|다음 달|다음 주|\d{1,2}월/);
    return other ? `timeline·closing에 "${other[0]}" 같은 시기 말이 있음 — 범위는 화면이 보여 주니 시기 말 없이` : '';
  },
  user: ({ input, plan: p }) => lines(
    `이름: ${input.name} / 오늘: ${input.today}\n고민: ${input.question}`,
    block('구성안', json({ verdict: p.verdict, facts: p.facts, season: p.season })),
    block('시기 창', input.timing.map((w, i) => `${i + 1}. ${w.range}\n   근거: ${w.basis.join(' / ')}${w.focus ? `\n   focus: ${w.focus}` : ''}`).join('\n')),
    input.src.tui,
    block('중심 자리', input.src.lines),
  ),
};

/* 나눈 이야기 — 2026-10-18 피드백: "본괘로 보면 / 흘러가는 곳으로 보면" 같은 각도 라벨이 글의 짜임을 설명하는 AI 말투였다.
   각도는 유지하되 라벨 없이 두 문단으로 자연스럽게 잇고, 질문마다 제목을 붙인다. */
const WRITE_QA = {
  name: 'write_qa',
  noQuote: ['qa'],
  noTiming: true,
  temperature: 0.45,
  timeoutMs: 30000,
  maxTokens: 2600,
  checkStyle: true,
  system: writerSystem('추가 문답에 대한 풀이', 'write_qa', `- qa: [문답]의 질문마다 하나씩, 빠짐없이 순서대로 씁니다. 각 항목은 {q: 질문 그대로, title, body}.
  · title: 그 답에서 연서가 짚은 핵심을 제목으로, 18자 안팎(예: "6개월은 짧지만 모자라진 않아요").
  · body 두 문단(문단 사이 줄바꿈), 합쳐 4~6문장: 첫 문단은 상담자가 남긴 답을 그 말 그대로 받아 주고 이 점에서 무엇을 뜻하는지 분명히 말합니다. 둘째 문단은 다른 쪽에서 비춰 봅니다 — 본괘·중심 효·지괘 가운데 첫 문단에서 쓰지 않은 것을 이름으로 짚어 근거를 대되, "~로 보면", "다른 각도에서" 같은 말머리 없이 바로 말합니다.
  · 다른 질문의 답에서 한 말을 되풀이하지 않습니다. 원문을 따옴표로 인용하지 않습니다. 시기 표현과 판정 한 줄(verdict.line)은 쓰지 않습니다.
- 문답이 없으면 빈 배열.`),
  tool: tool('write_qa', '질문마다 제목과 두 문단 풀이를 쓴다', {
    qa: arr(obj({
      q: str('질문 그대로'),
      title: str('제목 18자 안팎'),
      body: str('두 문단 4~6문장, 해요체, 문단 사이 줄바꿈'),
    }), '질문별 풀이', 0, 3),
  }),
  user: ({ input, analysis: a, plan: p }) => {
    const answered = input.qa.filter((x) => x && x.a && x.a !== '(답변 없음)');
    return lines(
      `이름: ${input.name}\n고민: ${input.question}`,
      block('구성안', json({ verdict: p.verdict, facts: p.facts, season: p.season })),
      block('문답', answered.map((x, i) => `Q${i + 1}. ${x.q}\nA. ${x.a}`).join('\n\n')),
      input.src.ben.split('\n').slice(0, 4).join('\n'),
      input.src.ji ? input.src.ji.split('\n').slice(0, 4).join('\n') : '',
      block('중심 자리', input.src.lines),
      block('괘 분석 메모', json({ fortune: a.fortune, heart: a.heart, direction: a.direction })),
    );
  },
};

const WRITERS = [WRITE_OPEN, WRITE_YAO, WRITE_CORE, WRITE_MOVES, WRITE_TAIL, WRITE_QA];

/* ── 실행기 ── */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function callClaude({ system, user, tool: t, temperature, maxTokens, timeoutMs }) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      signal: ctrl.signal,
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': process.env.ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: MODEL,
        max_tokens: maxTokens,
        temperature,
        system,
        messages: [{ role: 'user', content: user }],
        tools: [t],
        tool_choice: { type: 'tool', name: t.name },
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new NodeError(data?.error?.message || `Anthropic ${res.status}`, {
        status: res.status,
        retryable: res.status === 429 || res.status >= 500,
      });
    }
    return data;
  } catch (err) {
    if (err instanceof NodeError) throw err;
    if (err.name === 'AbortError') throw new NodeError('Anthropic 응답 시간 초과', { status: 504 });
    throw new NodeError(err.message);
  } finally {
    clearTimeout(timer);
  }
}

// 노드 하나 실행 = 시도마다 Langfuse generation 하나. 실패한 시도도 ERROR로 남는다.
// 문체 검사(checkStyle 노드) — 2026-10 테스트에서 실제로 나온 문제들:
//  · 기계적으로 고칠 수 있는 것은 다시 쓰게 하지 않고 바로 고친다(재시도마다 8~10초가 늘어서):
//    "당신" → "이름+님", 명령형 "~세요/~십시오/~해야 합니다" → "~는 쪽이 좋아요/좋습니다"
//  · 고칠 수 없는 것은 문제를 짚어 다시 쓰게 한다: 한자(없는 한자 원문 조작), 반말 종결, 지지 한글 읽기("술월"),
//    육효 용어(공망·출공…), 배정되지 않은 섹션의 인용(noQuote 필드)
//  · 끝까지 남으면 한자만 걷어내고 진행한다 — 점사 전체를 실패시키지는 않는다.
const HANJA = /[㐀-䶿一-鿿]+/g;
const JIJI_KO = /(?<![가-힣])(자|축|인|묘|진|사|오|미|신|유|술|해)(월|일)(?=[\s,.)에은는이가을의도까부]|$)/;
const JARGON = /공망|출공|세효|응효|용신|월건|일진|동효/;
const TIMING = /\d{1,2}월|다음\s?주|다음\s?달|두\s?달\s?안/;
// 해설서·번역서 말투 — 두 가지 이상 섞이면 다시 쓰게 한다("외부 진입이 지연", "물질적·외적 제약", "불굴의 의지")
const STIFF = /진입|지연|물질적|외적|내적|제약|불굴|도출|시사하|측면|형태를 갖/g;
const STOCK = /쪽이 좋아요|편이 좋아요|라는 뜻이에요|핵심이에요|중요해요/g;
const META = /(본괘|지괘|효|흘러가는 곳|다른 각도|이 섹션)(?:으)?로 보면|정리하면|다른 각도에서/;
const QUOTED = /["“'‘][^"”'’\n]*["”'’]/g;
const sentencesOf = (t) => t.split(/(?<=[.!?])\s+|\n+/).map((s) => s.trim()).filter(Boolean);
const isBanmal = (s) => /(?<!니)다[.!]?$/.test(s) || /(해|돼|봐|줘|거든|잖아)[.!]$/.test(s);
const mapStrings = (v, f) => (typeof v === 'string' ? f(v) : Array.isArray(v) ? v.map((x) => mapStrings(x, f))
  : v && typeof v === 'object' ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, mapStrings(x, f)])) : v);
const without = (o, keys = []) => Object.fromEntries(Object.entries(o || {}).filter(([k]) => !keys.includes(k)));

// 자주 나오는 해라체 문장 끝을 해요체로 바꾼다. 따옴표 안(원문 인용)은 끝 다음에 따옴표가 와서 걸리지 않는다.
const HAEYO = [['않는다', '않아요'], ['한다', '해요'], ['된다', '돼요'], ['있다', '있어요'], ['없다', '없어요'],
  ['진다', '져요'], ['린다', '려요'], ['인다', '여요'], ['온다', '와요']];
const hasBatchim = (ch) => { const c = ch.charCodeAt(0) - 0xac00; return c >= 0 && c <= 11171 && c % 28 !== 0; };
function toHaeyoPlain(s) {
  let t = s.replace(/([가-힣])이다([.!])(?=\s|$)/g, (m, prev, p) => `${prev}${hasBatchim(prev) ? '이에요' : '예요'}${p}`);
  for (const [from, to] of HAEYO) t = t.replace(new RegExp(`${from}([.!])(?=\\s|$)`, 'g'), `${to}$1`);
  return t;
}
// 따옴표 안(괘사·효사 원문 인용)은 손대지 않는다 — 원문 "극한 곤궁이다."가 "곤궁이에요."로 바뀐 일이 있었다
const toHaeyo = (s) => s.split(/(["“][^"”]*["”]|'[^'\n]*')/).map((part, i) => (i % 2 ? part : toHaeyoPlain(part))).join('');

function autoFix(out, name, node = {}) {
  const who = name ? `${name}님` : '이분';
  // 인용이 배정되지 않은 필드의 따옴표는 걷어낸다 — 같은 원문이 여러 섹션에 "인용"으로 반복되는 것을 막는다
  const unquoted = { ...out };
  for (const k of node.noQuote || []) if (k in unquoted) unquoted[k] = mapStrings(unquoted[k], (s) => s.replace(/["'“”‘’]/g, ''));
  // 원문·상담자 말 그대로인 필드(styleSkip)는 문장 끝을 바꾸지 않는다
  for (const k of Object.keys(unquoted)) if (!(node.styleSkip || []).includes(k)) unquoted[k] = mapStrings(unquoted[k], toHaeyo);
  return mapStrings(unquoted, (s) => s
    .replace(/[<>]/g, '') // 문장 끝에 ">"가 붙어 나온 일이 있었다
    .replace(/당신/g, who)
    .replace(/에너지/g, '기세')
    // "~해 보세요"처럼 부드러운 권유는 그대로 둔다 — 예전엔 "~세요"를 모두 "~는 쪽이 좋아요"로 바꿔 한 편에 여덟 번씩
    // 같은 끝맺음이 나왔다(2026-10-18). 딱딱한 하십시오체·의무형만 고친다.
    .replace(/십시오(?=[.!]?(\s|$))/g, '세요')
    .replace(/해야 합니다(?=[.!]?(\s|$))/g, '하는 게 좋아요')
    .replace(/해야 해요(?=[.!]?(\s|$))/g, '하는 게 좋아요'));
}

function styleIssues(out, node) {
  const all = stringsOf(out).join('\n');
  const checked = stringsOf(without(out, node.styleSkip)).join('\n'); // 원문·상담자 말 그대로인 필드는 문체 검사에서 뺀다
  const outside = checked.replace(QUOTED, ''); // 따옴표 안은 원문 인용
  const issues = [];
  const hz = all.match(HANJA);
  if (hz) issues.push(`한자(${[...new Set(hz)].slice(0, 6).join(' ')})`);
  const bm = sentencesOf(outside).filter(isBanmal);
  if (bm.length) issues.push(`반말로 끝난 문장("…${bm[0].slice(-16)}")`);
  const jj = outside.match(JIJI_KO);
  if (jj) issues.push(`지지 이름("${jj[0]}")`);
  const jg = outside.match(JARGON);
  if (jg) issues.push(`육효 용어("${jg[0]}")`);
  const dt = outside.match(/\d{1,2}월\s?\d{1,2}일/);
  if (dt) issues.push(`하루짜리 날짜("${dt[0]}") — "빠르면 ~, 늦어도 ~" 범위로`);
  // 시기는 「때」 카드 한 곳에만 — 같은 "11월 초부터 12월 중순"이 다섯 섹션에 되풀이된 일이 있었다(2026-10-18)
  const tm = node.noTiming && !dt && stringsOf(without(out, [...(node.styleSkip || []), ...(node.timingOk || [])])).join('\n').replace(QUOTED, '').match(TIMING);
  if (tm) issues.push(`시기 표현("${tm[0]}") — 시기는 「때」에서만 말하니 이 섹션에서는 빼기`);
  const st = [...new Set(outside.match(STIFF) || [])];
  if (st.length >= 2) issues.push(`해설서 말투(${st.slice(0, 4).join(', ')}) — 생활 말로`);
  // 같은 끝맺음·글 짜임 설명 — 기계가 쓴 티가 가장 많이 나던 곳(2026-10-18)
  const stock = outside.match(STOCK) || [];
  if (stock.length > 4) issues.push(`같은 끝맺음 반복("${[...new Set(stock)].slice(0, 3).join('", "')}" ${stock.length}번) — 끝맺음을 바꿔 가며`);
  const meta = outside.match(META);
  if (meta) issues.push(`글의 짜임을 설명하는 말("${meta[0]}") — 바로 내용으로`);
  return { issues, hanja: Boolean(hz) };
}
const stringsOf = (v) => (typeof v === 'string' ? [v] : Array.isArray(v) ? v.flatMap(stringsOf) : v && typeof v === 'object' ? Object.values(v).flatMap(stringsOf) : []);
const stripHanja = (v) => {
  if (typeof v === 'string') {
    return v
      .replace(/\s?[(（][^()（）]*[㐀-鿿][^()（）]*[)）]/g, '')
      .replace(HANJA, '')
      .replace(/(["“'‘「『])[\s,，、·.\-—]*(["”'’」』])/g, '')
      .replace(/[ \t]{2,}/g, ' ')
      .replace(/\s+([,.])/g, '$1');
  }
  if (Array.isArray(v)) return v.map(stripHanja);
  if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, stripHanja(x)]));
  return v;
};

async function runNode(node, state, parent, deadline) {
  const baseUser = node.user(state);
  const checkStyle = Boolean(node.checkStyle);
  let user = baseUser;
  let maxTokens = node.maxTokens;
  let lastErr;
  let styleRetried = false; // 문체 때문에 다시 쓰는 건 노드당 한 번만 — 그 이상은 시간만 늘고 잘 고쳐지지 않았다
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    const gen = parent.startObservation(node.name, {
      model: MODEL,
      input: [{ role: 'system', content: node.system }, { role: 'user', content: user }],
      modelParameters: { temperature: node.temperature, max_tokens: maxTokens },
      metadata: { attempt },
    }, { asType: 'generation' });
    try {
      const timeoutMs = Math.min(node.timeoutMs, deadline - Date.now());
      if (timeoutMs < 3000) throw new NodeError('점사 시간 예산 소진', { status: 504, retryable: false });
      const data = await callClaude({ system: node.system, user, tool: node.tool, temperature: node.temperature, maxTokens, timeoutMs });
      gen.update({ usageDetails: { input: data.usage?.input_tokens ?? 0, output: data.usage?.output_tokens ?? 0 } });
      if (data.stop_reason === 'max_tokens') {
        maxTokens = Math.round(maxTokens * 1.5);
        throw new NodeError('max_tokens 도달 — 한도를 늘려 다시 시도');
      }
      const out = coerce(node.tool.input_schema, data.content?.find((b) => b.type === 'tool_use')?.input);
      const missing = missingFields(node.tool.input_schema, out);
      if (missing.length) throw new NodeError(`필드 누락: ${missing.slice(0, 8).join(', ')}`);
      const invalid = node.validate?.(state, out);
      if (invalid && attempt < MAX_ATTEMPTS && deadline - Date.now() > node.timeoutMs + 5000) { // 마지막 시도면 모자란 채로라도 진행
        user = `${baseUser}\n\n[다시 쓰기] 직전 글은 ${invalid}. 처음부터 다시 쓰세요.`;
        throw new NodeError(invalid);
      }
      if (!checkStyle) {
        gen.update({ output: out }).end();
        return out;
      }
      const fixed = autoFix(out, state.input?.name, node);
      const { issues, hanja } = styleIssues(fixed, node);
      if (issues.length) {
        const summary = issues.join(', ');
        // 이미 한 번 다시 썼거나 시간이 모자라면 다시 쓰지 않고 경고만 남긴다
        const canRetry = !styleRetried && attempt < MAX_ATTEMPTS && deadline - Date.now() > node.timeoutMs + 5000;
        if (canRetry) {
          styleRetried = true;
          gen.update({ output: fixed, level: 'WARNING', statusMessage: `문체 문제: ${summary} — 다시 쓰게 함` }).end();
          user = `${baseUser}\n\n[다시 쓰기] 직전 글에 ${summary}이 있었습니다. 해요체 존댓말과 쉬운 생활 말로, 한자·지지 이름·육효 용어·원문 인용 없이${node.noTiming ? ', 시기 표현 없이' : ', 시기는 폭이 있는 범위로만'} 처음부터 다시 쓰세요.`;
          continue;
        }
        const clean = hanja ? stripHanja(fixed) : fixed;
        gen.update({ output: clean, level: 'WARNING', statusMessage: `문체 문제: ${summary} — ${hanja ? '한자만 걷어내고 ' : ''}진행` }).end();
        return clean;
      }
      gen.update({ output: fixed }).end();
      return fixed;
    } catch (err) {
      lastErr = err;
      gen.update({ level: 'ERROR', statusMessage: err.message }).end();
      if (!err.retryable) break;
      if (attempt < MAX_ATTEMPTS) await sleep(1500 * attempt);
    }
  }
  throw lastErr;
}

// 섹션 사이 되풀이를 걷어낸다 — 작가 다섯이 병렬로 쓰니 규칙만으로는 "믿음을 잃지 않으면 길이 열려요"가
// 한 리포트에 여섯 번 나오는 일을 다 막지 못했다(2026-10-18). 화면에 보이는 순서대로 읽으며, 앞에 이미 나온
// 문장과 글자 세 개 묶음이 60% 넘게 겹치는 문장은 뒤쪽에서 뺀다. 한 칸이 통째로 비지는 않게 첫 문장은 남긴다.
const tri = (s) => {
  const t = s.replace(/[^가-힣A-Za-z0-9]/g, '');
  const g = new Set();
  for (let i = 0; i + 3 <= t.length; i++) g.add(t.slice(i, i + 3));
  return g;
};
function dedupeReport(r, name) {
  const seen = [];
  let removed = 0;
  // 이름은 앞쪽 세 번까지만 — 한 편에 "재영님"이 열두 번씩 나와 기계가 쓴 티가 났다(2026-10-18). 마무리는 이름을 남긴다.
  let names = 0;
  const NAME = name ? new RegExp(`${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}님(?:께서는|께서|에게|은|는|이|가|의|도|께|을|를)?\\s?`, 'g') : null;
  const trimName = (t) => (NAME ? t.replace(NAME, (m) => (++names <= 3 ? m : '')) : t);
  const overlaps = (g) => g.size >= 8 && seen.some((h) => { let n = 0; for (const x of g) if (h.has(x)) n++; return n / g.size >= 0.6; });
  const see = (t) => { for (const x of sentencesOf(String(t || ''))) seen.push(tri(x)); };
  const prose = (t) => {
    if (!t) return t;
    const paras = String(t).split(/\n+/).map((p) => {
      const kept = sentencesOf(p).filter((x) => !(overlaps(tri(x)) && ++removed));
      return kept.join(' ');
    }).filter(Boolean);
    const out = trimName(paras.length ? paras.join('\n') : sentencesOf(String(t))[0]);
    see(out);
    return out;
  };
  const bubble = (t) => { if (!t) return t; if (overlaps(tri(t))) { removed++; return ''; } see(t); return trimName(t); };
  [r.headline, r.verdict.label].forEach(see);
  r.empathy = trimName(r.empathy || '');
  see(r.empathy);
  r.answer = prose(r.answer);
  r.shape = prose(r.shape);
  r.bubbles.heart = bubble(r.bubbles.heart);
  r.heart = prose(r.heart);
  r.stages = r.stages.map((x) => ({ ...x, reading: prose(x.reading) }));
  r.yao = r.yao.map((y) => ({ ...y, reading: prose(y.reading) }));
  r.bubbles.flow = bubble(r.bubbles.flow);
  r.flow = prose(r.flow);
  r.dos = r.dos.map((x) => ({ ...x, body: prose(x.body) }));
  r.bubbles.timing = bubble(r.bubbles.timing);
  see(r.season);
  r.timeline = r.timeline.map((x) => ({ ...x, what: prose(x.what), watch: trimName(x.watch || '') }));
  r.donts = r.donts.map((x) => ({ ...x, body: prose(x.body) }));
  r.qa = r.qa.map((x) => ({ ...x, body: prose(x.body) }));
  names = -99; // 마무리는 이름을 부르며 끝낸다
  r.closing = prose(r.closing);
  r.meta = { removedRepeats: removed };
  return r;
}

// 할 것·피할 것의 근거 표시는 독자가 원문에서 찾을 수 있는 이름만 남긴다("괘 분석", "방향" 같은 내부 말이 나왔다)
const cleanBasis = (x) => ({ ...x, basis: /대상전|괘사|단전|[초이삼사오상]효|지괘|본괘|호체/.test(x.basis || '') ? x.basis : '' });

// 화면이 그대로 그리는 리포트 객체. version이 바뀌면 index.html의 buildReport·parseReadingResponse도 같이 바꿀 것.
function assemble({ input, analysis: a, plan: p, open, yao, core, moves, tail, qa }) {
  const answered = input.qa.filter((x) => x && x.a && x.a !== '(답변 없음)');
  return {
    version: 4,
    headline: p.verdict.line,
    summary: { fortune: a.fortune, keywords: p.keywords, mood: p.mood },
    verdict: { kind: p.verdict.kind, label: p.verdict.label, reasons: p.verdict.reasons },
    empathy: p.empathy,
    // 섹션 제목 — 화면이 "지금의 형세" 같은 틀 이름 대신 이 제목을 크게 보인다(2026-10-18)
    titles: { shape: p.points.shape, heart: p.points.heart, flow: p.points.flow, dos: p.points.dos, donts: p.points.donts, timing: tail.timing_title },
    answer: open.answer,
    shape: open.shape,
    heart: yao.heart,
    yao: yao.yao || [],
    stages: yao.stages || [],
    flow: core.flow,
    dos: moves.dos.map(cleanBasis),
    donts: moves.donts.map(cleanBasis),
    season: p.season,
    // 범위·근거는 코드가 계산한 값(input.timing), 무엇이 움직이는지는 작가 몫
    timeline: input.timing.length
      ? input.timing.map((w, i) => ({ range: w.range, basis: w.basis, what: tail.timeline[i]?.what || '', watch: tail.timeline[i]?.watch || '' }))
      : (tail.timeline || []).map((t) => ({ range: '', basis: [], what: t.what, watch: t.watch })),
    qa: (qa.qa || []).map((x, i) => ({ ...x, said: answered[i]?.a || '' })),
    closing: tail.closing,
    bubbles: { ...p.bubbles },
  };
}

export async function runReadingGraph(input, root) {
  const deadline = Date.now() + GRAPH_BUDGET_MS;
  input.timing ||= [];
  const analysis = await runNode(ANALYZE, { input }, root, deadline);
  const plan = nestPlan(await runNode(PLAN, { input, analysis }, root, deadline));
  // 원문 배정은 모델에게 맡기지 않고 입력 블록에서 바로 꺼낸다 — 본괘 대상전 자리에 지괘 대상전이 들어가는 일이 반복됐다(2026-10-18)
  const pick = (blk, label) => (String(blk || '').match(new RegExp(`^${label}: (.+)$`, 'm')) || [])[1] || '';
  plan.quotes = {
    shape: pick(input.src.ben, '괘사 풀이') || plan.quotes.shape,
    flow: pick(input.src.ji, '괘사 풀이'),
    dos: pick(input.src.ben, '대상전 풀이') || plan.quotes.dos,
  };
  const [open, yao, core, moves, tail, qa] = await Promise.all(
    WRITERS.map((node) => runNode(node, { input, analysis, plan }, root, deadline)),
  );
  return dedupeReport(assemble({ input, analysis, plan, open, yao, core, moves, tail, qa }), input.name);
}
