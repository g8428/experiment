// 주역사주 v2 그래프 (2026-10-18). v1(api/_lib/reading-graph.js)을 복사해 사주 명식을 더했다 — v1은 그대로 둔다.
//
//   analyze_saju ─────┐                 ┌▶ write_flow    사주: 지금의 큰 흐름(대운·세운)과 이 고민이 놓인 자리
//   (명식만)           ├▶ plan_reading ─┼▶ write_open    질문에 대한 답 + 본괘(다산 물상·호체)
//   analyze_hexagram ─┘  (편집장 구성안) ├▶ write_yao     중심 효 + 효를 하나씩(다산 효변: 지괘 같은 자리와 겹쳐 읽기)
//   (괘 데이터만)                        ├▶ write_path    어떻게 움직일까 · 무엇이 막을까
//                                       ├▶ write_core    어디에 닿을까(지괘 + 다산 추이)
//                                       ├▶ write_tail    시기(육효 응기 창 × 그 달의 월운) · 마무리
//                                       └▶ write_qa      나눈 이야기
//                                                ▼
//                                      assemble → dedupeReport → 리포트 version 'v2-1'
//
// 역할 나눔: 사주는 "어떤 사람이 어떤 계절을 지나고 있나", 주역은 "이 일에서 어떻게 움직이나". 판정은 괘가 내고,
// 사주는 그 판정이 이 사람에게 왜 그렇게 작동하는지를 설명한다. 사주 명식은 서버가 계산한다(api/_lib/v2/saju.js).
// v1에서 배운 것(구성안 노드, 원문은 코드가 배정, 시기는 계산값, 말투·반복 검사)은 그대로 이어받는다.
import { TEN_MEANING, monthAt } from './saju.js';

const MODEL = 'claude-haiku-4-5-20251001';
const MAX_ATTEMPTS = 3;
// api/reading.js는 vercel.json에서 maxDuration 120초(Hobby + Fluid compute 한도는 300초). 그 안에서 응답을 돌려주도록
// 전체 마감을 GRAPH_BUDGET_MS로 둔다. 가끔 한 호출만 30초 넘게 멈추는 일이 있어서(2026-10-05 트레이스)
// 노드별 시도 시간을 끊고 다시 부르는 쪽이 빠르다. 평소 한 편은 30~40초.
const GRAPH_BUDGET_MS = 150000; // v2: 공감 장면을 넣어 글이 길어졌다(2026-10-19) — vercel.json maxDuration 180초 안

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
- 시기는 하루짜리 날짜("10월 14일", "○일 무렵")로 말하지 않습니다. 지지 한 글자로 달·날을 부르는 말("술월", "자일", "진월", "유월")도 쓰지 않습니다.
- 사주의 간지는 한글 두 글자로 씁니다("갑신 대운", "병오년의 운"). 십신 이름(비견·겁재·식신·상관·편재·정재·편관·정관·편인·정인)은 처음 쓸 때 뜻을 붙입니다("편관, 곧 나를 누르며 시험하는 힘").
- 육효 용어(공망, 출공, 세효, 응효, 용신, 월건, 일진, 동효)는 쓰지 않고 뜻으로 풀어 씁니다(예: "막혀 있던 일이 풀리는 때", "상대 쪽 사정").
- "추계", "하계" 같은 딱딱한 한자어 대신 "가을", "여름"처럼 쉬운 말을 씁니다.`;

/* ── 화자 '연서'와 공통 문체: 쓰기 노드(write_*)에만 붙는다 ── */
const VOICE = `[화자 — 연서]
- 화자는 '연서'입니다. 30대 초반의 역술가로, 주역을 오래 공부했고 또래에게 상담하듯 차분하고 섬세하게 말합니다.
- 해요체 존댓말이 기본입니다("괘가 나왔어요", "이 자리는 이렇게 읽혀요"). 무게를 실어야 하는 판단 한두 곳에서만 하십시오체("돌려 말하지 않겠습니다")를 씁니다. 반말 종결("~어.", "~다.", "~지.", "~야.")은 한 문장도 쓰지 않습니다.
- 1인칭은 "저"입니다("제가 보기엔", "이 괘에서 제 눈에 먼저 들어온 건"). 판단의 근거는 괘·효와 사주 명식으로 댑니다.
- 상담자는 "이름+님"으로 부르되 한 섹션에 많아야 한 번입니다. 주어가 분명하면 이름을 빼고 씁니다. "당신"이라고 쓰지 않습니다.

[구성안을 따릅니다 — 가장 중요]
- [구성안]의 point는 이 섹션의 제목으로 화면에 크게 나옵니다. 본문 첫 문장에서 제목을 되풀이하지 말고 바로 장면이나 근거로 들어갑니다. 다른 섹션의 메시지를 끌어오지 않습니다.
- 인용은 [구성안]이 이 섹션에 배정한 문구만 따옴표로 그대로, 한 번만 씁니다. 배정되지 않은 괘사·효사·대상전은 인용하지 않습니다.
- 계절·국면(season)은 화면의 시기 카드에 따로 나옵니다. 다른 섹션에서는 그 문장을 옮겨 적거나 계절을 다시 말하지 않습니다. 꼭 필요하면 season과 같은 뜻으로 몇 단어만 쓰고, 다른 계절·절기를 새로 꺼내지 않습니다.
- 상담자의 사정은 [구성안]의 facts에 있는 것만 사실로 씁니다(그 밖의 사정은 [공감]의 갈래 장면처럼 가능성으로만). "이미 결정하셨으니"처럼 말하지 않은 사정을 가정하지 않습니다.
- 달 단위 시기 표현("11월 초", "12월 중순", "다음 주", "두 달 안")은 시기 섹션에서만 씁니다. 다른 섹션에서는 꺼내지 않습니다 — 같은 시기가 다섯 군데 되풀이된 일이 있었습니다. 사주 흐름 섹션의 대운(10년)·세운(올해·내년)은 예외입니다.
- 괘사·효사·대상전 원문은 화면에 따로 상자로 보입니다. 본문에서 원문을 따옴표로 다시 옮겨 적지 않고, "괘사가 말하는 곤궁은 …"처럼 그 말이 지금 무엇을 가리키는지만 풉니다.
- 판정 한 줄(verdict.line)과 판정 이유(reasons)는 화면 맨 위에 따로 나옵니다. 그 문장을 되풀이하지 않고, 이 섹션에서만 할 수 있는 이야기를 씁니다.

[쉬운 말 — 해설서 문장이 아니라 사람에게 하는 말]
- 친한 언니·누나가 카페에서 말해 주듯 생활 말로 씁니다. 해설서·번역서 문장을 옮기지 않습니다.
- 이렇게 바꿉니다: "외부 진입이 지연되고 있다" → "회사 밖으로 나가는 일이 생각보다 늦어지고 있어요" / "물질적·외적 제약" → "돈이나 주변 여건" / "불굴의 의지가 형태를 갖춘 것" → "포기하지 않고 실제로 만들어 낸 것" / "결과 도출이 예상된다" → "결과가 보이기 시작할 수 있어요".
- 피할 말: 진입, 지연, 물질적, 외적, 내적, 제약, 불굴, 도출, 시사, 측면, 요소, 형태를 갖추다, ~에 해당하다.
- 추상어보다 상담자의 실제 장면을 씁니다("퇴사 날짜를 먼저 정하기보다, 첫 고객 한 명을 먼저 찾는 쪽").

