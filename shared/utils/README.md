# shared/utils

## langfuse_tracing.py — 범용 LLM 트레이싱 (Python)

LLM을 호출하는 어떤 스크립트에서든 Langfuse 트레이싱을 켠다. 키가 없으면 전부 no-op.

```python
sys.path.insert(0, str(ROOT / "shared" / "utils"))
from langfuse_tracing import setup_tracing, observe, propagate_attributes, flush

setup_tracing()   # anthropic 자동 계측 (setup_tracing(openai=True) 로 OpenAI 추가)
```

- 환경변수: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` (루트 `.env` 또는 CI Secrets)
- 의존성: `langfuse>=4,<5` (Python ≥ 3.10), `opentelemetry-instrumentation-anthropic`
- `load_dotenv()` 이후에 호출할 것. 짧게 끝나는 스크립트는 종료 전 `flush()` 필수.
- 규칙: 트레이스 1개 = 작업 1회, 이름은 `동사-목적어` 고정값(동적 값은 metadata), 큰 입력은 `@observe(capture_input=False)`.
- 사용 예: `projects/claude-code-monitor/generate_content.py`

## JS/Node (서버리스에서 raw fetch로 Anthropic 호출하는 경우)

SDK 없이 `fetch`를 쓰는 Vercel 함수용 헬퍼는 배포 루트 밖 import가 안 되므로 프로젝트 안에 둔다:
`projects/iching/lib/langfuse.js` (`traceAnthropicCall`). 다른 Node 프로젝트는 이 파일을 복사해서 쓰면 된다.
필요 패키지: `@langfuse/tracing`, `@langfuse/otel`, `@opentelemetry/sdk-node`.
