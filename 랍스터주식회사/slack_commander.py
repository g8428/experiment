import os
import time
import subprocess
from dotenv import load_dotenv
from slack_sdk import WebClient

# .env 로드
load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
CHECK_INTERVAL = 5

# 모니터링 대상 채널 (회사규칙.md 기준)
CHANNELS = {
    "랍스터본부": os.getenv("CHANNEL_랍스터본부", "C0AER6B3JKF"),
    "실무팀": os.getenv("CHANNEL_실무팀", "C0AEY7D2YSG"),
    "성과보고": os.getenv("CHANNEL_성과보고", "C0AFNTCB5TJ"),
    "인사팀장실": os.getenv("CHANNEL_인사팀장실", "C0AESH5HQ94"),
}

# 프로젝트 루트 경로
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

client = WebClient(token=SLACK_BOT_TOKEN)

# 처리 완료된 메시지 ts 기록 (중복 방지)
processed_ts = set()

# 채널 참여 실패 기록 (반복 시도 방지)
_join_failed = set()


def ensure_channel_joined(channel_id):
    """봇이 채널에 참여되어 있지 않으면 자동 참여"""
    if channel_id in _join_failed:
        return False
    try:
        client.conversations_join(channel=channel_id)
        print(f"  ✅ 채널 {channel_id} 참여 완료")
        return True
    except Exception as e:
        print(f"  [경고] 채널 참여 실패 ({channel_id}): {e}")
        _join_failed.add(channel_id)
        return False


def get_latest_messages(channel_id, limit=5):
    """채널에서 최근 메시지 가져오기 (not_in_channel 시 자동 참여 후 재시도)"""
    try:
        response = client.conversations_history(
            channel=channel_id,
            limit=limit,
            inclusive=True,
        )
        if response["ok"] and response["messages"]:
            return response["messages"]
    except Exception as e:
        if "not_in_channel" in str(e):
            if ensure_channel_joined(channel_id):
                try:
                    response = client.conversations_history(
                        channel=channel_id,
                        limit=limit,
                        inclusive=True,
                    )
                    if response["ok"] and response["messages"]:
                        return response["messages"]
                except Exception as retry_e:
                    print(f"  [에러] 재시도 실패: {retry_e}")
        else:
            print(f"  [에러] 메시지 조회 실패: {e}")
    return []


def is_boss_message(msg):
    """BOSS(사람) 메시지인지 판별 — bot_id가 없으면 사람"""
    if msg.get("bot_id"):
        return False
    if msg.get("subtype"):  # join, leave, topic 변경 등 시스템 메시지 제외
        return False
    return True


def send_message(channel_id, text):
    """Slack에 메시지 전송"""
    try:
        client.chat_postMessage(channel=channel_id, text=text)
    except Exception as e:
        print(f"  [에러] 전송 실패: {e}")


def spawn_agents(message_text, channel_name, channel_id):
    """BOSS 메시지 감지 시 인사팀장 + 과장1 자동 spawn"""
    prompt = f"""아래는 사장님(BOSS)이 Slack #{channel_name} 채널에 보낸 메시지입니다.

---
{message_text}
---

지시사항:
1. 먼저 '{PROJECT_DIR}/회사규칙.md'를 읽고 회사 구조와 규칙을 파악하세요.
2. 인사팀장과 과장1을 spawn하세요:
   - 인사팀장: '{PROJECT_DIR}/조직도/인사팀장.md'를 읽고 페르소나를 갖추어 활동. 사장님 메시지를 관찰하고 #인사팀장실에서만 사장님께 보고. #랍스터본부에는 글 쓰지 않음. #인사팀장실 대화 내용을 다른 채널에 공개 금지.
   - 과장1: '{PROJECT_DIR}/조직도/팀원정보/과장1-사업기획.md'를 읽고 페르소나를 갖추어 활동. 사장님 지시를 분석하고 #실무팀에서 업무를 기획/배분.
3. 과장1이 사장님 지시 내용을 판단하여 필요하면 추가 실무진을 spawn하세요:
   - 대리1: '{PROJECT_DIR}/조직도/팀원정보/대리1-기술자동화.md' (기술/자동화 필요 시)
   - 사원1: '{PROJECT_DIR}/조직도/팀원정보/사원1-시장조사.md' (리서치/분석 필요 시)
   - 사원2: '{PROJECT_DIR}/조직도/팀원정보/사원2-개발테스트.md' (개발/테스트 필요 시)
4. 각 에이전트는 Slack MCP 도구를 사용하여 해당 채널에 메시지를 작성하세요.
5. 실무 결과는 #성과보고 채널에, 최종 결재는 #랍스터본부에 올리세요.
"""

    print(f"  → claude CLI 호출 중... (인사팀장 + 과장1 spawn)")

    try:
        process = subprocess.Popen(
            ["claude", "--print", "-p", prompt],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=PROJECT_DIR,
        )

        # 비동기로 실행 — 결과를 기다리지 않음
        print(f"  → 에이전트 프로세스 시작됨 (PID: {process.pid})")
        return process

    except Exception as e:
        print(f"  [에러] claude CLI 실행 실패: {e}")
        return None


