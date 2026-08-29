"""
Real at-rest protection for secrets, using the OS keystore.

Replaces two things that were not encryption:
  - enterprise_security.encrypt_data's repeating-key XOR ("Simple XOR
    encryption for demonstration"), with the key stored in plaintext in the
    same directory as the ciphertext. Repeating-key XOR with a known-length
    key is broken by inspection; storing the key beside the output means
    there was no secret at all.
  - data/email_credentials.json holding a Gmail app password in clear text,
    readable by any process running as this user.

Uses Windows DPAPI (CryptProtectData / CryptUnprotectData) through ctypes -
no new dependency, and the key material is managed by the OS and tied to the
current user account, so the ciphertext is not portable to another user or
machine. That is the desired property for a local assistant's own secrets.

On non-Windows hosts DPAPI does not exist. Rather than silently falling back
to something weaker and calling it encrypted, `is_available()` returns False
and callers are expected to say so plainly.
"""

import base64
import ctypes
import json
import sys
from ctypes import wintypes
from typing import Optional

from loguru import logger

_IS_WINDOWS = sys.platform == "win32"

# Keys whose values are protected at rest rather than stored in clear text.
SENSITIVE_KEYS = {"password", "api_key", "token", "secret", "client_secret"}


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def is_available() -> bool:
    """Whether real OS-backed protection can be used on this host."""
    return _IS_WINDOWS


def _blob_to_bytes(blob: _DataBlob) -> bytes:
    size = int(blob.cbData)
    buffer = ctypes.create_string_buffer(size)
    ctypes.memmove(buffer, blob.pbData, size)
    return buffer.raw


def _free_blob(blob: _DataBlob) -> None:
    if blob.pbData:
        ctypes.windll.kernel32.LocalFree(blob.pbData)


def protect(plaintext: str, description: str = "VEGA secret") -> Optional[str]:
    """Encrypt `plaintext` for the current user. Returns base64, or None."""
    if not _IS_WINDOWS or plaintext is None:
        return None
    try:
        raw = plaintext.encode("utf-8")
        source = _DataBlob(len(raw), ctypes.cast(ctypes.create_string_buffer(raw), ctypes.POINTER(ctypes.c_char)))
        result = _DataBlob()
        ok = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(source),
            description,
            None, None, None,
            0,
            ctypes.byref(result),
        )
        if not ok:
            logger.warning("CryptProtectData failed (error {})", ctypes.GetLastError())
            return None
        try:
            return base64.b64encode(_blob_to_bytes(result)).decode("ascii")
        finally:
            _free_blob(result)
    except Exception as exc:
        logger.warning("Secret protection unavailable: {}", str(exc))
        return None


def unprotect(protected_b64: str) -> Optional[str]:
    """Decrypt a value produced by protect(). Returns None if it can't."""
    if not _IS_WINDOWS or not protected_b64:
        return None
    try:
        raw = base64.b64decode(protected_b64)
        source = _DataBlob(len(raw), ctypes.cast(ctypes.create_string_buffer(raw), ctypes.POINTER(ctypes.c_char)))
        result = _DataBlob()
        ok = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(source),
            None, None, None, None,
            0,
            ctypes.byref(result),
        )
        if not ok:
            return None
        try:
            return _blob_to_bytes(result).decode("utf-8")
        finally:
            _free_blob(result)
    except Exception as exc:
        logger.debug("Secret unprotect failed: {}", str(exc))
        return None


def looks_protected(value: str) -> bool:
    """Heuristic: does this value look like protect() output rather than
    a plaintext secret? Used to migrate existing plaintext transparently."""
    if not value or len(value) < 40:
        return False
    try:
        base64.b64decode(value, validate=True)
        return True
    except Exception:
        return False


def load_credentials(path) -> dict:
    """Read a credentials file, transparently handling both forms.

    Values under `protected_<name>` are decrypted and returned as `<name>`.
    Plaintext values are returned as-is AND upgraded in place on first read,
    so an existing install migrates without the user doing anything and
    without ever losing access to the secret.
    """
    from pathlib import Path

    path = Path(path)
    if not path.exists():
        return {}
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not read credentials file: {}", str(exc))
        return {}
    if not isinstance(stored, dict):
        return {}

    resolved: dict = {}
    plaintext_found: dict = {}

    for key, value in stored.items():
        if key.startswith("protected_"):
            name = key[len("protected_"):]
            clear = unprotect(str(value))
            if clear is not None:
                resolved[name] = clear
            else:
                logger.warning(
                    "Stored secret '{}' could not be decrypted on this account - "
                    "re-run setup_email.py to re-enter it.", name,
                )
        else:
            resolved[key] = value
            if key in SENSITIVE_KEYS and isinstance(value, str) and value:
                plaintext_found[key] = value

    if plaintext_found and is_available():
        _upgrade_plaintext(path, stored, plaintext_found)

    return resolved


def _upgrade_plaintext(path, stored: dict, plaintext: dict) -> None:
    """Replace plaintext secrets in the file with protected equivalents."""
    upgraded = dict(stored)
    changed = False
    for key, value in plaintext.items():
        blob = protect(value, description=f"VEGA:{key}")
        if blob:
            upgraded.pop(key, None)
            upgraded[f"protected_{key}"] = blob
            changed = True
    if not changed:
        return
    try:
        from core.atomic_io import write_json_atomic

        write_json_atomic(path, upgraded)
        logger.info("Upgraded {} stored secret(s) to OS-protected storage.", len(plaintext))
    except Exception as exc:
        logger.warning("Could not upgrade stored secrets in place: {}", str(exc))


def save_credentials(path, values: dict) -> None:
    """Write credentials, protecting sensitive values where possible."""
    from pathlib import Path

    from core.atomic_io import write_json_atomic

    path = Path(path)
    out: dict = {}
    for key, value in values.items():
        if key in SENSITIVE_KEYS and isinstance(value, str) and value and is_available():
            blob = protect(value, description=f"VEGA:{key}")
            if blob:
                out[f"protected_{key}"] = blob
                continue
        out[key] = value
    write_json_atomic(path, out)

