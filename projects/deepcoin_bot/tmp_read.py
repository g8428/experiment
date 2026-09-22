with open('server.py', encoding='utf-8') as f:
    lines = f.readlines()
for i, l in enumerate(lines[:300], 1):
    print(i, l, end='')
