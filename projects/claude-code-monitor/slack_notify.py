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


def load_top() -> dict:
    """monitor.py가 남긴 핵심 3줄·수집 실패 목록. 없거나 깨져도 보고는 계속한다."""
    try:
        return json.loads((ROOT / "research" / "state" / "latest-top.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


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

    blog = latest(ROOT / "content" / "blog", f"{today}-*.md")  # 오늘 만든 글만 (없으면 '없음')
    insta = latest(ROOT / "content" / "instagram", f"{today}-*.md")
    skip = ROOT / "content" / f"{today}-skip.txt"  # generate_content.py가 글감 없음(SKIP)으로 판단한 경우
    top = load_top()
    lines = [f"✅ Claude Code 소식 모니터 완료 ({today})"]
    if top.get("headline"):
        lines += ["*오늘의 핵심 3줄*"] + [f"{i}. {h}" for i, h in enumerate(top["headline"], 1)]
    else:
        lines.append("이번 주 글감급 소식 없음")
    if top.get("release_summary"):
        lines.append(top["release_summary"])
    if top.get("failures"):
        lines.append("⚠️ 수집 실패: " + ", ".join(f["label"] for f in top["failures"]) + " (리포트에 누락 가능)")
    if top.get("watchlist_warnings"):
        lines.append("⚠️ 감시 키워드 반응 있음·리포트 미반영: " + ", ".join(top["watchlist_warnings"]))
    if skip.exists():
        lines.append(f"이번 주는 글감 없음({skip.read_text(encoding='utf-8').strip()})")
    else:
        lines.append(f"블로그: {'스레드 참고' if blog else '없음'} / 인스타: {'스레드 참고' if insta else '없음'}")
    lines.append(f"로그: {run_url}")
    summary = "\n".join(lines)
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
