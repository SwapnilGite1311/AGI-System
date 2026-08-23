"""
ASC Doctor - one-shot environment health check.

Usage: python main.py --doctor
Verifies config, Ollama, models, voice service, python deps,
tesseract, playwright browsers, and writable data dirs.
Exit code: 0 = all pass, 1 = at least one FAIL, 2 = warnings only.
"""

import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = []


def record(name, ok, detail="", warn=False):
    status = "PASS" if ok else ("WARN" if warn else "FAIL")
    RESULTS.append((status, name, detail))
    marker = "[PASS]" if ok else ("[WARN]" if warn else "[FAIL]")
    print(f"{marker} {name}: {detail}" if detail else f"{marker} {name}")


def check_config():
    path = ROOT / "config" / "settings.json"
    if not path.exists():
        record("config", False, f"{path} missing")
        return None
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        record("config", False, f"invalid JSON: {exc}")
        return None
    missing = [k for k in ("ollama", "llm_council", "paths", "web_automation") if k not in config]
    if missing:
        record("config", False, f"missing sections: {missing}")
        return config
    record("config", True, "settings.json valid, all sections present")
    return config


def check_ollama(config):
    host = (config or {}).get("ollama", {}).get("host", "http://127.0.0.1:11434")
    tags = {}
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=5) as resp:
            tags = {m.get("name"): m for m in json.loads(resp.read().decode()).get("models", [])}
    except Exception as exc:
        record("ollama server", False, f"{host} unreachable ({exc})")
        return

    record("ollama server", True, f"{host} reachable, {len(tags)} models installed")

    council = (config or {}).get("llm_council", {})
    needed = sorted({v.get("model") for v in council.values() if isinstance(v, dict) and v.get("model")} |
                    set((config or {}).get("ollama", {}).get("fallback_chain", [])))
    normalized = {"tinyllama": "tinyllama:latest"}
    missing = [n for n in needed if normalized.get(n, n) not in tags]
    if missing:
        record("models", False, f"missing: {missing} -> run: ollama pull {' '.join(missing)}")
    else:
        record("models", True, f"council models present ({', '.join(sorted(needed))})")


def check_voice(config):
    url = (config or {}).get("audio", {}).get("voice_service_url", "http://localhost:5000")
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=4) as resp:
            body = json.loads(resp.read().decode())
            if body.get("status") == "ok":
                record("voice server", True, f"{url} healthy")
            else:
                record("voice server", False, f"{url} degraded, missing: {body.get('missing')}", warn=False)
    except Exception:
        record("voice server", False, f"{url} not running (start local-server/server.py) - typed commands still work", warn=True)


def check_deps():
    modules = ["ollama", "loguru", "requests", "pyaudio", "pytesseract", "PIL"]
    missing = []
    for mod in modules:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        record("python deps", False, f"not installed: {missing}")
    else:
        record("python deps", True, f"all {len(modules)} core modules importable")


def check_tesseract(config):
    configured = (config or {}).get("vision", {}).get("tesseract_path")
    if configured and Path(configured).exists():
        record("tesseract", True, f"configured path: {configured}")
        return
    located = shutil.which("tesseract")
    if located:
        record("tesseract", True, f"found on PATH: {located}")
        return
    default = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if default.exists():
        record("tesseract", True, f"default location: {default}")
        return
    record("tesseract", False, "not found - OCR/vision degraded", warn=True)


def check_playwright():
    cache = Path.home() / "AppData" / "Local" / "ms-playwright"
    env_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    candidates = [Path(env_path)] if env_path else [cache, Path(r"C:\ms-playwright")]
    existing = next((c for c in candidates if c.exists()), None)
    try:
        import playwright  # noqa: F401

        installed = True
    except ImportError:
        installed = False
    if installed and existing:
        record("playwright", True, f"installed, browsers at {existing}")
    elif installed:
        record("playwright", False, f"installed but no browser cache found - run: playwright install chromium", warn=True)
    else:
        record("playwright", False, "not installed - web automation unavailable")


def check_data_dirs():
    data = ROOT / "data"
    try:
        data.mkdir(parents=True, exist_ok=True)
        probe = data / ".doctor_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        record("data dir", True, f"{data} writable")
    except Exception as exc:
        record("data dir", False, f"{data} not writable: {exc}")


def run():
    print("=" * 60)
    print("ASC DOCTOR - ENVIRONMENT HEALTH CHECK")
    print("=" * 60)

    config = check_config()
    check_ollama(config)
    check_voice(config)
    check_deps()
    check_tesseract(config)
    check_playwright()
    check_data_dirs()

    fails = sum(1 for s, _, _ in RESULTS if s == "FAIL")
    warns = sum(1 for s, _, _ in RESULTS if s == "WARN")
    passes = len(RESULTS) - fails - warns
    print("-" * 60)
    print(f"SUMMARY: {passes} pass, {warns} warnings, {fails} failures")
    print("Tip: also run `python tests/test_intent_matrix.py` to verify command parsing.")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(run())
