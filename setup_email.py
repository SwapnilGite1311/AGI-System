"""
VEGA Email Setup Wizard - one-time SMTP configuration.

Usage: python setup_email.py

Prompts for Gmail address + App Password (never your real password - create
one at myaccount.google.com -> Security -> 2-Step Verification -> App
passwords), verifies by sending a test mail to yourself, and stores the
config for the business agent's send_email capability.
"""

import json
import smtplib
import sys
from email.mime.text import MIMEText
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CONFIG_PATH = Path(__file__).resolve().parent / "config" / "settings.json"
KNOWN_SMTP = {
    "gmail.com": ("smtp.gmail.com", 587),
    "outlook.com": ("smtp-mail.outlook.com", 587),
    "hotmail.com": ("smtp-mail.outlook.com", 587),
    "yahoo.com": ("smtp.mail.yahoo.com", 465),
}


def detect_smtp(email: str):
    domain = email.split("@")[-1].lower()
    if domain in KNOWN_SMTP:
        return KNOWN_SMTP[domain]
    return None


def main():
    print("=" * 60)
    print("VEGA EMAIL SETUP")
    print("=" * 60)
    print("\nYou need a MAIL APP PASSWORD (not your normal password).")
    print("Gmail: myaccount.google.com -> Security -> 2-Step Verification")
    print("       -> App passwords -> generate one.\n")

    email = input("Your email address: ").strip()
    if "@" not in email:
        print("Invalid email.")
        return 1

    detected = detect_smtp(email)
    default_server, default_port = detected or ("smtp.gmail.com", 587)
    server_in = input(f"SMTP server [{default_server}]: ").strip() or default_server
    port_in = input(f"SMTP port [{default_port}]: ").strip() or str(default_port)

    print("App password (visible so you can verify - paste with or without spaces):")
    password = input("> ").strip().replace(" ", "")
    if not password:
        print("Password required.")
        return 1
    if not password:
        print("Password required.")
        return 1

    print("\nSending verification email to yourself...")
    try:
        msg = MIMEText(
            "VEGA email setup successful! You can now command VEGA to send emails.\n\n"
            "- Autonomous System Controller"
        )
        msg["Subject"] = "VEGA Email Setup - Success"
        msg["From"] = email
        msg["To"] = email

        with smtplib.SMTP(server_in, int(port_in), timeout=30) as smtp:
            smtp.starttls()
            smtp.login(email, password)
            smtp.send_message(msg)
        print("[PASS] Test email sent to", email)
    except Exception as exc:
        print(f"[FAIL] {exc}")
        print("\nCommon fixes:")
        print("- Gmail: enable 2-Step Verification, use an APP PASSWORD")
        print("- Check the SMTP server/port values")
        return 1

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    config.setdefault("email", {})
    config["email"]["configured"] = True
    config["email"]["smtp_server"] = server_in
    config["email"]["smtp_port"] = int(port_in)
    config["email"]["email_address"] = email
    config["email"]["password"] = password
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")

    print("\n[DONE] Email configured. VEGA can now send email on your behalf.")
    print("Try: send an email to <address> about <subject>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
