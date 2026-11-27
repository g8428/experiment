"""publish_wordpress.py의 이미지·메모 정리 로직 테스트(네트워크 없이 도는 순수 함수만).

실행: python3 -m unittest projects/claude-code-monitor/test_publish_wordpress.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import publish_wordpress as pw  # noqa: E402

SAMPLE = """---
title: "GPT-6, 단백질까지 설계한다고요?"
meta_description: "요약"
slug: gpt-6-protein-design
tags: [GPT6, OpenAI]
---

GPT-6 단백질 설계 소식이 이번 주 가장 많이 회자됐어요.

## 한 줄 결론

생각하고 코드를 쓰는 방식만으로 설계했다는 발표예요.

## 이게 뭔데요?

단백질은 우리 몸에서 일하는 작은 부품이에요.

[이미지 제안: 전용 도구 여러 개 대신 만능 도구 하나를 쓰는 모습]

## 주의할 점

- 초기 실험 결과예요.

[내부 링크 제안: 일반인이 AI에게 전문 업무를 맡길 때 확인할 것]

## 출처

- [원문](https://example.com)
"""


class NoteCleanupTest(unittest.TestCase):
    def test_markdown_keeps_image_slot_and_drops_link_note(self):
        _, body = pw.split_frontmatter(SAMPLE)
        cleaned = pw.strip_editor_notes(body)
        self.assertIn("[이미지 제안:", cleaned)
        self.assertNotIn("[내부 링크 제안:", cleaned)

    def test_html_cleanup_removes_both_notes(self):
        html = "<p>본문</p>\n<p>[이미지 제안: 어떤 그림]</p>\n<p>[내부 링크 제안: 어떤 글]</p>\n<h2>다음</h2>"
        out = pw.insert_figures(html, [])
        self.assertNotIn("이미지 제안", out)
        self.assertNotIn("내부 링크 제안", out)
        self.assertIn("<p>본문</p>", out)
        self.assertIn("<h2>다음</h2>", out)


class ImageInsertTest(unittest.TestCase):
    def setUp(self):
        _, body = pw.split_frontmatter(SAMPLE)
        self.html = pw.markdown_to_html(pw.strip_editor_notes(body))
        self.fig = pw.figure_html("https://x.test/a.png", "설명", "123")

    def test_figure_replaces_placeholder_in_place(self):
        out = pw.insert_figures(self.html, [self.fig])
        self.assertNotIn("[이미지 제안:", out)
        self.assertIn("<figure class=\"wp-block-image size-large\">", out)
        self.assertIn('class="wp-image-123"', out)
        # '이게 뭔데요?' 절 안, '주의할 점' 소제목보다 앞
        self.assertLess(out.index("<figure"), out.index("주의할 점"))
        self.assertGreater(out.index("<figure"), out.index("이게 뭔데요?"))

    def test_extra_images_go_after_first_paragraph(self):
        second = pw.figure_html("https://x.test/b.png", "둘째", "124")
        out = pw.insert_figures(self.html, [self.fig, second])
        self.assertIn("a.png", out)
        self.assertIn("b.png", out)
        # 첫 문단 바로 뒤에 들어간다
        first_p_end = out.index("</p>")
        self.assertLess(first_p_end, out.index("b.png"))
        self.assertLess(out.index("b.png"), out.index("이게 뭔데요?"))

    def test_no_placeholder_inserts_after_first_paragraph(self):
        html = "<p>첫 문단</p>\n<h2>소제목</h2>\n<p>둘째</p>"
        out = pw.insert_figures(html, [self.fig])
        self.assertLess(out.index("</p>"), out.index("<figure"))
        self.assertLess(out.index("<figure"), out.index("<h2>"))

    def test_placeholder_only_body_gets_image_first(self):
        out = pw.insert_figures("<p>[이미지 제안: 그림]</p>", [self.fig])
        self.assertTrue(out.startswith("<figure"))

    def test_figure_escapes_alt_and_caption(self):
        fig = pw.figure_html("https://x.test/a.png?x=1&y=2", '따옴표 " 위험', None, "<b>설명</b>")
        self.assertIn("&quot;", fig)
        self.assertIn("&lt;b&gt;", fig)
        self.assertIn("&amp;y=2", fig)


class AltTest(unittest.TestCase):
    def test_slot_text_becomes_default_alt(self):
        html = "<p>[이미지 제안: 전용 도구 여러 개 대신 만능 도구 하나]</p>"
        texts = pw.image_slot_texts(html)
        self.assertEqual(texts, ["전용 도구 여러 개 대신 만능 도구 하나"])
        self.assertEqual(pw.default_alt(texts[0], "제목", 0), "전용 도구 여러 개 대신 만능 도구 하나")

    def test_alt_falls_back_to_title_and_truncates(self):
        self.assertEqual(pw.default_alt(None, "글 제목", 0), "글 제목")
        long_alt = pw.default_alt("가" * 300, "제목", 0)
        self.assertLessEqual(len(long_alt), pw.MAX_ALT)


class BuildPostTest(unittest.TestCase):
    def test_build_post_reads_frontmatter(self):
        tmp = Path("/tmp/pw-test-post.md")
        tmp.write_text(SAMPLE, encoding="utf-8")
        post = pw.build_post(tmp)
        self.assertEqual(post["title"], "GPT-6, 단백질까지 설계한다고요?")
        self.assertEqual(post["slug"], "gpt-6-protein-design")
        self.assertEqual(post["tags"], "GPT6, OpenAI")
        self.assertIn("[이미지 제안:", post["markdown"])


class DuplicateTest(unittest.TestCase):
    def test_matches_slug_or_title_and_skips_trash(self):
        post = {"slug": "gpt-6-protein-design", "title": "GPT-6, 단백질까지 설계한다고요?"}
        posts = [
            {"ID": 1, "slug": "gpt-6", "title": "다른 글", "status": "publish"},
            {"ID": 2, "slug": "gpt-6-protein-design", "title": "무관", "status": "trash"},
            {"ID": 3, "slug": "other", "title": "GPT-6 단백질까지 설계한다고요", "status": "publish"},
        ]
        self.assertEqual(pw.find_duplicate(posts, post)["ID"], 3)


if __name__ == "__main__":
    unittest.main()
