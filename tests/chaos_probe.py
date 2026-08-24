"""Chaos probe: hammer agent methods with hostile inputs to find crashes.

Run directly:  python tests/chaos_probe.py
Exits non-zero if any agent method crashes on hostile input.
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.business_agent import BusinessAgent
from agents.file_agent import FileAgent
from agents.system_agent import SystemAgent

biz = BusinessAgent()
fil = FileAgent()
sysa = SystemAgent()

crashes = []


def probe(label, fn):
    try:
        r = fn()
        err = ""
        if isinstance(r, dict):
            err = str(r.get("error", ""))[:60]
            if "success" not in r and not any(
                k in r for k in ("files", "drives", "tasks", "projects")
            ):
                crashes.append((label, f"no success flag, keys={list(r)[:5]}"))
                return
        print(f"  OK   {label} {('[' + err + ']') if err else ''}")
    except Exception as exc:
        crashes.append((label, f"{type(exc).__name__}: {str(exc)[:90]}"))


def run():
    print("=== BusinessAgent hostile inputs ===")
    probe("send_email all None", lambda: biz.send_email_notification(None, None, None))
    probe("send_email empty", lambda: biz.send_email_notification("", "", ""))
    probe("create_task title=None", lambda: biz.create_task(None))
    probe("create_task empty title", lambda: biz.create_task(""))
    probe("add_calendar_event no args", lambda: biz.add_calendar_event())
    probe("add_calendar_event bad time", lambda: biz.add_calendar_event(title="x", start_time="not-a-date"))
    probe("update_task_status None id", lambda: biz.update_task_status(None))
    probe("get_project_timeline None", lambda: biz.get_project_timeline(None))
    probe("configure_email empties", lambda: biz.configure_email("", None, "", ""))

    print("=== FileAgent hostile inputs ===")
    probe("delete_file None", lambda: fil.delete_file(None))
    probe("delete_file empty", lambda: fil.delete_file(""))
    probe("get_file_info missing", lambda: fil.get_file_info("Z:/definitely/missing.txt"))
    probe("move_file missing src", lambda: fil.move_file("missing_src.txt", "dst.txt"))
    probe("copy_file None", lambda: fil.copy_file(None, None))
    probe("search_files empty q", lambda: fil.search_files(".", ""))
    probe("create_folder empty", lambda: fil.create_folder(""))
    probe("organize_folder missing", lambda: fil.organize_folder("Z:/nope"))

    print("=== SystemAgent hostile inputs ===")
    probe("open_application empty", lambda: sysa.open_application(""))
    probe("open_application sentence", lambda: sysa.open_application("this is not a real app name at all"))
    probe("close_application None", lambda: sysa.close_application(None))
    probe("get_network_info", lambda: sysa.get_network_info())
    probe("run_command empty", lambda: sysa.run_command(""))
    probe("ssl_check bad domain", lambda: sysa.check_ssl_certificate("not a domain!!"))

    print()
    if crashes:
        print(f"FOUND {len(crashes)} CRASH/GAPS:")
        for label, why in crashes:
            print(f"  x {label}: {why}")
        return 1
    print("CHAOS PROBE: zero crashes")
    return 0


if __name__ == "__main__":
    sys.exit(run())
