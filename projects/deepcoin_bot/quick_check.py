import sys, json, urllib.request, urllib.error
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = 'http://localhost:5000'

def get(path):
    r = urllib.request.urlopen(BASE+path, timeout=5)
    return json.loads(r.read())

def post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(BASE+path, data=data,
          headers={'Content-Type':'application/json'}, method='POST')
    r = urllib.request.urlopen(req, timeout=5)
    return json.loads(r.read())

# 1. 봇별 config 독립 조회
mc = get('/api/momentum/config')
sc = get('/api/scalper/config')
print(f"모멘텀 cfg: lev={mc['leverage']}x  size={mc['size_pct']}  TP×{mc['tp_atr_mult']}  SL×{mc['sl_atr_mult']}")
print(f"스캘퍼 cfg: lev={sc['leverage']}x  size={sc['size_pct']}  TP×{sc['tp_atr_mult']}  SL×{sc['sl_atr_mult']}")

# 2. 봇별 config 독립 설정 — 모멘텀은 20x, 스캘퍼는 5x
r1 = post('/api/momentum/config', {'leverage':20, 'size_pct':2, 'tp_atr_mult':2.5, 'sl_atr_mult':1.0})
r2 = post('/api/scalper/config',  {'leverage':5,  'size_pct':1, 'tp_atr_mult':1.5, 'sl_atr_mult':0.8})
print(f"모멘텀 설정 후: lev={r1['config']['leverage']}x  TP×{r1['config']['tp_atr_mult']}")
print(f"스캘퍼 설정 후: lev={r2['config']['leverage']}x  TP×{r2['config']['tp_atr_mult']}")

# 3. 서로 영향 없는지 재확인
mc2 = get('/api/momentum/config')
sc2 = get('/api/scalper/config')
print(f"독립 확인 — 모멘텀: {mc2['leverage']}x / 스캘퍼: {sc2['leverage']}x  {'OK' if mc2['leverage']!=sc2['leverage'] else 'FAIL'}")

# 4. 두 봇 동시 시뮬 시작
r3 = post('/api/momentum/start', {'mode':'sim'})
r4 = post('/api/scalper/start',  {'mode':'sim'})
print(f"동시 시작: 모멘텀={r3['ok']} / 스캘퍼={r4['ok']}")

# 5. 상태 확인
ms = get('/api/momentum/status')
ss = get('/api/scalper/status')
print(f"모멘텀 실행중: {ms['running']} / 스캘퍼 실행중: {ss['running']}")

# 정리
post('/api/momentum/stop', {})
post('/api/scalper/stop', {})
print("두 봇 중지 완료")
