# Autonomous System Controller (ASC) / AGI-System - Full Project Handoff Context

Last audited: 2026-08-13  
Primary workspace: `C:\Users\Swapnil gite\LAN\PROJECTS\Agentic Web\AGI-System`  
Parent workspace: `C:\Users\Swapnil gite\LAN\PROJECTS\Agentic Web`

This document is meant to be given to another Codex/Copilot/premium account so the project can continue without losing context.

---

## 1. Core Vision

We are building an **Autonomous System Controller**, abbreviated as **ASC**.

The long-term vision is not just a chatbot. The goal is to evolve a classic conversational assistant into a local autonomous agent that can:

- Talk naturally with the user when the user wants conversation.
- Understand task requests from natural language.
- Plan multi-step workflows.
- Use local tools and system capabilities.
- Control browser workflows.
- Fill forms.
- Manage files and projects.
- Run safe system commands.
- Learn from user preferences, feedback, command history, and repeated workflows.
- Eventually support business-level assistance: project creation, scheduling, marketing tasks, meetings, daily planning, startup/project idea management, and surfacing important events that need user attention.

The desired final product is a local-first intelligent agent that can operate like an assistant, automation layer, and learning system together.

The target deadline is **before 15 September**.

---

## 2. Why This Project Exists

The user wants an agent that is more powerful than a normal chatbot.

A normal chatbot only talks. ASC should talk **and act**.

The project is intended to become an autonomous local agent that can:

- Understand intent from plain English.
- Decide whether a request is chat, browser automation, file work, system control, or a complex multi-agent task.
- Execute tasks safely.
- Ask for confirmation before dangerous actions.
- Learn user habits and preferences over time.
- Become increasingly personalized.

The project is also important for an upcoming interview. After all phases are complete, the user needs to understand every major part of the codebase, including architecture, algorithms, classes, agents, safety design, and technical tradeoffs.

---

## 3. Architecture From Original Diagrams

Two original architecture images were provided:

- `C:\Users\Swapnil gite\LAN\PROJECTS\Agentic Web\Autonomous system architecture flowchart.png`
- `C:\Users\Swapnil gite\LAN\PROJECTS\Agentic Web\Workflow diagram.png`

The original architecture describes a layered autonomous system:

### 3.1 Input Layer

Planned/desired inputs:

- Desktop dashboard / terminal UI.
- Mobile control such as WhatsApp, Telegram, or SMS.
- Voice interface with microphone, wake word, speech-to-text, and text-to-speech.
- Phone system for calls.

Current reality:

- The active interface is currently terminal-based through `main.py`.
- Voice is configured but not robustly working yet.
- Mobile/phone features are not production-ready.

### 3.2 Cognitive Core

The original design includes an **LLM Council**:

- Chairman: final decision maker.
- Strategist: planning.
- Executor: execution reasoning.
- Analyst: analysis.
- Vision model: visual understanding.
- Speed model: quick responses.
- Backup model: fallback.

Configured local Ollama models:

- `qwen2.5:14b`
- `qwen2.5:7b`
- `llama3.1:8b`
- `mistral:7b`
- `llava:7b`
- `gemma2:2b`
- `tinyllama:latest`
- `qwen2.5-coder:7b`

Current implementation:

- `core/council.py`
- `core/chairman.py`
- RAM-aware sequential model loading.
- Fallback model chain.
- `keep_alive=0` to unload models after use.
- `OLLAMA_MAX_LOADED_MODELS=1` and `OLLAMA_KEEP_ALIVE=0` are used when ASC starts Ollama.

Important limitation:

- Because the user's machine has limited RAM, the council often downgrades to `tinyllama:latest` or `gemma2:2b` instead of loading all large models. This prevents RAM exhaustion but means the full 7-model council is not always exercised with the configured large models.

### 3.3 Memory System

The original design includes:

- Short-term memory.
- Long-term memory.
- Episodic memory.
- Context/priority updates.

