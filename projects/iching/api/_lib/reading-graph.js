// 주역 점사 그래프. 각 노드는 앞 노드가 낸 JSON 가운데 자기에게 필요한 필드만 받아 자기 JSON을 낸다.
// 원본 괘 데이터 전체를 들고 가는 건 analyze_hexagram 하나뿐이다.
//
//   analyze_hexagram ─▶ map_situation ─┬▶ write_frame  총평 · 괘의 형세 · 마무리 · headline
//   (괘 데이터만)        (+ 고민 · 문답)  ├▶ write_core   대상전 — 지금 할 것 · 이 점괘의 심장
//                                       └▶ write_path   방향 · 시기
//                                                ▼
//                                     assemble (코드) → 7섹션
//
// 비용·시간 메모(2026-10-06 측정): 노드마다 붙는 고정 규칙·도구 안내가 입력 토큰의 절반을 차지했고,
// 시간은 앞 두 노드(순차)의 출력 길이가 좌우했다. → 쓰기 노드 5→3개, 공통 규칙 압축, 분석·연결 메모는 필드당 한 문장, JSON은 들여쓰기 없이.

const MODEL = 'claude-haiku-4-5-20251001';
const MAX_ATTEMPTS = 3;
// Vercel maxDuration 60초 안에 끝내야 한다. 가끔 한 호출만 30초 넘게 멈추는 일이 있어서(2026-10-05 트레이스),
// 노드별 시도 시간을 짧게 끊고 다시 부르는 쪽이 빠르다. 전체 마감은 GRAPH_BUDGET_MS.
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

/* ── 공통 문체 규칙: 글을 쓰는 노드(write_*)에만 붙는다. 노드마다 반복되므로 짧게 유지할 것 ── */
const STYLE = `[문체]
- 모든 문장을 존댓말(-습니다/-ㅂ니다/-입니다/-지요/-까요)로 끝냅니다. 반말 종결은 한 문장도 없습니다.
- 짧고 힘있는 문단, 담담한 전통 점술가의 말투. 상담자는 "이름+님"으로 한 번 이상 부릅니다.
- "~하세요/~해야 합니다" 같은 지시 대신 방향을 보여주고 선택은 본인 몫으로 둡니다.
- 금지: 항목 나열, 원론 설명, "중심을 지켜라"식 결론, 날짜·서명, 한자 표기, 육효 계산값(의미로 풀어 씀).
- 입력 JSON에 없는 괘 정보나 상담자 사정은 지어내지 않습니다.`;

const writerSystem = (parts, toolName, rules) =>
  `당신은 노련한 주역 점술가입니다. 점사 가운데 ${parts}을 ${toolName} 도구로 씁니다.

${rules}

${STYLE}`;