def monitor_channels():
    """모든 채널을 순회하며 BOSS 메시지 감지"""
    new_messages = []

    for channel_name, channel_id in CHANNELS.items():
        messages = get_latest_messages(channel_id, limit=3)

        for msg in messages:
            ts = msg.get("ts", "")

            # 이미 처리한 메시지 스킵
            if ts in processed_ts:
                continue

            # BOSS 메시지인지 확인
            if is_boss_message(msg):
                new_messages.append((channel_name, channel_id, msg))

    return new_messages


def main():
    print("=" * 50)
    print("랍스터 주식회사 — Slack Auto Commander")
    print("=" * 50)
    print(f"모니터링 채널: {', '.join(f'#{name}' for name in CHANNELS)}")
    print(f"폴링 간격: {CHECK_INTERVAL}초")
    print("BOSS 메시지 감지 시 자동으로 인사팀장 + 과장1 spawn")
    print("-" * 50)

    # 시작 알림 (#인사팀장실에 전송)
    hr_channel = CHANNELS.get("인사팀장실")
    if hr_channel:
        send_message(
            hr_channel,
            "🟢 Slack Auto Commander 시작됨\n"
            "모든 채널에서 사장님 메시지를 감지합니다.\n"
            "사장님이 메시지를 보내면 인사팀장 + 과장1이 자동 spawn됩니다.",
        )

    # 시작 시점의 기존 메시지는 무시 (초기 ts 수집)
    print("\n기존 메시지 스캔 중 (초기화)...")
    for channel_name, channel_id in CHANNELS.items():
        messages = get_latest_messages(channel_id, limit=10)
        for msg in messages:
            processed_ts.add(msg.get("ts", ""))
        print(f"  #{channel_name}: {len(messages)}개 메시지 기록됨")

    print(f"\n총 {len(processed_ts)}개 기존 메시지 무시 처리 완료")
    print("=" * 50)
    print("대기 중... (BOSS 메시지를 기다리는 중)\n")

    # 실행 중인 에이전트 프로세스 추적
    active_processes = []

    while True:
        new_messages = monitor_channels()

        for channel_name, channel_id, msg in new_messages:
            ts = msg.get("ts", "")
            text = msg.get("text", "")

            print(f"\n{'='*50}")
            print(f"🔔 BOSS 메시지 감지!")
            print(f"  채널: #{channel_name}")
            print(f"  내용: {text[:100]}{'...' if len(text) > 100 else ''}")
            print(f"  ts: {ts}")

            # 중복 방지 등록
            processed_ts.add(ts)

            # 에이전트 spawn
            process = spawn_agents(text, channel_name, channel_id)
            if process:
                active_processes.append(process)

        # 완료된 프로세스 정리
        still_active = []
        for proc in active_processes:
            ret = proc.poll()
            if ret is None:
                still_active.append(proc)
            else:
                print(f"  ✅ 에이전트 프로세스 완료 (PID: {proc.pid}, 코드: {ret})")
        active_processes = still_active

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
