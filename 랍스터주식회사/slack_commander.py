import os
import time
import subprocess
from dotenv import load_dotenv
from slack_sdk import WebClient

# .env 로드
load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID")
CHECK_INTERVAL = 5

client = WebClient(token=SLACK_BOT_TOKEN)

def get_latest_message():
    """최신 메시지 1개 가져오기"""
    try:
        # 비공개 채널도 지원
        response = client.conversations_history(
            channel=CHANNEL_ID,
            limit=1,
            inclusive=True
        )
        if response["ok"] and response["messages"]:
            return response["messages"][0]
        else:
            print(f"API 응답: {response}")
    except Exception as e:
        print(f"에러: {e}")
    return None
def send_message(text):
    """Slack에 메시지 전송"""
    try:
        client.chat_postMessage(
            channel=CHANNEL_ID,
            text=f"[인사팀장] {text}"
        )
    except Exception as e:
        print(f"전송 에러: {e}")

def execute_command(command):
    """Claude Code 실행"""
    try:
        result = subprocess.run(
            ["claude"],
            input=command + "\n\nexit\n",
            capture_output=True,
            text=True,
            timeout=300,
            encoding='utf-8',  # 추가
            errors='replace'   # 추가
        )
        return result.stdout if result.stdout else result.stderr
    except subprocess.TimeoutExpired:
        return "타임아웃: 5분 초과"
    except Exception as e:
        return f"실행 에러: {str(e)}"

def main():
    print("Slack Commander 시작...")
    print(f"채널 #{CHANNEL_ID} 모니터링 중... ({CHECK_INTERVAL}초 간격)")
    
    # 시작 알림
    send_message("🟢 Slack Commander 시작되었습니다. [명령] 태그로 명령어를 보내주세요.")
    
    last_ts = None
    
    while True:
        msg = get_latest_message()
        
        if msg and msg.get("ts") != last_ts:
            text = msg.get("text", "")
            
            if text.startswith("[명령]"):
                last_ts = msg["ts"]
                command = text.replace("[명령]", "").strip()
                
                print(f"\n명령 수신: {command}")
                send_message(f"⚙️ 명령 실행 중...\n```{command}```")
                
                result = execute_command(command)
                
                # 결과 미리보기
                print(f"결과 (처음 200자): {result[:200]}")
                
                if len(result) > 2800:
                    result = result[:2800] + "\n...(생략)"
                
                send_message(f"✅ 실행 완료:\n```\n{result}\n```")
                print("완료")
        
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
