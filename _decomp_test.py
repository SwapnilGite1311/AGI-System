import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core.task_decomposer import TaskDecomposer

td = TaskDecomposer()
commands = [
    "navigate to amazon.in and search for laptops",
    "open google and search for amazon and search laptops on amazon",
    "send an email saying hi to swapnilgite1311@gmail.com",
]
for cmd in commands:
    d = td.decompose(cmd)
    subs = d.get("subtasks", [])
    print(repr(cmd[:60]))
    print("  strategy=%s subtasks=%d" % (d.get("strategy"), len(subs)))
    for s in subs[:4]:
        print("   -", s.get("agent"), "|", s.get("action"), "|", str(s.get("description"))[:50])