Current implementation:

- `core/memory.py`
- Session storage.
- User preferences.
- Short-term recall.
- Episodic command recording.
- Learning data stored under `data/`.

Configured memory paths:

- `data/command_history.json`
- `data/adaptive_state.json`
- `data/phase5_model.json`
- `data/feedback.json`
- `data/user_preferences.json`
- `data/episodes.db`

### 3.4 Perception Layer

Original design:

- Vision module: screen capture, OCR, UI detection, object recognition.
- Audio module: speech-to-text, text-to-speech, emotion/speaker detection.
- System monitor: CPU/RAM/disk/process/network.

Current implementation:

- `agents/vision_agent.py`
- OCR support through Tesseract if available.
- Screenshot and screen text extraction.
- `agents/system_agent.py` for CPU/RAM/disk/process/network.
- Voice server exists separately in `C:\Users\Swapnil gite\LAN\PROJECTS\Agentic Web\local-server\server.py`.

Voice status:

- Voice dependencies exist: whisper executable/model and Piper executable/voice model.
- The voice server is not currently auto-managed by ASC.
- `voice status` reports offline if `http://localhost:5000/health` is not running.

### 3.5 Execution Layer

Original design:

- System control.
- Application control.
- Communication control.
- Browser automation.
- File operations.
- Process management.

Current implementation:

- `agents/system_agent.py`
- `agents/file_agent.py`
- `agents/web_agent.py`
- `agents/browser_driver.py`
- `core/task_decomposer.py`
- `core/tool_registry.py`
- `core/autonomy.py`

---

## 4. Why Classes Are Used

The project uses classes because ASC is a long-running multi-agent system with stateful components.

Classes make sense here because:

- Each agent owns configuration, dependencies, and local state.
- The controller coordinates many agents.
- Memory, browser sessions, preferences, learning state, and command history need persistence.
- The architecture maps naturally to object responsibilities.

Key class responsibilities:

- `AutonomousSystemController` in `main.py`: main orchestrator, command parsing, routing, execution, chat loop.
- `LLMCouncil` in `core/council.py`: local LLM decision-making and council model fallback.
- `Chairman` in `core/chairman.py`: final decision synthesis.
- `MemorySystem` in `core/memory.py`: preferences, sessions, episodic memory.
- `TaskDecomposer` in `core/task_decomposer.py`: splits complex commands into subtasks.
- `ToolRegistry` in `core/tool_registry.py`: describes available tools.
- `AutonomyEngine` in `core/autonomy.py`: autonomous planning support.
- `SystemAgent` in `agents/system_agent.py`: system commands, apps, processes, disk/network info, Ollama startup.
- `FileAgent` in `agents/file_agent.py`: file operations, search, backup, duplicate detection, organization.
- `WebAgent` in `agents/web_agent.py`: navigation, search, form filling, page interaction.
- `BrowserDriver` in `agents/browser_driver.py`: Playwright DOM control.
- `VisionAgent` in `agents/vision_agent.py`: screenshots and OCR.
- `ConversationAgent` in `agents/conversation_agent.py`: normal conversational responses.
- `LearningAgent` in `agents/learning_agent.py`: command history, rewards, workflow learning, adaptive and Phase 5 model hooks.
- `AdaptiveLearningEngine` in `learning/adaptive_engine.py`: Phase 4 semi-supervised/adaptive workflow learning.
- `OfflinePreferenceModel` in `learning/phase5_model.py`: Phase 5 lightweight offline preference model.
- `RewardModel` in `learning/reward_model.py`: converts execution success into reward scores.
- `ExperienceReplayBuffer` in `learning/experience_replay.py`: persistent replay history.

---

## 5. Phase History

### Phase 1 / Priority 1 - Core Command Foundation

Goal:

- Make the system boot.
- Accept text commands.
- Route simple direct commands.
- Initialize agents.
- Support basic system/file/conversation behavior.

