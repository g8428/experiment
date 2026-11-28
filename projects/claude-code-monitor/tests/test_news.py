from datetime import datetime, timezone

import pytest

pytest.importorskip("feedparser")
import news_collect as n  # noqa: E402

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>GPT-6 &amp; friends</title><link>https://ex.com/a</link>
<pubDate>Fri, 27 Nov 2026 10:00:00 GMT</pubDate>
<description>&lt;p&gt;Hello &lt;b&gt;world&lt;/b&gt;&lt;/p&gt;</description></item>
<item><title>Old news</title><link>https://ex.com/old</link><pubDate>Mon, 01 Jan 2024 10:00:00 GMT</pubDate></item>
<item><title></title><link>https://ex.com/empty</link></item>
</channel></rss>""".encode()


def test_parse_feed():
    items = n.parse_feed(RSS, "Ex", True)
    assert len(items) == 2
    assert items[0]["title"] == "GPT-6 & friends"
    assert items[0]["summary"] == "Hello world"
    assert items[0]["official"] is True


def test_parse_garbage_raises():
    with pytest.raises(ValueError):
        n.parse_feed(b"not a feed at all", "x", False)


def test_filter_recent():
    items = n.parse_feed(RSS, "Ex", True)
    now = datetime(2026, 11, 28, tzinfo=timezone.utc)
    assert [i["link"] for i in n.filter_recent(items, 7, now)] == ["https://ex.com/a"]


def test_dedupe_prefers_official():
    d = datetime.now(timezone.utc)

    def mk(t, link, o):
        return {"title": t, "link": link, "date": d, "source": "s", "official": o, "summary": "", "image": ""}

    out = n.dedupe([mk("Big News!", "https://a/1", False), mk("big news", "https://b/2", True), mk("Other", "https://a/1/", False)])
    assert [i["title"] for i in out] == ["big news", "Other"]  # 제목 중복은 공식 쪽만 남김
    dup_link = n.dedupe([mk("A", "https://a/1", False), mk("B", "https://a/1/", False)])
    assert len(dup_link) == 1  # 링크 중복(끝 슬래시 무시)


def test_summary_truncated():
    s = n.clean_summary("가" * 500)
    assert len(s) == 200 and s.endswith("…")


def test_og_image_extract():
    page = '<head><meta content="/img/x.png" property="og:image"><meta property="og:title" content="t"></head>'
    assert n.extract_og_image(page, "https://ex.com/p/1") == "https://ex.com/img/x.png"
    assert n.extract_og_image("<head></head>", "https://ex.com") == ""


def test_render_md_has_link_and_no_body():
    d = datetime(2026, 11, 27, tzinfo=timezone.utc)
    md = n.render_md([{"title": "T", "link": "https://x", "date": d, "source": "S", "official": True, "summary": "sum", "image": ""}],
                     "2026-11-28", 7, [("S", "1건")])
    assert "## T" in md and "공식 발표" in md and "https://x" in md
