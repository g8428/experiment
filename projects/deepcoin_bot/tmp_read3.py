import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
with open('server.py', encoding='utf-8', errors='replace') as f:
    lines = f.readlines()
print(f"Total lines: {len(lines)}")
# Print lines 600-900 to see trading logic
for i, l in enumerate(lines[599:950], 600):
    sys.stdout.write(f"{i} {l}")
