"""
VEGA Remote Gateway - receives commands from outside the laptop.

Endpoints:
  GET  /health            -> service status
  POST /hook/whatsapp     -> WhatsApp Cloud API message webhook
  POST /remote/task       -> generic remote task injection (JSON: sender, command)
  GET  /queue             -> recent queue entries (status view)

Security (skeleton phase):
  - Every request must include header/token ?token= matching REMOTE_TOKEN env
    or config security.remote_token. Configure a strong token before exposing.
Run:  python remote_gateway.py   (listens on :5001)
"""

import hmac
import os
import sys
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from flask import Flask, jsonify, request
from flask_cors import CORS

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.remote_queue import RemoteQueue  # noqa: E402

app = Flask(__name__)
# Bound request bodies. Flask leaves this unset, so a single large POST was
# parsed into memory unbounded (audit M-6). Commands are one-liners; 64KB is
# already far more than any legitimate one.
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
MAX_COMMAND_CHARS = 4000

# Per-IP throttle. Token comparison is constant-time, but nothing stopped an
# attacker making unlimited guesses, and nothing stopped a flood of valid
# requests filling the queue.
_RATE_WINDOW_SECONDS = 60
_RATE_MAX_REQUESTS = 30
_RATE_MAX_FAILURES = 8
_rate_hits: dict = defaultdict(deque)
_auth_failures: dict = defaultdict(deque)
_rate_lock = threading.Lock()


def _prune(bucket: deque, now: float) -> None:
    while bucket and now - bucket[0] > _RATE_WINDOW_SECONDS:
        bucket.popleft()


def _rate_limited() -> bool:
    """True when this client has exceeded its request or failure budget."""
    client = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
    client = client.split(",")[0].strip()
    now = time.time()
    with _rate_lock:
        hits, fails = _rate_hits[client], _auth_failures[client]
        _prune(hits, now)
        _prune(fails, now)
        if len(fails) >= _RATE_MAX_FAILURES or len(hits) >= _RATE_MAX_REQUESTS:
            return True
        hits.append(now)
    return False


def _note_auth_failure() -> None:
    client = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
    client = client.split(",")[0].strip()
    with _rate_lock:
        _auth_failures[client].append(time.time())


def _gate():
    """Shared entry check: throttle first, then authenticate.

    Returns an error response, or None when the request may proceed.
    """
    if _rate_limited():
        return jsonify({"error": "rate limited"}), 429
    if not _authorized():
        _note_auth_failure()
        return jsonify({"error": "unauthorized"}), 401
    return None


# No wildcard CORS: this service executes commands on the user's machine, so
# no web origin should be able to reach it from a browser at all. Legitimate
# clients (the WhatsApp webhook, scripts) are not browsers and send no Origin.
CORS(app, origins=[])

queue = RemoteQueue(ROOT / "data" / "remote_queue.json")

_TOKEN_CACHE: dict = {}


def _load_token() -> str:
    """Resolve the shared token once.

    This was re-read from disk on every single request; the token does not
    change while the process runs (audit M-6).
    """
    if "v" in _TOKEN_CACHE:
        return _TOKEN_CACHE["v"]

    token = os.environ.get("REMOTE_TOKEN", "")
    if not token:
        # Preferred: data/remote_token.txt (gitignored). Fallback: config.
        token_file = ROOT / "data" / "remote_token.txt"
        if token_file.exists():
            token = token_file.read_text(encoding="utf-8").strip()
    if not token:
        try:
            import json as _json

            cfg = _json.loads(
                (ROOT / "config" / "settings.json").read_text(encoding="utf-8-sig")
            )
            token = (cfg.get("security") or {}).get("remote_token", "")
        except Exception:
            token = ""

    _TOKEN_CACHE["v"] = token
    return token


def _authorized() -> bool:
    token = _load_token()
    # Header only. A token in the query string leaks into browser history,
    # Referer headers, and access logs - and this token authorises remote
    # command execution on the user's machine.
    supplied = request.headers.get("X-VEGA-Token", "")
    if not token or not supplied:
        return False
    # Constant-time: a plain == leaks token content through timing.
    return hmac.compare_digest(str(supplied), str(token))


def _extract_whatsapp_message(payload: dict):
    """Parse WhatsApp Cloud API webhook payload into (sender, text)."""
    try:
        entry = payload["entry"][0]["changes"][0]["value"]["messages"][0]
        sender = entry.get("from", "unknown")
        text = entry.get("text", {}).get("body", "").strip()
        return sender, text
    except (KeyError, IndexError, TypeError):
        return None, None


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "vega-remote-gateway"})


@app.route("/hook/whatsapp", methods=["POST"])
def whatsapp_hook():
    blocked = _gate()
    if blocked:
        return blocked
    payload = request.get_json(silent=True) or {}
    sender, text = _extract_whatsapp_message(payload)
    if not text:
        # Status updates and non-message callbacks are acknowledged silently.
        return jsonify({"status": "ignored"})
    entry = queue.enqueue(text, source="whatsapp", sender=str(sender))
    print(f"[Gateway] Queued WhatsApp task {entry['id']} from {sender}: {text[:60]}")
    return jsonify({"status": "queued", "id": entry["id"]})


@app.route("/remote/task", methods=["POST"])
def remote_task():
    blocked = _gate()
    if blocked:
        return blocked
    payload = request.get_json(silent=True) or {}
    command = str(payload.get("command", "")).strip()
    if not command:
        return jsonify({"error": "command required"}), 400
    if len(command) > MAX_COMMAND_CHARS:
        # This string is later executed; an unbounded one is both a memory
        # and a prompt-injection surface.
        return jsonify({"error": f"command exceeds {MAX_COMMAND_CHARS} characters"}), 413
    entry = queue.enqueue(
        command,
        source=payload.get("source", "api"),
        sender=str(payload.get("sender", "unknown")),
    )
    print(f"[Gateway] Queued task {entry['id']}: {command[:60]}")
    return jsonify({"status": "queued", "id": entry["id"]}), 201


@app.route("/queue", methods=["GET"])
def queue_view():
    blocked = _gate()
    if blocked:
        return blocked
    return jsonify({"tasks": queue.recent(30)})


if __name__ == "__main__":
    port = int(os.environ.get("REMOTE_GATEWAY_PORT", "5001"))
    print(f"VEGA Remote Gateway on http://localhost:{port}")
    app.run(port=port)
