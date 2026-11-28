"""카드 이미지 수집: 실사진(GitHub) 또는 AI 생성(OpenAI Images API).

환경변수:
  OPENAI_API_KEY      없으면 어두운 단색 배경으로 대체(경고 출력, 로컬 테스트용)
  OPENAI_IMAGE_MODEL  기본 gpt-image-1
  GITHUB_TOKEN        (선택) README 조회 rate limit 완화
"""
from __future__ import annotations

import base64
import html
import io
import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from PIL import Image

W, H = 1080, 1350
MAX_BYTES = 15 * 1024 * 1024
BADGE_HOSTS = ("shields.io", "badgen.net", "badge.fury.io", "travis-ci", "codecov.io", "coveralls.io",
               "img.shields.io", "github.com/sponsors", "star-history.com", "visitor-badge", "hits.seeyoufarm")
DARK = (22, 24, 30)


def _warn(msg: str) -> None:
    print(f"[images] {msg}", file=sys.stderr)


def cover_crop(img: Image.Image, w: int = W, h: int = H) -> Image.Image:
    img = img.convert("RGB")
    scale = max(w / img.width, h / img.height)
    nw, nh = round(img.width * scale), round(img.height * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def fetch_image(url: str) -> Image.Image:
    """URL에서 이미지를 받아 Pillow 이미지로. 실패 시 예외."""
    if not url.startswith("https://"):
        raise ValueError("https URL만 허용")
    r = requests.get(url, timeout=30, headers={"User-Agent": "claude-code-monitor-cards"}, stream=True)
    r.raise_for_status()
    ctype = r.headers.get("content-type", "")
    if not ctype.startswith("image/") or "svg" in ctype:
        raise ValueError(f"이미지가 아님: {ctype}")
    data = r.raw.read(MAX_BYTES + 1, decode_content=True)
    if len(data) > MAX_BYTES:
        raise ValueError("이미지가 너무 큼")
    img = Image.open(io.BytesIO(data))
    img.load()
    return img


def find_readme_image_urls(readme: str, repo: str, branch_hint: str = "HEAD") -> list[str]:
    """README 마크다운/HTML에서 절대 URL 이미지를 순서대로 추출(뱃지 제외)."""
    urls = re.findall(r"!\[[^\]]*\]\(\s*<?(https?://[^)\s>]+)", readme)
    urls += re.findall(r"<img[^>]+src=[\"'](https?://[^\"']+)[\"']", readme, flags=re.I)
    # 문서 내 등장 순서 유지를 위해 위치 기준 재정렬
    positions = []
    for u in dict.fromkeys(urls):
        positions.append((readme.find(u), u))
    out = []
    for _, u in sorted(positions):
        low = u.lower()
        if any(b in low for b in BADGE_HOSTS) or low.split("?")[0].endswith(".svg"):
            continue
        out.append(u)
    return out


def readme_image(repo: str) -> Image.Image:
    headers = {"Accept": "application/vnd.github.raw+json", "User-Agent": "claude-code-monitor-cards"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    r = requests.get(f"https://api.github.com/repos/{repo}/readme", headers=headers, timeout=30)
    r.raise_for_status()
    for u in find_readme_image_urls(r.text, repo)[:6]:
        try:
            return fetch_image(u)
        except Exception as e:  # 다음 후보
            _warn(f"README 이미지 실패 {urlparse(u).netloc}: {e}")
    raise ValueError("README에 쓸 만한 절대 URL 이미지 없음")


def openai_image(prompt: str) -> Image.Image | None:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        _warn("OPENAI_API_KEY 없음 -> 어두운 단색 배경으로 대체")
        return None
    model = os.environ.get("OPENAI_IMAGE_MODEL") or "gpt-image-1"
    r = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "prompt": prompt, "size": "1024x1536", "n": 1},
        timeout=300,
    )
    if r.status_code != 200:
        try:
            msg = r.json().get("error", {}).get("message", "")
        except Exception:
            msg = ""
        raise RuntimeError(f"OpenAI Images 실패 HTTP {r.status_code}: {msg[:200]}")
    b64 = r.json()["data"][0]["b64_json"]
    img = Image.open(io.BytesIO(base64.b64decode(b64)))
    img.load()
    return img


def og_image_url(page_url: str) -> str:
    r = requests.get(page_url, timeout=30, headers={"User-Agent": "Mozilla/5.0 (compatible; claude-code-monitor-cards)"})
    r.raise_for_status()
    for m in re.finditer(r"<meta\s+[^>]*>", r.text[:300000], flags=re.I):
        tag = m.group(0)
        if re.search(r"(property|name)=[\"']og:image(:secure_url)?[\"']", tag, flags=re.I):
            c = re.search(r"content=[\"']([^\"']+)[\"']", tag, flags=re.I)
            if c:
                return urljoin(page_url, html.unescape(c.group(1)))
    raise ValueError("og:image 없음")


