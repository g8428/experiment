import sys
with open('C:/Users/g8428/deepcoin_bot/server.py', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')
print(f'Total lines: {len(lines)}')

# Find klines/candle related code
for i, line in enumerate(lines):
    if any(k in line for k in ['kline', 'candle', 'high', 'low', 'close', 'open', 'ATR', 'atr', 'ema', 'rsi', '_sig', 'signal']):
        print(f'{i+1}: {line}')
