"""Reproduce: write wav to %TEMP%, IMMEDIATELY spawn whisper - measure failures."""
import hashlib
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LS = ROOT.parent / "local-server"
data = (ROOT / "_speech_test_16k.wav").read_bytes()

results = []
for i in range(5):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.write(data)
    tmp.close()
    t0 = time.perf_counter()
    r = subprocess.run(
        [str(LS / "whisper" / "main.exe"), "-m", str(LS / "whisper" / "ggml-small.bin"),
         "-f", tmp.name, "-l", "en", "-nt"],
        capture_output=True, text=True, timeout=180,
    )
    dt = time.perf_counter() - t0
    opened = "failed to open" not in (r.stderr or "").lower()
    text = (r.stdout or "").strip()[:40]
    results.append(opened)
    print(f"run{i+1}: rc={r.returncode} {'OPEN-OK' if opened else 'OPEN-FAIL'} {dt:.1f}s text={text!r}")
    Path(tmp.name).unlink(missing_ok=True)

print(f"\nopens: {sum(results)}/5 immediate-success")
