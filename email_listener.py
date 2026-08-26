"""
VEGA Email Listener - turns your inbox into a command channel.

Polls Gmail via IMAP for emails from ALLOWED_SENDERS whose subject contains
the command prefix (default "VEGA:"). Everything after the prefix becomes a
queued task; execution happens in ASC's interactive loop, and the result is
emailed back to the sender automatically.

Setup: run setup_email.py first (same app-password powers IMAP).
Run:   python email_listener.py    (keep running alongside ASC)
"""

import email
import imaplib
import json
import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.remote_queue import RemoteQueue  # noqa: E402

CONFIG_PATH = ROOT / "config" / "settings.json"
QUEUE_PATH = ROOT / "data" / "remote_queue.json"


def load_config():
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    email_cfg = cfg.get("email", {})
    # Merge gitignored credentials (password lives outside tracked config).
    creds_path = ROOT / "data" / "email_credentials.json"
    if creds_path.exists():
        try:
            email_cfg.update(json.loads(creds_path.read_text(encoding="utf-8")))
        except Exception as exc:
            print(f"[Email] credential merge failed: {exc}")
    if not email_cfg.get("configured") or not email_cfg.get("password"):
        print("[Email] Not configured - run setup_email.py first.")
        sys.exit(1)
    return {
        "address": email_cfg["email_address"],
        "password": email_cfg["password"],
        "imap": email_cfg.get("imap_server", "imap.gmail.com"),
        "port": int(email_cfg.get("imap_port", 993)),
        "allowed": email_cfg.get(
            "allowed_senders", [email_cfg["email_address"]]
        ),
        "prefix": email_cfg.get("subject_prefix", "VEGA:").upper(),
        "interval": int(email_cfg.get("check_interval_seconds", 20)),
    }


def get_text_body(msg) -> str:
    """Extract plain-text body from an email.message.Message."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(errors="replace")
        return ""
    payload = msg.get_payload(decode=True)
    return payload.decode(errors="replace") if payload else ""


def fetch_commands(cfg, queue: RemoteQueue):
    """Check inbox for new command emails; enqueue valid ones."""
    mail = imaplib.IMAP4_SSL(cfg["imap"], cfg["port"])
    mail.login(cfg["address"], cfg["password"])
    mail.select("INBOX")

    for sender in cfg["allowed"]:
        criteria = f'(UNSEEN FROM "{sender}")'
        status, data = mail.search(None, criteria)
        if status != "OK":
            continue
        for num in data[0].split():
            _, msg_data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            subject = str(msg.get("Subject", "")).strip()
            sender_addr = str(msg.get("From", ""))
            # normalize "Name <addr>" -> addr
            if "<" in sender_addr:
                sender_addr = sender_addr.split("<")[-1].rstrip(">")

            body = get_text_body(msg).strip()
            if cfg["prefix"] in subject.upper():
                command = subject.split(cfg["prefix"], 1)[1].strip() or body
            else:
                command = body[:500].strip()

            if not command:
                continue
            entry = queue.enqueue(command, source="email", sender=sender_addr)
            print(f"[Email] Queued {entry['id']} from {sender_addr}: {command[:60]}")

    mail.logout()


def main():
    cfg = load_config()
    queue = RemoteQueue(QUEUE_PATH)
    print("=" * 60)
    print(f"VEGA EMAIL LISTENER")
    print(f"  account : {cfg['address']}")
    print(f"  watching: subjects containing '{cfg['prefix']}' from {cfg['allowed']}")
    print(f"  interval: every {cfg['interval']}s")
    print("=" * 60)

    while True:
        try:
            fetch_commands(cfg, queue)
        except Exception as exc:
            print(f"[Email] poll error: {type(exc).__name__}: {str(exc)[:120]}")
        time.sleep(cfg["interval"])


if __name__ == "__main__":
    main()
