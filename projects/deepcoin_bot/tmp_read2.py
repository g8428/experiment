import sys
with open('server.py', encoding='utf-8', errors='replace') as f:
    lines = f.readlines()
print(f"Total lines: {len(lines)}")
for i, l in enumerate(lines[287:600], 288):
    print(i, l, end='')
