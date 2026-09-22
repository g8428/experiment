"""
serve.py — 대시보드 로컬 서버
실행: python dashboard/serve.py
브라우저: http://localhost:8899
"""
import os, sys, subprocess, threading, http.server, webbrowser

DASHBOARD_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR   = os.path.dirname(DASHBOARD_DIR)
PORT          = 8899


def regen_data():
    print("데이터 생성 중...")
    result = subprocess.run(
        [sys.executable, os.path.join(PROJECT_DIR, "evolution", "dashboard_gen.py")],
        cwd=PROJECT_DIR, capture_output=True, text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        print("경고:", result.stderr[:300])


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DASHBOARD_DIR, **kwargs)

    def log_message(self, format, *args):
        pass  # 로그 억제


regen_data()

print(f"\n대시보드 시작: http://localhost:{PORT}")
print("종료: Ctrl+C\n")

threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()

with http.server.HTTPServer(("", PORT), Handler) as httpd:
    httpd.serve_forever()
