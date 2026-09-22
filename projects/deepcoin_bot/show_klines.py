import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
with open('C:/Users/g8428/deepcoin_bot/server.py', encoding='utf-8') as f:
    lines = f.readlines()

# Show lines 130~210 (klines + signal logic)
for i, line in enumerate(lines[128:215], start=129):
    print(f'{i}: {line}', end='')
