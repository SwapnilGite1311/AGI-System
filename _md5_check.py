import hashlib
import json
import urllib.error
import urllib.request
from pathlib import Path

p = Path("_speech_test_16k.wav")
src_md5 = hashlib.md5(p.read_bytes()).hexdigest()
print("source md5:", src_md5, "size:", p.stat().st_size)

data = p.read_bytes()
boundary = "XB"
head = (
    "--" + boundary + "\r\n"
    'Content-Disposition: form-data; name="audio"; filename="s.wav"\r\n'
    "Content-Type: audio/wav\r\n\r\n"
).encode()
body = head + data + ("\r\n--" + boundary + "--\r\n").encode()
req = urllib.request.Request(
    "http://localhost:5000/listen",
    data=body,
    headers={"Content-Type": "multipart/form-data; boundary=" + boundary},
)
try:
    r = urllib.request.urlopen(req, timeout=180)
    print("OK:", r.read().decode()[:150])
except urllib.error.HTTPError as e:
    d = json.loads(e.read().decode())
    print("HTTP", e.code)
