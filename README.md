# VEGA — Autonomous System Controller

A local-first assistant that runs on your own machine and actually does
things to it: manages tasks and projects, creates and opens files, writes
real Word and Excel documents, drives a browser, fills forms, sends email,
reports what your system is doing, and takes commands by voice.

Every model runs locally through [Ollama](https://ollama.com). Nothing is
sent to a hosted API. It is built for a laptop, not a datacentre — the
reference machine is 7.4 GB of RAM and a 4 GB RTX 3050.

---

## What it can actually do

The honest list, in the sense that each of these has been verified against
reality rather than against a return value:

| Area | Examples |
|---|---|
| **Tasks & projects** | `create a task called call the supplier`, `list my tasks`, `delete the task call the supplier` |
| **Team** | `add priya to the team as a designer`, `show me the team`, `remove priya from the team` |
| **Files** | `create file notes.txt`, `open my_tasks.xlsx from documents folder`, `delete notes.txt`, `open the downloads folder` |
| **Documents** | `create a spreadsheet of my tasks`, research reports written as real `.docx` |
| **Web** | `go to amazon.in and search for laptops`, `search the web for X`, form filling with verified field values |
| **System** | `show system info`, `whats hogging the memory`, `show disk drives`, `tidy up my downloads folder` |
| **Email** | `send an email to raj@example.com about the invoice` |
| **Arithmetic** | `what is 17 percent of 4500` — parsed and evaluated locally, no model involved |
| **Voice** | say `voice` to enter continuous voice mode, `voice off` to leave |

Type `help` once it is running for the in-session list.

### What it does not do yet

Stated plainly, because a documented limit is more useful than a vague
claim of completeness:

- **Multi-step compound commands.** `count how many tasks I have and save
  that number to a file` fails more often than it works — 10 of 18 measured
  multi-step benchmark tasks fail. Single-step commands are the solid path.
- **Conversational reference.** `now open that spreadsheet` has nothing
  tracking what "that" refers to.
- **Intent understanding is pattern-matched, not learned.** Roughly
  two-thirds of commands are recognised by deterministic rules; the rest go
  to a local model, which is slower and less reliable.

---

## Requirements

- **Python 3.11+** (developed on 3.13)
- **[Ollama](https://ollama.com/download)** installed and running
- **Windows** for the full feature set. The core runs elsewhere, but the
  application-launching and UI-automation paths are Windows-specific.
- Optional: [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)
  for screen reading, and [ffmpeg](https://ffmpeg.org) on `PATH` for voice
  input. Both degrade gracefully — the system starts and runs without them.

---

## Setup

**1. Clone and install Python dependencies**

```bash
git clone https://github.com/SwapnilGite1311/AGI-System.git
cd AGI-System
pip install -r Documents/requirements.txt
```

**2. Pull the models**

```bash
ollama pull qwen2.5:3b
```

That one is required — it is the council, the intent router and the
conversation model. These three are optional and each degrades gracefully
if absent:

```bash
ollama pull gemma2:2b
ollama pull nomic-embed-text
ollama pull llava:7b
```

`gemma2:2b` is the fast fallback tier, `nomic-embed-text` gives semantic
memory recall (without it, recall falls back to keyword search), and
`llava:7b` is screen understanding — skip it on 4 GB of VRAM, it will not
fit alongside anything else.

**3. Run it**

```bash
python main.py
```

Ollama is started automatically if it is not already running. On first run
the system creates its own `data/` directory and databases; there is
nothing to initialise by hand.

**4. Check the install**

```bash
python main.py --doctor
```

---

## Command-line flags

| Flag | What it does |
|---|---|
| `--doctor` | Check the environment: models, dependencies, config |
| `--demo` | Guided walkthrough of the main capabilities |
| `--metrics` | Live usage and success metrics (`--json` for machine output) |
| `--tasks` | Print stored tasks without starting a session |
| `--journal` | Show the execution journal |
| `--clean-data` | Report duplicate/stale stored data. Add `--apply` to act; a backup is taken first |

---

## Configuration

Everything lives in `config/settings.json`. The keys worth knowing:

- `ollama.host` — where Ollama is listening (default `http://127.0.0.1:11434`)
- `llm_council.*.model` — which model plays each role
- `audio.voice_enabled` — turn voice on or off
- `audio.input_device_index` — force a specific microphone when the picker
  chooses a virtual or silent input, which Windows machines often expose
- `email.confirm_before_send` — prompt before sending mail. Off by default,
  so mail sends immediately; an hourly budget still prevents a runaway loop
- `paths.data` — where stored data lives

Email credentials are encrypted with Windows DPAPI on first use. Plaintext
credentials found in config are migrated automatically and the plaintext is
removed. Set them up with:

```bash
python setup_email.py
```

---

## Voice

Say `voice` to enter continuous voice mode, then just speak. Say
`voice off`, or press Ctrl+C, to go back to typing.

Voice input needs the local speech server running:

```bash
python ../local-server/server.py
```

If a command is misheard, the microphone threshold is calibrated per
session against your actual room noise. When the room is unusually loud,
set `audio.input_device_index` to pin a better microphone — Windows often
exposes a dozen capture endpoints and the default is not always the real
one.

---

## Tests and audits

```bash
python -m pytest tests/ -q
```

508 tests. Alongside them are four standing audits, each of which exists
because of a specific class of bug this project actually had:

```bash
python tests/contract_audit.py      # every parsed intent has an execution branch
python tests/test_intent_matrix.py  # 64 phrase-to-intent mappings
python tests/chaos_probe.py         # malformed input must not crash anything
python tests/honesty_audit.py       # no success claimed without verifying it
```

The last one is the important one. The recurring failure in a system like
this is not a crash — it is a confident `success: True` for something that
did not happen: a form filled on a page that never loaded, a file "created"
that is not on disk, an email "sent" that the server refused. The audit
walks the AST for functions that act and then claim success without
checking, and it currently reports zero.

If you add a function that does something to the world, it is expected to
verify the effect before reporting success, or to say `verified: False` and
explain why it cannot.

---

## Layout

```
main.py                 Controller, routing, intent parsing, CLI
agents/                 Capability agents: file, system, web, vision,
                        business, learning, conversation
core/                   Council, chairman (safety review), memory,
                        tool registry, ReAct loop, sandbox, secrets
learning/               Adaptive engine, reward model, experience replay,
                        neural command model
benchmark/              45 frozen tasks for measuring changes
tests/                  Test suite and the four standing audits
local-server/           Speech-to-text and text-to-speech (separate process)
```

## How a command is handled

1. **Deterministic parse** — `_parse_direct_command` recognises the command
   outright. Fastest path, no model involved.
2. **Model routing** — anything unrecognised goes to a local model, which
   picks an intent and arguments.
3. **Safety review** — commands judged destructive to the machine go to the
   Chairman for review before running. Deleting a task is ordinary work;
   deleting a folder is not.
4. **Execution** — the tool registry dispatches to an agent, which performs
   the action and verifies it.
5. **Learning** — the outcome is recorded so routing improves over time.
