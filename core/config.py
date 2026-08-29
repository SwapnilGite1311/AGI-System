"""
Single source of truth for settings.json.

Seventeen constructors each opened and parsed the same config file
independently, with three different encodings between them (plain, utf-8,
utf-8-sig) - so a BOM or a non-ASCII value broke some modules while others
kept working, and every lazily-built agent paid another parse. This caches
one parsed copy per path (keyed by file mtime, so an edit is still picked
up) and hands out defensive copies.

It also centralises data-path resolution: several modules used bare
Path("data/...") relative to the CURRENT WORKING DIRECTORY, so launching
VEGA from anywhere other than the project root silently split its state
across two locations.
"""

import json
import threading
from pathlib import Path
from typing import Any, Dict

_CACHE: Dict[str, Any] = {}
_LOCK = threading.Lock()


def load_config(config_path: str = "./config/settings.json") -> Dict[str, Any]:
    """Return the parsed config, cached per (path, mtime).

    Always uses utf-8-sig, which reads plain UTF-8 correctly and also
    tolerates a byte-order mark - the inconsistency that made some modules
    fail on files others could read.
    """
    path = Path(config_path).resolve()
    try:
        stamp = path.stat().st_mtime_ns
    except OSError:
        stamp = 0
    key = str(path)

    with _LOCK:
        entry = _CACHE.get(key)
        if entry is None or entry[0] != stamp:
            with open(path, "r", encoding="utf-8-sig") as handle:
                parsed = json.load(handle)
            # Keyed BY PATH, holding that path's current revision. This used
            # to clear the whole cache on every new revision, which evicted
            # other config paths too - so any setup using two configs (a test
            # fixture alongside the real one) re-parsed on every single call
            # and the cache never held more than one entry (audit M-5).
            _CACHE[key] = (stamp, parsed)
            entry = _CACHE[key]
        cached = entry[1]

    # Defensive copy: a caller mutating its config (several do, e.g. merging
    # email credentials) must not corrupt every other module's view.
    return json.loads(json.dumps(cached))


def project_root(config_path: str = "./config/settings.json") -> Path:
    """The repository root, derived from the config file's own location."""
    return Path(config_path).resolve().parent.parent


def data_dir(config_path: str = "./config/settings.json") -> Path:
    """Absolute data directory, honouring paths.data but never cwd-relative."""
    config = load_config(config_path)
    configured = config.get("paths", {}).get("data", "./data")
    candidate = Path(configured)
    resolved = candidate if candidate.is_absolute() else project_root(config_path) / configured
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved
