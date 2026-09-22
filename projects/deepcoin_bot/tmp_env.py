import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
with open('.env', encoding='utf-8', errors='replace') as f:
    for l in f:
        k = l.split('=')[0].strip()
        if k:
            print(k)