[사주와 주역 — 역할 나눔]
- 사주는 "이 사람이 어떤 사람이고 지금 어떤 계절을 지나고 있나", 주역은 "이 일에서 어떻게 움직이고 무엇에 막히고 어디에 닿나"를 말합니다.
- 판정(하라·기다려라)은 괘가 냅니다. 사주로 길흉을 따로 단정하지 않고, 괘가 낸 판정이 이 사람에게 왜 그렇게 작동하는지를 사주로 설명합니다(예: "일간이 바위와 쇠라 끊고 나가는 쪽인데, 괘는 아직 멈추라고 해요 — 그래서 지금이 더 답답한 거예요").
- 사주 판단은 [사주 메모]와 [사주 명식]에 있는 것만 씁니다. 명식에 없는 오행을 강하다고 하거나, 없는 운을 지어내지 않습니다. 신강·신약·용신은 단정하지 않습니다.

[읽는 법]
- 괘 원문이 풀이의 주인입니다. 괘 이름과 효 위치를 직접 짚습니다("수화기제는 …", "오효는 …").
- 다산 정약용이 정리한 해석법을 이름 없이 실제로 씁니다: 물상(괘의 자연 상징으로 장면 그리기), 호체(괘 안쪽에 숨은 괘로 속사정 읽기), 효변(변효 자리가 지괘의 같은 자리로 바뀐 모습까지 겹쳐 읽기), 추이(괘가 계절 따라 옮겨 가는 국면 읽기). 섹션마다 맡은 법이 정해져 있습니다.
- 상괘·하괘의 자연 상징(물·불·산·못·바람·우레·하늘·땅)으로 장면을 그리듯 풀고, 그 그림이 상담자의 지금과 어떻게 겹치는지 보여 줍니다.
- 용어(본괘·지괘·변효·불변효·대상전·호체)는 처음 나올 때 한 구절로 풀어 줍니다("지괘, 곧 이 일이 흘러가 닿는 괘").
- 원문(괘사·효사·대상전)이나 사주 글자를 다룰 때는 세 걸음으로 풉니다. 원문을 "~라고 해요"로 옮기고 끝내면 무슨 말인지 모르는 겉핥기가 됩니다(2026-10-19 피드백).
  ① 그림 — 그 말이 그리는 장면을 눈에 보이게("수레를 끌던 소가 멈춰 서고, 사람이 수레에서 내려 땅에 발을 딛는 장면이에요")
  ② 까닭 — 왜 그런 뜻이 되는지, 괘의 모양·효의 자리·오행의 관계로 한 문장("이 자리는 아래 괘의 맨 위, 안에서 밖으로 나서기 직전이라서요")
  ③ 삶 — 그 그림이 사람의 삶에서 어떤 모습으로 나타나는지 → 아래 [공감]의 방식으로

[공감 — 상황을 그려 주기]
읽는 사람이 "어, 내 얘기네" 하고 멈추게 하는 것이 이 리포트의 힘입니다. 괘와 사주가 말하는 흐름을 실제 생활 장면으로 바꿔 보여 줍니다.
- 갈래로 그려 주기: 한 장면을 단정하지 말고 두세 갈래로 펼쳐 읽는 사람이 자기 자리를 찾게 합니다.
  예: "이런 흐름이라면 회사 안에서 맡은 일은 늘었는데 인정은 그만큼 따라오지 않았을 수도 있고, 이미 마음은 밖에 나가 있는데 붙잡는 일이 하나둘 생겼을 수도 있어요. 혼자 준비해 오신 분이라면 밤마다 계획을 고쳐 쓰다가 '이게 맞나' 하고 덮어 둔 날이 있었을 가능성도 있어요."
- 속마음 들려주기: 상담자가 속으로 했을 법한 말을 따옴표 없이 그대로 옮깁니다. 예: 지금 나가면 너무 이른 건 아닐까, 그렇다고 더 기다리면 영영 못 나가는 건 아닐까 — 이런 생각이 번갈아 드셨을 것 같아요.
- 지나온 일 되짚기: 괘나 운이 가리키는 지난 흐름을 "~한 적도 있었을 것 같아요", "~하셨을 수도 있어요"로 짚습니다.
- 애쓴 것 알아주기: 겉으로 보이는 모습과 속사정의 차이를 짚습니다. 예: 주변에서는 알아서 잘하는 사람으로 보지만, 사실 혼자 하고 싶어서 그렇게 해 온 건 아니잖아요.
- 앞으로 올 장면과 그때의 마음: 일어날 수 있는 일을 장면으로 그리고, 그때 들 마음까지 미리 짚습니다. 예: 막상 기회가 먼저 오면 반갑기보다 '내가 해도 되나' 망설여질 수 있어요.
- 다르게 보기: 막힘이나 기다림을 다른 각도로 바꿔 보여 줍니다. 예: 늦어지는 게 밀려난 게 아니라, 그릇이 만들어지는 시간일 수 있어요.
- 지켜야 할 선: 갈래 장면은 괘·효·사주가 가리키는 흐름과 상담자가 말한 사정(facts)에서 나와야 합니다. 그럴듯한 아무 이야기나 붙이지 않습니다. 모르는 사정은 "~했을 수도 있어요", "~일 가능성도 있어요"처럼 가능성으로만 말하고, 상담자가 한 말처럼 단정하지 않습니다. 겁주는 장면(사고·병·이별)은 만들지 않습니다.

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

/* ── 사주 명식을 모델이 읽을 글로 — 간지는 한글, 십신은 뜻과 함께 ── */
function sajuText(s) {
  if (!s) return '';
  const tg = (x) => `${x.ganTen}/${x.zhiTen}`;
  const pil = s.pillars.map((p) => (p.unknown ? `${p.name}: 태어난 시간 모름 — 시주 없이 봄`
    : `${p.name} ${p.gz} — 천간 ${p.gan.ko}(${p.gan.el}, ${p.gan.ten}) / 지지 ${p.zhi.ko}(${p.zhi.el}, ${p.zhi.ten})${p.hidden?.length ? ` · 지장간 ${p.hidden.map((h) => `${h.ko}(${h.ten})`).join(' ')}` : ''}`));
  const used = new Set(Object.keys(s.tens));
  [s.current, ...s.seun, ...s.monthly].filter(Boolean).forEach((x) => { used.add(x.ganTen || x.month?.ganTen); used.add(x.zhiTen || x.month?.zhiTen); });
  const nextDw = s.daewoon.find((d) => s.current && d.startYear > s.current.startYear);
  return lines(
    `[사주 명식] ${s.input.calendar} ${s.input.year}.${s.input.month}.${s.input.day}${s.input.leap ? '(윤달)' : ''} ${s.input.timeKnown ? `${s.input.hour}시 ${s.input.minute}분` : '태어난 시간 모름'} · ${s.input.gender} · ${s.zodiac}띠\n${pil.join('\n')}`,
    `[일간] ${s.dayMaster.gan}${s.dayMaster.el}(${s.dayMaster.yang ? '양' : '음'}) — ${s.dayMaster.image}: ${s.dayMaster.trait}`,
    `[오행 — 드러난 글자 수] ${Object.entries(s.elements).map(([k, v]) => `${k}${v}`).join(' ')}\n[십신 — 일간 제외 개수] ${Object.entries(s.tens).map(([k, v]) => `${k}${v}`).join(' ')}`,
    `[지금의 운]\n대운 ${s.current ? `${s.current.startYear}~${s.current.endYear}년 ${s.current.gz}(천간 ${s.current.ganTen}, 지지 ${s.current.zhiTen})` : '아직 대운 전'}${nextDw ? `\n다음 대운 ${nextDw.startYear}~${nextDw.endYear}년 ${nextDw.gz}(${tg(nextDw)})` : ''}\n${s.seun.map((y) => `${y.year}년 세운 ${y.gz}(천간 ${y.ganTen}, 지지 ${y.zhiTen})`).join('\n')}`,
    `[앞으로 12개월 월운]\n${s.monthly.map((m) => `${m.ym} ${m.month.gz}(${m.month.ganTen}/${m.month.zhiTen})`).join('\n')}`,
    `[십신 뜻]\n${[...used].filter((k) => TEN_MEANING[k]).map((k) => `${k}: ${TEN_MEANING[k]}`).join('\n')}`,
  );
}

