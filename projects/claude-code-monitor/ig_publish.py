"""Slack 승인(오너 ✅) 확인 후 Instagram 캐러셀 게시.

흐름:
  1) conversations.history 로 최근 7일 내 `ig-run:<id>` 표식이 있는 봇 메시지 중 최신 선택
  2) reactions.get 으로 white_check_mark 에 SLACK_OWNER_USER_ID 가 있는지 확인 (없으면 조용히 종료)
  3) conversations.replies 로 "인스타 게시 완료" 표식이 이미 있으면 종료 (중복 게시 방지)
  4) 승인 후에만: PNG -> JPEG 변환 -> ig-media 브랜치 커밋·푸시 -> raw URL 검증 -> Graph API 게시
  5) 스레드에 결과 회신

사용:
  python ig_publish.py --check                    # Slack만 확인, GITHUB_OUTPUT 에 approved/run_id 기록
  python ig_publish.py --cards-dir DIR [--dry-run]  # 전체 흐름 (dry-run: 게시·푸시·회신 없이 계획만 출력)

환경변수:
  SLACK_BOT_TOKEN, SLACK_CHANNEL_ID, SLACK_OWNER_USER_ID   (필수)
  IG_ACCESS_TOKEN, IG_USER_ID                              (게시 시 필수)
  GITHUB_REPOSITORY (owner/repo), RUN_URL(선택), IG_GRAPH_VERSION(기본 v21.0)
토큰은 요청 파라미터로만 전달하며 출력·로그에 남기지 않는다(오류 문자열은 마스킹).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from cards import schema  # noqa: E402

KST = timezone(timedelta(hours=9))
DONE_MARK = "인스타 게시 완료"
FAIL_MARK = "인스타 게시 실패"
MAX_FAILS = 3  # 같은 스레드에서 실패 회신이 이만큼 쌓이면 더 시도하지 않는다
RUN_RE = re.compile(r"ig-run:(\d+)")
SLACK = "https://slack.com/api"

SECRET_ENVS = ("IG_ACCESS_TOKEN", "SLACK_BOT_TOKEN", "OPENAI_API_KEY", "GITHUB_TOKEN")


def mask(text: str) -> str:
    """환경변수 속 비밀값과 토큰처럼 보이는 문자열을 가린다."""
    text = str(text)
    for name in SECRET_ENVS:
        v = os.environ.get(name)
        if v:
            text = text.replace(v, "***")
    text = re.sub(r"(access_token=)[^&\s\"']+", r"\1***", text)
    text = re.sub(r"\b(EAA[A-Za-z0-9]{10,}|xox[a-z]-[A-Za-z0-9-]{10,})", "***", text)
    return text


class GraphError(RuntimeError):
    def __init__(self, message: str, code=None):
        super().__init__(mask(message))
        self.code = code


# ---------------------------------------------------------------- Slack

def slack_get(token: str, method: str, **params) -> dict:
    r = requests.get(f"{SLACK}/{method}", headers={"Authorization": f"Bearer {token}"}, params=params, timeout=30)
    body = r.json()
    if not body.get("ok"):
        raise RuntimeError(f"Slack {method} 실패: {body.get('error')}")
    return body


def slack_post(token: str, channel: str, thread_ts: str, text: str) -> None:
    r = requests.post(
        f"{SLACK}/chat.postMessage",
        headers={"Authorization": f"Bearer {token}"},
        json={"channel": channel, "thread_ts": thread_ts, "text": text},
        timeout=30,
    )
    body = r.json()
    if not body.get("ok"):
        print(f"Slack 회신 실패: {body.get('error')}")


def find_latest_run_message(messages: list[dict]):
    """봇 메시지 중 ig-run 표식이 있는 가장 최근 것 -> (message, run_id) 또는 None."""
    best = None
    for m in messages:
        if not (m.get("bot_id") or m.get("subtype") == "bot_message"):
            continue
        mt = RUN_RE.search(m.get("text") or "")
        if mt and (best is None or float(m["ts"]) > float(best[0]["ts"])):
            best = (m, mt.group(1))
    return best


def is_approved(reactions: list[dict] | None, owner_id: str) -> bool:
    return any(r.get("name") == "white_check_mark" and owner_id in (r.get("users") or []) for r in reactions or [])


def already_published(replies: list[dict]) -> bool:
    return any(DONE_MARK in (m.get("text") or "") for m in replies)


def fail_count(replies: list[dict]) -> int:
    return sum(1 for m in replies if FAIL_MARK in (m.get("text") or ""))


def check_approval(token: str, channel: str, owner_id: str, now: float | None = None) -> dict:
    """{'status': 'none|not_approved|published|too_many_failures|approved', 'run_id', 'ts', 'date'}"""
    now = now or time.time()
    hist = slack_get(token, "conversations.history", channel=channel, oldest=str(now - 7 * 86400), limit=200)
    found = find_latest_run_message(hist.get("messages", []))
    if not found:
        return {"status": "none"}
    msg, run_id = found
    info = {"run_id": run_id, "ts": msg["ts"], "date": datetime.fromtimestamp(float(msg["ts"]), KST).strftime("%Y-%m-%d")}
    rx = slack_get(token, "reactions.get", channel=channel, timestamp=msg["ts"], full="true")
    if not is_approved((rx.get("message") or {}).get("reactions"), owner_id):
        return {"status": "not_approved", **info}
    replies = slack_get(token, "conversations.replies", channel=channel, ts=msg["ts"], limit=200).get("messages", [])
    if already_published(replies):
        return {"status": "published", **info}
    if fail_count(replies) >= MAX_FAILS:
        return {"status": "too_many_failures", **info}
    return {"status": "approved", **info}


# ---------------------------------------------------------------- 미디어 브랜치

def run(cmd: list[str], cwd: str | None = None) -> str:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(mask(f"{' '.join(cmd[:3])} 실패: {p.stderr.strip()[:300]}"))
    return p.stdout


def to_jpeg_bytes(png_path: Path) -> bytes:
    """Instagram Graph API는 JPEG만 공식 지원 -> 업로드용 JPEG로 변환."""
    from PIL import Image

    buf = io.BytesIO()
    Image.open(png_path).convert("RGB").save(buf, "JPEG", quality=92)
    return buf.getvalue()


def publish_media_branch(pngs: list[Path], date: str, repo: str) -> list[str]:
    """ig-media(orphan) 브랜치에 <date>/NN.jpg 커밋·푸시하고 raw URL 목록 반환."""
    run(["git", "fetch", "origin", "ig-media"]) if _remote_branch_exists() else None
    tmp = tempfile.mkdtemp(prefix="ig-media-")
    wt = str(Path(tmp) / "wt")
    if _remote_branch_exists():
        run(["git", "worktree", "add", "-B", "ig-media", wt, "origin/ig-media"])
    else:
        run(["git", "worktree", "add", "--detach", wt])
        run(["git", "checkout", "--orphan", "ig-media"], cwd=wt)
        run(["git", "rm", "-rf", "--quiet", "."], cwd=wt)
    out = Path(wt) / date
    out.mkdir(parents=True, exist_ok=True)
    urls = []
    for p in pngs:
        name = p.stem + ".jpg"
        (out / name).write_bytes(to_jpeg_bytes(p))
        urls.append(f"https://raw.githubusercontent.com/{repo}/ig-media/{date}/{name}")
    run(["git", "add", date], cwd=wt)
    run(["git", "-c", "user.name=github-actions[bot]", "-c", "user.email=github-actions[bot]@users.noreply.github.com",
         "commit", "-m", f"ig-media: {date} 카드 {len(pngs)}장"], cwd=wt)
    run(["git", "push", "origin", "ig-media"], cwd=wt)
    return urls


def _remote_branch_exists() -> bool:
    p = subprocess.run(["git", "ls-remote", "--exit-code", "--heads", "origin", "ig-media"], capture_output=True)
    return p.returncode == 0


def wait_url_ready(url: str, tries: int = 12, delay: float = 5.0) -> None:
    for _ in range(tries):
        try:
            r = requests.get(url, timeout=20)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
                return
        except requests.RequestException:
            pass
        time.sleep(delay)
    raise RuntimeError(f"이미지 URL이 준비되지 않음: {url}")


# ---------------------------------------------------------------- Instagram Graph

class Graph:
    def __init__(self, token: str, ig_user_id: str, version: str | None = None):
        self.token = token
        self.uid = ig_user_id
        self.base = f"https://graph.facebook.com/{version or os.environ.get('IG_GRAPH_VERSION') or 'v21.0'}"

    def _handle(self, r) -> dict:
        try:
            body = r.json()
        except Exception:
            raise GraphError(f"Graph 응답 파싱 실패 HTTP {r.status_code}")
        if r.status_code >= 400 or "error" in body:
            e = body.get("error", {})
            raise GraphError(e.get("message", f"HTTP {r.status_code}"), e.get("code"))
        return body

    def post(self, path: str, **params) -> dict:
        return self._handle(requests.post(f"{self.base}/{path}", data={**params, "access_token": self.token}, timeout=60))

    def get(self, path: str, **params) -> dict:
        return self._handle(requests.get(f"{self.base}/{path}", params={**params, "access_token": self.token}, timeout=60))

    def wait_finished(self, container_id: str, tries: int = 60, delay: float = 5.0) -> None:
        for _ in range(tries):
            code = self.get(container_id, fields="status_code").get("status_code")
            if code == "FINISHED":
                return
            if code in ("ERROR", "EXPIRED"):
                raise GraphError(f"컨테이너 {container_id} 상태 {code}")
            time.sleep(delay)
        raise GraphError(f"컨테이너 {container_id} 처리 시간 초과")

    def publish(self, image_urls: list[str], caption: str) -> str:
        """이미지 1장이면 단일 게시, 2장 이상이면 캐러셀. permalink 반환."""
        if len(image_urls) == 1:
            cid = self.post(f"{self.uid}/media", image_url=image_urls[0], caption=caption)["id"]
            self.wait_finished(cid)
        else:
            children = []
            for u in image_urls:
                children.append(self.post(f"{self.uid}/media", image_url=u, is_carousel_item="true")["id"])
            for c in children:
                self.wait_finished(c)
            cid = self.post(f"{self.uid}/media", media_type="CAROUSEL", children=",".join(children), caption=caption)["id"]
            self.wait_finished(cid)
        media_id = self.post(f"{self.uid}/media_publish", creation_id=cid)["id"]
        return self.get(media_id, fields="permalink")["permalink"]


# ---------------------------------------------------------------- main

def require_env(names: list[str]) -> list[str]:
    return [n for n in names if not os.environ.get(n)]


def write_output(**kv) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")


def load_cards(cards_dir: Path):
    pngs = sorted(p for p in cards_dir.rglob("*.png") if re.fullmatch(r"\d{2}", p.stem))[:schema.MAX_CARDS]
    cj = next(iter(cards_dir.rglob("card.json")), None)
    if not pngs or not cj:
        raise RuntimeError(f"{cards_dir} 에 NN.png / card.json 이 없습니다")
    spec = json.loads(cj.read_text(encoding="utf-8"))
    return pngs, schema.full_caption(spec)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="승인 여부만 확인하고 GITHUB_OUTPUT 기록")
    ap.add_argument("--dry-run", action="store_true", help="게시·푸시·회신 없이 계획만 출력")
    ap.add_argument("--cards-dir", help="ig-cards 아티팩트를 풀어놓은 디렉터리")
    a = ap.parse_args(argv)

    need = ["SLACK_BOT_TOKEN", "SLACK_CHANNEL_ID", "SLACK_OWNER_USER_ID"]
    if not a.check:
        need += ["IG_ACCESS_TOKEN", "IG_USER_ID", "GITHUB_REPOSITORY"]
    missing = require_env(need)
    if missing:
        print("필요한 환경변수가 없습니다: " + ", ".join(missing))
        return 2

    token, channel = os.environ["SLACK_BOT_TOKEN"], os.environ["SLACK_CHANNEL_ID"]
    try:
        st = check_approval(token, channel, os.environ["SLACK_OWNER_USER_ID"])
    except Exception as e:
        print(mask(f"승인 확인 실패: {e}"))
        return 1
    print(f"승인 상태: {st['status']}" + (f" (run {st['run_id']})" if "run_id" in st else ""))
    approved = st["status"] == "approved"
    write_output(approved=str(approved).lower(), run_id=st.get("run_id", ""))
    if not approved or a.check:
        return 0

    if not a.cards_dir:
        print("--cards-dir 가 필요합니다")
        return 2
    run_url = os.environ.get("RUN_URL", "")
    try:
        pngs, caption = load_cards(Path(a.cards_dir))
        repo = os.environ["GITHUB_REPOSITORY"]
        urls = [f"https://raw.githubusercontent.com/{repo}/ig-media/{st['date']}/{p.stem}.jpg" for p in pngs]
        if a.dry_run:
            print(f"[dry-run] ig-media 브랜치에 {st['date']}/ 아래 JPEG {len(pngs)}장 커밋·푸시")
            for u in urls:
                print(f"[dry-run]   {u}")
            print(f"[dry-run] Graph {'캐러셀' if len(pngs) > 1 else '단일'} 게시, 캡션 {len(caption)}자")
            print(f"[dry-run] 스레드 {st['ts']} 에 결과 회신")
            return 0
        urls = publish_media_branch(pngs, st["date"], repo)
        for u in urls:
            wait_url_ready(u)
        permalink = Graph(os.environ["IG_ACCESS_TOKEN"], os.environ["IG_USER_ID"]).publish(urls, caption)
    except Exception as e:
        detail = mask(str(e))
        code = f" / code {e.code}" if isinstance(e, GraphError) and e.code is not None else ""
        print(f"인스타 게시 실패: {detail}{code}")
        slack_post(token, channel, st["ts"], f"❌ {FAIL_MARK}: {detail}{code}\n로그: {run_url}")
        return 1
    print(f"게시 완료: {permalink}")
    slack_post(token, channel, st["ts"], f"✅ {DONE_MARK}: {permalink}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
