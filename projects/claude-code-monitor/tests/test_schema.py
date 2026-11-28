import copy
import json
from pathlib import Path

import pytest

from cards import schema

SAMPLE = json.loads((Path(__file__).parent.parent / "cards" / "sample.json").read_text(encoding="utf-8"))


def test_sample_valid_and_six_cards():
    spec = schema.validate(SAMPLE)
    assert [c["type"] for c in spec["cards"]] == ["photo", "photo", "figure", "photo", "figure", "end"]
    assert "title_highlight" in spec["cards"][0]


def bad(mutate):
    spec = copy.deepcopy(SAMPLE)
    mutate(spec)
    with pytest.raises(schema.SpecError):
        schema.validate(spec)


def test_first_must_be_ai_photo():
    bad(lambda s: s["cards"][0]["image"].update(kind="repo_og", repo="a/b"))
    bad(lambda s: s["cards"].insert(0, s["cards"].pop(2)))


def test_last_must_be_end():
    bad(lambda s: s["cards"].pop())


def test_max_10_cards():
    def more(s):
        s["cards"][1:1] = [copy.deepcopy(s["cards"][1]) for _ in range(5)]

    bad(more)


def test_source_url_required_for_body_cards():
    bad(lambda s: s["cards"][1].pop("source_url"))


def test_highlight_must_be_in_title():
    bad(lambda s: s["cards"][0].update(title_highlight="없는말"))


def test_kind_requirements():
    bad(lambda s: s["cards"][1]["image"].update(kind="bogus"))
    bad(lambda s: s["cards"][1]["image"].update(kind="official_og", url="http://x"))
    bad(lambda s: s["cards"][1]["image"].update(kind="repo_og", repo="no-slash"))
    bad(lambda s: s["cards"][1]["image"].update(kind="wikimedia", prompt="", repo="a/b"))


def test_wikimedia_with_query_ok():
    spec = copy.deepcopy(SAMPLE)
    spec["cards"][1]["image"] = {"kind": "wikimedia", "prompt": "data center", "source_note": ""}
    assert schema.validate(spec)["cards"][1]["image"]["kind"] == "wikimedia"


def test_caption_and_tags():
    bad(lambda s: s.update(caption=""))
    bad(lambda s: s.update(hashtags=[]))
    spec = copy.deepcopy(SAMPLE)
    spec["hashtags"] = ["AI"]
    assert schema.validate(spec)["hashtags"] == ["#AI"]
    assert "#AI" in schema.full_caption(schema.validate(spec))


def test_markdown_contains_titles():
    md = schema.to_markdown(schema.validate(SAMPLE))
    assert "## 캡션" in md and SAMPLE["cards"][1]["title"] in md
