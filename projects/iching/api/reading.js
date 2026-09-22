// Vercel Serverless Function: /api/reading
// 주역 본괘 풀이 생성 - Claude Haiku 사용

export default async function handler(req, res) {
  // CORS 헤더
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) return res.status(500).json({ error: 'API key not configured' });

  const { prompt, model = 'claude-haiku-4-5-20251001', max_tokens = 3500 } = req.body;
  if (!prompt) return res.status(400).json({ error: 'prompt is required' });

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 60000);

    const anthropicRes = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({ model, max_tokens, messages: [{ role: 'user', content: prompt }] }),
    });

    clearTimeout(timeout);
    const data = await anthropicRes.json();

    if (!anthropicRes.ok) {
      // 429/529 rate limit은 그대로 전달해서 클라이언트가 재시도하게
      return res.status(anthropicRes.status).json({ error: data?.error?.message || anthropicRes.status });
    }

    return res.status(200).json(data);
  } catch (err) {
    if (err.name === 'AbortError') return res.status(504).json({ error: 'Request timeout' });
    console.error('[/api/reading]', err);
    return res.status(500).json({ error: err.message });
  }
}
