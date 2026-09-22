"""
index.html 패치: BB 스캘퍼 → MTF FVG 스캘퍼 대시보드 업데이트
"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

with open(r'C:\Users\g8428\deepcoin_bot\index.html', 'r', encoding='utf-8') as f:
    src = f.read()

# ── 1. 타이틀 업데이트 ─────────────────────────────────────────────────────
src = src.replace(
    '<title>Deepcoin Bot v3</title>',
    '<title>Deepcoin Bot v4</title>'
)
print("[1] 타이틀 업데이트 OK")

# ── 2. 스캘퍼 카드 헤더 + 설명 교체 ───────────────────────────────────────
OLD_CARD_HEADER = '''    <!-- BB 스캘퍼 봇 -->
    <div class="card">
      <h2>BB 스캘퍼 봇 <span style="font-size:10px;color:var(--mt)">볼린저밴드 평균회귀 + Claude 레벨</span></h2>'''
NEW_CARD_HEADER = '''    <!-- MTF FVG 스캘퍼 봇 -->
    <div class="card">
      <h2>MTF FVG 스캘퍼 <span style="font-size:10px;color:var(--mt)">1h 트렌드 → 15m FVG → 1m 진입</span></h2>'''
assert OLD_CARD_HEADER in src, "ERROR: 스캘퍼 카드 헤더를 못 찾음"
src = src.replace(OLD_CARD_HEADER, NEW_CARD_HEADER, 1)
print("[2] 스캘퍼 카드 헤더 OK")

# ── 3. 스캘퍼 카드 설명 텍스트 교체 ──────────────────────────────────────
OLD_DESC = '        진입존 ±50% 여유 적용 · Claude TP/SL 우선 사용'
NEW_DESC = '        쿨다운 15분 · ATR TP/SL · 미체결 FVG에 가격 진입 시 1m 타이밍 확인'
assert OLD_DESC in src, "ERROR: 스캘퍼 설명 텍스트를 못 찾음"
src = src.replace(OLD_DESC, NEW_DESC, 1)
print("[3] 스캘퍼 설명 텍스트 OK")

# ── 4. FVG 패널 HTML — tp-sl-info div 다음에 삽입 ──────────────────────────
OLD_TP_SL_INFO = '      <div id="s-tp-sl-info" style="margin-top:4px;font-size:11px;color:var(--mt);display:none"></div>'
NEW_TP_SL_INFO = '''      <div id="s-tp-sl-info" style="margin-top:4px;font-size:11px;color:var(--mt);display:none"></div>
      <!-- MTF FVG 패널 -->
      <div id="s-fvg-panel" style="margin-top:10px;display:none">
        <div style="font-size:10px;color:var(--mt);font-weight:600;text-transform:uppercase;
             letter-spacing:.5px;margin-bottom:6px">FVG 상태 (15분봉 기준)</div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-bottom:8px">
          <div style="background:var(--bg);border:1px solid var(--bd);border-radius:6px;padding:8px;text-align:center">
            <div id="s-fvg-trend" style="font-size:14px;font-weight:700">—</div>
            <div style="font-size:10px;color:var(--mt);margin-top:2px">1h 트렌드</div>
          </div>
          <div style="background:var(--bg);border:1px solid var(--bd);border-radius:6px;padding:8px;text-align:center">
            <div id="s-fvg-bull-cnt" style="font-size:14px;font-weight:700;color:var(--gr)">0</div>
            <div style="font-size:10px;color:var(--mt);margin-top:2px">미체결 롱FVG</div>
          </div>
          <div style="background:var(--bg);border:1px solid var(--bd);border-radius:6px;padding:8px;text-align:center">
            <div id="s-fvg-bear-cnt" style="font-size:14px;font-weight:700;color:var(--rd)">0</div>
            <div style="font-size:10px;color:var(--mt);margin-top:2px">미체결 숏FVG</div>
          </div>
        </div>
        <div id="s-fvg-list" style="font-size:11px;background:var(--bg);border:1px solid var(--bd);
             border-radius:6px;padding:8px;max-height:80px;overflow-y:auto;line-height:1.6"></div>
      </div>'''
assert OLD_TP_SL_INFO in src, "ERROR: tp-sl-info div를 못 찾음"
src = src.replace(OLD_TP_SL_INFO, NEW_TP_SL_INFO, 1)
print("[4] FVG 패널 HTML 삽입 OK")

# ── 5. updateScalp() JS 함수 교체 ─────────────────────────────────────────
OLD_UPDATE_SCALP = '''// ── 스캘퍼 상태 업데이트 ────────────────────────────────────────
function updateScalp(d) {
  const run = d.running, pnl = d.pnl || 0;
  const pnlEl = document.getElementById('s-pnl');
  pnlEl.textContent = (pnl>=0?'+':'')+fmt(pnl,2)+'%';
  pnlEl.style.color = pnlColor(pnl);
  let sub = `거래 ${d.trades||0}회 | `;
  sub += d.position ? `${d.position.toUpperCase()} @ $${fmt(d.entry||0,0)}` : '포지션 없음';
  document.getElementById('s-trades').textContent = sub;
  document.getElementById('s-dot').className = 'dot '+(run?'dot-c':'dot-m');
  document.getElementById('s-st').textContent = run
    ? `${d.mode==='sim'?'[시뮬]':'[실제]'} 실행 중 — $${fmt(d.price||0,0)}` : '미실행';
  const badge = document.getElementById('scalp-mode-badge');
  badge.textContent = run ? (d.mode==='sim'?'스캘퍼 시뮬':'스캘퍼 실제') : '스캘퍼 -';
  badge.className = 'badge '+(run?(d.mode==='sim'?'bc':'bp'):'bm');
  const sm = document.getElementById('s-stop-msg');
  if (d.stop_msg) { sm.textContent='🚫 '+d.stop_msg; sm.style.display='block'; }
  else sm.style.display='none';
  const wm = document.getElementById('s-watch-msg');
  if (run && !d.position && d.watch_msg) { wm.textContent='👁 '+d.watch_msg; wm.style.display='block'; }
  else wm.style.display='none';
  const ti = document.getElementById('s-tp-sl-info');
  if (run && d.position && (d.tp_px || d.sl_px)) {
    ti.textContent = `TP: $${fmt(d.tp_px||0,0)}  |  SL: $${fmt(d.sl_px||0,0)}`;
    ti.style.display='block';
  } else ti.style.display='none';
}'''

NEW_UPDATE_SCALP = '''// ── 스캘퍼 상태 업데이트 ────────────────────────────────────────
function updateScalp(d) {
  const run = d.running, pnl = d.pnl || 0;
  const pnlEl = document.getElementById('s-pnl');
  pnlEl.textContent = (pnl>=0?'+':'')+fmt(pnl,2)+'%';
  pnlEl.style.color = pnlColor(pnl);
  let sub = `거래 ${d.trades||0}회 | `;
  sub += d.position ? `${d.position.toUpperCase()} @ $${fmt(d.entry||0,0)}` : '포지션 없음';
  document.getElementById('s-trades').textContent = sub;
  document.getElementById('s-dot').className = 'dot '+(run?'dot-c':'dot-m');
  document.getElementById('s-st').textContent = run
    ? `${d.mode==='sim'?'[시뮬]':'[실제]'} 실행 중 — $${fmt(d.price||0,0)}` : '미실행';
  const badge = document.getElementById('scalp-mode-badge');
  badge.textContent = run ? (d.mode==='sim'?'FVG 시뮬':'FVG 실제') : '스캘퍼 -';
  badge.className = 'badge '+(run?(d.mode==='sim'?'bc':'bp'):'bm');
  const sm = document.getElementById('s-stop-msg');
  if (d.stop_msg) { sm.textContent='🚫 '+d.stop_msg; sm.style.display='block'; }
  else sm.style.display='none';
  const wm = document.getElementById('s-watch-msg');
  if (run && !d.position && d.watch_msg) { wm.textContent='👁 '+d.watch_msg; wm.style.display='block'; }
  else wm.style.display='none';
  const ti = document.getElementById('s-tp-sl-info');
  if (run && d.position && (d.tp_px || d.sl_px)) {
    ti.textContent = `TP: $${fmt(d.tp_px||0,0)}  |  SL: $${fmt(d.sl_px||0,0)}`;
    ti.style.display='block';
  } else ti.style.display='none';
  // FVG 패널
  const panel = document.getElementById('s-fvg-panel');
  if (run) {
    panel.style.display = 'block';
    const t1h = d.trend_1h;
    const tEl = document.getElementById('s-fvg-trend');
    if (t1h === 'bull')    { tEl.textContent='▲ 상승'; tEl.style.color='var(--gr)'; }
    else if (t1h === 'bear') { tEl.textContent='▼ 하락'; tEl.style.color='var(--rd)'; }
    else                   { tEl.textContent='— 중립'; tEl.style.color='var(--mt)'; }
    document.getElementById('s-fvg-bull-cnt').textContent = d.fvg_bull || 0;
    document.getElementById('s-fvg-bear-cnt').textContent = d.fvg_bear || 0;
    const listEl = document.getElementById('s-fvg-list');
    const fvgs = d.fvg_active || [];
    if (fvgs.length === 0) {
      listEl.innerHTML = '<span style="color:var(--mt)">탐지된 FVG 없음</span>';
    } else {
      listEl.innerHTML = fvgs.slice().reverse().map(fg => {
        const col = fg.type === 'bull' ? 'var(--gr)' : 'var(--rd)';
        const lbl = fg.type === 'bull' ? '롱' : '숏';
        const sta = fg.filled
          ? '<span style="color:var(--mt)">[체결됨]</span>'
          : '<span style="color:var(--cy)">[미체결]</span>';
        return `<span style="color:${col}">${lbl}FVG</span> `
          + `$${fmt(fg.low,0)}~$${fmt(fg.high,0)} ${sta}`;
      }).join('<br>');
    }
  } else {
    panel.style.display = 'none';
  }
}'''
assert OLD_UPDATE_SCALP in src, "ERROR: updateScalp() 함수를 못 찾음"
src = src.replace(OLD_UPDATE_SCALP, NEW_UPDATE_SCALP, 1)
print("[5] updateScalp() JS 함수 교체 OK")

# ── 6. poll()에 /api/fvg 추가 ─────────────────────────────────────────────
OLD_POLL = '''  try {
    const [st, ms, sc, cb, tk, lg, dy, bl, ps, score] = await Promise.all([
      fetch('/api/status').then(r=>r.json()),
      fetch('/api/momentum/status').then(r=>r.json()),
      fetch('/api/scalper/status').then(r=>r.json()),
      fetch('/api/claude/status').then(r=>r.json()),
      fetch('/api/ticker').then(r=>r.json()),
      fetch('/api/logs?n=60').then(r=>r.json()),
      fetch('/api/daily').then(r=>r.json()),
      fetch('/api/balance').then(r=>r.json()).catch(()=>({ok:false})),
      fetch('/api/positions').then(r=>r.json()).catch(()=>({ok:false,positions:[]})),
      fetch('/api/score').then(r=>r.json()).catch(()=>({}))
    ]);'''
NEW_POLL = '''  try {
    const [st, ms, sc, cb, tk, lg, dy, bl, ps, score, fvg] = await Promise.all([
      fetch('/api/status').then(r=>r.json()),
      fetch('/api/momentum/status').then(r=>r.json()),
      fetch('/api/scalper/status').then(r=>r.json()),
      fetch('/api/claude/status').then(r=>r.json()),
      fetch('/api/ticker').then(r=>r.json()),
      fetch('/api/logs?n=60').then(r=>r.json()),
      fetch('/api/daily').then(r=>r.json()),
      fetch('/api/balance').then(r=>r.json()).catch(()=>({ok:false})),
      fetch('/api/positions').then(r=>r.json()).catch(()=>({ok:false,positions:[]})),
      fetch('/api/score').then(r=>r.json()).catch(()=>({})),
      fetch('/api/fvg').then(r=>r.json()).catch(()=>({}))
    ]);'''
assert OLD_POLL in src, "ERROR: poll() 시작 블록을 못 찾음"
src = src.replace(OLD_POLL, NEW_POLL, 1)
print("[6] poll() /api/fvg 추가 OK")

# ── 7. updateScalp() 호출 시 FVG 데이터 머지해서 전달 ────────────────────
OLD_UPDATE_CALL = '    updateClaude(cb); updateMom(ms); updateScalp(sc);'
NEW_UPDATE_CALL = '''    // FVG 데이터를 scalper 상태에 머지해서 전달
    const scWithFvg = Object.assign({}, sc, {
      fvg_bull: fvg.unfilled_bull || sc.fvg_bull || 0,
      fvg_bear: fvg.unfilled_bear || sc.fvg_bear || 0,
      fvg_active: fvg.fvgs || sc.fvg_active || [],
      trend_1h: fvg.trend_1h || sc.trend_1h || null,
    });
    updateClaude(cb); updateMom(ms); updateScalp(scWithFvg);'''
assert OLD_UPDATE_CALL in src, "ERROR: updateClaude/Mom/Scalp 호출부를 못 찾음"
src = src.replace(OLD_UPDATE_CALL, NEW_UPDATE_CALL, 1)
print("[7] FVG 데이터 머지 호출 OK")

# ── 8. startScalp() 로그 메시지 업데이트 ──────────────────────────────────
OLD_SCALP_LOG = "  log('스캘퍼 '+(r.ok?`시작 (${lev}x · Claude TP/SL 적용)`:'오류'));"
NEW_SCALP_LOG = "  log('FVG스캘퍼 '+(r.ok?`시작 (${lev}x · MTF 1h→15m→1m)`:'오류'));"
assert OLD_SCALP_LOG in src, "ERROR: startScalp log 메시지를 못 찾음"
src = src.replace(OLD_SCALP_LOG, NEW_SCALP_LOG, 1)
print("[8] startScalp() 로그 메시지 OK")

# ── 저장 ───────────────────────────────────────────────────────────────────
with open(r'C:\Users\g8428\deepcoin_bot\index.html', 'w', encoding='utf-8') as f:
    f.write(src)
print(f"\n✅ index.html 패치 완료! (총 {len(src.splitlines())}줄)")