Implemented:

- `main.py` controller.
- Agent initialization.
- Direct command parsing.
- Conversation fallback.
- Command execution result format.
- Memory/session recording.

Current status:

- Mostly complete.
- Basic conversation now routes through `ConversationAgent`.
- If Ollama is unavailable, conversation uses deterministic fallback text.

Known limitation:

- Normal chat is still basic compared with a full LLM when Ollama is offline.

### Phase 2 / Priority 2 - Web Automation and Practical Task Execution

Goal:

- Execute practical tasks from natural language.
- Support browser commands such as opening Google/Amazon/YouTube.
- Support file and system operations.
- Reduce hardcoded command behavior.

Implemented:

- Browser command parsing.
- Known-site handling for Amazon, Flipkart, Google, YouTube, Bing.
- File commands.
- PowerShell/CMD command execution.
- App open/close.
- System status, process listing, drives, network, environment variables.
- Safety confirmation for dangerous system commands.

Breakthrough:

- Command like `open chrome and search for amazon and search for laptops there` now opens a single Amazon search target instead of two tabs.
- Verified target: `https://www.amazon.in/s?k=laptops`.

Current status:

- Phase 2 is mostly working.
- Needs continued polish for edge-case command parsing and safer system-control expansion.

### Phase 3 / Priority 3 - Browser Driver, Forms, Ollama Helpers

Goal:

- Move browser automation from rough browser launching toward reliable DOM control.
- Add Playwright driver.
- Add better form filling.
- Add Ollama startup/health helpers.

Implemented:

- `agents/browser_driver.py`
- Playwright integration.
- Browser binary path support via `C:\ms-playwright`.
- `web_automation.driver = "playwright"`.
- Headless Chromium support.
- Selector discovery for form labels.
- Submit button detection.
- Form staging and confirmation tokens.
- Integration test: `tests/test_form_fill_integration.py`.
- Ollama health/start/stop helpers in `SystemAgent`.

Current status:

- Playwright form integration test passes.
- Basic browser commands work.
- Real-world form filling is not fully reliable yet.

Known form issue:

- In one live smoke test, command:

```text
https://example.com fill form with name: Swapnil, email: swapnil@example.com
```

reported success, but the result showed fallback OCR/keyboard behavior and strange detected labels from the current visible screen. This means form fill can still falsely report success when it did not confidently map fields on the intended page.

Required fix:

- Form filling must only report success if fields were confidently filled through DOM selectors or a clearly verified fallback.
- When a URL is included, the result should include `navigated_url`.
- If no confident field mapping exists, return `success: false` or `requires_user_help: true`, not fake success.

### Phase 4 / Priority 4 - Adaptive Learning and Preference Memory

Goal:

- Make ASC learn user preferences and workflows over time without bypassing safety.

Implemented:

- `learning/adaptive_engine.py`
- Semi-supervised labels from success/failure, rewards, and explicit user feedback.
- Workflow clustering.
- Preference signals.
- Strategy recommendations.
- Evaluation metrics.
- Commands:

```text
phase 4 status
show adaptive learning
show learned workflows
show workflow templates
show adaptive evaluation
classify command show system status
that worked
that failed
remember default browser is chrome
show preferences
approve preference default browser is edge
reject preference default_browser chrome
```

Current status:

- Good foundation.
- Still advisory only.
- Does not fine-tune local LLMs.

Why advisory:

- Learned behavior should not bypass safety gates.
- It should suggest or influence routing, not directly perform risky tasks without confirmation.

### Phase 5 / Priority 5 - Learning Intelligence, Experience Replay, Neural Network Scaffold

Copilot appears to have implemented Phase 5 files:

- `learning/experience_replay.py`
- `learning/reward_model.py`
- `learning/phase5_model.py`
- `data/phase5_model.json`

Implemented capabilities:

