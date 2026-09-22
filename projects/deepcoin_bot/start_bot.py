import urllib.request, json
body = json.dumps({"mode": "claude-real"}).encode()
req = urllib.request.Request(
    "http://localhost:5000/api/claude/start",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST"
)
r = urllib.request.urlopen(req, timeout=5)
print(r.read().decode())
