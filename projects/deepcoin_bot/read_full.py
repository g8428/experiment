import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
with open('C:/Users/g8428/deepcoin_bot/server.py', encoding='utf-8') as f:
    lines = f.readlines()
print(f'=== TOTAL LINES: {len(lines)} ===')
for i, line in enumerate(lines, start=1):
    print(f'{i}: {line}', end='')
