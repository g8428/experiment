"""generate_content.py의 인스타 JSON 경로 테스트(네트워크·API 없이 도는 순수 함수만).

검사하는 것: ① 코드펜스·앞뒤 설명이 섞여도 JSON을 뽑아내는지 ② 렌더러가 못 먹을 출력을 걸러내는지
③ 통과한 데이터가 research/content 스키마(A형 표지 3줄 + 4~5줄 본문) 그대로인지
④ '~했다/…습니다' 보고서체를 잡아내는지 ⑤ md 요약이 6장 구조로 나오는지.

실행: python3 -m unittest projects/claude-code-monitor/test_generate_content.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import generate_content as gc  # noqa: E402

GOOD = {
    "handle": "청년 재테크 · AI 뉴스 카드",
    "badge": "OPENAI · GPT-6",
    "title_lines": ["전용 AI 없이", "단백질을", "설계했대요"],
    "highlight_word": "단백질을",
    "subtitle": "신약 후보 단백질, 실험실에서 붙었어요",
    "meta": "2026.11.24 · OpenAI 프리프린트",
    "hook_type": "통념 반박",
    "cover_visual": "어두운 배경에서 빛나는 단백질 나선",
    "slides": [
        {"mode": "fullbleed", "kicker": "왜 중요한가?", "headline": "약은 단백질로 만들어요",
         "body": "항체나 효소 같은 치료제는 대부분 단백질로 만들어요. 표적에 딱 맞는 모양이어야 약이 되니까, "
                 "어떤 모양으로 빚느냐가 신약의 출발점이거든요. 예전엔 이걸 하려면 전용 AI를 따로 돌려야 했어요.",
         "visual_hint": "공식 발표 인물 사진"},
        {"mode": "card", "kicker": "뭐가 달라졌는데?", "headline": "도구 없이, 말로 설계",
         "body": "이번엔 GPT-6.2가 표적 5개에 붙을 모양을 코드로 직접 짰어요. AlphaFold가 기존 구조를 맞히는 "
                 "AI였다면, 이번엔 아예 새로 만든 거죠. 온아바 실험실에서 322개 중 35개가 실제로 붙었어요.",
         "visual_hint": "공식 발표 도표"},
        {"mode": "fullbleed", "kicker": "실험실 결과는?", "headline": "표적 5개, 다 붙었어요",
         "headline_highlight": "5개",
         "body": "표적 5개(PD-L1·IL-7Rα·TrkA·VEGF-A·IL-17A) 모두에서 결합하는 단백질이 최소 하나씩 나왔어요. "
                 "322개 중 35개가 붙었으니 적중률은 10.9%. 종이 위 설계가 아니라 실험실에서 확인된 결과예요.",
         "visual_hint": "실험실 장면"},
        {"mode": "card", "kicker": "한계와 주의할 점", "headline": "아직은 초기 연구예요",
         "body": "아직 동료 심사를 거치기 전 논문이고, OpenAI가 직접 공개한 초기 결과예요. 서열을 채우거나 "
                 "후보를 추리는 건 기존 AI 도움을 받았고요. 당장 약국에 나올 신약은 아니라는 점만 짚고 갈게요.",
         "visual_hint": "벤치마크 차트"},
    ],
    "cta": {"kicker": "저장해 두세요", "headline": "매주 AI 소식\n한 장씩 정리해요",
            "body": "@earnretech · 놓치기 쉬운 흐름만 짚어 드려요"},
    "caption": "단백질 설계는 전문 AI만 하는 줄 알았어요. 이번엔 GPT-6가 전용 AI 없이 설계했고, 실험실에서 붙었대요. "
               "다만 심사 전 논문이라 약이 나온 건 아니에요. 출처: https://openai.com/",
    "hashtags": ["#AI뉴스", "#AI활용", "#직장인꿀팁", "#OpenAI", "#인공지능", "#신약개발"],
}


def as_response(data: dict) -> str:
    return "```json\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n```"


def with_slides(**changes) -> dict:
    """1장만 바꾼 데이터."""
    return {**GOOD, "slides": [{**GOOD["slides"][0], **changes}] + GOOD["slides"][1:]}


class ParseTest(unittest.TestCase):
    def test_code_fence_and_chatter(self):
        text = "네, 만들었어요.\n" + as_response(GOOD) + "\n확인해 보세요."
        self.assertEqual(gc.parse_instagram_json(text)["badge"], "OPENAI · GPT-6")

    def test_no_json(self):
        with self.assertRaises(ValueError):
            gc.parse_instagram_json("SKIP: 사유")


class ValidateTest(unittest.TestCase):
    def test_good_passes(self):
        self.assertEqual(gc.validate_instagram(GOOD), [])

    def test_wrong_slide_count(self):
        data = {**GOOD, "slides": GOOD["slides"][:3]}
        self.assertTrue(any("4개" in p for p in gc.validate_instagram(data)))

    def test_long_headline(self):
        problems = gc.validate_instagram(with_slides(headline="열세글자가넘어가는아주긴헤드라인"))
        self.assertTrue(any("headline" in p for p in problems))

    def test_banned_phrase(self):
        data = {**GOOD, "caption": "정말 혁신적인 발표예요."}
        self.assertIn("금지어: 혁신적인", gc.validate_instagram(data))

    def test_bad_mode(self):
        problems = gc.validate_instagram(with_slides(mode="photo"))
        self.assertTrue(any("mode" in p for p in problems))

    def test_hashtag_needs_hash(self):
        self.assertTrue(any("hashtags" in p for p in gc.validate_instagram({**GOOD, "hashtags": ["AI뉴스"]})))

    def test_not_a_dict(self):
        self.assertEqual(gc.validate_instagram([]), ["최상위가 JSON 객체가 아닙니다"])

    def test_highlight_must_be_in_headline(self):
        problems = gc.validate_instagram(with_slides(headline_highlight="없는구절"))
        self.assertTrue(any("highlight" in p for p in problems))

    # ---- A형 표지 스키마 ----
    def test_title_lines_need_three(self):
        problems = gc.validate_instagram({**GOOD, "title_lines": ["전용 AI 없이", "설계했대요"]})
        self.assertTrue(any("title_lines" in p and "3" in p for p in problems))

    def test_title_line_too_long(self):
        problems = gc.validate_instagram({**GOOD, "title_lines": ["전용 AI 없이", "단백질을", "아주아주아주길게설계했대요"]})
        self.assertTrue(any("title_lines 3" in p for p in problems))

    def test_highlight_word_must_be_in_title_lines(self):
        problems = gc.validate_instagram({**GOOD, "highlight_word": "없는구절"})
        self.assertTrue(any("highlight_word" in p for p in problems))

    def test_badge_too_long(self):
        problems = gc.validate_instagram({**GOOD, "badge": "OPENAI · GPT-6 · PROTEIN DESIGN PAPER"})
        self.assertTrue(any("badge" in p for p in problems))

    def test_meta_required(self):
        data = {k: v for k, v in GOOD.items() if k != "meta"}
        self.assertTrue(any("meta" in p for p in gc.validate_instagram(data)))

    # ---- 본문 길이(3~5줄 설명) ----
    def test_body_too_short(self):
        problems = gc.validate_instagram(with_slides(body="도구를 이어 붙이지 않고 설계했어요."))
        self.assertTrue(any("body" in p and "이상" in p for p in problems))

    def test_body_too_long(self):
        long_body = GOOD["slides"][0]["body"] * 3
        problems = gc.validate_instagram(with_slides(body=long_body))
        self.assertTrue(any("body" in p and "이내" in p for p in problems))

    # ---- 말투: '~했다/…습니다' 보고서체 ----
    def test_report_style_ending_in_body(self):
        problems = gc.validate_instagram(with_slides(body="OpenAI가 11월 24일, 전용 AI 없이 단백질을 설계했다. "
                                                          "실험실에서 35개가 표적에 결합했고, 5개 표적 모두 성공했다."))
        self.assertTrue(any("말투" in p for p in problems))

    def test_report_style_ending_in_cover_title(self):
        data = {**GOOD, "title_lines": ["전용 AI 없이", "단백질을", "만들었다"], "highlight_word": "단백질을"}
        self.assertTrue(any("말투" in p for p in gc.validate_instagram(data)))

    def test_report_style_ending_in_cta(self):
        data = {**GOOD, "cta": {**GOOD["cta"], "body": "쌓이면 흐름이 보입니다."}}
        self.assertTrue(any("CTA" in p and "말투" in p for p in gc.validate_instagram(data)))

    def test_conditional_endings_pass(self):
        # '였다면', '했는데요'처럼 문장이 끝나지 않는 형태는 통과해야 한다
        data = with_slides(body="AlphaFold가 구조를 예측하는 AI였다면, 이번엔 새로 만든 쪽이에요. "
                                "후보를 추리는 일은 기존 AI가 거들었는데요, 실험은 실험실에서 했어요.")
        self.assertEqual(gc.validate_instagram(data), [])

    def test_conversational_good_body_passes(self):
        self.assertEqual(gc.report_style_hits(GOOD["slides"][0]["body"]), [])


class MarkdownTest(unittest.TestCase):
    def test_renders_all_slides(self):
        md = gc.instagram_markdown(GOOD, "2026-12-01")
        for i in (2, 3, 4, 5, 6):
            self.assertIn(f"## {i}.", md)
        self.assertIn("## 캡션", md)
        self.assertIn("#AI뉴스", md)

    def test_cover_three_lines(self):
        md = gc.instagram_markdown(GOOD, "2026-12-01")
        self.assertIn("전용 AI 없이 / 단백질을 / 설계했대요", md)
        self.assertIn("강조: 단백질을", md)


if __name__ == "__main__":
    unittest.main()
