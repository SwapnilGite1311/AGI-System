"""
Keep the test suite out of the user's real data.

Ten tests instantiate agents against the live `config/settings.json`, which
points at the real `data/` directory. They then create tasks, projects,
team members and reminders in it. The consequences were not hypothetical:

  - `test_schedule_reminder` scheduled a reminder for one hour ahead, so
    every test run planted a "Test Reminder" that interrupted the next real
    session an hour later. That was mistaken for a bug in the reminder
    system three separate times.
  - Repeated runs accumulated 1,026 tasks of which 27 were distinct,
    573 projects mostly named "Test Project", and four team members
    duplicated 39 times each - which then skewed every analytic the
    product computed, because those files ARE the product's data.

This redirects the data directory to a per-session temp copy before any
test imports an agent. Tests keep using the real config path, so nothing in
them changes; only the destination moves.
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REAL_CONFIG = ROOT / "config" / "settings.json"
REAL_DATA = ROOT / "data"

# Small files worth copying so tests see realistic shapes; anything large or
# regenerable is left behind.
SEED_FILES = (
    "business_tasks.json",
    "projects.json",
    "team_members.json",
    "schedules.json",
    "user_preferences.json",
)


# Standalone diagnostic scripts, not pytest modules. Several construct
# agents at import time - chaos_probe.py does `biz = BusinessAgent()` on line
# 16 - which runs during COLLECTION, before any fixture can redirect the data
# directory. Collecting them was quietly writing into the user's real data on
# every test run.
collect_ignore = [
    "brain_battery.py",
    "brain_v2_test.py",
    "chaos_probe.py",
    "comprehensive_system_test.py",
    "config_audit.py",
    "contract_audit.py",
    "diag_commands.py",
    "extended_system_test.py",
    "session_harness.py",
    "tier_battery.py",
]


@pytest.fixture(scope="session", autouse=True)
def isolate_test_data():
    """Point every agent at a throwaway data directory for the whole run."""
    sandbox = Path(tempfile.mkdtemp(prefix="vega_test_data_"))

    for name in SEED_FILES:
        source = REAL_DATA / name
        if source.exists():
            try:
                shutil.copy2(source, sandbox / name)
            except Exception:
                pass

    # Rewrite only the data path; everything else stays as the product has it,
    # so tests still exercise the real configuration.
    try:
        config = json.loads(REAL_CONFIG.read_text(encoding="utf-8-sig"))
    except Exception:
        yield None
        return

    config.setdefault("paths", {})["data"] = str(sandbox)
    for section, key in (("session", "session_file"), ("session", "preferences_file")):
        if isinstance(config.get(section), dict) and config[section].get(key):
            config[section][key] = str(sandbox / Path(config[section][key]).name)

    sandbox_config = sandbox / "settings.json"
    sandbox_config.write_text(json.dumps(config, indent=2), encoding="utf-8")

    # core.config caches per path; make the real path resolve to the sandbox
    # copy so agents constructed with "./config/settings.json" land here.
    from core import config as config_module

    original_load = config_module.load_config

    def redirected(config_path: str = "./config/settings.json"):
        try:
            same = Path(config_path).resolve() == REAL_CONFIG
        except Exception:
            same = False
        return original_load(str(sandbox_config)) if same else original_load(config_path)

    config_module.load_config = redirected

    # Agents do `from core.config import load_config`, so they hold a
    # reference to the ORIGINAL function and never see the module attribute
    # being swapped. Patch every module that imported it.
    import importlib
    import pkgutil

    patched = []
    for package in ("agents", "core", "learning", "vision"):
        try:
            pkg = importlib.import_module(package)
        except Exception:
            continue
        for info in pkgutil.iter_modules(getattr(pkg, "__path__", [])):
            name = f"{package}.{info.name}"
            try:
                module = importlib.import_module(name)
            except Exception:
                continue
            if getattr(module, "load_config", None) is original_load:
                module.load_config = redirected
                patched.append(module)

    try:
        yield sandbox
    finally:
        config_module.load_config = original_load
        for module in patched:
            module.load_config = original_load
        shutil.rmtree(sandbox, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def guard_real_data(isolate_test_data):
    """Fail loudly if a test still managed to write into the real data dir.

    Redirection covers agents that read their paths through core.config; a
    module that hardcodes a path would slip past it, and this catches that
    rather than letting it silently pollute again.
    """
    def snapshot():
        counts = {}
        for name in SEED_FILES:
            path = REAL_DATA / name
            if not path.exists():
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                items = raw.get("tasks", raw) if isinstance(raw, dict) else raw
                counts[name] = len(items) if isinstance(items, list) else 0
            except Exception:
                counts[name] = -1
        return counts

    before = snapshot()
    yield
    after = snapshot()

    grew = {k: (before.get(k), after.get(k)) for k in after if after.get(k, 0) > before.get(k, 0)}
    if grew:
        detail = ", ".join(f"{k}: {b} -> {a}" for k, (b, a) in grew.items())
        pytest.fail(
            "The test run wrote into the real data directory: " + detail +
            ". A module is bypassing core.config and hardcoding its path."
        )
