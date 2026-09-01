"""
Drive the real program the way a person does.

Every bug found in live sessions - the Ctrl+C crash, the prompt scrolling
away, voice mode hanging, "successfully" printed above an empty screen -
lived in `run_interactive`, and NOT ONE unit test touches that function.
The suite calls `process_command` directly and builds controllers with
`object.__new__`, skipping `__init__` as well. It therefore cannot observe
startup, the prompt, the display path, interrupt handling, or shutdown.

This launches `python main.py` as a subprocess, types into its stdin, and
reads what a user would actually see. It is slower than a unit test and
needs Ollama running, so it is not part of the default suite - run it with:

    python tests/session_harness.py

Exit code is non-zero if any check fails, so CI can gate on it.
"""

import re
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
STARTUP_TIMEOUT = 180
COMMAND_TIMEOUT = 90

# Log lines and engine chatter the user does not type into.
ANSI = re.compile(chr(27) + r"\[[0-9;]*m")


def _safe(text: str) -> str:
    """Print without dying on emoji in a cp1252 console."""
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    return text.encode(enc, errors="replace").decode(enc, errors="replace")


NOISE = re.compile(
    r"^(?:\d\d:\d\d:\d\d \||time=|\[GIN\]|llama_|load|ggml|print_|init:|"
    r"whisper_|system_info|main:|build:|register_|Device )"
)


def _clean(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines()
        if line.strip() and not NOISE.match(line.strip())
    )


class Session:
    """A live `python main.py` you can type into."""

    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, "-u", str(ROOT / "main.py")],
            cwd=str(ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
        )
        self._buffer: List[str] = []

    def _read_until(self, marker: str, timeout: float) -> Tuple[bool, str]:
        """Collect output until `marker` appears or time runs out."""
        deadline = time.time() + timeout
        chunk: List[str] = []
        while time.time() < deadline:
            if self.proc.poll() is not None:
                chunk.append(f"<<PROCESS EXITED rc={self.proc.returncode}>>")
                break
            line = self.proc.stdout.readline()
            if not line:
                time.sleep(0.05)
                continue
            chunk.append(line.rstrip("\n"))
            self._buffer.append(line.rstrip("\n"))
            if marker in line:
                return True, "\n".join(chunk)
        return False, "\n".join(chunk)

    def wait_for_prompt(self, timeout: float = STARTUP_TIMEOUT) -> Tuple[bool, str]:
        return self._read_until("You:", timeout)

    def send(self, command: str, timeout: float = COMMAND_TIMEOUT) -> Tuple[bool, str]:
        """Type a command and read everything up to the next prompt."""
        if self.proc.poll() is not None:
            return False, "<<PROCESS ALREADY DEAD>>"
        self.proc.stdin.write(command + "\n")
        self.proc.stdin.flush()
        return self._read_until("You:", timeout)

    def alive(self) -> bool:
        return self.proc.poll() is None

    def close(self) -> None:
        try:
            if self.proc.poll() is None:
                self.proc.stdin.write("exit\n")
                self.proc.stdin.flush()
                self.proc.wait(timeout=30)
        except Exception:
            pass
        finally:
            if self.proc.poll() is None:
                self.proc.kill()


# ---------------------------------------------------------------------------
# Checks. Each returns (name, passed, detail).
# ---------------------------------------------------------------------------

CHECKS: List[Tuple[str, str, callable]] = []


def check(name: str, command: str):
    def register(fn):
        CHECKS.append((name, command, fn))
        return fn
    return register


@check("prompt appears at startup", "")
def _prompt(_out: str) -> Tuple[bool, str]:
    return True, ""      # handled by wait_for_prompt


@check("system info shows real numbers", "system info")
def _system_info(out: str) -> Tuple[bool, str]:
    if "CPU" not in out:
        return False, "no CPU line in output"
    if not re.search(r"\d+(\.\d+)?%", out):
        return False, "no percentage figure - output may be empty"
    return True, ""


@check("list tasks prints something", "list tasks")
def _list_tasks(out: str) -> Tuple[bool, str]:
    # The renderer once said "completed successfully" above a blank screen.
    body = [l for l in out.splitlines() if l.strip()]
    if len(body) < 2:
        return False, f"only {len(body)} line(s) of output: {body}"
    if "successfully" in out.lower() and not re.search(r"[Tt]asks?\s*\(", out):
        return False, "claimed success but listed nothing"
    return True, ""

@check("disk drives prints drives", "disk drives")
def _drives(out: str) -> Tuple[bool, str]:
    if not re.search(r"[A-Z]:\\|[Dd]rives?\s*\(", out):
        return False, "no drive listed"
    return True, ""


@check("file creation reports a real path", "create a file called harness_probe.txt with content ok")
def _create(out: str) -> Tuple[bool, str]:
    if "called harness_probe" in out:
        return False, "filename kept the word 'called'"
    if not re.search(r"harness_probe\.txt", out):
        return False, "no filename in output"
    return True, ""


@check("unknown phrasing does not claim success", "flurbick wibble wobble")
def _nonsense(out: str) -> Tuple[bool, str]:
    if re.search(r"completed successfully|Task completed", out, re.I):
        return False, "claimed to have completed gibberish"
    return True, ""


@check("destructive command is refused", "delete the entire windows folder")
def _refuse(out: str) -> Tuple[bool, str]:
    if re.search(r"completed successfully", out, re.I):
        return False, "did not refuse"
    if "Unknown error" in out:
        return False, "refused but reported it as an unknown error"
    return True, ""


@check("conversation replies", "hello")
def _chat(out: str) -> Tuple[bool, str]:
    if len([l for l in out.splitlines() if l.strip()]) < 1:
        return False, "no reply"
    return True, ""


def main() -> int:
    print("=" * 68)
    print("SESSION HARNESS - drives the real interactive loop")
    print("=" * 68)

    session = Session()
    ok, startup = session.wait_for_prompt()
    if not ok:
        print("FAIL: no prompt within startup timeout")
        print(_safe(_clean(startup)[-1500:]))
        session.close()
        return 1
    print("startup: prompt appeared\n")

    failures = 0
    for name, command, verify in CHECKS:
        if not command:
            print(f"  PASS  {name}")
            continue
        if not session.alive():
            print(f"  FAIL  {name}  <- process died earlier")
            failures += 1
            continue

        reached, raw = session.send(command)
        out = _clean(raw)
        if not reached:
            print(f"  FAIL  {name}  <- no prompt returned (hang or crash)")
            print(_safe(f"        last output: {out[-300:]}"))
            failures += 1
            continue

        passed, detail = verify(out)
        print(f"  {'PASS' if passed else 'FAIL'}  {name}" + ("" if passed else f"  <- {detail}"))
        if not passed:
            failures += 1
            for line in out.splitlines()[:6]:
                print(_safe(f"        | {line[:88]}"))

    still_alive = session.alive()
    print(f"\n  {'PASS' if still_alive else 'FAIL'}  session survived every command")
    if not still_alive:
        failures += 1

    session.close()
    print("\n" + "=" * 68)
    print(f"{len(CHECKS) - failures}/{len(CHECKS) + 1} checks passed")
    print("=" * 68)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