- Persistent replay buffer.
- Reward scoring from command execution result.
- Offline preference model.
- K-means-like unsupervised clustering.
- Lightweight online token-weight updates.
- A tiny hand-written shallow neural profile.
- Commands:

```text
phase 5 status
show phase 5 model
```

Current audit result:

- Phase 5 exists, but it is **not complete** if the intended definition is deep autonomous intelligence.
- It is a useful scaffold, not a powerful learning brain.

Important truth:

- The current Phase 5 does **not** fine-tune Ollama models.
- It does **not** train a deep PyTorch neural network.
- It does **not** perform large-scale semi-supervised learning.
- It does **not** safely generalize business workflows by itself yet.

What it actually does:

- Stores experiences.
- Scores success/failure.
- Learns lightweight preference signals.
- Clusters command patterns.
- Produces advisory predictions like `default_browser = chrome`.

Why this is still useful:

- It creates the data pipeline needed for real learning later.
- It gives us a place to plug in a stronger neural network.
- It keeps safety intact while learning is immature.

---

## 6. Current Test Status

Last tested on 2026-08-13:

```text
python -m pytest tests -rs
```

Result:

```text
83 passed, 5 skipped
```

Skipped tests:

- Live Ollama council tests skip when Ollama server is offline.

Compile check:

```text
python -m compileall main.py agents core learning tests test_council_live.py
```

Result:

- Passed.

Live council script:

```powershell
$env:PYTHONUTF8='1'
python test_council_live.py
```

Result:

- Passed with Ollama reachable.

Issue:

- Without `PYTHONUTF8=1`, `test_council_live.py` can fail on Windows CP1252 terminal due to emoji printing.

---

## 7. Current Working Capabilities

### 7.1 Conversation

Working:

```text
hi
what can you do?
```

Behavior:

- Routes as conversation.
- Uses local LLM if available.
- Falls back to deterministic response if LLM unavailable.

Limitation:

- Conversation quality depends on Ollama/model availability.

### 7.2 Browser

Working examples:

```text
open browser
open chrome
search for artificial intelligence
open google
open youtube and search for python tutorials
open chrome and search for amazon and search for laptops there
search amazon for laptops
```

Known breakthrough:

- Amazon laptop search now opens one target URL through Playwright:

```text
https://www.amazon.in/s?k=laptops
```

### 7.3 File System

Working examples:

```text
list files in desktop
search files for roadmap in desktop
show file info for launch_checklist_note.txt
make a note about project ideas
backup desktop as desktop_snapshot
find duplicates in desktop
analyze disk usage in desktop
```

### 7.4 System Commands

Working examples:

```text
run powershell Get-Date
show system status
list running processes
network status
show drives
show env PATH
close notepad
```

Dangerous commands:

```text
run powershell Remove-Item test.txt
confirm command
cancel command
```

Current behavior:

- Dangerous commands require confirmation.

### 7.5 Ollama

Working:

- Ollama executable found at:

```text
C:\Users\Swapnil gite\AppData\Local\Programs\Ollama\ollama.exe
```

Available models:

```text
tinyllama:latest
gemma2:2b
llava:7b
mistral:7b
llama3.1:8b
qwen2.5:14b
qwen2.5:7b
qwen2.5-coder:7b
```

RAM issue:

- Available memory has been observed very low, around `0.79 GB` free in one smoke test.
- The system must avoid loading multiple large models simultaneously.

Current mitigation:

- Sequential model loading.
- `keep_alive=0`.
- `max_loaded_models=1`.
- Model fallback to `gemma2:2b` / `tinyllama:latest` when memory is low.

---

## 8. Known Current Problems

### 8.1 Web Preview Problem

The user mentioned a "web preview" says "site cannot be reached."

Important clarification:

- We are not building a website as the main product.
- Any web preview failure is not the core ASC product unless a local dashboard/frontend is explicitly added later.
- The current system is terminal/controller based.

Action:

- Ignore web preview for now unless a UI/dashboard phase is started.

