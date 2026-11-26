"""
생성된 블로그 초안(content/blog, research/content)을 워드프레스 블로그(earninsu.wordpress.com)에 올린다.

2026-11-27 추가. 계기: 사용자가 "자동으로 수집해서 블로그 글 쓰는 거를 올려봐"라고 요청.
워크플로(.github/workflows/claude-code-monitor.yml)는 GitHub App에 `workflows` 권한이 없어 고칠 수 없어서,
업로드는 이 스크립트를 부르는 쪽(Pickle 예약 액션 `📮 주간 블로그 글 워드프레스 발행`)이 맡는다.
Actions가 research/content/{날짜}-blog.md 로 커밋해 둔 글을 받아 그대로 올린다.

실행:
  python projects/claude-code-monitor/publish_wordpress.py                    # 가장 최근 주 글을 공개 발행
  python projects/claude-code-monitor/publish_wordpress.py --dry-run          # 업로드 없이 무엇을 올릴지·중복 여부만 확인
  python projects/claude-code-monitor/publish_wordpress.py --file <경로.md>   # 파일 지정 (날짜 제한 없음)
  python projects/claude-code-monitor/publish_wordpress.py --status draft     # 초안으로 (수동용, 기본은 publish)
  python projects/claude-code-monitor/publish_wordpress.py --max-age-days 8   # 최근 8일 글만 대상(기본 8)

토큰: 환경변수 WORDPRESS_ACCESS_TOKEN → 없으면 토큰 파일(WORDPRESS_TOKEN_FILE 또는 기본 경로).
토큰은 화면에 찍지 않는다(로그·에러 메시지 포함).

중복 방지: 업로드 전에 WordPress REST로 최근 글을 받아 같은 슬러그(또는 같은 제목)가 있으면 건너뛴다.
그래서 같은 주에 여러 번 돌아도(월요일 저녁 + 화요일 아침) 한 번만 올라간다.
research/state/... 대신 레포 밖 상태 파일에 업로드 이력을 남기는 이유: 예약 실행이 `git reset --hard`로
레포를 매번 되돌리기 때문. 상태 파일은 기록용이고, 판단은 항상 WordPress 쪽 실제 글로 한다.

의존성: requests, pyyaml, markdown (requirements.txt 참고)
"""

from __future__ import annotations

import argparse
import json
import os
import re
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
# research/content = Actions가 커밋하는 사본(발행 근거), content/blog = 생성 원본(Actions 러너에만 존재)
ARTICLE_DIRS = (ROOT / "research" / "content", ROOT / "content" / "blog")
DATE_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)\.md$")
MAX_EXCERPT = 400


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
    return {"title": title, "slug": slug, "excerpt": excerpt, "tags": tag_text,
            "markdown": body, "meta": meta, "path": path}


def markdown_to_html(text: str) -> str:
    try:
        import markdown  # requirements.txt (Actions 스텝에서는 pip install markdown)
    except ImportError as e:  # pragma: no cover
        raise PublishError("markdown 패키지가 없습니다: pip install markdown") from e
    return markdown.markdown(text, extensions=["extra", "sane_lists", "nl2br", "toc"])


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


def request(method: str, url: str, token: str, *, params=None, data=None, attempts: int = 3):
    headers = {"Authorization": f"Bearer {token}"}
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            r = requests.request(method, url, headers=headers, params=params, data=data, timeout=45)
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
                           "토큰 만료·권한(publish_posts) 문제일 수 있습니다.")
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
                            "fields": "ID,title,slug,status,date,URL"})
        check_auth_error(r, "글 목록 조회")
        batch = r.json().get("posts") or []
        posts.extend(batch)
        if len(batch) < 100:
            break
    return posts


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
    r = request("POST", f"{API}/sites/{site}/posts/new", token, data=payload)
    check_auth_error(r, "글 업로드")
    return r.json()


# ---------------------------------------------------------------- 상태 파일


def state_path(arg: str | None) -> Path:
    return Path(arg or os.environ.get("WORDPRESS_STATE_FILE") or DEFAULT_STATE_FILE)


def record_upload(path: Path, site: str, post: dict, created: dict) -> None:
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
        posts[post["slug"]] = {
            "id": created.get("ID"),
            "title": post["title"],
            "status": created.get("status"),
            "url": created.get("URL"),
            "uploaded_at": now,
            "source": str(post["path"]).replace(str(ROOT) + "/", ""),
        }
        data = {"updated_at": now, "site": site, "posts": posts}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as e:
        print(f"  (경고) 업로드 이력 저장 실패: {e}")


# ---------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="워드프레스 블로그 자동 업로드")
    ap.add_argument("--file", type=Path, help="올릴 마크다운 파일 (생략 시 가장 최근 주 글)")
    ap.add_argument("--status", choices=["publish", "draft"], default="publish",
                    help="발행 상태 (기본 publish=공개. 사용자 선택 2026-11-27)")
    ap.add_argument("--dry-run", action="store_true", help="업로드 없이 대상·중복 여부만 확인")
    ap.add_argument("--max-age-days", type=int, default=8,
                    help="자동 선택 시 이 일수보다 오래된 글은 올리지 않는다 (기본 8)")
    ap.add_argument("--site", help=f"사이트 (기본 {DEFAULT_SITE})")
    ap.add_argument("--token-file", type=Path, help="토큰 파일 경로 (기본 %s)" % DEFAULT_TOKEN_FILE)
    ap.add_argument("--state-file", type=Path, help="업로드 이력 파일 (기본 %s)" % DEFAULT_STATE_FILE)
    args = ap.parse_args(argv)

    try:
        site = site_name(args.site)
        path, why = find_latest_article(args.file, -1 if args.file else args.max_age_days)
        if path is None:
            print(f"올릴 새 글 없음: {why}")
            return 0
        post = build_post(path)
        post["html"] = markdown_to_html(post["markdown"])
        rel = str(path).replace(str(ROOT) + "/", "")
        print(f"대상 글: {rel}")
        print(f"제목: {post['title']}")
        print(f"슬러그: {post['slug']}  ·  본문 HTML {len(post['html']):,}자  ·  태그 {post['tags'] or '없음'}")

        token = load_token(args.token_file)
        existing = fetch_existing(token, site)
        dup = find_duplicate(existing, post)
        if dup:
            print(f"건너뜀: 이미 올린 글입니다 (ID {dup.get('ID')}, {dup.get('status')}, {dup.get('date')}) — 중복 업로드 안 함")
            return 0
        print(f"중복 검사: 같은 슬러그/제목 글 없음 (사이트 글 {len(existing)}개 확인)")

        if args.dry_run:
            print(f"[dry-run] 업로드하지 않음 — status={args.status}")
            print(f"[dry-run] 본문 미리보기: {post['html'][:300]}…")
            return 0

        created = upload(token, site, post, args.status)
        post_id = created.get("ID")
        print(f"발행 완료: ID {post_id} · {created.get('status')} · {created.get('URL')}")
        print(f"편집 링크: https://wordpress.com/post/{site}/{post_id}")
        record_upload(state_path(args.state_file), site, post, created)
        return 0
    except PublishError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
