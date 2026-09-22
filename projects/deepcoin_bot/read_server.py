import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
with open(r'C:\Users\g8428\deepcoin_bot\index.html', 'r', encoding='utf-8', errors='replace') as f:
    lines = f.readlines()
for i, l in enumerate(lines[990:1050], 991):
    print(f'{i:4d}: {l}', end='')