### 8.2 Voice Recognition

Problem:

- `voice status` reports offline when `local-server/server.py` is not running.
- ASC currently checks the server but does not robustly start or recover it.

Voice server path:

```text
C:\Users\Swapnil gite\LAN\PROJECTS\Agentic Web\local-server\server.py
```

Dependencies exist:

- `local-server\whisper\main.exe`
- `local-server\whisper\ggml-small.bin`
- `local-server\piper\piper\piper.exe`
- `local-server\piper\en_US-ryan-high.onnx`

Later fix:

- Add `start voice server`.
- Add automatic startup if configured.
- Add clearer diagnostics.
- Add `/health` retry.
- Add recording/transcription test command.

### 8.3 Form Filling Reliability

Problem:

- Integration test passes on simple fixture.
- Real commands can still fall back to blind keyboard input and report success.

Required fixes:

- Track navigation result inside form result.
- Require confident selector mapping before success.
- Distinguish:

```text
success
partial_success
needs_user_attention
failed
```

- Do not claim success if fields were not actually mapped or verified.
- Add tests for URL + form fill real flow.
- Add tests for no matching fields.
- Add tests for submit confirmation and verification.

### 8.4 Phase 5 Learning Is Too Shallow

Problem:

- Current neural network is hand-written and tiny.
- No serious PyTorch training pipeline yet.
- No train/validation split.
- No model metrics beyond lightweight summaries.
- No model promotion policy.
- No rollback policy.
- No online safety guard for learned actions.

Required direction:

- Build a real local neural intent/preference model.
- Keep it advisory first.
- Use deterministic safety above all learned behavior.
- Add evaluation harness before using model predictions for execution routing.

### 8.5 System Control Commands

Desired commands:

```text
shutdown system
restart system
sleep system
lock laptop
```

Important safety:

- Shutdown/restart/sleep are termination or session-impacting commands and must require explicit confirmation.
- "Turn on the system" is generally impossible from software if the machine is fully powered off, unless Wake-on-LAN or BIOS/firmware scheduling is configured.
- "Unlock laptop" is security-sensitive. The agent should not store or type passwords. Safe options are limited to assisting with lock screen workflow or using OS-supported secure authentication mechanisms, not bypassing login.

Recommended implementation:

- Add direct intents for shutdown/restart/sleep/lock.
- Always stage them with confirmation.
- For sleep, the agent process may pause because the OS sleeps. When the machine wakes, the process may or may not resume depending on environment.
- For unlock, do not implement password bypass. Treat as unsupported unless an explicit secure enterprise/auth mechanism exists.

### 8.6 Windows Terminal Encoding

Problem:

- `test_council_live.py` prints emoji and can crash in CP1252 terminal.

Fix:

- Either set:

```powershell
$env:PYTHONUTF8='1'
```

- Or remove/replace emoji in the script.

---

## 9. The Biggest Issues Faced So Far

### 9.1 RAM Exhaustion From Ollama Models

The largest practical issue was RAM exhaustion when trying to use multiple local models.

Why it happened:

- Models like `qwen2.5:14b`, `llama3.1:8b`, `mistral:7b`, and `llava:7b` are large.
- Loading several together can exhaust system RAM.

How it was handled:

- Sequential council loading.
- Only one model active at a time.
- `OLLAMA_MAX_LOADED_MODELS=1`.
- `OLLAMA_KEEP_ALIVE=0`.
- Runtime RAM-aware model selection.
- Fallback to `gemma2:2b` and `tinyllama:latest`.

Tradeoff:

- The machine survives.
- But the full high-quality council is not always used.

### 9.2 Hardcoded Behavior vs Autonomy

The user correctly noticed that early versions felt hardcoded.

Why:

- Direct regex command parsing was used to make Phase 1/2 reliable.
- This was necessary to get working execution quickly.

How it is being improved:

