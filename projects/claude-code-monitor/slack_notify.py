"""
Slack Bot Token으로 #성과보고에 결과 보고 (웹훅 대신 chat.postMessage 사용).
컨텐츠(블로그/인스타) 본문은 GitHub에 올리지 않고 요약 메시지의 스레드로 전송한다.

환경변수:
  SLACK_BOT_TOKEN   xoxb-... (필수, 없으면 스킵)
  SLACK_CHANNEL_ID  채널 ID (필수, 없으면 스킵). 봇이 해당 채널에 초대되어 있어야 함
  JOB_STATUS        success | failure | cancelled
  RUN_URL           Actions 실행 로그 URL
  GITHUB_RUN_ID     있고 카드 PNG(cards/out)가 있으면 요약에 ig-run:<id> 표식 + 스레드에 카드 미리보기 업로드
                    (봇 스코프: chat:write, files:write)

실행: python projects/claude-code-monitor/slack_notify.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
KST = timezone(timedelta(hours=9))
CARDS_DIR = Path(__file__).parent / "cards" / "out"
MAX_LEN = 39000  # chat.postMessage 본문 상한(40,000자) 여유분


def latest(directory: Path, pattern: str) -> Path | None:
    matches = sorted(directory.glob(pattern), reverse=True)
    return matches[0] if matches else None


def post(token: str, payload: dict) -> dict:
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def main() -> int:
    token = os.environ.get("SLACK_BOT_TOKEN")
    channel = os.environ.get("SLACK_CHANNEL_ID")
    if not token or not channel:
        print("SLACK_BOT_TOKEN / SLACK_CHANNEL_ID 미설정, 보고 스킵")
        return 0

    today = datetime.now(KST).strftime("%Y-%m-%d")
    status = os.environ.get("JOB_STATUS", "success")
    run_url = os.environ.get("RUN_URL", "")

    if status != "success":
        text = f"❌ Claude Code 트렌드 모니터 실패 ({today})\n로그: {run_url}"
        body = post(token, {"channel": channel, "text": text})
        return report(body)

    blog = latest(ROOT / "content" / "blog", "*.md")
    insta = latest(ROOT / "content" / "instagram", "*.md")
    summary = (
        f"✅ Claude Code 트렌드 모니터 완료 ({today})\n"
        f"블로그: {'스레드 참고' if blog else '없음'} / 인스타: {'스레드 참고' if insta else '없음'}\n"
        f"로그: {run_url}"
    )
    pngs = sorted(CARDS_DIR.glob("[0-9][0-9].png"))
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if pngs and run_id:
        summary += f"\nig-run:{run_id}"  # ig_publish.py가 읽는 표식 (지우지 말 것)
    body = post(token, {"channel": channel, "text": summary})
    if report(body):
        return 1

    thread_ts = body["ts"]
    for label, path in (("📝 블로그 초안", blog), ("📸 인스타 초안", insta)):
        if path is None:
            continue
        content = path.read_text(encoding="utf-8")[:MAX_LEN]
        reply = post(
            token,
            {"channel": channel, "thread_ts": thread_ts, "text": f"*{label}*\n\n{content}"},
        )
        if report(reply):
            return 1

    if pngs and run_id:
        return post_card_preview(token, channel, thread_ts, pngs)
    return 0


def slack_api(token: str, method: str, **kw) -> dict:
    import requests

    r = requests.post(f"https://slack.com/api/{method}", headers={"Authorization": f"Bearer {token}"}, timeout=60, **kw)
    return r.json()


def upload_files(token: str, channel: str, thread_ts: str, pngs: list[Path]) -> int:
    """files.getUploadURLExternal -> 업로드 -> files.completeUploadExternal (스레드에 한 번에 첨부)."""
    import requests

    files = []
    for p in pngs:
        data = p.read_bytes()
        body = slack_api(token, "files.getUploadURLExternal", data={"filename": p.name, "length": len(data)})
        if not body.get("ok"):
            print(f"Slack 업로드 URL 실패: {body.get('error')}")
            return 1
        up = requests.post(body["upload_url"], data=data, timeout=120)
        if up.status_code != 200:
            print(f"Slack 파일 업로드 실패: HTTP {up.status_code}")
            return 1
        files.append({"id": body["file_id"], "title": p.name})
    done = slack_api(
        token, "files.completeUploadExternal",
        json={"files": files, "channel_id": channel, "thread_ts": thread_ts, "initial_comment": "🖼️ 인스타 카드뉴스 미리보기"},
    )
    return report(done)


def post_card_preview(token: str, channel: str, thread_ts: str, pngs: list[Path]) -> int:
    if upload_files(token, channel, thread_ts, pngs):
        return 1
    caption = ""
    card_json = CARDS_DIR / "card.json"
    if card_json.exists():
        spec = json.loads(card_json.read_text(encoding="utf-8"))
        caption = spec.get("caption", "") + "\n\n" + " ".join(spec.get("hashtags", []))
    text = (
        f"*캡션 미리보기*\n{caption[:2200]}\n\n"
        "✅ 반응을 달면 인스타에 게시합니다 (오너만 유효)"
    )
    return report(post(token, {"channel": channel, "thread_ts": thread_ts, "text": text}))


def report(body: dict) -> int:
    if not body.get("ok"):
        # 토큰은 출력하지 않고 Slack 에러 코드만 노출 (예: channel_not_found, not_in_channel)
        print(f"Slack 전송 실패: {body.get('error')}")
        return 1
    print("Slack 전송 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
