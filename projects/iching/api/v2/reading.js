// Vercel Serverless Function: /api/v2/reading — 주역사주 v2 풀이.
// v1(/api/reading)과 같은 괘 재료에 생년월일시(birth)를 더해 받는다. 사주 명식은 클라이언트 값이 아니라 여기서 다시 계산한다.
import { propagateAttributes, startObservation } from '@langfuse/tracing';
import { ensureTracing, flushTraces } from '../../lib/langfuse.js';
import { runReadingGraph } from '../_lib/v2/graph.js';
import { computeSaju } from '../_lib/v2/saju.js';
import { readBirth } from './saju.js';

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });
  if (!process.env.ANTHROPIC_API_KEY) return res.status(500).json({ error: 'API key not configured' });

  const body = req.body || {};
  if (!body.hexagram || !body.heartRule || !body.today || !body.birth) {
    return res.status(400).json({ error: 'hexagram, heartRule, today, birth 가 필요합니다' });
  }
  let saju;
  try { saju = computeSaju(readBirth(body.birth)); } catch (err) { return res.status(400).json({ error: err.message }); }

  const input = {
    name: String(body.name || '상담자'),
    today: String(body.today),
    question: String(body.question || '(없음)'),
    qa: (Array.isArray(body.qa) ? body.qa : []).map((x) => ({ q: String(x?.q ?? ''), a: String(x?.a || '(답변 없음)') })),
    hexagram: String(body.hexagram),
    heartRule: String(body.heartRule),
    src: Object.fromEntries(
      ['ben', 'ji', 'lines', 'focus', 'hoche', 'tui', 'eunggi'].map((k) => [k, String(body.src?.[k] ?? '')]),
    ),
    timing: (Array.isArray(body.timing) ? body.timing : []).slice(0, 3).map((w) => ({
      range: String(w?.range ?? ''),
      basis: (Array.isArray(w?.basis) ? w.basis : []).slice(0, 4).map(String),
      focus: String(w?.focus ?? ''),
      start: String(w?.start ?? ''),
    })).filter((w) => w.range),
    saju,
  };
  const meta = {
    ben: String(body.meta?.ben ?? ''),
    ji: String(body.meta?.ji ?? ''),
    changed: Array.isArray(body.meta?.changed) ? body.meta.changed.map(String) : [],
  };

  ensureTracing();
  try {
    const result = await propagateAttributes(
      {
        traceName: 'iching-saju-reading',
        tags: ['iching', 'v2', 'saju', `변효${meta.changed.length}`],
        metadata: { ben: meta.ben, ji: meta.ji || '없음', changed: meta.changed.join(',') || '없음', dayMaster: saju.dayMaster.gan + saju.dayMaster.el },
      },
      async () => {
        const root = startObservation('iching-saju-reading', {
          input: { question: input.question, ...meta, dayMaster: saju.dayMaster.gan },
        }, { asType: 'agent' });
        try {
          const reading = await runReadingGraph(input, root);
          root.update({ output: reading }).end();
          return { reading, traceId: root.traceId };
        } catch (err) {
          root.update({ level: 'ERROR', statusMessage: err.message }).end();
          throw err;
        }
      },
    );
    await flushTraces();
    return res.status(200).json(result);
  } catch (err) {
    await flushTraces();
    console.error('[/api/v2/reading]', err);
    const status = err.status === 429 || err.status === 529 ? err.status : 502;
    return res.status(status).json({ error: err.message });
  }
}
