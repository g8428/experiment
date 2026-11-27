"""
생성된 블로그 초안(content/blog, research/content)을 워드프레스 블로그(earninsu.wordpress.com)에 올린다.

2026-11-27 추가. 계기: 사용자가 "자동으로 수집해서 블로그 글 쓰는 거를 올려봐"라고 요청.
워크플로(.github/workflows/claude-code-monitor.yml)는 GitHub App에 `workflows` 권한이 없어 고칠 수 없어서,
업로드는 이 스크립트를 부르는 쪽(Pickle 예약 액션 `📮 주간 블로그 글 워드프레스 발행`)이 맡는다.
Actions가 research/content/{날짜}-blog.md 로 커밋해 둔 글을 받아 그대로 올린다.

2026-11-27 추가(2). 계기: 사용자가 "블로그글이 텍스트밖에 없는데 gpt이미지든 무료소스 이미지든 관련글을
올리거나 인스타 카드뉴스 썸네일을 같이 쓰거나 하도록 해줘"라고 요청. 그래서 대표 이미지·본문 이미지를 붙인다.
- `--image <path>` : 이미지 파일을 미디어 라이브러리에 올려 대표 이미지(featured_image)로 걸고,
  본문의 `[이미지 제안: ...]` 자리에 같은 이미지를 넣는다. 여러 번 줄 수 있다(순서대로 치환).
- `--image-prompt "<영어 프롬프트>"` : `images` 명령으로 먼저 이미지를 만들고(--image와 같은 효과).
- `--image-alt "..."` : 대체텍스트(이미지 순서대로). 없으면 `[이미지 제안: ...]` 문구 → 글 제목 순으로 쓴다.
- `[이미지 제안: ...]`, `[내부 링크 제안: ...]` 같은 작성자 메모는 발행 시 지운다.
- `--update-post-id <ID>` : 이미 올라간 글을 고친다(본문 메모 정리 + 이미지 삽입 + 대표 이미지 설정).
- `--fill-missing-image` : 중복이라 건너뛸 글이 대표 이미지가 없으면 그 글에만 이미지를 채워 넣는다.

실행:
  python projects/claude-code-monitor/publish_wordpress.py                    # 가장 최근 주 글을 공개 발행
  python projects/claude-code-monitor/publish_wordpress.py --dry-run          # 업로드 없이 무엇을 올릴지·중복 여부만 확인
  python projects/claude-code-monitor/publish_wordpress.py --file <경로.md>   # 파일 지정 (날짜 제한 없음)
  python projects/claude-code-monitor/publish_wordpress.py --status draft     # 초안으로 (수동용, 기본은 publish)
  python projects/claude-code-monitor/publish_wordpress.py --max-age-days 8   # 최근 8일 글만 대상(기본 8)
  python projects/claude-code-monitor/publish_wordpress.py --image downloads/blog.png --image-alt "설명"
  python projects/claude-code-monitor/publish_wordpress.py --update-post-id 50 --image downloads/blog.png
  python projects/claude-code-monitor/publish_wordpress.py --image-prompt "flat vector illustration, no text"

토큰: 환경변수 WORDPRESS_ACCESS_TOKEN → 없으면 토큰 파일(WORDPRESS_TOKEN_FILE 또는 기본 경로).
토큰은 화면에 찍지 않는다(로그·에러 메시지 포함).

중복 방지: 업로드 전에 WordPress REST로 최근 글을 받아 같은 슬러그(또는 같은 제목)가 있으면 건너뛴다.
그래서 같은 주에 여러 번 돌아도(월요일 저녁 + 화요일 아침) 한 번만 올라간다.
research/state/... 대신 레포 밖 상태 파일에 업로드 이력을 남기는 이유: 예약 실행이 `git reset --hard`로
레포를 매번 되돌리기 때문. 상태 파일은 기록용이고, 판단은 항상 WordPress 쪽 실제 글로 한다.

의존성: requests, pyyaml, markdown (requirements.txt 참고). 이미지 생성은 셸의 `images` 명령(선택).
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

import requests
import yaml

ROOT = Path(__file__).parent.parent.parent
KST = timezone(timedelta(hours=9))

API = "https://public-api.wordpress.com/rest/v1.1"
DEFAULT_SITE = "earninsu.wordpress.com"
DEFAULT_TOKEN_FILE = Path("/workspace/.pickle-secrets/wordpress-earninsu.json")
DEFAULT_STATE_FILE = Path("/workspace/state/wordpress-published.json")
DEFAULT_IMAGE_DIR = Path("/workspace/downloads")
# research/content = Actions가 커밋하는 사본(발행 근거), content/blog = 생성 원본(Actions 러너에만 존재)
ARTICLE_DIRS = (ROOT / "research" / "content", ROOT / "content" / "blog")
DATE_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)\.md$")
MAX_EXCERPT = 400
MAX_ALT = 130

# 작성자 메모: `[이미지 제안: ...]`, `[내부 링크 제안: ...]` (마크다운 한 줄 / HTML 한 문단)
NOTE_LINE = re.compile(r"^[ \t]*\[(?:이미지|내부\s*링크)\s*제안\s*:.*?\][ \t]*$", re.M)
LINK_NOTE_HTML = re.compile(r"<p>\s*\[내부\s*링크\s*제안\s*:.*?\]\s*</p>\s*", re.S)
IMAGE_NOTE_HTML = re.compile(r"<p>\s*\[이미지\s*제안\s*:.*?\]\s*</p>\s*", re.S)
# 치환할 이미지 자리. group(1) = 제안 문구(대체텍스트 기본값으로 쓴다)
IMAGE_SLOT_HTML = re.compile(r"<p>\s*\[이미지\s*제안\s*:(.*?)\]\s*</p>", re.S)


class PublishError(RuntimeError):
    pass


# ---------------------------------------------------------------- 입력 찾기/읽기

def today_kst() -> datetime:
    return datetime.now(KST)


def find_latest_article(explicit: Path | None, max_age_days: int) -> tuple[Path | None, str]:
    """가장 최근 날짜의 블로그 md를 고른다. 같은 날짜면 research/content(커밋본)를 우선한다.
    돌려주는 두 번째 값은 '왜 없음/무엇을 골랐는지' 설명."""
    if explicit:
        if not explicit.exists():
            raise PublishError(f"파일이 없습니다: {explicit}")
        return explicit, f"지정한 파일 {explicit}"
    found: list[tuple[str, int, float, Path]] = []
    for priority, d in enumerate(ARTICLE_DIRS):
        if not d.is_dir():
            continue
        for p in d.glob("*.md"):
            m = DATE_NAME.match(p.name)
            if not m:
                continue
            found.append((m.group(1), -priority, p.stat().st_mtime, p))
    if not found:
        return None, "research/content, content/blog에 날짜가 붙은 블로그 글이 없습니다"
    found.sort()
    date_str, _, _, path = found[-1]
    age = (today_kst().date() - datetime.strptime(date_str, "%Y-%m-%d").date()).days
    if max_age_days >= 0 and age > max_age_days:
        return None, (f"올릴 새 글이 없습니다 — 가장 최근 글 {date_str}({path.name})이 {age}일 지나 "
                      f"기준({max_age_days}일) 밖입니다")
    return path, f"{date_str} 글 {path}"


def split_frontmatter(text: str) -> tuple[dict, str]:
    """YAML 프론트매터를 떼고 (메타, 본문)을 돌려준다. 프론트매터가 없으면 ({}, 전문)."""
    if text.lstrip().startswith("---"):
        stripped = text.lstrip()
        end = stripped.find("\n---", 3)
        if end != -1:
            fm_text = stripped[3:end]
            body = stripped[end + 4:].lstrip("\n")
            try:
                meta = yaml.safe_load(fm_text) or {}
            except yaml.YAMLError:
                meta = {}
            if not isinstance(meta, dict):
                meta = {}
            return meta, body
    return {}, text


def norm(text: str) -> str:
    """제목 비교용 정규화: 공백·구두점·마크업 기호를 걷어내고 소문자로."""
    return re.sub(r"[\s\W_]+", "", text or "", flags=re.UNICODE).lower()


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:60].strip("-") or "post"


def first_heading(body: str) -> str | None:
    m = re.search(r"^\s*#\s+(.+?)\s*$", body, re.M)
    return m.group(1).strip() if m else None


def build_post(path: Path) -> dict:
    meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
    title = str(meta.get("title") or "").strip()
    heading = first_heading(body)
    if not title:
        title = heading or path.stem
    # 본문 맨 앞 H1이 제목과 같으면 뺀다 (워드프레스는 글 제목을 따로 보여 줘서 중복된다)
    if heading and norm(heading) == norm(title):
        body = re.sub(r"^\s*#\s+.+?\s*$", "", body, count=1, flags=re.M).lstrip("\n")
    if not body.strip():
        raise PublishError(f"본문이 비어 있습니다: {path}")

    slug = str(meta.get("slug") or "").strip() or slugify(title)
    excerpt = meta.get("meta_description") or meta.get("description") or meta.get("excerpt") or ""
    if isinstance(excerpt, str):
        excerpt = excerpt.strip()[:MAX_EXCERPT]
    else:
        excerpt = ""
    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tag_text = tags
    else:
        tag_text = ", ".join(str(t).strip() for t in tags if str(t).strip())
    date = str(meta.get("date") or "").strip()
    return {"title": title, "slug": slug, "excerpt": excerpt, "tags": tag_text,
            "markdown": body, "meta": meta, "path": path, "date": date}


def markdown_to_html(text: str) -> str:
    try:
        import markdown  # requirements.txt (Actions 스텝에서는 pip install markdown)
    except ImportError as e:  # pragma: no cover
        raise PublishError("markdown 패키지가 없습니다: pip install markdown") from e
    return markdown.markdown(text, extensions=["extra", "sane_lists", "nl2br", "toc"])


# ---------------------------------------------------------------- 편집 메모 정리 / 이미지

def strip_editor_notes(markdown: str) -> str:
    """마크다운에 남은 `[내부 링크 제안: ...]` 줄을 지운다. 이미지 자리는 나중에 치환해야 하므로 남긴다."""
    text = re.sub(r"^[ \t]*\[내부\s*링크\s*제안\s*:.*?\][ \t]*$\n?", "", markdown, flags=re.M)
    return re.sub(r"\n{3,}", "\n\n", text)


def strip_editor_notes_html(html: str) -> str:
    """HTML에 남은 이미지·내부 링크 제안 문단을 지운다(이미지 자리는 insert_figures가 먼저 치환)."""
    html = LINK_NOTE_HTML.sub("", html)
    html = IMAGE_NOTE_HTML.sub("", html)
    return html


def image_slot_texts(html: str) -> list[str]:
    """본문의 `[이미지 제안: ...]` 문구를 순서대로. 대체텍스트 기본값으로 쓴다."""
    return [re.sub(r"\s+", " ", m.group(1)).strip() for m in IMAGE_SLOT_HTML.finditer(html)]


def default_alt(text: str | None, title: str, index: int) -> str:
    alt = (text or "").strip().strip("-–—:·").strip() or title
    if len(alt) > MAX_ALT:
        alt = alt[:MAX_ALT - 1].rstrip() + "…"
    return alt or f"{title} 이미지 {index + 1}"


def figure_html(url: str, alt: str, media_id: str | None = None, caption: str | None = None) -> str:
    src = html_lib.escape(url, quote=True)
    alt_attr = html_lib.escape(alt, quote=True)
    cls = f' class="wp-image-{html_lib.escape(str(media_id), quote=True)}"' if media_id else ""
    fig = (f'<figure class="wp-block-image size-large">'
           f'<img src="{src}" alt="{alt_attr}"{cls} loading="lazy"/>')
    if caption:
        fig += f'<figcaption class="wp-element-caption">{html_lib.escape(caption)}</figcaption>'
    return fig + "</figure>"


def insert_near_top(html: str, figure: str) -> str:
    """이미지 자리가 없을 때: 첫 문단 뒤, 첫 문단이 없으면 첫 소제목(h2) 앞, 그것도 없으면 맨 위."""
    m = re.search(r"</p>", html)
    if m:
        return html[:m.end()] + "\n" + figure + html[m.end():]
    m = re.search(r"<h2\b", html)
    if m:
        return html[:m.start()] + figure + "\n" + html[m.start():]
    return figure + "\n" + html


def insert_figures(html: str, figures: list[str]) -> str:
    """`[이미지 제안: ...]` 자리를 순서대로 그림으로 바꾼다. 남는 그림은 본문 상단에 넣는다."""
    if not figures:
        return strip_editor_notes_html(html)
    queue = list(figures)

    def repl(_match: re.Match) -> str:
        return queue.pop(0) if queue else ""

    html = IMAGE_SLOT_HTML.sub(repl, html)
    for fig in queue:
        html = insert_near_top(html, fig)
    return strip_editor_notes_html(html)


def content_has_image(html: str) -> bool:
    return bool(re.search(r"<img\b", html or "", re.I))


def generate_image(prompt: str, out_path: Path) -> Path:
    """셸의 `images` 명령으로 영어 프롬프트에서 이미지를 만든다(API 키 불필요)."""
    exe = shutil.which("images")
    if not exe:
        raise PublishError("이미지 생성 명령(images)을 찾을 수 없습니다. --image <파일>로 직접 넘겨 주세요.")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run([exe, prompt, "--out", str(out_path)],
                          capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:300]
        raise PublishError(f"이미지 생성 실패: {detail}")
    if not out_path.exists():
        raise PublishError(f"이미지 생성은 끝났는데 파일이 없습니다: {out_path}")
    return out_path


def resolve_image_specs(args) -> list[dict]:
    """--image / --image-prompt 를 순서대로 하나의 목록으로. path 또는 prompt 중 하나를 갖는다."""
    specs: list[dict] = []
    for p in args.image or []:
        specs.append({"path": Path(p), "alt": None, "caption": None})
    for prompt in args.image_prompt or []:
        specs.append({"path": None, "prompt": prompt, "alt": None, "caption": None})
    alts = list(args.image_alt or [])
    caps = list(args.image_caption or [])
    for i, spec in enumerate(specs):
        if i < len(alts) and alts[i]:
            spec["alt"] = alts[i]
        if i < len(caps) and caps[i]:
            spec["caption"] = caps[i]
    return specs


def upload_media(token: str, site: str, path: Path, *, alt: str | None = None,
                 caption: str | None = None, title: str | None = None) -> dict:
    """미디어 라이브러리에 이미지를 올리고 {id, url, ...}을 돌려준다."""
    path = Path(path)
    if not path.exists():
        raise PublishError(f"이미지 파일이 없습니다: {path}")
    if path.stat().st_size > 20 * 1024 * 1024:
        raise PublishError(f"이미지가 너무 큽니다(20MB 초과): {path}")
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    data = None
    attrs = {k: v for k, v in (("alt", alt), ("caption", caption), ("title", title)) if v}
    if attrs:
        # WP.com v1.1: media[]와 같은 순서의 attrs[] (JSON 한 칸)
        data = {"attrs[]": json.dumps(attrs, ensure_ascii=False)}
    files = {"media[]": (path.name, path.read_bytes(), mime)}
    r = request("POST", f"{API}/sites/{site}/media/new", token, data=data, files=files,
                attempts=2, timeout=120)
    check_auth_error(r, "이미지 업로드")
    items = (r.json() or {}).get("media") or []
    if not items:
        raise PublishError(f"이미지 업로드 응답에 media가 없습니다 (HTTP {r.status_code})")
    m = items[0]
    media_id = m.get("ID")
    url = m.get("URL")
    if not media_id or not url:
        raise PublishError("이미지 업로드 응답에 ID/URL이 없습니다")
    if attrs:
        # media/new 의 attrs[]는 무시되는 경우가 있어(2026-11-27 확인) 미디어 정보를 한 번 더 맞춘다.
        # 실패해도 본문·대표 이미지는 이미 정상이므로 치명적으로 다루지 않는다.
        try:
            r2 = request("POST", f"{API}/sites/{site}/media/{media_id}", token, data=attrs, attempts=2)
            if r2.status_code >= 400:
                print(f"  (경고) 미디어 정보(alt/title) 설정 실패 HTTP {r2.status_code} — 이미지 자체는 정상")
        except PublishError as e:
            print(f"  (경고) 미디어 정보 설정 실패: {e}")
    return {"id": str(media_id), "url": url, "file": str(path),
            "width": m.get("width"), "height": m.get("height")}


def attach_images(post: dict, token: str, site: str, specs: list[dict], *,
                  dry_run: bool = False, use_featured: bool = True,
                  image_dir: Path | None = None) -> dict:
    """이미지를 (필요하면 생성해) 올리고 본문 HTML에 넣는다. post를 제자리에서 고쳐 돌려준다."""
    if not specs:
        post["html"] = strip_editor_notes_html(post.get("html", ""))
        return post
    slot_texts = image_slot_texts(post.get("html", ""))
    media: list[dict] = []
    for i, spec in enumerate(specs):
        alt = spec.get("alt") or default_alt(slot_texts[i] if i < len(slot_texts) else None,
                                             post["title"], i)
        spec["alt"] = alt
        if dry_run:
            where = spec.get("path") or f"(생성 예정) {spec.get('prompt')}"
            print(f"[dry-run] 이미지 {i + 1}: {where} · alt '{alt}' — 업로드하지 않음")
            media.append({"id": None, "url": "about:blank", "file": str(spec.get("path") or "")})
            continue
        path = spec.get("path")
        if path is None:
            date_str = post.get("date") or today_kst().strftime("%Y-%m-%d")
            suffix = "" if len(specs) == 1 else f"-{i + 1}"
            path = (image_dir or DEFAULT_IMAGE_DIR) / f"blog-{date_str}-{post.get('slug') or 'post'}{suffix}.png"
            print(f"이미지 생성 중: {path.name}")
            path = generate_image(spec["prompt"], path)
            spec["path"] = path
        info = upload_media(token, site, path, alt=alt, caption=spec.get("caption"),
                            title=post["title"])
        print(f"이미지 업로드: media {info['id']} · {info['url']}")
        media.append(info)
    figures = [figure_html(m["url"], s["alt"], m.get("id"), s.get("caption"))
               for m, s in zip(media, specs)]
    post["html"] = insert_figures(post.get("html", ""), figures)
    post["images"] = media
    if use_featured and media and media[0].get("id"):
        post["featured_image"] = media[0]["id"]
    return post


# ---------------------------------------------------------------- 워드프레스

def load_token(token_file: Path | None) -> str:
    token = (os.environ.get("WORDPRESS_ACCESS_TOKEN") or "").strip()
    if token:
        return token
    path = Path(os.environ.get("WORDPRESS_TOKEN_FILE") or (token_file or DEFAULT_TOKEN_FILE))
    if not path.exists():
        raise PublishError(
            "워드프레스 토큰이 없습니다: WORDPRESS_ACCESS_TOKEN 환경변수가 비어 있고 "
            f"토큰 파일도 없습니다 ({path}).")
    data = json.loads(path.read_text(encoding="utf-8"))
    token = (data.get("access_token") or "").strip()
    if not token:
        raise PublishError(f"토큰 파일에 access_token이 없습니다: {path}")
    return token


def site_name(arg: str | None) -> str:
    return (arg or os.environ.get("WORDPRESS_SITE") or DEFAULT_SITE).strip()


def request(method: str, url: str, token: str, *, params=None, data=None, files=None,
            attempts: int = 3, timeout: int = 45):
    headers = {"Authorization": f"Bearer {token}"}
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            r = requests.request(method, url, headers=headers, params=params, data=data,
                                 files=files, timeout=timeout)
        except requests.RequestException as e:
            last = e
            if attempt < attempts:
                print(f"  네트워크 오류({e.__class__.__name__}) — {attempt}번째 시도, 잠시 뒤 재시도")
                time.sleep(3 * attempt)
                continue
            raise PublishError(f"워드프레스 연결 실패: {e.__class__.__name__}") from e
        if r.status_code in (429, 500, 502, 503, 504) and attempt < attempts:
            print(f"  HTTP {r.status_code} — {attempt}번째 시도, 잠시 뒤 재시도")
            time.sleep(3 * attempt)
            continue
        return r
    raise PublishError(f"워드프레스 요청 실패: {last}")


def check_auth_error(r, action: str) -> None:
    if r.status_code in (401, 403):
        raise PublishError(f"{action} 권한이 거부되었습니다 (HTTP {r.status_code}). "
                           "토큰 만료·권한(publish_posts, upload_files) 문제일 수 있습니다.")
    if r.status_code >= 400:
        detail = ""
        try:
            detail = json.dumps(r.json(), ensure_ascii=False)[:300]
        except ValueError:
            detail = r.text[:300]
        raise PublishError(f"{action} 실패 (HTTP {r.status_code}): {detail}")


def fetch_existing(token: str, site: str, limit_pages: int = 3) -> list[dict]:
    """사이트의 최근 글 목록(상태 무관). 중복 판단은 이 목록으로 한다."""
    posts: list[dict] = []
    for page in range(1, limit_pages + 1):
        r = request("GET", f"{API}/sites/{site}/posts/", token,
                    params={"number": 100, "page": page, "status": "any",
                            "fields": "ID,title,slug,status,date,URL,featured_image"})
        check_auth_error(r, "글 목록 조회")
        batch = r.json().get("posts") or []
        posts.extend(batch)
        if len(batch) < 100:
            break
    return posts


def fetch_post(token: str, site: str, post_id: int | str) -> dict:
    r = request("GET", f"{API}/sites/{site}/posts/{post_id}", token,
                params={"fields": "ID,title,slug,status,date,URL,content,featured_image"})
    check_auth_error(r, f"글 {post_id} 조회")
    return r.json()


def find_duplicate(posts: list[dict], post: dict) -> dict | None:
    want_slugs = {unquote(post["slug"]).strip(), slugify(post["title"])}
    want_title = norm(post["title"])
    for p in posts:
        if (p.get("status") or "") == "trash":  # 휴지통은 '올린 적 없음'으로 본다
            continue
        if unquote(str(p.get("slug") or "")) in want_slugs or norm(str(p.get("title") or "")) == want_title:
            return p
    return None


def upload(token: str, site: str, post: dict, status: str) -> dict:
    payload = {
        "title": post["title"],
        "content": post["html"],
        "slug": post["slug"],
        "status": status,
        "format": "standard",
    }
    if post["excerpt"]:
        payload["excerpt"] = post["excerpt"]
    if post["tags"]:
        payload["tags"] = post["tags"]
    if post.get("featured_image"):
        payload["featured_image"] = str(post["featured_image"])
    r = request("POST", f"{API}/sites/{site}/posts/new", token, data=payload)
    check_auth_error(r, "글 업로드")
    return r.json()


def update_post(token: str, site: str, post_id: int | str, payload: dict) -> dict:
    r = request("POST", f"{API}/sites/{site}/posts/{post_id}", token, data=payload)
    check_auth_error(r, f"글 {post_id} 수정")
    return r.json()


# ---------------------------------------------------------------- 상태 파일

def state_path(arg: str | None) -> Path:
    return Path(arg or os.environ.get("WORDPRESS_STATE_FILE") or DEFAULT_STATE_FILE)


def record_upload(path: Path, site: str, post: dict, created: dict, action: str = "publish") -> None:
    """업로드 이력(기록용). 실패해도 업로드는 이미 끝났으므로 치명적으로 다루지 않는다."""
    try:
        now = today_kst().isoformat(timespec="seconds")
        posts = {}
        if path.exists():
            try:
                old = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(old, dict) and isinstance(old.get("posts"), dict):
                    posts = old["posts"]
            except (ValueError, OSError):
                posts = {}
        posts[post.get("slug") or str(created.get("ID"))] = {
            "id": created.get("ID"),
            "title": post.get("title"),
            "status": created.get("status"),
            "url": created.get("URL"),
            "uploaded_at": now,
            "action": action,
            "source": str(post.get("path") or "").replace(str(ROOT) + "/", ""),
            "featured_image": post.get("featured_image"),
            "images": [{k: v for k, v in m.items() if k in ("id", "url", "file")}
                       for m in post.get("images") or []],
        }
        data = {"updated_at": now, "site": site, "posts": posts}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as e:
        print(f"  (경고) 업로드 이력 저장 실패: {e}")


# ---------------------------------------------------------------- 기존 글에 이미지 채우기

def patch_existing_post(token: str, site: str, post_id: int | str, specs: list[dict], *,
                        args, dry_run: bool = False) -> dict:
    """이미 올라간 글을 읽어 메모를 정리하고 이미지를 넣는다. 본문 글자는 건드리지 않는다."""
    current = fetch_post(token, site, post_id)
    post = {"title": current.get("title") or "", "slug": current.get("slug") or "",
            "date": str(current.get("date") or "")[:10],
            "html": current.get("content") or "", "path": None, "meta": {}}
    if not post["html"].strip():
        raise PublishError(f"글 {post_id} 본문이 비어 있습니다")
    if dry_run:
        print(f"[dry-run] 글 {post_id} '{post['title']}' 수정 예정 — 메모 정리 + 이미지 {len(specs)}장")
        attach_images(post, token, site, specs, dry_run=True, use_featured=False,
                      image_dir=args.image_dir)
        return current
    post = attach_images(post, token, site, specs,
                         use_featured=not args.no_featured_image, image_dir=args.image_dir)
    payload = {"content": post["html"]}
    if post.get("featured_image") and not args.no_featured_image:
        payload["featured_image"] = post["featured_image"]
    updated = update_post(token, site, post_id, payload)
    print(f"글 수정 완료: ID {post_id} · {updated.get('status')} · {updated.get('URL')}")
    return updated


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="워드프레스 블로그 자동 업로드(이미지 포함)")
    ap.add_argument("--file", type=Path, help="올릴 마크다운 파일 (생략 시 가장 최근 주 글)")
    ap.add_argument("--status", choices=["publish", "draft"], default="publish",
                    help="발행 상태 (기본 publish=공개. 사용자 선택 2026-11-27)")
    ap.add_argument("--dry-run", action="store_true", help="업로드 없이 대상·중복 여부만 확인")
    ap.add_argument("--max-age-days", type=int, default=8,
                    help="자동 선택 시 이 일수보다 오래된 글은 올리지 않는다 (기본 8)")
    ap.add_argument("--image", action="append", default=[], type=Path,
                    help="본문·대표 이미지로 쓸 이미지 파일 (여러 번 지정 가능, 순서대로 치환)")
    ap.add_argument("--featured-image", action="append", default=[], type=Path, dest="image",
                    help="--image 와 같다")
    ap.add_argument("--image-prompt", action="append", default=[],
                    help="영어 프롬프트. images 명령으로 이미지를 만들어 --image처럼 쓴다")
    ap.add_argument("--image-alt", action="append", default=[],
                    help="이미지 대체텍스트(이미지 순서대로)")
    ap.add_argument("--image-caption", action="append", default=[],
                    help="이미지 설명문(이미지 순서대로)")
    ap.add_argument("--image-dir", type=Path, help="--image-prompt로 만든 이미지를 저장할 폴더")
    ap.add_argument("--no-featured-image", action="store_true", help="대표 이미지를 설정하지 않는다")
    ap.add_argument("--update-post-id", type=int,
                    help="이미 올라간 글을 수정한다(메모 정리 + 이미지 삽입 + 대표 이미지)")
    ap.add_argument("--fill-missing-image", action="store_true",
                    help="이미 올라간 같은 글이 대표 이미지 없이 있으면 그 글에만 이미지를 채운다")
    ap.add_argument("--site", help=f"사이트 (기본 {DEFAULT_SITE})")
    ap.add_argument("--token-file", type=Path, help="토큰 파일 경로 (기본 %s)" % DEFAULT_TOKEN_FILE)
    ap.add_argument("--state-file", type=Path, help="업로드 이력 파일 (기본 %s)" % DEFAULT_STATE_FILE)
    args = ap.parse_args(argv)

    try:
        site = site_name(args.site)
        token = load_token(args.token_file)

        # (1) 이미 올라간 글을 지정해 고치는 경로
        if args.update_post_id:
            specs = resolve_image_specs(args)
            for spec in specs:
                if spec.get("path") and not Path(spec["path"]).exists():
                    raise PublishError(f"이미지 파일이 없습니다: {spec['path']}")
            updated = patch_existing_post(token, site, args.update_post_id, specs,
                                          args=args, dry_run=args.dry_run)
            if not args.dry_run:
                record_upload(state_path(args.state_file), site,
                              {"title": updated.get("title"), "slug": updated.get("slug"),
                               "path": "", "featured_image": updated.get("featured_image")},
                              updated, action="update")
            return 0

        path, why = find_latest_article(args.file, -1 if args.file else args.max_age_days)
        if path is None:
            print(f"올릴 새 글 없음: {why}")
            return 0
        post = build_post(path)
        specs = resolve_image_specs(args)
        post["html"] = markdown_to_html(strip_editor_notes(post["markdown"]))
        rel = str(path).replace(str(ROOT) + "/", "")
        print(f"대상 글: {rel}")
        print(f"제목: {post['title']}")
        print(f"슬러그: {post['slug']}  ·  본문 HTML {len(post['html']):,}자  ·  태그 {post['tags'] or '없음'}")

        existing = fetch_existing(token, site)
        dup = find_duplicate(existing, post)
        if dup:
            dup_id = dup.get("ID")
            if specs and args.fill_missing_image and not dup.get("featured_image"):
                print(f"이미 올라간 글(ID {dup_id})에 대표 이미지가 없어 이미지를 채웁니다")
                updated = patch_existing_post(token, site, dup_id, specs, args=args,
                                              dry_run=args.dry_run)
                if not args.dry_run:
                    record_upload(state_path(args.state_file), site,
                                  {"title": post["title"], "slug": post["slug"],
                                   "path": path, "featured_image": updated.get("featured_image")},
                                  updated, action="fill-image")
                return 0
            print(f"건너뜀: 이미 올린 글입니다 (ID {dup_id}, {dup.get('status')}, {dup.get('date')}) — 중복 업로드 안 함")
            if not dup.get("featured_image"):
                print(f"  (참고) 그 글에는 대표 이미지가 없습니다 — --fill-missing-image --image <파일> 로 채울 수 있습니다")
            elif specs and not args.fill_missing_image:
                print(f"  (참고) 그 글에는 이미 대표 이미지가 있습니다")
            return 0
        print(f"중복 검사: 같은 슬러그/제목 글 없음 (사이트 글 {len(existing)}개 확인)")

        if args.dry_run:
            print(f"[dry-run] 업로드하지 않음 — status={args.status}")
            attach_images(post, token, site, specs, dry_run=True, use_featured=False,
                          image_dir=args.image_dir)
            print(f"[dry-run] 본문 미리보기: {post['html'][:300]}…")
            return 0

        post = attach_images(post, token, site, specs,
                             use_featured=not args.no_featured_image, image_dir=args.image_dir)
        created = upload(token, site, post, args.status)
        post_id = created.get("ID")
        print(f"발행 완료: ID {post_id} · {created.get('status')} · {created.get('URL')}")
        print(f"편집 링크: https://wordpress.com/post/{site}/{post_id}")
        if post.get("featured_image"):
            print(f"대표 이미지: media {post['featured_image']}")
        record_upload(state_path(args.state_file), site, post, created)
        return 0
    except PublishError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
