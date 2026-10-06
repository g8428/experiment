// 주역 점사 그래프. 분석·연결 노드는 메모(JSON)를 내고, 쓰기 노드는 그 메모 + 자기 섹션에 필요한 괘 원문 조각을 받는다.
//
//   analyze_hexagram ─▶ map_situation ─┬▶ write_frame  총평 · 괘의 형세(본괘) · 마무리 · headline
//   (괘 데이터만)        (+ 고민 · 문답)  ├▶ write_core   대상전(본괘·지괘) · 이 점괘의 심장(변효/불변효)
//                                       └▶ write_path   방향(지괘) · 시기
//                                                ▼
//                                     assemble (코드) → 7섹션
//
// 2026-10-06 품질 회귀에서 배운 것: 쓰기 노드에 분석 메모만 넘기면 괘 이름·효 위치·자연 상징이 풀이에서 사라지고
// "에너지", "전환기" 같은 일반론과 창업 코칭만 남는다(같은 괘 비교에서 괘 이름 언급 4.3회 → 0회).
// → 쓰기 노드는 원문 조각(input.src)을 직접 받고, 원문이 풀이의 주인·상담자 상황은 비추는 자리로 명시한다.

const MODEL = 'claude-haiku-4-5-20251001';
const MAX_ATTEMPTS = 3;
// Vercel maxDuration 60초 안에 끝내야 한다. 가끔 한 호출만 30초 넘게 멈추는 일이 있어서(2026-10-05 트레이스),
// 노드별 시도 시간을 끊고 다시 부르는 쪽이 빠르다. 전체 마감은 GRAPH_BUDGET_MS.
const GRAPH_BUDGET_MS = 55000;

// 클라이언트 READING_TAGS와 같은 문자열이어야 렌더러가 섹션을 찾는다
const READING_TAGS = ['총평', '괘의 형세', '대상전 — 지금 할 것', '이 점괘의 심장', '방향', '시기', '마무리'];

class NodeError extends Error {
  constructor(message, { status = 502, retryable = true } = {}) {
    super(message);
    this.status = status;
    this.retryable = retryable;
  }
}

const str = (description) => ({ type: 'string', description });
const obj = (properties) => ({ type: 'object', properties, required: Object.keys(properties) });
const tool = (name, description, properties) => ({ name, description, input_schema: obj(properties) });
const json = (o) => JSON.stringify(o);
const block = (title, text) => (text && text.trim() ? `[${title}]\n${text.trim()}` : '');
const lines = (...parts) => parts.filter(Boolean).join('\n\n');

/* ── 공통 문체·해석 규칙: 쓰기 노드(write_*)에만 붙는다 ── */
const STYLE = `[읽는 법 — 가장 중요]
- 괘 원문이 풀이의 주인입니다. 괘 이름과 효 위치를 직접 짚으며 읽습니다("수화기제는 …", "오효는 …", "지괘 택수곤은 …").
- 상괘·하괘의 자연 상징(물·불·산·못·바람·우레·하늘·땅)으로 장면을 그리듯 풀어, 그 그림이 상담자의 지금과 어떻게 겹치는지 보여 줍니다.
- 상담자의 고민은 원문을 비추는 자리입니다. "몇 명을 만나 보라", "체크리스트" 같은 현대식 실행 조언으로 흐르지 않습니다.
- "에너지", "기운이 감싼다", "전환기의 흐름" 같은 막연한 말로 원문을 대신하지 않습니다.

[문체]
- 모든 문장을 존댓말(-습니다/-ㅂ니다/-입니다/-지요/-까요)로 끝냅니다. 반말 종결은 한 문장도 없습니다.
- 담담하고 힘 있는 전통 점술가의 말투. 상담자는 "이름+님"으로만 부르고 "당신"이라고 쓰지 않습니다.
- "~하세요/~해야 합니다" 같은 지시 대신 방향을 보여 주고 선택은 본인 몫으로 둡니다.
- 한자는 괘사·대상전 원문을 인용할 때만 쓰고 바로 풀이를 잇습니다. 효사는 주어진 국문 문구를 따옴표로 그대로 인용하고, 없는 한자 원문을 만들지 않습니다.
- 육효 계산값(壬午 같은 간지)은 나열하지 않고 의미로 녹입니다.
- 금지: 항목 나열, 원론 설명("~라는 것은 ~라는 뜻입니다"), "중심을 지켜라"식 결론, 날짜·서명.
- 분량은 유료 리포트 수준으로 충분히. 섹션마다 정해진 문장 수를 채웁니다.`;

