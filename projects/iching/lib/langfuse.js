// Langfuse 트레이싱 헬퍼 — Anthropic Messages API를 raw fetch로 호출하는 서버리스 핸들러용.
// LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 가 없으면 전부 no-op (기존 동작 유지).
//
// 사용:
//   const { status, ok, data } = await traceAnthropicCall(
//     { name: 'generate-reading', payload, tags: ['reading'] },
//     async () => { const r = await fetch(...); return { status: r.status, ok: r.ok, data: await r.json() }; },
//   );
//
// 점 질문은 개인정보에 가까우므로, 내용을 남기고 싶지 않으면 LANGFUSE_MASK_IO=1 로 입력/출력을 마스킹한다.
// (모델명/토큰/지연/에러는 그대로 남는다)

import { NodeSDK } from '@opentelemetry/sdk-node';
import { LangfuseSpanProcessor } from '@langfuse/otel';
import { startActiveObservation, propagateAttributes } from '@langfuse/tracing';

const enabled = !!(process.env.LANGFUSE_PUBLIC_KEY && process.env.LANGFUSE_SECRET_KEY);
let processor = null;

function init() {
  if (!enabled || processor) return;
  // dev/prod 트레이스 분리 + 배포 버전 추적 (Vercel 환경변수 활용)
  process.env.LANGFUSE_TRACING_ENVIRONMENT ??= process.env.VERCEL_ENV || 'development';
  if (process.env.VERCEL_GIT_COMMIT_SHA) process.env.LANGFUSE_RELEASE ??= process.env.VERCEL_GIT_COMMIT_SHA;

  // 트레이싱 설정 오류(잘못된 URL 등)가 점사 자체를 막으면 안 된다 — 경고만 남기고 끈다
  try {
    const p = new LangfuseSpanProcessor({
      exportMode: 'immediate', // 서버리스: 응답 후 프로세스가 freeze 되어도 유실되지 않게 즉시 전송
      ...(process.env.LANGFUSE_MASK_IO === '1' ? { mask: () => '[MASKED]' } : {}),
    });
    new NodeSDK({ spanProcessors: [p] }).start();
    processor = p;
  } catch (err) {
    console.warn('[langfuse] 초기화 실패 — 트레이싱 없이 진행:', err.message);
  }
}

// 직접 startObservation으로 계측하는 코드(점사 그래프 등)용 — 같은 NodeSDK/processor를 공유한다
export function ensureTracing() {
  init();
}

export async function flushTraces() {
  try { await processor?.forceFlush(); } catch { /* noop */ }
}

// Anthropic content 블록 → Langfuse가 읽기 좋은 OpenAI 스타일 assistant 메시지 (+ thinking 분리)
function toAssistantOutput(content = []) {
  const text = content.filter(b => b.type === 'text').map(b => b.text).join('\n');
  const thinking = content.filter(b => b.type === 'thinking').map(b => b.thinking).join('\n');
  const toolCalls = content
    .filter(b => b.type === 'tool_use')
    .map(b => ({ id: b.id, type: 'function', function: { name: b.name, arguments: JSON.stringify(b.input ?? {}) } }));
  const message = { role: 'assistant', content: text };
  if (toolCalls.length) message.tool_calls = toolCalls;
  return { message, thinking };
}

function toInputMessages(payload) {
  const msgs = [...(payload.messages || [])];
  if (payload.system) {
    const sys = typeof payload.system === 'string' ? payload.system : JSON.stringify(payload.system);
    msgs.unshift({ role: 'system', content: sys });
  }
  return msgs;
}

function lastUserText(payload) {
  const last = [...(payload.messages || [])].reverse().find(m => m.role === 'user');
  if (!last) return undefined;
  return typeof last.content === 'string' ? last.content : JSON.stringify(last.content);
}

/**
 * Anthropic 호출 1회 = trace 1개 (root span + generation).
 * @param {{name: string, payload: object, tags?: string[], metadata?: Record<string,string>}} opts
 *   name: 동사-목적어 형태의 고정 이름 (동적 값 금지, 값은 metadata로)
 * @param {() => Promise<{status:number, ok:boolean, data:any}>} run  실제 fetch 수행 (결과를 그대로 반환해야 함)
 */
export async function traceAnthropicCall({ name, payload, tags = [], metadata = {} }, run) {
  if (!enabled) return run();
  init();

  try {
    return await propagateAttributes({ tags, metadata }, () =>
      startActiveObservation(name, async (root) => {
        root.update({ input: lastUserText(payload) });

        return startActiveObservation('call-claude', async (gen) => {
          gen.update({
            model: payload.model,
            input: toInputMessages(payload),
            modelParameters: {
              max_tokens: payload.max_tokens,
              ...(typeof payload.temperature === 'number' ? { temperature: payload.temperature } : {}),
            },
          });

          let result;
          try {
            result = await run();
          } catch (err) {
            gen.update({ level: 'ERROR', statusMessage: err.name === 'AbortError' ? 'timeout' : err.message });
            root.update({ level: 'ERROR', statusMessage: err.message });
            throw err;
          }

          if (!result.ok) {
            const msg = result.data?.error?.message || String(result.status);
            gen.update({ level: 'ERROR', statusMessage: msg, metadata: { http_status: String(result.status) } });
            root.update({ level: 'ERROR', statusMessage: msg });
            return result;
          }

          const { data } = result;
          const { message, thinking } = toAssistantOutput(data.content);
          const u = data.usage || {};
          gen.update({
            output: message,
            usageDetails: {
              input: u.input_tokens ?? 0,
              output: u.output_tokens ?? 0,
              ...(u.cache_read_input_tokens ? { cache_read_input_tokens: u.cache_read_input_tokens } : {}),
              ...(u.cache_creation_input_tokens ? { cache_creation_input_tokens: u.cache_creation_input_tokens } : {}),
            },
            metadata: { stop_reason: String(data.stop_reason), ...(thinking ? { thinking } : {}) },
          });
          // max_tokens로 잘린 응답은 눈에 띄게
          if (data.stop_reason === 'max_tokens') gen.update({ level: 'WARNING', statusMessage: 'stopped at max_tokens' });
          root.update({ output: message.content });
          return result;
        }, { asType: 'generation' });
      }),
    );
  } finally {
    // 서버리스는 응답 직후 freeze 되므로 반환 전에 전송 완료. 실패해도 본 응답에는 영향 없게 삼킨다.
    try { await processor?.forceFlush(); } catch { /* noop */ }
  }
}
