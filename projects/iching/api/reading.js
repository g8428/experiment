// Vercel Serverless Function: /api/reading
// 주역 점사 생성 — Anthropic Messages API 프록시.
// 클라이언트가 system / messages / tools / tool_choice / temperature 를 그대로 보내면 전달한다.
// (구버전 호환: prompt만 오면 user 메시지 하나로 감싼다)

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) return res.status(500).json({ error: 'API key not configured' });

  const {
    prompt, messages, system, tools, tool_choice, temperature,
    model = 'claude-haiku-4-5-20251001',
    max_tokens = 8000,
  } = req.body || {};

  const msgs = Array.isArray(messages) && messages.length
    ? messages
    : (prompt ? [{ role: 'user', content: prompt }] : null);
  if (!msgs) return res.status(400).json({ error: 'messages or prompt is required' });

  const payload = { model, max_tokens, messages: msgs };
  if (system)                      payload.system = system;
  if (Array.isArray(tools) && tools.length) payload.tools = tools;
  if (tool_choice)                 payload.tool_choice = tool_choice;
  if (typeof temperature === 'number') payload.temperature = temperature;

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 120000);

    const anthropicRes = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify(payload),
    });

    clearTimeout(timeout);
    const data = await anthropicRes.json();

    if (!anthropicRes.ok) {
      // 429/529 rate limit은 그대로 전달해서 클라이언트가 재시도하게
      return res.status(anthropicRes.status).json({ error: data?.error?.message || anthropicRes.status });
    }

    // stop_reason(max_tokens 여부)과 content(tool_use 블록)를 그대로 넘긴다
    return res.status(200).json(data);
  } catch (err) {
    if (err.name === 'AbortError') return res.status(504).json({ error: 'Request timeout' });
    console.error('[/api/reading]', err);
    return res.status(500).json({ error: err.message });
  }
}