- Task decomposition.
- Tool registry.
- Council fallback for ambiguous tasks.
- Adaptive learning.
- Workflow templates.
- Phase 5 replay/reward/preference model.

Remaining challenge:

- We still need a stronger planner and learned routing model so the system is not just a command table.

### 9.3 Voice Pipeline Integration

Problem:

- Voice server is separate from AGI-System.
- ASC checks it but does not manage it.

Solution needed:

- Integrate voice server lifecycle commands into `SystemAgent` or a new `VoiceAgent`.

### 9.4 Form Filling Reality Gap

Problem:

- Simple form fixture works.
- Real pages are messy.
- OCR fallback can act on the wrong page and still report success.

Solution needed:

- Make DOM-based Playwright filling the primary success path.
- Treat OCR/keyboard fallback as uncertain unless verified.

---

## 10. How Commands Flow Through the System

Typical command flow:

1. User runs:

```powershell
python main.py
```

2. `AutonomousSystemController` initializes:

- Council.
- Chairman.
- Memory.
- Learning agent.
- Conversation agent.
- System agent.
- Vision agent.
- File agent.
- Web agent.

3. User enters command.

4. `process_command()` receives command.

5. The controller decides route:

- Conversation route for greetings/questions.
- Direct deterministic route for known safe commands.
- Decomposer route for multi-step commands.
- Council/autonomy fallback for ambiguous complex tasks.

6. The chosen agent executes:

- `SystemAgent`
- `FileAgent`
- `WebAgent`
- `ConversationAgent`
- `LearningAgent`

7. Result is recorded:

- Episodic memory.
- Command history.
- Reward score.
- Adaptive learning state.
- Phase 5 model state.

8. User sees result summary.

---

## 11. Why We Kept Deterministic Rules

The goal is autonomy, but local system control is risky.

Deterministic rules are still needed for:

- Dangerous PowerShell commands.
- File deletion.
- Shutdown/restart/sleep.
- Form submission.
- Security-related commands.
- Avoiding accidental damage.

The right architecture is not "pure LLM controls everything."

The better architecture is:

- LLM or neural planner proposes.
- Tool registry constrains available actions.
- Safety policy validates.
- Deterministic executor performs.
- Learning system observes and improves.

This gives autonomy without chaos.

---

## 12. Phase 5 Deep Learning Plan

The next real Phase 5 work should convert the current scaffold into a stronger learning system.

### 12.1 Data Sources

Use:

- Command text.
- Parsed intent.
- Chosen route.
- Steps completed.
- Success/failure.
- Reward score.
- Execution tier.
- User feedback: "that worked", "that failed".
- Preferences: default browser, notes folder, workflow preferences.
- Workflow templates.

### 12.2 Model Types

Recommended local models:

- Intent classifier: predicts command category.
- Tool/router classifier: predicts best agent/tool.
- Preference model: predicts user-specific choices.
- Workflow recommender: suggests reusable workflows.
- Risk classifier: predicts whether confirmation is required.

### 12.3 Suggested Neural Implementation

Use PyTorch because `torch` is installed.

Start with:

- Bag-of-words or TF-IDF features.
- Small MLP classifier.
- Train offline from `data/command_history.json`.
- Store model under `models/`.
- Save vocabulary and labels.

Do not immediately replace the deterministic parser.

Use neural predictions as:

- Advisory signal.
- Fallback when deterministic parser is uncertain.
- Ranking signal for workflow templates.

### 12.4 Safety Rules

Never let learned behavior bypass:

- Dangerous command confirmation.
- Form submission confirmation.
- File deletion safeguards.
- System shutdown/restart/sleep confirmation.
- Authentication/privacy restrictions.

### 12.5 Evaluation Before Promotion

Before using a learned model in routing:

- Split history into train/eval.
- Measure accuracy.
- Measure false dangerous-action rate.
- Measure user correction rate.
- Require minimum confidence.
- Log all model-influenced decisions.
- Allow rollback to deterministic routing.

---

