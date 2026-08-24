"""
ASC Remote Gateway - receives commands from outside the laptop.

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

import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from flask import Flask, jsonify, request
from flask_cors import CORS

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.remote_queue import RemoteQueue  # noqa: E402

app = Flask(__name__)
CORS(app)

queue = RemoteQueue(ROOT / "data" / "remote_queue.json")


def _authorized() -> bool:
    token = os.environ.get("REMOTE_TOKEN", "")
    if not token:
        # Preferred: data/remote_token.txt (gitignored). Fallback: config.
        token_file = ROOT / "data" / "remote_token.txt"
        if token_file.exists():
            token = token_file.read_text(encoding="utf-8").strip()
    if not token:
        try:
            import json as _json

            cfg = _json.loads((ROOT / "config" / "settings.json").read_text(encoding="utf-8-sig"))
            token = (cfg.get("security") or {}).get("remote_token", "")
        except Exception:
            token = ""
    supplied = request.args.get("token") or request.headers.get("X-ASC-Token", "")
    return bool(token) and supplied == token


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
    return jsonify({"status": "ok", "service": "asc-remote-gateway"})


@app.route("/hook/whatsapp", methods=["POST"])
def whatsapp_hook():
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401
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
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    command = str(payload.get("command", "")).strip()
    if not command:
        return jsonify({"error": "command required"}), 400
    entry = queue.enqueue(
        command,
        source=payload.get("source", "api"),
        sender=str(payload.get("sender", "unknown")),
    )
    print(f"[Gateway] Queued task {entry['id']}: {command[:60]}")
    return jsonify({"status": "queued", "id": entry["id"]}), 201


@app.route("/queue", methods=["GET"])
def queue_view():
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify({"tasks": queue.recent(30)})


if __name__ == "__main__":
    port = int(os.environ.get("REMOTE_GATEWAY_PORT", "5001"))
    print(f"ASC Remote Gateway on http://localhost:{port}")
    app.run(port=port)
