"""generate_content.py의 인스타 JSON 경로 테스트(네트워크·API 없이 도는 순수 함수만).

검사하는 것: ① 코드펜스·앞뒤 설명이 섞여도 JSON을 뽑아내는지 ② 렌더러가 못 먹을 출력을 걸러내는지
③ 통과한 데이터가 research/content 스키마 그대로인지 ④ md 요약이 6장 구조로 나오는지.

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
    "title": "약 만드는 AI",
    "subtitle": "전용 장비 없이 해냈다",
    "hook_type": "통념 반박",
    "cover_visual": "어두운 화면에서 단백질 구조가 떠오르는 장면",
    "slides": [
        {"mode": "fullbleed", "kicker": "무슨 일이야?", "headline": "전용 AI가 빠졌다",
         "body": "OpenAI가 11월 24일, 생물학 전용 AI 없이 GPT-6가 단백질을 설계했다고 밝혔어요.",
         "visual_hint": "공식 발표 인물 사진"},
        {"mode": "card", "kicker": "어떻게 한 거야?", "headline": "말로 시켰다",
         "body": "도구를 이어 붙이지 않고 자연어 지시만으로 설계해요.", "visual_hint": "공식 발표 도표"},
        {"mode": "fullbleed", "kicker": "나한테 뭐가 좋아요?", "headline": "먼저 시켜보세요",
         "body": "전용 AI를 찾기 전에 쓰던 AI에게 먼저 맡겨 볼 수 있어요.", "visual_hint": "실험실 장면"},
        {"mode": "card", "kicker": "주의할 점", "headline": "약은 아니에요",
         "body": "심사 전 논문이고 초기 실험 결과예요. 업체가 직접 공개했어요.", "visual_hint": "벤치마크 차트"},
    ],
    "cta": {"headline": "매주 AI 소식\n한 장씩", "body": "다음에 또 꺼내 보시라고 저장"},
    "caption": "단백질 설계는 전문 AI만 하는 줄 알았습니다. 이번엔 달랐어요. 출처: https://openai.com/",
    "hashtags": ["#AI뉴스", "#AI활용", "#직장인꿀팁", "#OpenAI", "#인공지능"],
}


def as_response(data: dict) -> str:
    return "```json\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n```"


class ParseTest(unittest.TestCase):
    def test_code_fence_and_chatter(self):
        text = "네, 만들었습니다.\n" + as_response(GOOD) + "\n확인해 보세요."
        self.assertEqual(gc.parse_instagram_json(text)["title"], "약 만드는 AI")

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
        slides = [{**GOOD["slides"][0], "headline": "열세글자가넘어가는아주긴헤드라인"}] + GOOD["slides"][1:]
        self.assertTrue(any("headline" in p for p in gc.validate_instagram({**GOOD, "slides": slides})))

    def test_banned_phrase(self):
        data = {**GOOD, "caption": "정말 혁신적인 발표입니다."}
        self.assertIn("금지어: 혁신적인", gc.validate_instagram(data))

    def test_bad_mode(self):
        slides = [{**GOOD["slides"][0], "mode": "photo"}] + GOOD["slides"][1:]
        self.assertTrue(any("mode" in p for p in gc.validate_instagram({**GOOD, "slides": slides})))

    def test_hashtag_needs_hash(self):
        self.assertTrue(any("hashtags" in p for p in gc.validate_instagram({**GOOD, "hashtags": ["AI뉴스"]})))

    def test_not_a_dict(self):
        self.assertEqual(gc.validate_instagram([]), ["최상위가 JSON 객체가 아닙니다"])


class MarkdownTest(unittest.TestCase):
    def test_renders_all_slides(self):
        md = gc.instagram_markdown(GOOD, "2026-12-01")
        for i in (2, 3, 4, 5, 6):
            self.assertIn(f"## {i}.", md)
        self.assertIn("## 캡션", md)
        self.assertIn("#AI뉴스", md)


if __name__ == "__main__":
    unittest.main()
