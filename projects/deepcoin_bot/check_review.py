import sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from pathlib import Path
log = Path('trade_logs/review_test.log')
if log.exists():
    print(log.read_text(encoding='utf-8', errors='replace'))
else:
    print("review_test.log 없음 - 아직 실행 중이거나 다른 곳에 저장됨")
    # 실행 중인 프로세스 확인
    import subprocess
    r = subprocess.run(['tasklist'], capture_output=True, text=True, encoding='cp949', errors='replace')
    for line in r.stdout.splitlines():
        if 'python' in line.lower():
            print(line)
