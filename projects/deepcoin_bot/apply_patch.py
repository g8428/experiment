"""
apply_patch.py — server.py에 tuning.json 자동 반영 + 다중전략 패치 적용
실행: python apply_patch.py
백업: server.py.bak 생성 후 패치
"""
import re, shutil, sys
from pathlib import Path

BASE       = Path(__file__).parent
SERVER     = BASE / "server.py"
SERVER_BAK = BASE / "server.py.bak"

# 백업
shutil.copy2(SERVER, SERVER_BAK)
print(f"[backup] {SERVER_BAK}")

code = SERVER.read_text(encoding="utf-8", errors="replace")
original_len = len(code)

# ── 패치 1: strategies.py import + tuning.json 로더 추가 ──────────
PATCH_IMPORT = '''
# == 다중전략 / 자동 튜닝 ==
try:
    from strategies import get_best_signal, ema200_filter
    _STRATEGIES_AVAILABLE = True
except ImportError:
    _STRATEGIES_AVAILABLE = False
    def get_best_signal(*a, **kw): return None
    def ema200_filter(*a, **kw):   return "neutral"

import threading as _thr_mod2

_TUNING_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tuning.json")
_tuning_mtime = 0.0

def _load_tuning():
    global _cfg, _claude_cfg, _tuning_mtime
    try:
        mtime = os.path.getmtime(_TUNING_PATH)
        if mtime <= _tuning_mtime:
            return
        with open(_TUNING_PATH, encoding="utf-8") as f:
            t = json.load(f)
        for k in ("max_daily_trades", "daily_profit_stop", "daily_loss_stop"):
            if k in t: _cfg[k] = t[k]
        for k in ("leverage", "size_pct", "cooldown"):
            if k in t: _claude_cfg[k] = t[k]
        if "max_daily_losses" in t: _cfg["max_daily_losses"] = t["max_daily_losses"]
        _tuning_mtime = mtime
        print(f"[tuning] v{t.get('version',0)} 반영 ({t.get('last_tuned','')})")
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[tuning] 로드 오류: {e}")

_load_tuning()

def _tuning_watcher():
    import time as _tt
    while True:
        try: _load_tuning()
        except Exception: pass
        _tt.sleep(60)

_thr_mod2.Thread(target=_tuning_watcher, daemon=True).start()
# == end 다중전략 / 자동 튜닝 ==
'''

TARGET_AFTER = '"cooldown":  900,   # '
if TARGET_AFTER in code:
    idx = code.find(TARGET_AFTER)
    close_idx = code.find("\n}", idx)
    if close_idx != -1:
        insert_pos = close_idx + 2
        code = code[:insert_pos] + PATCH_IMPORT + code[insert_pos:]
        print("[patch 1] tuning 로더 삽입 완료")
    else:
        print("[!] patch 1 실패")
else:
    print("[!] patch 1 실패 - 타겟 못 찾음")

# ── 패치 2: 다중전략 체크 삽입 ────────────────────────────────────
PATCH_MULTI = '''            # == 추가 전략 평가 (SMC 시그널 없을 때) ==
            if not s_sig and _STRATEGIES_AVAILABLE and ok:
                _kl_1h_alt = _klines(bar="1H", n=220)
                _t_json_alt = {}
                try:
                    import json as _jsalt
                    if os.path.exists(_TUNING_PATH):
                        _t_json_alt = _jsalt.load(open(_TUNING_PATH, encoding="utf-8"))
                except Exception:
                    pass
                _alt_sig = get_best_signal(kl, _kl_1h_alt,
                                           asian_high=smc.get("asian_high") if smc else None,
                                           asian_low=smc.get("asian_low") if smc else None,
                                           tuning=_t_json_alt)
                if _alt_sig and _alt_sig.get("signal"):
                    s_sig   = _alt_sig["signal"]
                    s_sl    = _alt_sig.get("sl")
                    s_tp    = _alt_sig.get("tp")
                    smc_rsn = f"[{_alt_sig['strategy'].upper()}] {_alt_sig['reason']}"
            # == end 추가 전략 ==
'''

kz_pattern = 'elif kz not in ("london", "newyork"):'
if kz_pattern in code:
    idx = code.find(kz_pattern)
    next_elif = code.find("elif not s_sig:", idx)
    if next_elif != -1:
        line_start = code.rfind("\n", 0, next_elif) + 1
        code = code[:line_start] + PATCH_MULTI + "\n" + code[line_start:]
        print("[patch 2] 다중전략 체크 삽입 완료")
    else:
        print("[!] patch 2 실패")
else:
    print("[!] patch 2 실패 - 킬존 줄 못 찾음")

# ── 패치 3: max_daily_losses 동적 파라미터 ────────────────────────
OLD_LOSSES = 'if st.get("losses", 0) >= 2:'
NEW_LOSSES = 'if st.get("losses", 0) >= _cfg.get("max_daily_losses", 2):'
if OLD_LOSSES in code:
    code = code.replace(OLD_LOSSES, NEW_LOSSES, 1)
    print("[patch 3] max_daily_losses 동적 파라미터 완료")
else:
    print("[~] patch 3 스킵")

# ── 저장 ─────────────────────────────────────────────────────────
try:
    SERVER.write_text(code, encoding="utf-8")
    print(f"\n[OK] server.py 패치 완료 ({original_len:,} -> {len(code):,}자)")
    print(f"     백업: {SERVER_BAK}")
except Exception as e:
    print(f"[!] 저장 실패: {e}")
    sys.exit(1)

print("""
[다음 단계]
  1. server.py 재시작 필요 (패치 반영)
  2. daily_review.py 테스트: python daily_review.py
  3. Task Scheduler 등록: setup_scheduler.bat 실행 (관리자 권한)
""")
