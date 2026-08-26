"""Replicate server.py's exact whisper invocation outside Flask."""
import hashlib
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LS = ROOT.parent / "local-server"

data = Path("_speech_test_16k.wav").read_bytes()
print("source:", len(data), "bytes md5:", hashlib.md5(data).hexdigest()[:12])

tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
tmp.write(data)
tmp.close()
saved = Path(tmp.name)
print("saved:", saved.name, "md5:", hashlib.md5(saved.read_bytes()).hexdigest()[:12], "size:", saved.stat().st_size)

r = subprocess.run(
    [str(LS / "whisper" / "main.exe"), "-m", str(LS / "whisper" / "ggml-small.bin"),
     "-f", str(saved), "-l", "en", "-nt"],
    capture_output=True, text=True, timeout=180,
)
print("returncode:", r.returncode)
tail = (r.stderr or "").strip()[-250:]
print("stderr tail:", tail)
print("stdout text:", repr((r.stdout or "").strip()[:150]))
saved.unlink(missing_ok=True)
