"""v2 스모크 테스트: 롱 컨텍스트 1회 생성(피클 저장) → 전략별 1회 실행, 시간·건수·청산사유 확인."""
import collections
import os
import pickle
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from chain2 import build_chain, load_hist_1h  # noqa: E402
from core import load_1m  # noqa: E402
from strats2 import RUNNERS  # noqa: E402

PK = os.path.join(os.path.dirname(__file__), "..", "backtest", "cache", "ctx_v2_long.pkl")

t = time.time()
if os.path.exists(PK) and "--rebuild" not in sys.argv:
    c = pickle.load(open(PK, "rb"))
else:
    c = build_chain(load_1m(), load_hist_1h())
    try:
        pickle.dump(c, open(PK, "wb"), protocol=4)
    except Exception as e:  # 저장 실패해도 테스트는 계속
        print("피클 저장 실패:", e, flush=True)
print(f"ctx {time.time()-t:.0f}s  n={c['n']}  rest={c['rest_block'].mean():.3f} obst={c['obstacle_block'].mean():.3f} "
      f"gate_s={c['gate_structure'].mean():.3f} gate_n={c['gate_narrative'].mean():.3f}", flush=True)
for name, (fn, uses_w) in RUNNERS.items():
    t = time.time()
    tr = fn(c, "structure", 3 * 1440)
    R = np.array([x["R"] for x in tr])
    print(f"{name:4} {time.time()-t:6.1f}s n={len(tr):4} "
          f"avgR={R.mean() if len(R) else float('nan'):+.3f} totR={R.sum():+.1f} "
          f"{dict(collections.Counter(x['why'] for x in tr))} {dict(collections.Counter(x['tag'] for x in tr))}", flush=True)