/* ── 노드 1-2: 사주 분석 — 고민을 모르는 채로 명식만 읽는다(괘 분석과 병렬) ── */
const ANALYZE_SAJU = {
  name: 'analyze_saju',
  temperature: 0.2,
  timeoutMs: 25000,
  maxTokens: 1600,
  system: `당신은 명리학(사주) 해석가입니다. 상담자의 고민을 모르는 채로 [사주 명식]만 읽고, 뒤 단계가 쓸 해석 재료를 record_saju 도구로 메모합니다.
- 메모입니다. 각 필드 1~2문장, 근거(어느 기둥·어느 글자·어느 십신)를 한글로 남깁니다. 한자는 쓰지 않습니다.
- 명식에 있는 것만 씁니다. 신강·신약·용신은 단정하지 말고 "~쪽으로 기울어 보인다"처럼 경향과 근거로만.
- 시주가 없으면(태어난 시간 모름) 시주에 기댄 판단을 하지 않습니다.
- 대운은 10년의 큰 계절, 세운은 그해의 날씨, 월운은 그달의 바람으로 읽습니다.`,
  tool: tool('record_saju', '명식만으로 해석 재료를 메모한다', {
    temperament: str('일간과 명식 구성으로 본 기질 1~2문장'),
    strengths: str('명식에서 두드러지는 힘(많은 오행·십신)과 그것이 삶에서 드러나는 모습'),
    gaps: str('부족하거나 없는 오행·십신과 그 빈자리가 드러나는 모습'),
    daewoon_now: str('지금 대운이 이 사람에게 어떤 10년인지(십신·오행 근거)'),
    seun_now: str('올해 세운이 어떤 해인지'),
    seun_next: str('내년 세운이 어떤 해인지'),
    notable_months: arr(obj({ ym: str('YYYY-MM'), why: str('그 달이 두드러지는 이유(월운 십신)') }), '앞으로 12개월 가운데 두드러지는 달 2~4개', 0, 4),
    tension: str('명식·운에서 부딪히는 지점(예: 편관이 겹치는 해) 1~2문장'),
  }),
  user: ({ input }) => sajuText(input.saju),
};

