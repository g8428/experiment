import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("anthropic")
gc = pytest.importorskip("generate_content")

SAMPLE = (Path(__file__).parent.parent / "cards" / "sample.json").read_text(encoding="utf-8")


class FakeClient:
    def __init__(self, replies):
        self.replies, self.n = replies, 0
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **kw):
        r = self.replies[self.n]
        self.n += 1
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=r)])


def test_parse_json_with_fence():
    assert gc.parse_json_text('```json\n{"a": 1}\n```') == {"a": 1}
    assert gc.parse_json_text('앞말 {"a": 1} 뒷말') == {"a": 1}


def test_retry_once_then_ok():
    c = FakeClient(["not json", SAMPLE])
    spec = gc.generate_instagram_post(c, "r", "d")
    assert len(spec["cards"]) == 6 and c.n == 2


def test_fail_twice_raises():
    c = FakeClient(["nope", json.dumps({"cards": []})])
    with pytest.raises(RuntimeError, match="2회"):
        gc.generate_instagram_post(c, "r", "d")
