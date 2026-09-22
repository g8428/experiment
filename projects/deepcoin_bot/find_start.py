import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
with open('server.py', encoding='utf-8', errors='replace') as f:
    lines = f.readlines()
for i, l in enumerate(lines, 1):
    if 'claude/start' in l or ('start' in l.lower() and 'def' in l and 'claude' in l.lower()):
        print(i, l.rstrip())
    if 'do_POST' in l:
        # print surrounding 30 lines
        start = max(0, i-1)
        end = min(len(lines), i+60)
        for j in range(start, end):
            print(j+1, lines[j].rstrip())
        break