const writerSystem = (parts, toolName, rules) =>
  `당신은 수십 년 경력의 주역 점술가입니다. 점사 가운데 ${parts}을 ${toolName} 도구로 씁니다.

[이 부분의 규칙]
${rules}

${STYLE}`;

/* ── 노드 1: 괘 분석 — 상담자의 고민을 모르는 채로 괘 데이터만 읽는다 ── */
const ANALYZE = {
  name: 'analyze_hexagram',
  temperature: 0.2,
  timeoutMs: 25000,
  maxTokens: 1800,
  system: `당신은 주역·다산역·육효점 해석가입니다. 상담자의 고민을 모르는 채로 괘 데이터만 읽고, 뒤 단계 작가들이 쓸 해석 재료를 record_hexagram 도구로 메모합니다.
- 메모입니다. 꾸미지 않되 판단의 근거(어느 괘·어느 효·어느 상징)를 이름으로 남깁니다. 각 필드 1~2문장.
- 데이터에 없으면 빈 문자열이나 빈 배열로 둡니다.
- 변효 개수별 [해석 원칙]을 따르고, 어떤 효를 읽을지는 [심장 규칙]이 정합니다.
- 효사는 데이터의 문구 그대로 옮깁니다. 한자 원문이 데이터에 없으면 만들지 않습니다(심장 규칙의 "한자 원문" 표현보다 우선).
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
    windows: {
      type: 'array',
      maxItems: 3,
      description: '응기에서 고른 시기 창. 근거 없으면 빈 배열',
      items: obj({
        when: str('실제 날짜·달. 예: "10월 17일 무렵", "2027년 4월"'),
        why: str('근거. 예: "세효 값", "용신 합"'),
        what: str('그때 움직이는 일'),
      }),
    },
  }),
  user: ({ input }) => lines(`오늘: ${input.today}`, input.hexagram, block('심장 규칙', input.heartRule)),
};

/* ── 노드 2: 상황 연결 — 괘 메모(노드 1 출력)와 상담자의 고민·문답을 잇는다 ── */
const MAP = {
  name: 'map_situation',
  temperature: 0.3,
  timeoutMs: 15000,
  maxTokens: 1000,
  system: `당신은 주역 상담가입니다. 괘 메모(JSON)와 상담자의 고민·문답을 받아, 괘가 상담자의 삶에서 무엇에 해당하는지 map_situation 도구로 메모합니다.
- 각 필드는 짧은 한 문장. 문답에 실제로 나온 사실만 근거로 씁니다.
- 괘 메모의 길흉 기조를 바꾸지 않습니다. 실행 조언이 아니라 "괘의 무엇이 삶의 무엇에 해당하는가"만 적습니다.`,
  tool: tool('map_situation', '괘 메모를 상담자 상황에 연결한다', {
    situation: str('상담자 상황 요약'),
    tension: str('상담자를 붙잡고 있는 핵심 갈등'),
    need: str('상담자가 이 점사에서 들어야 할 것'),
    answer: str('고민에 대한 괘의 답 (길흉 포함)'),
    link_image: str('본괘의 그림(물상)이 상담자 상황의 무엇인지'),
    link_heart: str('중심 효의 메시지가 상담자에게 뜻하는 바'),
    link_action: str('대상전의 태도가 상담자 삶에서 무엇에 해당하는지'),
    link_path: str('지괘의 방향·시기가 상담자의 선택지·일정 어디에 걸리는지'),
  }),
  user: ({ input, analysis: a }) => lines(
    block('괘 메모', json({ fortune: a.fortune, why: a.why, image: a.image, phase: a.phase, flow: a.flow, heart: a.heart, direction: a.direction, season: a.season, windows: a.windows })),
    `[상담자] ${input.name}\n고민: ${input.question}\n${input.qa.map((x, i) => `Q${i + 1}. ${x.q}\nA. ${x.a}`).join('\n') || '(추가 문답 없음)'}`,
  ),
};

/* ── 노드 3: 쓰기 노드들 — map_situation 뒤에 병렬로 돈다. 각자 자기 섹션의 원문 조각을 받는다 ── */
const WRITE_FRAME = {
  name: 'write_frame',
  temperature: 0.35,
  timeoutMs: 25000,
  maxTokens: 2200,
  system: writerSystem('「총평」「괘의 형세」「마무리」', 'write_frame', `- title: 이 점괘 전체를 관통하는 한 문장.
- overview(총평) 4~5문장: 본괘에서 (중심 효를 거쳐) 지괘로 가는 큰 흐름을 괘 이름으로 짚고, 길흉 방향과 고민에 대한 괘의 답을 밝힙니다.
- shape(괘의 형세) 5~8문장: 본괘 원문을 바탕으로 씁니다. 상괘·하괘의 자연 상징이 겹친 장면을 그림처럼 먼저 그리고(예: "물이 불 위에 놓인 형상입니다…"), 그 그림이 상담자의 지금과 어떻게 겹치는지 잇습니다. 이어 추이(자라는 국면인지 거두는 국면인지)와 호체("겉은 ~이지만 안에 ~가 숨어 있습니다")를 항목 나열 없이 한 서사로 녹입니다. 괘사 원문을 한 번 인용해도 좋습니다.
  · 호체는 [호체] 블록의 내호·외호 괘와 그 상징으로만 말합니다. 지괘와 섞지 않습니다(지괘는 "흘러가는 곳", 호체는 "본괘 안에 숨은 구조").
  · 계절·절기 이름은 [추이] 블록에 적힌 것만 씁니다.
- closing(마무리) 2~3문장: 응축한 응원과 위로.
- headline: 점사 전체를 한 줄로. closing_line: 마지막 여운 한 문장.`),
  tool: tool('write_frame', '총평·괘의 형세·마무리를 쓴다', {
    title: str('총평 소제목 한 문장'),
    overview: str('총평 4~5문장'),
    shape: str('괘의 형세 5~8문장'),
    closing: str('마무리 2~3문장'),
    headline: str('점사 전체 한 줄'),
    closing_line: str('마지막 여운 한 문장'),
  }),
  user: ({ input, analysis: a, situation: s }) => lines(
    `이름: ${input.name}`,
    input.src.ben,
    input.src.ji ? input.src.ji.split('\n').slice(0, 4).join('\n') : '',
    input.src.lines,
    input.src.hoche,
    input.src.tui,
    block('괘 분석 메모', json({ fortune: a.fortune, why: a.why, image: a.image, phase: a.phase, hidden: a.hidden, flow: a.flow })),
    block('상담자', json({ situation: s.situation, tension: s.tension, answer: s.answer, link_image: s.link_image })),
  ),
};

const WRITE_CORE = {
  name: 'write_core',
  temperature: 0.35,
  timeoutMs: 25000,
  maxTokens: 2200,
  system: writerSystem('「대상전 — 지금 할 것」과 「이 점괘의 심장」', 'write_core', `- action(대상전 — 지금 할 것) 4~6문장: 본괘 대상전 원문을 인용하고 풀이한 뒤, 그 태도가 상담자의 지금에서 무엇인지 비춥니다. 지괘가 있으면 지괘 대상전을 "흘러가며 갖출 태도"로 이어 씁니다. 추상적 덕목 나열이나 실행 체크리스트는 쓰지 않습니다.
- heart(이 점괘의 심장) 5~8문장: 점사의 중심입니다. 첫머리에 길흉 기조를 분명히 합니다("전반적으로 길한 흐름입니다" / "조심이 필요한 국면입니다").
  [중심 자리]에 효가 있으면 그 효를 위치로 짚고("오효는 …"), 효사 문구를 따옴표로 그대로 인용한 뒤, 그 자리의 의미(군위·중심, 완성·마무리 등)가 상담자의 갈등에 무엇을 말하는지 풉니다. 효가 여럿이면 [해석 원칙]의 순서대로 잇습니다.
  [중심 자리]가 비어 있으면(변효 없음·여섯 효 모두 변함) [해석 원칙]대로 괘사나 여섯 자리 흐름으로 읽습니다.
  육효 메모는 서사에 녹입니다. [해석 원칙]과 [심장 규칙]이 이 섹션의 다른 지침보다 우선합니다.`),
  tool: tool('write_core', '대상전과 심장을 쓴다', {
    action: str('대상전 — 지금 할 것 4~6문장'),
    heart: str('이 점괘의 심장 5~8문장'),
  }),
  user: ({ input, analysis: a, situation: s }) => lines(
    `이름: ${input.name}`,
    input.src.ben,
    input.src.ji,
    block('중심 자리', input.src.lines),
    block('해석 원칙', input.src.focus),
    block('심장 규칙', input.heartRule),
    block('괘 분석 메모', json({ fortune: a.fortune, why: a.why, heart: a.heart, liuyao: a.liuyao })),
    block('상담자', json({ situation: s.situation, tension: s.tension, need: s.need, link_heart: s.link_heart, link_action: s.link_action })),
  ),
};

const WRITE_PATH = {
  name: 'write_path',
  temperature: 0.35,
  timeoutMs: 25000,
  maxTokens: 2000,
  system: writerSystem('「방향」과 「시기」', 'write_path', `- direction(방향) 4~6문장: 지괘(없으면 본괘)를 이름으로 짚고, 그 괘의 상괘·하괘 상징과 괘사로 지금 흐름이 어디로 향하는지 그림처럼 보여 줍니다(예: "택수곤은 못에 물이 빠진 형상입니다…"). 그 방향에서 갖출 태도로 맺습니다. "1단계, 2단계" 같은 액션플랜은 쓰지 않습니다.
- timing(시기) 4~6문장: [추이 — 계절 국면]으로 지금이 자라는 국면인지 거두는 국면인지, 가까운 일인지 먼 일인지를 먼저 말합니다. 이어서 시기 메모의 windows에 있는 날짜·달만 그대로 써서("~월 초순은 ~, ~일 무렵은 ~") 그때 무엇이 움직이는지 풉니다. windows에 없는 달, "몇 달 뒤" 같은 어림 숫자, 오늘 이전 날짜는 쓰지 않습니다. windows가 비면 국면만 말합니다.`),
  tool: tool('write_path', '방향과 시기를 쓴다', {
    direction: str('방향 4~6문장'),
    timing: str('시기 4~6문장'),
  }),
  user: ({ input, analysis: a, situation: s }) => lines(
    `이름: ${input.name} / 오늘: ${input.today}`,
    input.src.ji || input.src.ben,
    input.src.tui,
    block('시기 메모', json({ direction: a.direction, season: a.season, windows: a.windows })),
    block('상담자', json({ situation: s.situation, link_path: s.link_path })),
  ),
};

const WRITERS = [WRITE_FRAME, WRITE_CORE, WRITE_PATH];

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
async function runNode(node, state, parent, deadline) {
  const user = node.user(state);
  let maxTokens = node.maxTokens;
  let lastErr;
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
      const out = data.content?.find((b) => b.type === 'tool_use')?.input;
      const missing = node.tool.input_schema.required.filter((k) => out?.[k] == null);
      if (missing.length) throw new NodeError(`필드 누락: ${missing.join(', ')}`);
      gen.update({ output: out }).end();
      return out;
    } catch (err) {
      lastErr = err;
      gen.update({ level: 'ERROR', statusMessage: err.message }).end();
      if (!err.retryable) break;
      if (attempt < MAX_ATTEMPTS) await sleep(1500 * attempt);
    }
  }
  throw lastErr;
}

function assemble({ frame, core, path }) {
  const readings = [frame.overview, frame.shape, core.action, core.heart, path.direction, path.timing, frame.closing];
  return {
    headline: frame.headline,
    closing_line: frame.closing_line,
    sections: READING_TAGS.map((tag, i) => ({ tag, title: i === 0 ? frame.title : '', reading: readings[i] })),
  };
}

export async function runReadingGraph(input, root) {
  const deadline = Date.now() + GRAPH_BUDGET_MS;
  const analysis = await runNode(ANALYZE, { input }, root, deadline);
  const situation = await runNode(MAP, { input, analysis }, root, deadline);
  const [frame, core, path] = await Promise.all(
    WRITERS.map((node) => runNode(node, { input, analysis, situation }, root, deadline)),
  );
  return assemble({ frame, core, path });
}
