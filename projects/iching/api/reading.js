// Vercel Serverless Function: /api/reading
// 주역 점사 생성 — 노드 그래프(_lib/reading-graph.js)를 돌리고, 노드마다 Langfuse generation을 남긴다.
// 클라이언트는 프롬프트가 아니라 재료(괘 데이터 텍스트·심장 규칙·고민·문답)만 보낸다.
import { propagateAttributes, startObservation } from '@langfuse/tracing';
import { ensureTracing, flushTraces } from '../lib/langfuse.js';
import { runReadingGraph } from './_lib/reading-graph.js';

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });
  if (!process.env.ANTHROPIC_API_KEY) return res.status(500).json({ error: 'API key not configured' });

  const body = req.body || {};
  if (!body.hexagram || !body.heartRule || !body.today) {
    return res.status(400).json({ error: 'hexagram, heartRule, today 가 필요합니다' });
  }
  const input = {
    name: String(body.name || '상담자'),
    today: String(body.today),
    question: String(body.question || '(없음)'),
    qa: (Array.isArray(body.qa) ? body.qa : []).map((x) => ({ q: String(x?.q ?? ''), a: String(x?.a || '(답변 없음)') })),
    hexagram: String(body.hexagram),
    heartRule: String(body.heartRule),
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
        traceName: 'iching-reading',
        tags: ['iching', 'reading-graph', `변효${meta.changed.length}`],
        metadata: { ben: meta.ben, ji: meta.ji || '없음', changed: meta.changed.join(',') || '없음' },
      },
      async () => {
        const root = startObservation('iching-reading', {
          input: { question: input.question, ...meta },
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
    console.error('[/api/reading]', err);
    // 429/529는 그대로 넘겨 클라이언트 재시도 로직이 기다렸다 다시 부르게 한다
    const status = err.status === 429 || err.status === 529 ? err.status : 502;
    return res.status(status).json({ error: err.message });
  }
}
