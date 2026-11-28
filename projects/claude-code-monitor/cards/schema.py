"""인스타 카드뉴스 JSON 스펙 검증 + Slack용 마크다운 변환.

스키마:
{
  "brand_label": "선택",
  "cards": [
    {"type": "photo|figure|end", "kicker": "...", "title": "...", "body": "...",
     "title_highlight": "title 안의 강조할 부분 문자열(선택, 표지 권장)",
     "source_url": "근거 링크(표지·마무리 외 필수)",
     "image": {"kind": "ai|repo_og|owner_avatar|readme_image|url|official_og|wikimedia",
               "prompt": "ai일 때", "repo": "owner/name (repo_og/owner_avatar/readme_image)",
               "url": "url일 때", "source_note": "출처 문구(선택)"}}
  ],
  "caption": "...", "hashtags": ["#..."]
}
첫 장은 photo(ai), 마지막은 end, 최대 10장.
"""
from __future__ import annotations

import re

MAX_CARDS = 10
CARD_TYPES = {"photo", "figure", "end"}
IMAGE_KINDS = {"ai", "repo_og", "owner_avatar", "readme_image", "url", "official_og", "wikimedia"}
REPO_KINDS = {"repo_og", "owner_avatar", "readme_image"}
REPO_RE = re.compile(r"^[\w.-]+/[\w.-]+$")


class SpecError(ValueError):
    pass


def _s(d: dict, key: str, where: str, required: bool = True) -> str:
    v = d.get(key)
    if v is None or (isinstance(v, str) and not v.strip()):
        if required:
            raise SpecError(f"{where}.{key} 누락")
        return ""
    if not isinstance(v, str):
        raise SpecError(f"{where}.{key}는 문자열이어야 함")
    return v.strip()


def validate(spec) -> dict:
    """검증 후 정규화된 dict 반환. 문제가 있으면 SpecError."""
    if not isinstance(spec, dict):
        raise SpecError("최상위가 객체(dict)가 아님")
    cards = spec.get("cards")
    if not isinstance(cards, list) or len(cards) < 2:
        raise SpecError("cards는 2장 이상의 배열이어야 함")
    if len(cards) > MAX_CARDS:
        raise SpecError(f"cards는 최대 {MAX_CARDS}장 (현재 {len(cards)})")

    out_cards = []
    for i, c in enumerate(cards):
        where = f"cards[{i}]"
        if not isinstance(c, dict):
            raise SpecError(f"{where}가 객체가 아님")
        t = c.get("type")
        if t not in CARD_TYPES:
            raise SpecError(f"{where}.type은 {sorted(CARD_TYPES)} 중 하나 (현재 {t!r})")
        is_end = t == "end"
        card = {
            "type": t,
            "kicker": _s(c, "kicker", where, required=not is_end),
            "title": _s(c, "title", where),
            "body": _s(c, "body", where, required=not (is_end or i == 0)),  # 표지 body = 선택 부제
        }
        hl = _s(c, "title_highlight", where, required=False)
        if hl:
            if hl not in card["title"]:
                raise SpecError(f"{where}.title_highlight({hl!r})가 title 안에 없음")
            card["title_highlight"] = hl
        if t in ("photo", "figure"):
            img = c.get("image")
            if not isinstance(img, dict):
                raise SpecError(f"{where}.image 누락 ({t} 카드는 이미지 필요)")
            kind = img.get("kind")
            if kind not in IMAGE_KINDS:
                raise SpecError(f"{where}.image.kind는 {sorted(IMAGE_KINDS)} 중 하나 (현재 {kind!r})")
            iw = f"{where}.image"
            im = {
                "kind": kind,
                "source_note": _s(img, "source_note", iw, required=False),
                "prompt": _s(img, "prompt", iw, required=(kind == "ai")),
            }
            if kind in REPO_KINDS:
                repo = _s(img, "repo", iw)
                if not REPO_RE.match(repo):
                    raise SpecError(f"{iw}.repo는 owner/name 형식 (현재 {repo!r})")
                im["repo"] = repo
            if kind in ("url", "official_og", "wikimedia"):
                # wikimedia는 url(Commons 파일 페이지) 또는 prompt(검색어) 중 하나면 된다
                url = _s(img, "url", iw, required=(kind != "wikimedia"))
                if url and not url.startswith("https://"):
                    raise SpecError(f"{iw}.url은 https:// 로 시작해야 함")
                if kind == "wikimedia" and not url and not im["prompt"]:
                    raise SpecError(f"{iw}: wikimedia는 url 또는 prompt(검색어) 필요")
                if url:
                    im["url"] = url
            card["image"] = im
        src = _s(c, "source_url", where, required=(0 < i < len(cards) - 1))  # 표지·마무리 외 카드는 근거 링크 필수
        if src:
            if not src.startswith("https://"):
                raise SpecError(f"{where}.source_url은 https:// 로 시작해야 함")
            card["source_url"] = src
        out_cards.append(card)

    if out_cards[0]["type"] != "photo":
        raise SpecError("첫 장은 photo여야 함")
    if out_cards[0]["image"]["kind"] != "ai":
        raise SpecError("첫 장(표지)의 image.kind는 ai여야 함")
    if out_cards[-1]["type"] != "end":
        raise SpecError("마지막 장은 end여야 함")
    if any(c["type"] == "end" for c in out_cards[:-1]):
        raise SpecError("end 카드는 마지막 한 장뿐이어야 함")

    caption = _s(spec, "caption", "spec")
    tags = spec.get("hashtags")
    if not isinstance(tags, list) or not tags or not all(isinstance(t, str) and t.strip() for t in tags):
        raise SpecError("hashtags는 비어있지 않은 문자열 배열이어야 함")
    tags = [t.strip() if t.strip().startswith("#") else "#" + t.strip() for t in tags]

    out = {"cards": out_cards, "caption": caption, "hashtags": tags}
    bl = spec.get("brand_label")
    if isinstance(bl, str) and bl.strip():
        out["brand_label"] = bl.strip()
    return out


def full_caption(spec: dict, limit: int = 2200) -> str:
    text = spec["caption"].strip() + "\n\n" + " ".join(spec["hashtags"])
    return text[:limit]


def to_markdown(spec: dict) -> str:
    """Slack 스레드용 읽기 좋은 마크다운."""
    lines = ["# 인스타 카드뉴스", ""]
    n = len(spec["cards"])
    for i, c in enumerate(spec["cards"], 1):
        lines.append(f"## {i}/{n} [{c['type']}] {c['title']}")
        if c.get("kicker"):
            lines.append(f"- 키커: {c['kicker']}")
        if c.get("body"):
            lines.append(f"- 설명: {c['body']}")
        img = c.get("image")
        if img:
            ref = img.get("repo") or img.get("url") or img.get("prompt") or ""
            lines.append(f"- 이미지: {img['kind']} {ref}".rstrip())
        if c.get("source_url"):
            lines.append(f"- 근거: {c['source_url']}")
        lines.append("")
    lines += ["## 캡션", spec["caption"], "", "## 해시태그", " ".join(spec["hashtags"]), ""]
    return "\n".join(lines)
