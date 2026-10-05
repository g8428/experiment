"""
범용 Langfuse 트레이싱 헬퍼 (Python).

LLM을 호출하는 어떤 스크립트에서든 맨 위에서 setup_tracing()만 호출하면 된다.
LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 가 없으면 전부 no-op이라 기존 동작을 깨지 않는다.

사용 예:
    import sys; sys.path.insert(0, str(ROOT / "shared" / "utils"))
    from langfuse_tracing import setup_tracing, observe, propagate_attributes, flush

    setup_tracing()                      # anthropic 호출 자동 계측 (openai=True 로 OpenAI도 가능)

    @observe(name="summarize-doc", capture_input=False)   # 이름은 '동사-목적어', 동적 값 금지
    def summarize(doc): ...

    with propagate_attributes(tags=["feature-x"], metadata={"run": "weekly"}):
        summarize(doc)
    flush()                              # 짧게 끝나는 스크립트는 종료 전 반드시 호출

의존성(선택): langfuse>=4 (Python>=3.10), opentelemetry-instrumentation-anthropic
주의: load_dotenv() 이후에 setup_tracing()을 호출할 것 (키를 import 시점에 읽는다).
"""

import os
from contextlib import nullcontext

TRACING_ENABLED = bool(os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"))

if TRACING_ENABLED:
    from langfuse import get_client, observe, propagate_attributes
else:
    def observe(*args, **kwargs):
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]
        return lambda fn: fn

    def propagate_attributes(**kwargs):
        return nullcontext()

    def get_client():
        return None


def setup_tracing(anthropic: bool = True, openai: bool = False, default_environment: str = "development") -> bool:
    """트레이싱 초기화. 활성화되면 True. 키가 없으면 아무것도 하지 않고 False."""
    if not TRACING_ENABLED:
        return False

    # dev/prod 트레이스가 섞이지 않게 environment 지정 (CI에서는 LANGFUSE_TRACING_ENVIRONMENT=production)
    os.environ.setdefault("LANGFUSE_TRACING_ENVIRONMENT", default_environment)
    get_client()  # 클라이언트(OTel provider) 먼저 초기화

    if anthropic:
        from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor

        AnthropicInstrumentor().instrument()
    if openai:
        from opentelemetry.instrumentation.openai import OpenAIInstrumentor

        OpenAIInstrumentor().instrument()
    return True


def flush() -> None:
    """짧게 끝나는 프로세스 종료 전 버퍼 전송."""
    client = get_client()
    if client is not None:
        client.flush()
