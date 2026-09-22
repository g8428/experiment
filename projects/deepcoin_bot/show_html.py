import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
start = int(sys.argv[1])
end = int(sys.argv[2])
with open('C:/Users/g8428/deepcoin_bot/index.html', encoding='utf-8') as f:
    lines = f.readlines()
print(f'=== html lines {start}-{end} of {len(lines)} ===')
for i, line in enumerate(lines[start-1:end], start=start):
    print(f'{i}: {line}', end='')
