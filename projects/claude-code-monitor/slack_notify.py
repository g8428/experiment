"""
Slack Bot Token으로 #성과보고에 결과 보고 (웹훅 대신 chat.postMessage 사용).

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


def first_match(directory: Path, pattern: str) -> str:
    matches = sorted(directory.glob(pattern), reverse=True)
    return str(matches[0].relative_to(ROOT)).replace("\\", "/") if matches else "없음"


def build_message(status: str, run_url: str, repo: str, branch: str) -> str:
    today = datetime.now(KST).strftime("%Y-%m-%d")
    if status != "success":
        return f"❌ Claude Code 트렌드 모니터 실패 ({today})\n로그: {run_url}"

    def link(path: str) -> str:
        if path == "없음" or not repo:
            return path
        return f"<https://github.com/{repo}/blob/{branch}/{path}|{path}>"

    blog = first_match(ROOT / "content" / "blog", "*.md")
    insta = first_match(ROOT / "content" / "instagram", "*.md")
    trend = first_match(ROOT / "research", "claude-code-trends-*.md")
    return (
        f"✅ Claude Code 트렌드 모니터 완료 ({today})\n"
        f"블로그: {link(blog)}\n인스타: {link(insta)}\n트렌드: {link(trend)}\n"
        f"로그: {run_url}"
    )


def main() -> int:
    token = os.environ.get("SLACK_BOT_TOKEN")
    channel = os.environ.get("SLACK_CHANNEL_ID")
    if not token or not channel:
        print("SLACK_BOT_TOKEN / SLACK_CHANNEL_ID 미설정, 보고 스킵")
        return 0

    text = build_message(
        os.environ.get("JOB_STATUS", "success"),
        os.environ.get("RUN_URL", ""),
        os.environ.get("GITHUB_REPOSITORY", ""),
        os.environ.get("GITHUB_REF_NAME", "master"),
    )
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps({"channel": channel, "text": text}).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)

    if not body.get("ok"):
        # 토큰은 출력하지 않고 Slack 에러 코드만 노출 (예: channel_not_found, not_in_channel)
        print(f"Slack 전송 실패: {body.get('error')}")
        return 1
    print("Slack 전송 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