/* ── 노드 2: 구성안(편집장) — 리포트 전체의 단일 기준을 정한다. 이후 작가들은 이 기준만 따른다 ── */
// 출력은 평평한 필드로 받는다 — 중첩 객체(verdict·points·quotes·bubbles)로 받았을 때 Haiku가 객체째 빼먹는 일이 잦았다.
// 작가 노드가 쓰기 편하게 nestPlan()이 다시 묶는다.
const PLAN = {
  name: 'plan_reading',
  styleSkip: ['facts', 'keywords', 'point_saju', 'point_shape', 'point_heart', 'point_flow', 'point_dos', 'point_donts', 'quote_shape', 'quote_flow', 'quote_dos'],
  noQuote: ['verdict_label', 'verdict_line', 'reasons', 'empathy', 'bubble_heart', 'bubble_flow', 'bubble_timing', 'season'],
  noTiming: true,
  timingOk: ['season'], // season은 「때」 카드 맨 위에 나오니 달 이름이 있어도 된다 — 이것 때문에 구성안을 다시 쓰면 순차 구간이 8~10초 늘었다
  temperature: 0.3,
  timeoutMs: 20000,
  maxTokens: 1800,
  checkStyle: true,
  system: `당신은 주역사주 리포트의 편집장입니다. 괘 분석 메모·사주 메모·괘 원문·상담자의 고민과 문답을 보고, 화자 '연서'가 쓸 리포트의 기준을 plan_reading 도구로 한 번에 정합니다. 이 기준이 섹션 사이의 반복과 모순을 막습니다.
- 판정은 괘가 냅니다. 사주 메모는 그 판정이 이 사람에게 왜 그렇게 작동하는지(기질·지금의 운)를 설명하는 데 씁니다. 사주로 판정을 뒤집지 않습니다.
- verdict_kind: 고민에 대한 분명한 판정. go(해도 좋다) / wait(아직 때가 아니다) / conditional(조건이 맞으면 좋다) / no(하지 않는 편이 길하다) / general(고민 없이 본 점). 괘 분석의 길흉 기조와 어긋나지 않게 정합니다.
- verdict_label: 연서가 건네는 판정 한 마디(해요체, 20자 안팎. 예: "떠나도 괜찮아요, 조건이 하나 있어요").
- verdict_line: 리포트 전체를 한 줄로(30자 안팎). 명사형이나 해요체로 끝내고 "~열린다."처럼 반말로 끝내지 않습니다.
- reasons: 2~3개. 각각 근거가 된 괘나 효 이름을 넣은 해요체 한 문장. 원문 문구를 따옴표로 옮기지 말고 뜻으로 풀어 쓰고(인용은 각 섹션 몫), 날짜는 넣지 않습니다.
- keywords: 이 점을 요약하는 명사형 단어 3개(2~6자, 해시태그 없이).
- season: 지금의 국면을 해요체 한 문장(50자 안팎, 쉬운 말)으로 확정합니다. 날짜·괘 이름·벽괘 이름은 넣지 않습니다. 분석 메모와 [추이] 블록을 따르고 다른 계절·절기를 새로 만들지 않습니다. 이후 모든 섹션은 이 문장만 씁니다.
- facts: 상담자가 고민·문답에서 실제로 말한 사실만 3~6개. 짐작이나 해석은 넣지 않습니다.
- empathy: 연서가 여는 공감 한 문장(해요체). 상담자가 쓴 말을 빌려 지금의 갈등을 짚습니다.
- point_saju / point_shape / point_heart / point_dos / point_donts / point_flow: 섹션 제목입니다. 화면에 크게 나오니 잡지 기사 소제목처럼 장면이 보이게, 18자 안팎으로 씁니다. "지금의 형세", "이 점의 핵심"처럼 섹션 이름을 설명하는 말은 제목이 아닙니다. 서로 겹치지 않게: saju=사주로 본 이 사람의 지금 계절(예: "쇠가 불에 달궈지는 한 해"), shape=본괘 그림이 말하는 지금(예: "물이 다 빠진 연못 앞이에요"), heart=중심 효가 고민에 답하는 것(예: "금 수레는 늦게 와도 와요"), dos=어떻게 움직일지의 큰 줄기(예: "바닥이 드러났을 때 할 일"), donts=무엇이 막는지의 큰 줄기(예: "조급함이 먼저 길을 막아요"), flow=지괘가 보여 주는 결과(예: "험한 물길을 두 번 건너는 일").
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
    point_saju: str('사주 흐름 섹션 제목, 18자 안팎'),
    point_shape: str('본괘 섹션 제목, 18자 안팎, 장면이 보이게'),
    point_heart: str('중심 효 섹션 제목, 18자 안팎'),
    point_dos: str('어떻게 움직일까 섹션 제목, 18자 안팎'),
    point_donts: str('무엇이 막을까 섹션 제목, 18자 안팎'),
    point_flow: str('어디에 닿을까(지괘) 섹션 제목, 18자 안팎'),
    quote_shape: str('본괘 괘사 풀이 그대로'),
    quote_flow: str('지괘 괘사 풀이 그대로, 없으면 빈 문자열'),
    quote_dos: str('본괘 대상전 풀이 그대로'),
    bubble_heart: str('중심 효 앞 한마디, 해요체, 상담자 사정을 짚는 말'),
    bubble_flow: str('지괘 앞 한마디, 해요체, 상담자 사정을 짚는 말'),
    bubble_timing: str('시기 앞 한마디, 해요체, 상담자 사정을 짚는 말'),
    mood: { type: 'string', enum: ['smile', 'serious', 'warm'] },
  }, ['quote_flow', 'facts']),
  user: ({ input, analysis: a, saju: sj }) => lines(
    block('괘 분석 메모', json(without(a, ['windows']))), // 시기 창은 「때」 작가 몫 — 구성안에 주면 달 이름을 여기저기 옮겨 적었다
    block('사주 메모', json(without(sj, ['notable_months']))),
    `[일간] ${input.saju.dayMaster.gan}${input.saju.dayMaster.el} — ${input.saju.dayMaster.image}`,
    input.src.ben,
    input.src.ji,
    block('중심 자리', input.src.lines),
    input.src.tui,
    `[상담자] ${input.name}\n고민: ${input.question}\n${qaText(input.qa)}`,
  ),
};

// 제목이 길면(18자 안팎을 넘어 40자까지 나왔다) 쉼표 앞 첫 마디만 쓴다
const shortTitle = (t) => { const s = String(t || '').trim(); return s.length > 24 && /[,，]/.test(s) ? s.split(/[,，]/)[0].trim() : s; };
function nestPlan(f) {
  for (const k of ['point_saju', 'point_shape', 'point_heart', 'point_flow', 'point_dos', 'point_donts']) f[k] = shortTitle(f[k]);
  return {
    verdict: { kind: f.verdict_kind, label: f.verdict_label, line: f.verdict_line, reasons: f.reasons },
    keywords: f.keywords,
    season: f.season,
    facts: f.facts || [],
    empathy: f.empathy,
    points: { saju: f.point_saju, shape: f.point_shape, heart: f.point_heart, flow: f.point_flow, dos: f.point_dos, donts: f.point_donts },
    quotes: { shape: f.quote_shape, flow: f.quote_flow || '', dos: f.quote_dos },
    bubbles: { heart: f.bubble_heart, flow: f.bubble_flow, timing: f.bubble_timing },
    mood: f.mood,
  };
}

/* ── 노드 3: 쓰기 노드들 — 구성안 뒤에 병렬로 돈다. 구성안 + 자기 섹션 원문만 받는다 ──
   2026-10-17 피드백으로 효 읽기(write_yao)와 질문별 답(write_qa)을 따로 뗐다: 한 노드에 몰았더니 효사는 한두 줄,
   질문 답은 한 마디로 줄어들었다. 변효가 없으면 여섯 효를 초반·중반·후반 흐름으로 하나씩 읽는다. */
const STAGE_RULE = `효의 자리는 흐름의 단계이기도 합니다: 초효·이효 = 초반 흐름(일의 시작, 가까운 때), 삼효·사효 = 중반 흐름(전환, 안과 밖이 만나는 때), 오효·상효 = 후반 흐름(정점과 마무리, 먼 때).`;

const sajuBrief = (input, sj) => block('사주 메모', json({ 일간: `${input.saju.dayMaster.gan}${input.saju.dayMaster.el} — ${input.saju.dayMaster.image}`, ...without(sj, ['notable_months']) }));

/* 사주 흐름 — 명식으로 본 이 사람의 지금 계절과, 이 고민이 그 안에서 놓인 자리 */
const WRITE_FLOW = {
  name: 'write_flow',
  noQuote: ['portrait', 'past', 'now', 'fit'],
  noTiming: true,
  temperature: 0.45,
  timeoutMs: 35000,
  maxTokens: 2600,
  checkStyle: true,
  // 2026-10-19 피드백: "사주 내용이 어떻게 하고 끝" — 운 이름만 말하고 끝났다. 사람 그림 → 지나온 시간 → 올해 → 이 고민의 자리로,
  // 장면마다 [공감]의 갈래·속마음·되짚기를 넣는다.
  system: writerSystem('사주로 본 이 사람과 지금의 흐름', 'write_flow', `- 제목(point_saju)은 화면에 크게 나오니 되풀이하지 않습니다. 네 문단을 씁니다.
- portrait 5~6문장: 이 사람의 그림. 일간의 모습("바위와 쇠의 사람이에요") → 까닭(일간의 오행, 명식에서 많은 오행·적거나 없는 오행) → 이런 기질이 실제 삶에서 드러나는 장면을 갈래로("이런 분들은 ~할 때 ~하는 경우가 많아요. ~하신 분이라면 ~했던 기억도 있으실 거예요") → 겉으로 보이는 모습과 속사정을 알아주는 한 문장.
- past 4~5문장: 지금 대운에 들어선 해(명식의 대운 시작 연도)부터 지나온 시간을 되짚습니다. 그 대운의 십신이 가리키는 흐름을 장면 갈래로("~년 무렵부터 ~한 일이 늘었을 수도 있고, ~하신 분이라면 ~를 겪으면서 ~하셨을 가능성도 있어요"). 단정하지 않고 가능성으로.
- now 4~5문장: 올해 세운이 이 사람에게 어떤 날씨인지(십신의 뜻을 풀어서), 그 날씨 속에서 요즘 들었을 법한 속마음, 내년 세운으로 넘어가며 바뀌는 결.
- fit 3~4문장: 이 고민이 그 흐름의 어디에 놓였는지 — 판정(verdict)이 이 사람의 기질·지금의 운에서 왜 그렇게 작동하는지. 괘 이름을 한 번 짚어 주역 풀이로 넘어가는 다리가 되게 합니다.
- 대운·세운 이름은 한글 간지로("갑신 대운", "병오년"). 사주로 길흉을 단정하지 않고, 명식에 있는 것만 씁니다.`),
  tool: tool('write_flow', '사주로 본 이 사람과 지금의 흐름을 쓴다', {
    portrait: str('이 사람의 그림 5~6문장, 해요체'),
    past: str('지금 대운에서 지나온 시간 4~5문장, 해요체'),
    now: str('올해와 내년 4~5문장, 해요체'),
    fit: str('이 고민이 놓인 자리 3~4문장, 해요체'),
  }),
  user: ({ input, plan: p, saju: sj }) => lines(
    `이름: ${input.name}\n고민: ${input.question}`,
    block('구성안', json({ verdict: p.verdict, facts: p.facts, point_saju: p.points.saju })),
    input.src.ben.split('\n')[0],
    sajuText(input.saju),
    sajuBrief(input, sj),
  ),
};

const WRITE_OPEN = {
  name: 'write_open',
  noQuote: ['answer', 'shape'],
  noTiming: true,
  temperature: 0.4,
  timeoutMs: 35000,
  maxTokens: 2800,
  checkStyle: true,
  system: writerSystem('질문에 대한 답과 본괘 풀이', 'write_open', `- answer 5~6문장: empathy는 화면에서 연서의 말풍선으로, verdict.label은 바로 위 판정 줄로 따로 보이니 다시 쓰지 않습니다. 판정의 이유를 괘·효 이름을 짚어 두 가지쯤 풀고, 그것이 상담자의 사정(facts)에서 무엇을 뜻하는지 실제 장면으로 말합니다. 이 고민 앞에서 들었을 법한 속마음을 한 번 짚고, 사주 메모에서 한 가지(기질이나 올해의 운)를 엮어 "이 사람에게 왜 그런지"를 붙입니다. 원문 인용과 달 단위 시기 표현은 쓰지 않습니다.
- shape 두 문단, 합쳐 7~9문장(문단 사이 줄바꿈): 제목(point_shape)은 되풀이하지 않습니다.
  · 첫 문단 — 괘사를 세 걸음으로: 물상(본괘의 상괘·하괘 자연 상징이 겹친 장면, "못 아래로 물이 다 빠져나간 모습이에요") → 까닭(왜 그 모양이 그런 뜻인지) → 괘사(quote_shape)가 그 장면에 붙인 말이 무슨 뜻인지. 괘사는 화면 상자에 나오니 옮겨 적지 말고 풉니다.
  · 둘째 문단 — 그 장면이 상담자의 지금과 겹치는 모습을 [공감]의 갈래로 두세 가지 그리고, 호체 블록이 있으면 "겉은 ~이지만 안에는 ~가 숨어 있어요"로 속사정을 짚습니다(호체를 지괘와 섞지 않습니다).`),
  tool: tool('write_open', '질문에 대한 답과 본괘 풀이를 쓴다', {
    answer: str('질문에 대한 답 5~6문장, 해요체'),
    shape: str('본괘 풀이 두 문단 7~9문장, 해요체, 문단 사이 줄바꿈'),
  }),
  user: ({ input, analysis: a, plan: p, saju: sj }) => lines(
    `이름: ${input.name}\n고민: ${input.question}`,
    block('구성안', json({ verdict: p.verdict, empathy: p.empathy, facts: p.facts, point_shape: p.points.shape, quote_shape: p.quotes.shape })),
    input.src.ben,
    input.src.hoche,
    block('괘 분석 메모', json({ image: a.image, hidden: a.hidden, why: a.why })),
    sajuBrief(input, sj),
  ),
};

const WRITE_YAO = {
  name: 'write_yao',
  noQuote: ['heart', 'yao', 'stages'],
  noTiming: true,
  temperature: 0.4,
  timeoutMs: 48000,
  maxTokens: 5200,
  checkStyle: true,
  system: writerSystem('중심 효 풀이와 효 하나하나', 'write_yao', `- 쓰는 순서: yao(효 전부) → stages → heart. yao를 빈 배열로 두면 안 됩니다([중심 자리]가 "여섯 효 모두 변함"일 때만 빈 배열).
- heart 4~5문장: 제목(point_heart)은 되풀이하지 않습니다. 길흉 기조를 한 번 분명히 하고, 아래 효들이 모여 고민에 무엇을 말하는지 한데 묶어 줍니다. 그 메시지를 들었을 때 상담자가 느낄 법한 마음을 한 번 짚습니다.
- yao: [중심 자리]에 적힌 효를 하나도 빼지 않고, 적힌 순서대로 하나씩 읽습니다. 각 항목은 {pos: "초효"처럼 효 이름, stage: "초반"·"중반"·"후반" 중 하나, reading: 두 문단 5~7문장, 문단 사이 줄바꿈}. 효사 원문은 화면에서 그 효 바로 위 상자에 보이니 옮겨 적지 않습니다.
  · 첫 문단 — 효사를 세 걸음으로: 그림(효사가 그리는 장면) → 까닭(이 자리가 괘의 어디이고 왜 그런 말이 붙었는지, 자리 풀이 참고) → 뜻.
  · 둘째 문단 — 그 효가 상담자의 고민에서 어떤 장면으로 나타나는지 [공감]의 갈래로 두 가지쯤("~한 상황이라면 ~했을 수도 있고, ~하신 분이라면 ~") 그리고, 효변 줄이 있으면 바뀐 뒤의 모습을 이어 붙입니다.
- 효변: [중심 자리]에 "효변 — 지괘 ○○의 같은 자리" 줄이 있는 효는, 그 자리가 바뀐 뒤의 모습(지괘 같은 자리의 효사)을 한 문장으로 겹쳐 읽습니다("이 자리가 바뀌면 ~가 돼요 — 지금의 ~가 ~로 넘어가는 거예요").
- stages: [중심 자리]가 "변효 없음"이면 초반·중반·후반 흐름 세 개를 {stage, reading: 2~3문장}으로 씁니다(시기 표현 없이). 변효가 있으면 빈 배열.
- [중심 자리]가 "여섯 효 모두 변함"이면 yao는 빈 배열이고, heart를 6~8문장으로 늘려 [해석 원칙]대로 읽습니다.
- ${STAGE_RULE}
- [해석 원칙]과 [심장 규칙]이 이 부분의 다른 지침보다 우선합니다.`),
  tool: tool('write_yao', '효 하나하나를 읽고, 중심 효 풀이로 묶는다', {
    yao: arr(obj({ pos: str('효 이름, 예: "초효"'), stage: { type: 'string', enum: ['초반', '중반', '후반'] }, reading: str('그 효의 풀이 두 문단 5~7문장, 해요체, 효사 원문은 옮겨 적지 않음') }), '필수 — [중심 자리]에 적힌 효 전부를 순서대로(변효 없음이면 여섯 개)', 0, 6),
    stages: arr(obj({ stage: { type: 'string', enum: ['초반 흐름', '중반 흐름', '후반 흐름'] }, reading: str('그 단계의 흐름 2~3문장, 해요체') }), '변효가 없을 때만 세 단계, 아니면 빈 배열', 0, 3),
    heart: str('중심 효 풀이 4~5문장, 해요체'),
  }, ['stages']),
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

/* 어떻게 움직일까 · 무엇이 막을까 — 행동양식과 장애물. 둘 다 근거(괘·효·호체·사주)를 단다 */
const WRITE_PATH = {
  name: 'write_path',
  noQuote: ['acts', 'blocks'],
  noTiming: true,
  temperature: 0.45,
  timeoutMs: 40000,
  maxTokens: 3800,
  checkStyle: true,
  system: writerSystem('어떻게 움직일지와 무엇이 막을지', 'write_path', `- acts 3개 {head, body, basis}: 이 일에서 움직이는 방식.
  · head: 한 줄 제목 16자 안팎, 행동이 보이게("첫 고객 한 명부터 만나 보기").
  · body 3~4문장: ① 왜 — 근거가 된 괘·효의 그림과 그 까닭(원문 따옴표 없이) ② 어떻게 — 상담자의 사정(facts) 안에서 무엇을, 얼마나, 어떤 순서로 ③ 해 보면 어떤 장면이 펼쳐질지, 그때 들 마음.
  · 첫 항목은 본괘 대상전(quote_dos)의 태도를 옮긴 것(basis "대상전"). 한 항목은 사주 메모의 강점(strengths)을 살리는 방식으로 쓰고 basis에 사주 근거를 씁니다(예: "일간 경금", "대운 편재").
- blocks 3개 {head, body, sign, basis}: 이 일을 막는 것. 근거가 있는 것만 씁니다 — 흉하거나 경계하는 효사, 호체가 말하는 속사정, 사주 메모의 부딪히는 지점(tension)이나 빈자리(gaps).
  · head: 한 줄 제목 16자 안팎("조급함이 먼저 길을 막아요").
  · body 3~4문장: 무엇이, 왜(근거의 그림과 까닭), 어떤 장면으로 막는지 — [공감]의 갈래로("~한 상황이라면 ~하다가 ~할 수도 있고"). 막히는 게 상담자 탓이 아닌 경우는 그렇게 알아줍니다.
  · sign 1~2문장: 그 장애물이 다가올 때 알아차릴 신호를 속마음으로("'이 정도는 혼자 해도 되겠지' 싶어질 때가 그 신호예요").
  · 적어도 하나는 사주에서, 적어도 하나는 괘·효에서 가져옵니다.
- basis 이름: 괘·효 쪽은 "대상전"(본괘 것만), "괘사", "단전", 효 이름("사효"), "호체", "지괘", "지괘 대상전". 사주 쪽은 "일간 ○○", "대운 ○○(십신)", "올해 세운 ○○(십신)", "오행 ○ 부족" 처럼 명식에 실제로 있는 것만.
- 뻔한 조언 금지("가족과 충분히 대화", "준비를 철저히", "신중하게"). 이 괘와 이 명식이 아니었다면 떠올리지 못했을 한 수를 씁니다.
- 여섯 항목이 서로 겹치지 않게, 같은 문장 끝을 되풀이하지 않게 씁니다.`),
  tool: tool('write_path', '행동양식과 장애물을 쓴다', {
    acts: arr(obj({ head: str('한 줄 제목'), body: str('왜 + 어떻게 + 펼쳐질 장면, 3~4문장'), basis: str('근거 이름') }), '어떻게 움직일까', 3, 3),
    blocks: arr(obj({ head: str('한 줄 제목'), body: str('무엇이 왜 어떤 장면으로 막는지, 3~4문장'), sign: str('알아차릴 신호 1~2문장, 속마음으로'), basis: str('근거 이름') }), '무엇이 막을까', 3, 3),
  }),
  user: ({ input, plan: p, saju: sj }) => {
    const nameOf = (blk) => (String(blk || '').match(/^\[(?:본괘|지괘)\] (\S+?)\(/m) || [])[1] || '';
    const ben = nameOf(input.src.ben), ji = nameOf(input.src.ji);
    return lines(
      `이름: ${input.name}\n고민: ${input.question}\n${qaText(input.qa)}`,
      `[근거 이름 정하기] 본괘는 ${ben}${ji ? `, 지괘는 ${ji}` : ', 지괘 없음'}입니다. basis "괘사"·"대상전"·"단전"은 ${ben}의 것에만 씁니다.${ji ? ` ${ji}의 괘사·대상전이면 "지괘", "지괘 대상전"이라고 쓰고 본문에서도 ${ji}라고 부릅니다.` : ''}`,
      block('구성안', json({ verdict: p.verdict, facts: p.facts, point_dos: p.points.dos, point_donts: p.points.donts, quote_dos: p.quotes.dos })),
      input.src.ben,
      block('중심 자리', input.src.lines),
      input.src.hoche,
      input.src.ji,
      sajuBrief(input, sj),
    );
  },
};

/* 어디에 닿을까 — 지괘(물상) + 추이(계절 국면) + 그즈음의 운 */
const WRITE_CORE = {
  name: 'write_core',
  noQuote: ['flow'],
  noTiming: true,
  temperature: 0.4,
  timeoutMs: 35000,
  maxTokens: 1800,
  checkStyle: true,
  system: writerSystem('어디에 닿을지(지괘)', 'write_core', `- flow 두 문단, 합쳐 6~8문장(문단 사이 줄바꿈): 제목(point_flow)은 되풀이하지 않습니다. 지괘가 없으면 본괘의 자리가 그대로 이어진다는 뜻으로 씁니다.
  · 첫 문단 — 지괘 괘사를 세 걸음으로: 지괘의 상괘·하괘 상징이 그리는 장면(물상) → 까닭 → 괘사(quote_flow, 화면 상자에 나오니 옮겨 적지 않음)의 뜻. [추이] 블록의 국면(자라는 쪽인지 거두는 쪽인지)으로 그 결과가 어떤 계절의 결과인지 한 문장.
  · 둘째 문단 — 그곳에 닿았을 때의 장면을 [공감]의 방식으로: 그때 실제로 어떤 모습일지 갈래로 그리고, 그때 들 마음(반가움·허탈함·망설임 등)을 미리 짚고, 사주 메모의 내년 세운(seun_next)으로 그즈음 이 사람의 운을 한 문장 덧붙입니다.`),
  tool: tool('write_core', '어디에 닿을지 쓴다', {
    flow: str('결과 두 문단 6~8문장, 해요체, 문단 사이 줄바꿈'),
  }),
  user: ({ input, analysis: a, plan: p, saju: sj }) => lines(
    `이름: ${input.name}\n고민: ${input.question}`,
    block('구성안', json({ verdict: p.verdict.kind, facts: p.facts, point_flow: p.points.flow, quote_flow: p.quotes.flow })),
    input.src.ji,
    input.src.tui,
    block('괘 분석 메모', json({ direction: a.direction, phase: a.phase })),
    block('사주 메모', json({ seun_next: sj.seun_next, daewoon_now: sj.daewoon_now })),
  ),
};

/* 시기 — 범위·근거는 육효 응기 계산값, 그 달의 월운은 서버가 붙인 값. 작가는 무엇이 움직이고 그 달이 어떤 달인지만 쓴다 */
const WRITE_TAIL = {
  name: 'write_tail',
  noQuote: ['timeline', 'closing', 'timing_title'],
  temperature: 0.4,
  timeoutMs: 35000,
  maxTokens: 2400,
  checkStyle: true,
  system: writerSystem('시기와 마무리', 'write_tail', `- timeline: [시기 창]의 창마다 하나씩, 같은 순서·같은 개수로 {what, watch, luck}를 씁니다. 범위(range)는 화면이 그대로 보여 주니 쓰지 않고, 달 이름도 다시 쓰지 않습니다.
  · what 3문장: 일어날 수 있는 일을 갈래로 두 가지쯤 그리고("~에서 먼저 연락이 올 수도 있고, ~하신 분이라면 ~"), 그때 들 마음을 한 문장. 그 창의 근거(basis)에 적힌 자리가 무엇을 나타내는지에 맞춰, 그 사이 상담자에게 실제로 일어날 수 있는 일(사건·반응·변화)을 장면으로 씁니다. 나를 나타내는 자리(세효)면 상담자 쪽의 마음·준비·결단, 상대·결과를 나타내는 자리(응효)면 상대나 바깥의 반응, 물으신 일을 맡은 자리(용신)면 그 일 자체의 움직임, 움직이는 자리면 지금 바뀌고 있는 일. "비어 있던 자리가 차는 달"은 실체가 생기는 때, "깨진 자리가 다시 서는 달"은 틀어졌던 것이 바로 서는 때, "짝을 만나 묶이는 달"은 사람·조건이 맞물리는 때, "부딪혀 깨어나는 달"은 멈춰 있던 일이 부딪힘으로 움직이는 때로 읽습니다.
  · watch 1문장: 그때 무엇을 보면 흐름을 알 수 있는지.
  · luck 1문장: 그 창의 [그 달의 운](월운 간지와 십신)이 이 사람에게 어떤 바람인지 — 십신의 뜻으로 풀고 what과 이어지게("편재가 드는 달이라 돈이 오가는 일이 함께 움직여요").
  · what·watch·luck·closing에는 계절·달 이름·"내년"·"다음 주" 같은 시기 말을 쓰지 않습니다. 할 일 목록이 아니라 일어날 수 있는 일을 씁니다.
- timing_title: 시기 섹션 제목 18자 안팎, 장면이 보이게. 달 이름은 넣지 않습니다.
- closing 2문장: 연서의 다정한 마무리. 판정과 같은 결로, 시기와 판정 한 줄을 되풀이하지 않고 상담자의 사정(facts)에 닿는 한마디로 맺습니다.
- 괘사·효사·대상전을 인용하지 않습니다.`),
  tool: tool('write_tail', '시기 창마다 움직일 일·그 달의 운과 마무리를 쓴다', {
    timeline: arr(obj({
      what: str('그 사이 일어날 수 있는 일 갈래와 그때의 마음, 3문장, 해요체'),
      watch: str('그때 볼 것 1문장, 해요체'),
      luck: str('그 달의 운 1문장, 해요체'),
    }), '[시기 창]과 같은 순서·같은 개수', 1, 3),
    timing_title: str('시기 섹션 제목 18자 안팎'),
    closing: str('마무리 2문장, 해요체'),
  }),
  validate: ({ input }, out) => {
    if ((out.timeline || []).length < input.timing.length) return `timeline이 ${(out.timeline || []).length}개뿐 — [시기 창] ${input.timing.length}개마다 하나씩`;
    const other = [...(out.timeline || []).flatMap((t) => [t.what, t.watch, t.luck]), out.closing].join(' ').match(/봄|여름|가을|겨울|연말|연초|내년|다음 달|다음 주|\d{1,2}월/);
    return other ? `timeline·closing에 "${other[0]}" 같은 시기 말이 있음 — 범위는 화면이 보여 주니 시기 말 없이` : '';
  },
  user: ({ input, plan: p }) => lines(
    `이름: ${input.name} / 오늘: ${input.today}\n고민: ${input.question}`,
    block('구성안', json({ verdict: p.verdict, facts: p.facts, season: p.season })),
    block('시기 창', input.timing.map((w, i) => `${i + 1}. ${w.range}\n   근거: ${w.basis.join(' / ')}${w.luck ? `\n   그 달의 운: ${w.luck}` : ''}${w.focus ? `\n   focus: ${w.focus}` : ''}`).join('\n')),
    block('십신 뜻', Object.entries(TEN_MEANING).map(([k, v]) => `${k}: ${v}`).join('\n')),
    `[일간] ${input.saju.dayMaster.gan}${input.saju.dayMaster.el} — ${input.saju.dayMaster.image}`,
    input.src.tui,
    block('중심 자리', input.src.lines),
  ),
};

/* 나눈 이야기 — v1과 같고, 사주 메모를 함께 본다 */
const WRITE_QA = {
  name: 'write_qa',
  noQuote: ['qa'],
  noTiming: true,
  temperature: 0.45,
  timeoutMs: 40000,
  maxTokens: 3400,
  checkStyle: true,
  system: writerSystem('추가 문답에 대한 풀이', 'write_qa', `- qa: [문답]의 질문마다 하나씩, 빠짐없이 순서대로 씁니다. 각 항목은 {q: 질문 그대로, title, body}.
  · title: 그 답에서 연서가 짚은 핵심을 제목으로, 18자 안팎.
  · body 두 문단(문단 사이 줄바꿈), 합쳐 6~8문장: 첫 문단은 상담자가 남긴 답을 그 말 그대로 받아 주고, 그 답 뒤에 있었을 법한 사정과 속마음을 [공감]의 갈래로 짚은 뒤, 이 점에서 무엇을 뜻하는지 분명히 말합니다. 둘째 문단은 다른 쪽에서 비춰 봅니다 — 본괘·중심 효·지괘·사주(기질이나 지금의 운) 가운데 첫 문단에서 쓰지 않은 것을 이름으로 짚어 근거를 대되, "~로 보면", "다른 각도에서" 같은 말머리 없이 바로 말합니다.
  · 다른 질문의 답에서 한 말을 되풀이하지 않습니다. 원문을 따옴표로 인용하지 않습니다. 달 단위 시기 표현과 판정 한 줄은 쓰지 않습니다.
- 문답이 없으면 빈 배열.`),
  tool: tool('write_qa', '질문마다 제목과 두 문단 풀이를 쓴다', {
    qa: arr(obj({
      q: str('질문 그대로'),
      title: str('제목 18자 안팎'),
      body: str('두 문단 6~8문장, 해요체, 문단 사이 줄바꿈'),
    }), '질문별 풀이', 0, 3),
  }),
  user: ({ input, analysis: a, plan: p, saju: sj }) => {
    const answered = input.qa.filter((x) => x && x.a && x.a !== '(답변 없음)');
    return lines(
      `이름: ${input.name}\n고민: ${input.question}`,
      block('구성안', json({ verdict: p.verdict, facts: p.facts, season: p.season })),
      block('문답', answered.map((x, i) => `Q${i + 1}. ${x.q}\nA. ${x.a}`).join('\n\n')),
      input.src.ben.split('\n').slice(0, 4).join('\n'),
      input.src.ji ? input.src.ji.split('\n').slice(0, 4).join('\n') : '',
      block('중심 자리', input.src.lines),
      block('괘 분석 메모', json({ fortune: a.fortune, heart: a.heart, direction: a.direction })),
      sajuBrief(input, sj),
    );
  },
};

const WRITERS = [WRITE_FLOW, WRITE_OPEN, WRITE_YAO, WRITE_PATH, WRITE_CORE, WRITE_TAIL, WRITE_QA];

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
  // 화면 순서대로: 요약 → 사주 흐름 → 답 → 본괘 → 중심 효 → 움직일 방식 → 막는 것 → 닿을 곳 → 시기 → 나눈 이야기 → 마무리
  [r.headline, r.verdict.label].forEach(see);
  r.saju_flow = { portrait: prose(r.saju_flow.portrait), past: prose(r.saju_flow.past), now: prose(r.saju_flow.now), fit: prose(r.saju_flow.fit) };
  r.empathy = trimName(r.empathy || '');
  see(r.empathy);
  r.answer = prose(r.answer);
  r.shape = prose(r.shape);
  r.bubbles.heart = bubble(r.bubbles.heart);
  r.heart = prose(r.heart);
  r.stages = r.stages.map((x) => ({ ...x, reading: prose(x.reading) }));
  r.yao = r.yao.map((y) => ({ ...y, reading: prose(y.reading) }));
  r.acts = r.acts.map((x) => ({ ...x, body: prose(x.body) }));
  r.blocks = r.blocks.map((x) => ({ ...x, body: prose(x.body), sign: trimName(x.sign || '') }));
  r.bubbles.flow = bubble(r.bubbles.flow);
  r.flow = prose(r.flow);
  r.bubbles.timing = bubble(r.bubbles.timing);
  see(r.season);
  r.timeline = r.timeline.map((x) => ({ ...x, what: prose(x.what), watch: trimName(x.watch || ''), luck: trimName(x.luck || '') }));
  r.qa = r.qa.map((x) => ({ ...x, body: prose(x.body) }));
  names = -99; // 마무리는 이름을 부르며 끝낸다
  r.closing = prose(r.closing);
  r.meta = { removedRepeats: removed };
  return r;
}

// 근거 표시는 독자가 원문이나 명식에서 찾을 수 있는 이름만 남긴다("괘 분석", "방향" 같은 내부 말이 나왔다)
const cleanBasis = (x) => ({ ...x, basis: /대상전|괘사|단전|[초이삼사오상]효|지괘|본괘|호체|일간|대운|세운|월운|오행|비견|겁재|식신|상관|편재|정재|편관|정관|편인|정인/.test(x.basis || '') ? x.basis : '' });

// 화면이 그대로 그리는 리포트 객체. version이 바뀌면 v2/index.html의 buildReport·parseReadingResponse도 같이 바꿀 것.
function assemble({ input, analysis: a, plan: p, flow, open, yao, path, core, tail, qa }) {
  const answered = input.qa.filter((x) => x && x.a && x.a !== '(답변 없음)');
  return {
    version: 'v2-1',
    headline: p.verdict.line,
    summary: { fortune: a.fortune, keywords: p.keywords, mood: p.mood },
    verdict: { kind: p.verdict.kind, label: p.verdict.label, reasons: p.verdict.reasons },
    empathy: p.empathy,
    titles: { saju: p.points.saju, shape: p.points.shape, heart: p.points.heart, flow: p.points.flow, dos: p.points.dos, donts: p.points.donts, timing: shortTitle(tail.timing_title) },
    saju: input.saju,
    saju_flow: { portrait: flow.portrait, past: flow.past, now: flow.now, fit: flow.fit },
    answer: open.answer,
    shape: open.shape,
    heart: yao.heart,
    yao: yao.yao || [],
    stages: yao.stages || [],
    acts: path.acts.map(cleanBasis),
    blocks: path.blocks.map(cleanBasis),
    flow: core.flow,
    season: p.season,
    // 범위·근거는 육효 응기 계산값, 그 달의 운은 서버가 붙인 월운, 무엇이 움직이는지는 작가 몫
    timeline: input.timing.length
      ? input.timing.map((w, i) => ({ range: w.range, basis: w.basis, luckGz: w.luckGz || '', what: tail.timeline[i]?.what || '', watch: tail.timeline[i]?.watch || '', luck: tail.timeline[i]?.luck || '' }))
      : (tail.timeline || []).map((t) => ({ range: '', basis: [], luckGz: '', what: t.what, watch: t.watch, luck: t.luck })),
    qa: (qa.qa || []).map((x, i) => ({ ...x, said: answered[i]?.a || '' })),
    closing: tail.closing,
    bubbles: { ...p.bubbles },
  };
}

// 시기 창마다 그 달의 월운(절기 기준 월주)을 붙인다 — 창의 시작일 며칠 뒤로 짚어 절기월 안에 들게 한다
function attachMonthLuck(input) {
  const dg = input.saju.dayMaster.gan;
  input.timing = input.timing.map((w) => {
    const t = w.start ? new Date(new Date(w.start).getTime() + 5 * 86400000) : null;
    if (!t || Number.isNaN(t.getTime())) return w;
    const { month: m, year: y } = monthAt(dg, t);
    return m ? { ...w, luckGz: `${m.gz} (${m.ganTen}·${m.zhiTen})`, luck: `${y.gz}년의 ${m.gz} 달 — 천간 ${m.ganTen}, 지지 ${m.zhiTen}` } : w;
  });
}

export async function runReadingGraph(input, root) {
  const deadline = Date.now() + GRAPH_BUDGET_MS;
  input.timing ||= [];
  attachMonthLuck(input);
  // 괘 분석과 사주 분석은 서로 모르는 채로 병렬
  const [analysis, saju] = await Promise.all([
    runNode(ANALYZE, { input }, root, deadline),
    runNode(ANALYZE_SAJU, { input }, root, deadline),
  ]);
  const plan = nestPlan(await runNode(PLAN, { input, analysis, saju }, root, deadline));
  // 원문 배정은 모델에게 맡기지 않고 입력 블록에서 바로 꺼낸다 — 본괘 대상전 자리에 지괘 대상전이 들어가는 일이 반복됐다
  const pick = (blk, label) => (String(blk || '').match(new RegExp(`^${label}: (.+)$`, 'm')) || [])[1] || '';
  plan.quotes = {
    shape: pick(input.src.ben, '괘사 풀이') || plan.quotes.shape,
    flow: pick(input.src.ji, '괘사 풀이'),
    dos: pick(input.src.ben, '대상전 풀이') || plan.quotes.dos,
  };
  const [flow, open, yao, path, core, tail, qa] = await Promise.all(
    WRITERS.map((node) => runNode(node, { input, analysis, plan, saju }, root, deadline)),
  );
  return dedupeReport(assemble({ input, analysis, plan, flow, open, yao, path, core, tail, qa }), input.name);
}
