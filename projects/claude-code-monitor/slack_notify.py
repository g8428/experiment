"""
Slack Bot Token으로 #성과보고에 결과 보고 (웹훅 대신 chat.postMessage 사용).
컨텐츠(블로그/인스타) 본문은 GitHub에 올리지 않고 요약 메시지의 스레드로 전송한다.

환경변수:
  SLACK_BOT_TOKEN   xoxb-... (필수, 없으면 스킵)
  SLACK_CHANNEL_ID  채널 ID (필수, 없으면 스킵). 봇이 해당 채널에 초대되어 있어야 함
  JOB_STATUS        success | failure | cancelled
  RUN_URL           Actions 실행 로그 URL

실행: python projects/claude-code-monitor/slack_notify.py
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
KST = timezone(timedelta(hours=9))
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
    return 0


def report(body: dict) -> int:
    if not body.get("ok"):
        # 토큰은 출력하지 않고 Slack 에러 코드만 노출 (예: channel_not_found, not_in_channel)
        print(f"Slack 전송 실패: {body.get('error')}")
        return 1
    print("Slack 전송 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
