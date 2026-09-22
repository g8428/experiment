// 로컬 개발 서버 — vercel dev 대체
// 사용: node server.js (포트 3000)
import { createServer } from 'http';
import { readFile } from 'fs/promises';
import { existsSync } from 'fs';
import { join, extname } from 'path';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

// .env 로드
try {
  const envText = await readFile('.env', 'utf8');
  for (const line of envText.split('\n')) {
    const [k, ...v] = line.split('=');
    if (k && k.trim() && !k.startsWith('#')) process.env[k.trim()] = v.join('=').trim();
  }
} catch {}

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = process.env.PORT || 3000;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js':   'application/javascript; charset=utf-8',
  '.css':  'text/css',
  '.json': 'application/json',
  '.png':  'image/png',
  '.svg':  'image/svg+xml',
};

async function handleApi(path, req, res) {
  // 동적으로 핸들러 임포트 (path는 /reading 형태 — api/ 접두사 없음)
  const mod = await import(`./api${path}.js?t=${Date.now()}`);
  const handler = mod.default;
  // req에 body 파싱
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const body = Buffer.concat(chunks).toString();
  try { req.body = JSON.parse(body); } catch { req.body = {}; }
  // 쿠키 파싱
  req.cookies = Object.fromEntries(
    (req.headers.cookie||'').split(';').map(c=>{const[k,...v]=c.trim().split('=');return[k,v.join('=')];}).filter(([k])=>k)
  );
  // 간이 res 래퍼
  let statusCode = 200;
  const headers = { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' };
  res.setHeader = (k, v) => { headers[k] = v; };
  res.status = (code) => { statusCode = code; return res; };
  res.json = (data) => {
    if (!res.headersSent) {
      res.writeHead(statusCode, headers);
      res.end(JSON.stringify(data));
    }
  };
  res.end = res.end.bind(res);
  await handler(req, res);
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const path = url.pathname;

  // CORS preflight
  if (req.method === 'OPTIONS') {
    res.writeHead(204, { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'POST, GET, OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type' });
    res.end();
    return;
  }

  // API 라우팅
  if (path.startsWith('/api/')) {
    const apiPath = path.replace(/^\/api/, '').replace(/\.js$/, '');
    try {
      await handleApi(apiPath, req, res);
    } catch (e) {
      console.error('[API Error]', e.message);
      if (!res.headersSent) {
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: e.message }));
      }
    }
    return;
  }

  // 정적 파일 서빙
  let filePath = path === '/' ? '/index.html' : path;
  const absPath = join(__dirname, filePath);

  if (!existsSync(absPath) || !absPath.startsWith(__dirname)) {
    // SPA fallback
    const indexPath = join(__dirname, 'index.html');
    try {
      const content = await readFile(indexPath);
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(content);
    } catch {
      res.writeHead(404);
      res.end('Not found');
    }
    return;
  }

  try {
    const content = await readFile(absPath);
    const ext = extname(absPath);
    res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
    res.end(content);
  } catch {
    res.writeHead(404);
    res.end('Not found');
  }
});

server.listen(PORT, () => {
  console.log(`\n✦ 주역 로컬 서버 실행 중: http://localhost:${PORT}\n`);
});
