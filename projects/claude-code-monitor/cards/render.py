"""카드 JSON -> 이미지 수집 -> PNG(1080x1350) 렌더.

실행: python projects/claude-code-monitor/cards/render.py [spec.json] [--out DIR]
  spec 생략 시 content/instagram/ 의 최신 *-instagram.json
의존성: jinja2, playwright(chromium), pillow, requests
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

HERE = Path(__file__).parent
ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(HERE.parent))
from cards import images, schema  # noqa: E402

DEFAULT_BRAND = "청년재테크 · AI 뉴스 카드"
DEFAULT_OUT = HERE / "out"


def title_html(card: dict) -> Markup:
    title, hl = card["title"], card.get("title_highlight")
    if hl and hl in title:
        a, b = title.split(hl, 1)
        return Markup(f"{escape(a)}<span class=\"hl\">{escape(hl)}</span>{escape(b)}")
    return Markup(str(escape(title)))


def source_label(card: dict, res: dict) -> str:
    if not res.get("source"):
        return ""
    if res["source"] == "AI 생성":
        return "이미지: AI 생성"
    return ("출처: " if res["type"] == "figure" else "사진: ") + res["source"]


def build_html(spec: dict, results: list[dict], out_dir: Path) -> list[Path]:
    env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape(["html", "j2"]))
    tpl = env.get_template("card.html.j2")
    brand = os.environ.get("IG_BRAND_LABEL") or spec.get("brand_label") or DEFAULT_BRAND
    total = len(spec["cards"])
    paths = []
    for i, (card, res) in enumerate(zip(spec["cards"], results), 1):
        card = dict(card, type=res["type"])
        html = tpl.render(
            card=card, is_cover=(i == 1), brand=brand, page=i, total=total,
            title_html=title_html(card), source_label=source_label(card, res),
            image_src=res["path"].name if res.get("path") else "",
        )
        p = out_dir / f"card_{i:02d}.html"
        p.write_text(html, encoding="utf-8")
        paths.append(p)
    return paths


def screenshot(html_paths: list[Path], out_dir: Path) -> list[Path]:
    from playwright.sync_api import sync_playwright

    pngs = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1350})
        for i, hp in enumerate(html_paths, 1):
            try:
                page.goto(hp.resolve().as_uri(), wait_until="networkidle", timeout=30000)
            except Exception as e:  # 폰트 CDN 지연 등: 로드된 상태로 진행
                print(f"[render] 로드 경고 {hp.name}: {e}", file=sys.stderr)
            page.evaluate("document.fonts.ready")
            png = out_dir / f"{i:02d}.png"
            page.screenshot(path=str(png), clip={"x": 0, "y": 0, "width": 1080, "height": 1350})
            pngs.append(png)
        browser.close()
    return pngs


def render(spec: dict, out_dir: Path) -> list[Path]:
    spec = schema.validate(spec)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    results = images.collect(spec, out_dir)
    html_paths = build_html(spec, results, out_dir)
    pngs = screenshot(html_paths, out_dir)
    (out_dir / "card.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    return pngs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", nargs="?")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    a = ap.parse_args()
    if a.spec:
        spec_path = Path(a.spec)
    else:
        cands = sorted((ROOT / "content" / "instagram").glob("*-instagram.json"), reverse=True)
        if not cands:
            print("카드 JSON이 없습니다 (content/instagram/*-instagram.json)", file=sys.stderr)
            return 1
        spec_path = cands[0]
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    pngs = render(spec, Path(a.out))
    for p in pngs:
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