/* ── 노드 1: 괘 분석 — 상담자의 고민을 모르는 채로 괘 데이터만 읽는다 ── */
const ANALYZE = {
  name: 'analyze_hexagram',
  temperature: 0.2,
  timeoutMs: 25000,
  maxTokens: 1500,
  system: `당신은 주역·다산역·육효점 해석가입니다. 상담자의 고민을 모르는 채로 괘 데이터만 읽고, 뒤 단계 작가들이 쓸 재료를 record_hexagram 도구로 메모합니다.
- 메모입니다. 각 필드는 짧은 한 문장(40자 안팎). 꾸미지 않습니다. 데이터에 없으면 빈 문자열이나 빈 배열.
- 변효 개수별 [해석 원칙]을 따르고, 어떤 효사를 읽을지는 [심장 규칙]이 정합니다.
- 효사는 데이터에 있는 문구 그대로 옮깁니다. 한자 원문이 데이터에 없으면 만들지 않습니다(심장 규칙의 "한자 원문" 표현보다 우선).
- 시기는 [추이 — 계절 국면]과 [시기 판단 근거 — 육효 응기]에서만 고릅니다. 세효·용신·동효의 응기 후보만, 가까운 일은 날짜, 먼 일은 달로. 블록에 없는 달·어림 숫자 금지.`,
  tool: tool('record_hexagram', '괘 데이터만으로 해석 재료를 메모한다', {
    fortune: { type: 'string', enum: ['길', '소길', '평', '조심', '흉'], description: '전체 길흉 기조' },
    why: str('길흉 근거 한 문장'),
    image: str('물상 — 상괘·하괘의 자연 상징이 그리는 장면 한 문장'),
    phase: str('추이 — 자라는 국면인지 거두는 국면인지 한 문장'),
    hidden: str('호체 — "겉은 ~, 안은 ~" 한 문장. 데이터 없으면 빈 문자열'),
    quote: str('심장 규칙에 따라 인용할 효사 문구(데이터 그대로). 인용하지 않으면 빈 문자열'),
    heart: str('이 점괘의 핵심 메시지 한 문장 (읽는 자리의 의미 포함)'),
    act_now: str('본괘 대상전이 요구하는 실천 한 문장'),
    act_later: str('지괘 대상전이 요구하는 태도 한 문장. 지괘 없으면 빈 문자열'),
    direction: str('지괘(없으면 본괘)가 가리키는 방향 한 문장'),
    liuyao: str('세효·응효·공망 등의 의미 한 문장. 계산값 나열 금지'),
    season: str('시기 국면 + 가까운 일인지 먼 일인지 한 문장'),
    windows: {
      type: 'array',
      maxItems: 3,
      description: '응기에서 고른 시기 창. 근거 없으면 빈 배열',
      items: obj({
        when: str('실제 날짜·달. 예: "10월 17일 무렵", "2027년 4월"'),
        why: str('근거 몇 글자. 예: "세효 값", "용신 합"'),
        what: str('그때 움직이는 일 짧게'),
      }),
    },
  }),
  user: ({ input }) => `오늘: ${input.today}

${input.hexagram}

[심장 규칙]
${input.heartRule}`,
};

/* ── 노드 2: 상황 연결 — 괘 메모(노드 1 출력)와 상담자의 고민·문답을 잇는다 ── */
const MAP = {
  name: 'map_situation',
  temperature: 0.3,
  timeoutMs: 15000,
  maxTokens: 1000,
  system: `당신은 주역 상담가입니다. 괘 메모(JSON)와 상담자의 고민·문답을 받아, 괘가 상담자의 삶에서 무엇에 해당하는지 map_situation 도구로 메모합니다.
- 각 필드는 짧은 한 문장(40자 안팎). 문답에 실제로 나온 사실만 근거로 씁니다.
- 괘 메모의 길흉 기조를 바꾸지 않습니다.`,
  tool: tool('map_situation', '괘 메모를 상담자 상황에 연결한다', {
    situation: str('상담자 상황 요약'),
    tension: str('상담자를 붙잡고 있는 핵심 갈등'),
    need: str('상담자가 이 점사에서 들어야 할 것'),
    answer: str('고민에 대한 괘의 답 (길흉 포함)'),
    link_image: str('물상이 상담자 상황의 무엇인지'),
    link_heart: str('핵심 메시지가 상담자에게 뜻하는 바'),
    link_action: str('대상전 실천이 상담자 일상에서 구체적으로 무엇인지'),
    link_path: str('방향·시기가 상담자의 선택지·일정 어디에 걸리는지'),
    avoid: str('이 상담자에게 하면 안 되는 뻔한 말'),
  }),
  user: ({ input, analysis: a }) => `[괘 메모]
${json({ fortune: a.fortune, why: a.why, image: a.image, phase: a.phase, heart: a.heart, act_now: a.act_now, act_later: a.act_later, direction: a.direction, season: a.season, windows: a.windows })}

[상담자] ${input.name}
고민: ${input.question}
${input.qa.map((x, i) => `Q${i + 1}. ${x.q}\nA. ${x.a}`).join('\n') || '(추가 문답 없음)'}`,
};

