import json
import urllib.request
from pathlib import Path

token = json.loads(Path("config/settings.json").read_text(encoding="utf-8"))["security"]["remote_token"]

body = json.dumps({"command": "show system info", "source": "test", "sender": "supervisor"}).encode()
req = urllib.request.Request(
    f"http://localhost:5001/remote/task?token={token}",
    data=body,
    headers={"Content-Type": "application/json"},
)
r = urllib.request.urlopen(req, timeout=10)
print("gateway enqueue:", r.status, r.read().decode())

q = urllib.request.urlopen(f"http://localhost:5001/queue?token={token}", timeout=10)
data = json.loads(q.read().decode())
print("queue view:", [(t["command"], t["status"]) for t in data["tasks"]])

# unauthorized probe must fail
try:
    urllib.request.urlopen("http://localhost:5001/queue", timeout=10)
    print("SECURITY FAIL: unauthenticated request allowed!")
except urllib.error.HTTPError as e:
    print("security check:", "PASS" if e.code == 401 else "FAIL")