## 13. Phase 5 Immediate Fix List

These are the best next tasks.

1. Fix form-filling false success.
2. Add richer form tests:

```text
URL navigation + form fill
no matching fields should fail
partial mapping should report partial success
confirmation should submit exactly once
```

3. Add system power commands with confirmation:

```text
shutdown system
restart system
sleep system
lock laptop
```

4. Fix `test_council_live.py` Unicode issue.
5. Add a real PyTorch intent/preference classifier.
6. Add model training command:

```text
train learning model
show learning model metrics
```

7. Add model promotion rule:

```text
use learned model only if eval accuracy is above threshold
```

8. Keep the neural model advisory until enough data proves it is safe.

---

## 14. Commands To Verify Current System

Run from:

```powershell
cd "C:\Users\Swapnil gite\LAN\PROJECTS\Agentic Web\AGI-System"
```

Tests:

```powershell
python -m pytest tests -rs
python -m compileall main.py agents core learning tests test_council_live.py
```

Ollama:

```powershell
ollama list
ollama ps
$env:PYTHONUTF8='1'
python test_council_live.py
```

Run ASC:

```powershell
python main.py
```

Manual commands:

```text
hi
what can you do?
show system status
run powershell Get-Date
open chrome and search for amazon and search for laptops there
search amazon for laptops
phase 4 status
show adaptive learning
show learned workflows
show workflow templates
phase 5 status
show phase 5 model
voice status
```

Form test commands:

```text
https://example.com fill form with name: Swapnil, email: swapnil@example.com
go to https://example.com and fill form with name: Swapnil, email: swapnil@example.com
stage the form with name: Alice, email: alice@example.com and confirm before submitting
confirm submission
```

Dangerous command confirmation:

```text
run powershell Remove-Item test.txt
cancel command
```

---

## 15. Current Repo Structure

Important files/folders:

```text
AGI-System/
  main.py
  config/settings.json
  core/
    autonomy.py
    chairman.py
    council.py
    memory.py
    task_decomposer.py
    tool_registry.py
  agents/
    browser_driver.py
    conversation_agent.py
    file_agent.py
    learning_agent.py
    system_agent.py
    vision_agent.py
    web_agent.py
  learning/
    adaptive_engine.py
    experience_replay.py
    phase5_model.py
    reward_model.py
  tests/
    test_basic.py
    test_council_integration.py
    test_form_fill_integration.py
    test_system_agent_ollama.py
  data/
    adaptive_state.json
    command_history.json
    feedback.json
    phase5_model.json
    user_preferences.json
  docs/
    phase2_manual_test_commands.md
  Phase3_README.md
  PHASE3_POLISH_TASKS.md
  PHASE4_LEARNING_PLAN.md
  test_council_live.py
```

Voice server outside AGI-System:

```text
local-server/
  server.py
  whisper/
  piper/
```

---

## 16. Important Configuration

`config/settings.json` includes:

```json
"ollama": {
  "host": "http://127.0.0.1:11434",
  "timeout": 120,
  "max_retries": 3,
  "max_loaded_models": 1,
  "keep_alive": "0"
}
```

```json
"web_automation": {
  "default_browser": "chrome",
  "driver": "playwright",
  "driver_browser": "chromium",
  "browsers_path": "C:\\ms-playwright",
  "headless": true
}
```

```json
"learning": {
  "reinforcement_learning": true,
  "unsupervised_learning": true,
  "model_finetuning": false,
  "training_interval": "daily",
  "history_limit": 500,
  "adaptive_min_confidence": 0.82
}
```

Important:

- `model_finetuning` is currently `false`.
- This confirms the current system does not fine-tune Ollama models.

---

## 17. September 15 Delivery Strategy

Recommended approach:

### Week 1

- Fix form filling false-success problem.
- Add system power commands with confirmation.
- Fix live test Unicode issue.
- Improve command parsing edge cases.
- Add voice server start/status commands if time allows.