OK_LICENSE = re.compile(r"^(CC[ -]BY|CC0|Public domain|PD)", re.I)  # CC BY / BY-SA / CC0 / 퍼블릭 도메인만
COMMONS_API = "https://commons.wikimedia.org/w/api.php"


def wikimedia_image(image: dict) -> tuple[Image.Image, str]:
    """Commons에서 CC/퍼블릭 도메인 이미지만 사용. 출처에 작성자·라이선스 표기."""
    params = {"action": "query", "format": "json", "prop": "imageinfo", "iiprop": "url|extmetadata|mime",
              "iiurlwidth": 1600}
    url = image.get("url", "")
    if "/wiki/File:" in url:
        params["titles"] = "File:" + url.split("/wiki/File:", 1)[1]
    else:
        params.update({"generator": "search", "gsrsearch": image["prompt"], "gsrnamespace": 6, "gsrlimit": 8})
    r = requests.get(COMMONS_API, params=params, timeout=30, headers={"User-Agent": "claude-code-monitor-cards"})
    r.raise_for_status()
    pages = sorted((r.json().get("query", {}).get("pages", {})).values(), key=lambda p: p.get("index", 0))
    for pg in pages:
        info = (pg.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        lic = (meta.get("LicenseShortName", {}).get("value") or "").strip()
        mime = info.get("mime", "")
        if not OK_LICENSE.match(lic) or not mime.startswith("image/") or "svg" in mime:
            continue
        artist = re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "") or "").strip() or "작성자 미상"
        try:
            img = fetch_image(info.get("thumburl") or info["url"])
        except Exception as e:
            _warn(f"Commons 이미지 다운로드 실패: {e}")
            continue
        return img, f"{artist[:40]} / {lic} (Wikimedia Commons)"
    raise ValueError("라이선스 조건을 만족하는 Commons 이미지 없음")


def real_photo(image: dict) -> tuple[Image.Image, str]:
    """실사진 + 출처 문구(접두어 없는 본문). 실패하면 예외."""
    kind = image["kind"]
    if kind == "repo_og":
        repo = image["repo"]
        return fetch_image(f"https://opengraph.githubassets.com/1/{repo}"), f"GitHub {repo}"
    if kind == "owner_avatar":
        owner = image["repo"].split("/")[0]
        return fetch_image(f"https://github.com/{owner}.png?size=1080"), f"GitHub @{owner}"
    if kind == "readme_image":
        return readme_image(image["repo"]), f"GitHub {image['repo']} README"
    if kind == "official_og":
        host = urlparse(image["url"]).netloc.removeprefix("www.")
        return fetch_image(og_image_url(image["url"])), host + " 공식 발표"
    if kind == "wikimedia":
        return wikimedia_image(image)
    if kind == "url":
        host = urlparse(image["url"]).netloc
        return fetch_image(image["url"]), host
    raise ValueError(kind)


def _strip_prefix(note: str) -> str:
    return re.sub(r"^(사진|이미지|출처)\s*[:：]\s*", "", note.strip())


def collect(spec: dict, out_dir: Path) -> list[dict]:
    """카드별 {"path": Path|None, "source": str, "type": 최종 카드 타입}. 실사진 실패 시 ai 폴백."""
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for i, card in enumerate(spec["cards"], 1):
        res = {"path": None, "source": "", "type": card["type"]}
        image = card.get("image")
        if image is None:  # end 카드
            results.append(res)
            continue
        img, source, is_ai = None, "", image["kind"] == "ai"
        if not is_ai:
            try:
                img, source = real_photo(image)
                if image.get("source_note"):
                    source = _strip_prefix(image["source_note"])
            except Exception as e:
                _warn(f"{i}번 카드 실사진 실패({image['kind']}): {e} -> AI 폴백")
                is_ai = True
        if is_ai:
            prompt = image.get("prompt") or (
                f"{card['title']}을(를) 연상시키는 상황이 한눈에 보이는 일러스트풍 장면. 글자와 로고, 실존 인물 얼굴 없음."
            )
            try:
                img = openai_image(prompt)
            except Exception as e:
                _warn(f"{i}번 카드 AI 생성 실패: {e} -> 단색 배경")
                img = None
            source = "AI 생성"
            if image["kind"] != "ai":
                res["type"] = "photo"  # 도표용 실사진이 없으면 사진 카드로 전환
        if img is None:
            img = Image.new("RGB", (W, H), DARK)
        if res["type"] == "photo" and not is_ai and img.width / img.height > 1.3:
            res["type"] = "figure"  # 가로형 실사진(OG 카드 등)을 세로 전체로 잘라 쓰면 깨지므로 흰 박스 카드로 전환
        if res["type"] == "photo":
            img = cover_crop(img)
        else:  # figure: 비율 유지(contain은 CSS), 용량 제한만
            img = img.convert("RGB")
            img.thumbnail((2000, 2000))
        path = out_dir / f"img_{i:02d}.png"
        img.save(path, "PNG")
        res["path"], res["source"] = path, source
        results.append(res)
    return results