/* ── 노드 3: 쓰기 노드들 — map_situation 뒤에 병렬로 돈다 ── */
const WRITE_FRAME = {
  name: 'write_frame',
  temperature: 0.35,
  timeoutMs: 18000,
  maxTokens: 1500,
  system: writerSystem('「총평」「괘의 형세」「마무리」', 'write_frame', `- title: 점괘 전체를 관통하는 한 문장.
- overview(총평) 3~4문장: 고민에 대한 괘의 답(answer)과 길흉 방향으로 엽니다.
- shape(괘의 형세) 4~5문장: 물상·추이·호체를 나열 없이 한 서사로. 호체가 있으면 "겉은 ~이지만 안에 ~" 구조. 물상이 상담자 상황의 무엇인지 녹입니다.
- closing(마무리) 1~2문장: 응축한 응원과 위로.
- headline: 점사 전체를 한 줄로. closing_line: 마지막 여운 한 문장.`),
  tool: tool('write_frame', '총평·괘의 형세·마무리를 쓴다', {
    title: str('총평 소제목 한 문장'),
    overview: str('총평 3~4문장'),
    shape: str('괘의 형세 4~5문장'),
    closing: str('마무리 1~2문장'),
    headline: str('점사 전체 한 줄'),
    closing_line: str('마지막 여운 한 문장'),
  }),
  user: ({ input, analysis: a, situation: s }) => `이름: ${input.name}
[괘] ${json({ fortune: a.fortune, why: a.why, image: a.image, phase: a.phase, hidden: a.hidden, heart: a.heart })}
[상담자] ${json({ situation: s.situation, tension: s.tension, answer: s.answer, need: s.need, link_image: s.link_image })}`,
};

const WRITE_CORE = {
  name: 'write_core',
  temperature: 0.35,
  timeoutMs: 18000,
  maxTokens: 1500,
  system: writerSystem('「대상전 — 지금 할 것」과 「이 점괘의 심장」', 'write_core', `- action(대상전 — 지금 할 것) 4~5문장: 대상전의 실천을 상담자 일상에 구체적으로. act_later가 있으면 지금 당장(act_now) → 흘러가며 갖출 태도(act_later) 순서. 추상적 덕목 나열 금지.
- heart(이 점괘의 심장) 4~6문장: 점사의 중심. 첫머리에 길흉 기조를 분명히 하고 상담자의 갈등(tension)에 정면으로 답합니다. quote가 있으면 그 문구를 따옴표로 그대로 인용하고 풀이를 잇습니다(한자를 붙이지 않음). liuyao는 서사에 녹입니다. [심장 규칙]이 이 섹션의 다른 지침보다 우선합니다.`),
  tool: tool('write_core', '대상전과 심장을 쓴다', {
    action: str('대상전 — 지금 할 것 4~5문장'),
    heart: str('이 점괘의 심장 4~6문장'),
  }),
  user: ({ input, analysis: a, situation: s }) => `이름: ${input.name}
[괘] ${json({ fortune: a.fortune, quote: a.quote, heart: a.heart, liuyao: a.liuyao, act_now: a.act_now, act_later: a.act_later })}
[상담자] ${json({ situation: s.situation, tension: s.tension, need: s.need, link_heart: s.link_heart, link_action: s.link_action, avoid: s.avoid })}
[심장 규칙] ${input.heartRule}`,
};

const WRITE_PATH = {
  name: 'write_path',
  temperature: 0.35,
  timeoutMs: 18000,
  maxTokens: 1200,
  system: writerSystem('「방향」과 「시기」', 'write_path', `- direction(방향) 3~5문장: 지괘(없으면 본괘)가 가리키는 방향·태도·기운. "1단계, 2단계" 같은 액션플랜 금지.
- timing(시기) 3~5문장: season으로 지금 국면과 원근을 먼저 말하고, windows의 날짜·달만 그대로 써서 그때 무엇이 움직이는지 풉니다. windows에 없는 달, "몇 달 뒤" 같은 어림 숫자, 오늘 이전 날짜 금지. windows가 비면 국면만.`),
  tool: tool('write_path', '방향과 시기를 쓴다', {
    direction: str('방향 3~5문장'),
    timing: str('시기 3~5문장'),
  }),
  user: ({ input, analysis: a, situation: s }) => `이름: ${input.name} / 오늘: ${input.today}
[괘] ${json({ direction: a.direction, season: a.season, windows: a.windows })}
[상담자] ${json({ situation: s.situation, link_path: s.link_path })}`,
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