### Week 2

- Implement real PyTorch local learning model.
- Train from command history.
- Add evaluation metrics.
- Keep model advisory.
- Add command classification and route recommendation.

### Week 3

- Strengthen autonomous planner.
- Make workflow templates executable.
- Add business/project workflow commands.
- Add scheduling/meeting/task planning stubs or integrations.

### Final days before September 15

- Full regression testing.
- Documentation.
- Interview preparation.
- Architecture explanation.
- Line-by-line code walkthrough for major files.
- Demo script with reliable commands.

---

## 18. Interview Explanation Summary

If asked "what did you build?", answer:

ASC is a local autonomous assistant that combines natural language command parsing, multi-agent architecture, browser automation, system control, memory, and adaptive learning. It uses deterministic safety rules for reliable execution, an Ollama-based local LLM council for reasoning, Playwright for browser automation, and a learning pipeline that records experiences, rewards, preferences, and workflow patterns to personalize future behavior.

If asked "why not just use an LLM directly?", answer:

Direct LLM control is unsafe and unreliable for system-level automation. ASC uses LLMs for reasoning and planning, but deterministic agents execute constrained tools. Safety gates handle dangerous commands and form submissions. Learning remains advisory until evaluated.

If asked "what was the biggest engineering challenge?", answer:

RAM management with local LLMs. Large Ollama models cannot all stay loaded on a low-RAM machine, so the council uses sequential loading, `keep_alive=0`, `OLLAMA_MAX_LOADED_MODELS=1`, and fallback to smaller models.

If asked "how does it learn?", answer:

It records command experiences, execution outcomes, rewards, feedback, and preferences. Phase 4 builds semi-supervised labels and workflow clusters. Phase 5 adds replay, reward modeling, preference prediction, and a lightweight neural scaffold. The next step is a real PyTorch classifier trained offline and used advisory-first.

If asked "how does form filling work?", answer:

The browser agent uses Playwright to inspect DOM labels and map user-provided fields to selectors, then fills fields and optionally submits. It also has OCR/keyboard fallback, but this needs improvement because fallback can be uncertain on real pages.

If asked "what safety controls exist?", answer:

Dangerous shell commands require confirmation. Form submission can be staged before submit. Learned behavior is advisory and does not bypass deterministic safety gates. Shutdown/restart/sleep commands should also require confirmation.

---

## 19. Critical Next Message For The New Agent

Use this instruction with the new account:

```text
You are continuing the Autonomous System Controller project at:
C:\Users\Swapnil gite\LAN\PROJECTS\Agentic Web\AGI-System

Read PROJECT_HANDOFF_CONTEXT.md first. Then audit current tests. The immediate goal is Phase 5 hardening:
1. Fix form filling false-success behavior.
2. Add confirmed system power commands: shutdown, restart, sleep, lock.
3. Fix Windows Unicode issue in test_council_live.py.
4. Implement a real PyTorch-based advisory intent/preference model trained from command history.
5. Keep all learned behavior advisory until evaluated.
6. Run pytest after every change.

Do not remove safety confirmations. Do not claim the system is fully autonomous until real-world workflows and tests prove it.
```

---

## 20. Honest Project Status

The system is no longer just a simple hardcoded chatbot. It has:

- Multi-agent structure.
- Local LLM council integration.
- Browser automation.
- File/system control.
- Memory.
- Preferences.
- Workflow learning.
- Experience replay.
- Reward scoring.
- Lightweight Phase 5 learning scaffold.

But it is not yet the final "anything and everything" autonomous business assistant.

The next major step is to make Phase 5 real:

- Better data.
- Real neural model.
- Evaluation.
- Safer learned routing.
- More reliable form execution.
- Stronger autonomy planner.

The best path is to keep building in layers:

1. Reliability.
2. Safety.
3. Learning.
4. Autonomy.
5. Business-level workflows.
6. Documentation/interview mastery.
