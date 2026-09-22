import sys, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from pathlib import Path
t = Path('tuning.json')
if t.exists():
    print("tuning.json 내용:")
    print(t.read_text(encoding='utf-8'))
else:
    print("tuning.json 없음")
    # review_history 확인
    h = Path('trade_logs/review_history.jsonl')
    if h.exists():
        lines = h.read_text(encoding='utf-8').strip().split('\n')
        if lines:
            last = json.loads(lines[-1])
            print("review_history 마지막 항목:")
            print(json.dumps(last, ensure_ascii=False, indent=2))
